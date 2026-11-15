"""Isolated YourMT3+ inference process and explicit asset setup."""

import argparse
import importlib
import json
import os
import sys
import time
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from youtube_midi.yourmt3 import (  # noqa: E402
    CHECKPOINT_FILE,
    CHECKPOINT_SHA256,
    SOURCE_REVISION,
    SPACE_ID,
    file_sha256,
    model_directory,
    normalize_notes,
    validate_assets,
)


def select_device(requested: str) -> str:
    torch = importlib.import_module("torch")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable in the model runtime.")
    device = "cuda" if requested == "auto" and torch.cuda.is_available() else requested
    if device == "auto":
        device = "cpu"
    if device == "cuda":
        torch.ones(1, device="cuda").sum().item()
    return device


def load_model(directory: Path, device: str) -> Any:
    sys.path.insert(0, str(directory / "source/amt/src"))
    torch = importlib.import_module("torch")
    config = importlib.import_module("config.config")
    manager = importlib.import_module("utils.task_manager")
    module = importlib.import_module("model.ymt3")
    audio, model, shared = (
        deepcopy(config.audio_cfg),
        deepcopy(config.model_cfg),
        deepcopy(config.shared_cfg),
    )
    tokenizer = shared["TOKENIZER"]
    tokenizer["max_shift_steps"] = int(
        (audio["input_frames"] / audio["sample_rate"]) // (tokenizer["shift_step_ms"] / 1000) + 2
    )
    task = manager.TaskManager(
        task_name="mt3_full_plus", max_shift_steps=tokenizer["max_shift_steps"]
    )
    network = module.YourMT3(audio_cfg=audio, model_cfg=model, shared_cfg=shared, task_manager=task)
    checkpoint = torch.load(
        directory / "source" / CHECKPOINT_FILE, map_location="cpu", weights_only=False
    )
    state = {
        name: value for name, value in checkpoint["state_dict"].items() if "pitchshift" not in name
    }
    network.load_state_dict(state, strict=True)
    del checkpoint, state
    torch.set_float32_matmul_precision("high")
    return network.eval().to(device)


def install_assets(directory: Path, device: str) -> None:
    hub = importlib.import_module("huggingface_hub")
    source = directory / "source"
    hub.snapshot_download(
        repo_id=SPACE_ID,
        repo_type="space",
        revision=SOURCE_REVISION,
        allow_patterns=["amt/src/**/*.py", CHECKPOINT_FILE],
        local_dir=source,
    )
    if file_sha256(source / CHECKPOINT_FILE) != CHECKPOINT_SHA256:
        raise RuntimeError("Downloaded checkpoint does not match the published SHA-256.")
    selected = select_device(device)
    model = load_model(directory, selected)
    torch = importlib.import_module("torch")
    with torch.inference_mode():
        model.inference_file(
            bsz=1, audio_segments=torch.zeros(1, 1, model.audio_cfg["input_frames"])
        )
    manifest = {
        "name": "YourMT3+ (T5)",
        "repo_id": SPACE_ID,
        "revision": SOURCE_REVISION,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "validated_device": selected,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "source_sha256": {
            path.relative_to(source).as_posix(): file_sha256(path)
            for path in sorted((source / "amt/src").rglob("*.py"))
        },
    }
    temporary = directory / "manifest.partial.json"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(directory / "manifest.json")
    print(f"YourMT3+ ready on {selected}: {directory}", flush=True)


def transcribe(request: dict[str, Any], directory: Path) -> dict[str, Any]:
    validate_assets(directory)
    if request.get("schema_version") != 1 or request["batch_size"] < 1:
        raise ValueError("Invalid inference request.")
    device = select_device(request["device"])
    torch = importlib.import_module("torch")
    torch.set_num_threads(min(8, os.cpu_count() or 1))
    model = load_model(directory, device)
    torchaudio = importlib.import_module("torchaudio")
    audio_utils = importlib.import_module("utils.audio")
    events = importlib.import_module("utils.event2note")
    note_utils = importlib.import_module("utils.note2event")
    vocabulary = importlib.import_module("config.vocabulary")
    waveform, sample_rate = torchaudio.load(request["audio"]["path"])
    waveform = waveform.mean(dim=0, keepdim=True)
    waveform = torchaudio.functional.resample(waveform, sample_rate, model.audio_cfg["sample_rate"])
    frames, rate = model.audio_cfg["input_frames"], model.audio_cfg["sample_rate"]
    segments = audio_utils.slice_padded_array(waveform.numpy(), frames, frames)
    segments = torch.from_numpy(segments.astype("float32")).unsqueeze(1)
    started = time.monotonic()
    predictions = []
    with torch.inference_mode():
        for start in range(0, len(segments), request["batch_size"]):
            batch = segments[start : start + request["batch_size"]]
            tokens, _ = model.inference_file(bsz=len(batch), audio_segments=batch)
            predictions.extend(tokens)
            print(f"Segments: {min(start + len(batch), len(segments))}/{len(segments)}", flush=True)
    starts = [frames * index / rate for index in range(len(segments))]
    channels = []
    errors: Counter[str] = Counter()
    for channel in range(model.task_manager.num_decoding_channels):
        channel_tokens = [array[:, channel, :] for array in predictions]
        zipped, _, decoding_errors = model.task_manager.detokenize_list_batches(
            channel_tokens,
            starts,
            return_events=True,
        )
        notes, merge_errors = events.merge_zipped_note_events_and_ties_to_notes(zipped)
        channels.append(notes)
        errors.update(decoding_errors)
        errors.update(merge_errors)
    names = {
        int(program): name
        for name, programs in vocabulary.GM_INSTR_EXT_CLASS_PLUS.items()
        for program in programs
    }
    tracks, warnings = normalize_notes(
        note_utils.mix_notes(channels), request["audio"]["duration"], names
    )
    if not any(track.notes for track in tracks):
        raise RuntimeError(
            "No notes detected. Try a longer musical excerpt with audible instruments."
        )
    if errors:
        warnings += (f"Model decoding/merge diagnostics: {dict(errors)}",)
    print(f"Inference seconds: {time.monotonic() - started:.3f}", flush=True)
    if device == "cuda":
        print(
            f"Peak CUDA allocated MiB: {torch.cuda.max_memory_allocated() / 1024**2:.1f}",
            flush=True,
        )
    return {
        "schema_version": 1,
        "backend": {
            "name": "YourMT3+ (T5)",
            "revision": SOURCE_REVISION,
            "checkpoint_sha256": CHECKPOINT_SHA256,
        },
        "device": device,
        "tracks": [asdict(track) for track in tracks],
        "warnings": list(warnings),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--response", type=Path)
    args = parser.parse_args()
    directory = model_directory()
    if args.setup:
        install_assets(directory, args.device)
    elif args.check:
        print(select_device(args.device))
    else:
        if args.request is None or args.response is None:
            parser.error("--request and --response are required for inference")
        request = json.loads(args.request.read_text(encoding="utf-8"))
        torch = importlib.import_module("torch")
        try:
            result = transcribe(request, directory)
        except torch.cuda.OutOfMemoryError as error:
            raise RuntimeError(
                "CUDA memory exhausted. Retry with --batch-size 1, close other GPU applications, "
                "or use --device cpu."
            ) from error
        args.response.write_text(json.dumps(result, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
