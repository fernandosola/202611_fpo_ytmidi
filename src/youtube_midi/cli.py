"""Command-line entry point; model runtimes are loaded only during inference."""

import json
import logging
import shutil
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from youtube_midi import __version__
from youtube_midi.errors import ProjectError
from youtube_midi.models import ConversionOptions

app = typer.Typer(no_args_is_help=True, invoke_without_command=True, pretty_exceptions_enable=False)


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", is_eager=True)] = False,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
) -> None:
    """Download YouTube videos and prepare multitrack MIDI conversions."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)


@app.command()
def doctor(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Report local tools without importing or downloading models."""
    from youtube_midi.yourmt3 import model_status

    model = model_status()
    binaries = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe", "deno", "nvidia-smi")}
    data: dict[str, Any] = {
        "python": {"version": sys.version.split()[0], "executable": sys.executable},
        "binaries": binaries,
        "gpu_driver_report": None,
        "backend": model.get("name", "not configured; run yt-midi setup-model"),
        "model": model,
        "model_cuda_status": (
            f"Last setup validation: {model.get('validated_device')}; "
            "current availability not checked"
            if model["ready"]
            else "not checked; no model runtime imported"
        ),
    }
    if binaries["nvidia-smi"]:
        try:
            result = subprocess.run(
                [
                    binaries["nvidia-smi"],
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                data["gpu_driver_report"] = result.stdout.strip()
            else:
                data["gpu_driver_error"] = "nvidia-smi could not query the GPU"
        except (OSError, subprocess.TimeoutExpired):
            data["gpu_driver_error"] = "nvidia-smi failed or timed out"
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    typer.echo(f"Python: {data['python']['version']} ({sys.executable})")
    for binary, path in binaries.items():
        typer.echo(f"{binary}: {path or 'not found'}")
    typer.echo(f"GPU (driver report): {data['gpu_driver_report'] or 'unavailable'}")
    typer.echo(f"Transcription backend: {data['backend']}.")
    typer.echo(f"Model CUDA: {data['model_cuda_status']}.")


class Device(StrEnum):
    AUTO = "auto"
    CUDA = "cuda"
    CPU = "cpu"


@app.command("setup-model")
def setup_model_command(device: Annotated[Device, typer.Option()] = Device.AUTO) -> None:
    """Install pinned YourMT3+ sources, checkpoint and isolated Linux/WSL runtime."""
    from youtube_midi.yourmt3 import setup_model

    try:
        directory = setup_model(device.value)
    except ProjectError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(error.exit_code) from error
    except OSError as error:
        typer.echo(f"Filesystem error: {error}", err=True)
        raise typer.Exit(1) from error
    except KeyboardInterrupt as error:
        typer.echo("Cancelled.", err=True)
        raise typer.Exit(130) from error
    typer.echo(f"YourMT3+ installed: {directory}")


def _options(
    source: str | None,
    audio_file: Path | None,
    output_dir: Path,
    max_duration: float,
    max_download_size: int,
    *,
    device: Device = Device.AUTO,
    batch_size: int = 4,
    keep_intermediates: bool = False,
    bpm: float = 120,
) -> ConversionOptions:
    try:
        return ConversionOptions(
            source=source,
            audio_file=audio_file,
            output_dir=output_dir,
            max_duration=max_duration,
            max_download_size=max_download_size,
            device=device.value,
            batch_size=batch_size,
            keep_intermediates=keep_intermediates,
            bpm=bpm,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


def _execute(
    options: ConversionOptions,
    *,
    prepare_only: bool,
    worker: Path | None = None,
    worker_python: Path | None = None,
) -> None:
    from youtube_midi.pipeline import prepare_media, run_conversion
    from youtube_midi.transcription import WorkerTranscriber, YourMT3Transcriber

    def progress(message: str) -> None:
        typer.echo(message, err=True)

    try:
        if prepare_only:
            media = prepare_media(options, progress)
            report = media.directory / "result.json"
        else:
            transcriber = (
                WorkerTranscriber(worker, python=worker_python or Path(sys.executable))
                if worker is not None
                else YourMT3Transcriber(device=options.device)
            )
            report = run_conversion(options, transcriber, progress)
    except ProjectError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(error.exit_code) from error
    except OSError as error:
        typer.echo(f"Filesystem error: {error}", err=True)
        raise typer.Exit(1) from error
    except KeyboardInterrupt as error:
        typer.echo("Cancelled.", err=True)
        raise typer.Exit(130) from error
    typer.echo(str(report))


@app.command()
def prepare(
    source: Annotated[str | None, typer.Argument()] = None,
    audio_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    output_dir: Annotated[Path, typer.Option()] = Path("output"),
    max_duration: Annotated[float, typer.Option(min=0.01)] = 900,
    max_download_size: Annotated[int, typer.Option(min=1)] = 1024**3,
) -> None:
    """Download a single video and extract WAV, or prepare a local audio file."""
    _execute(
        _options(source, audio_file, output_dir, max_duration, max_download_size),
        prepare_only=True,
    )


@app.command()
def convert(
    source: Annotated[str | None, typer.Argument()] = None,
    audio_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    output_dir: Annotated[Path, typer.Option()] = Path("output"),
    worker: Annotated[Path | None, typer.Option(dir_okay=False)] = None,
    worker_python: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    device: Annotated[Device, typer.Option()] = Device.AUTO,
    batch_size: Annotated[int, typer.Option(min=1)] = 4,
    max_duration: Annotated[float, typer.Option(min=0.01)] = 3600,
    max_download_size: Annotated[int, typer.Option(min=1)] = 1024**3,
    keep_intermediates: Annotated[bool, typer.Option()] = False,
    bpm: Annotated[float, typer.Option(min=1, max=1000)] = 120,
) -> None:
    """Convert to instrument MIDI tracks with YourMT3+ or a trusted custom worker."""
    if worker_python is not None and worker is None:
        raise typer.BadParameter("--worker-python requires --worker.")
    _execute(
        _options(
            source,
            audio_file,
            output_dir,
            max_duration,
            max_download_size,
            device=device,
            batch_size=batch_size,
            keep_intermediates=keep_intermediates,
            bpm=bpm,
        ),
        prepare_only=False,
        worker=worker,
        worker_python=worker_python,
    )
