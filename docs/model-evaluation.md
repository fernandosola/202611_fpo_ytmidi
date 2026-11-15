# Avaliação do modelo

## Ambiente

| Item | Evidência |
| --- | --- |
| Sistema | Linux em ambiente WSL, nvidia-smi em /usr/lib/wsl/lib |
| Python do terminal | 3.10.12 |
| Python do projeto | CPython 3.11.14 selecionado pelo uv |
| uv | 0.9.30 |
| GPU | NVIDIA GeForce RTX 3070 Ti Laptop GPU |
| VRAM | 8192 MiB reportados pelo driver |
| Driver | 617.42 reportado por nvidia-smi |
| FFmpeg/ffprobe | Binários presentes; extração local testada |
| Deno | Não encontrado no PATH |
| Runtime ML | Python 3.11, torch/torchaudio 2.5.1+cu124 em virtualenv isolado |
| CUDA em PyTorch | Operação CUDA, carregamento e inferência real aprovados |

`doctor --json` mostra o último dispositivo validado na instalação, sem importar
ML. `convert` verifica a disponibilidade atual antes de preparar mídia.

## Backend instalado

- Referência: [YourMT3](https://github.com/mimbres/YourMT3).
- Fonte de inferência: [Space YourMT3+](https://huggingface.co/spaces/mimbres/YourMT3).
- A fonte principal não oferece um pacote Python instalável completo.
- Revisão da fonte: `5e66c1ea173a8186e0d20432b841d3180cc015b5`.
- Modelo: YMT3+ com encoder/decoder T5 e tarefa `mt3_full_plus`.
- Checkpoint: `notask_all_cross_v6_xk2_amp0811_gm_ext_plus_nops_b72/checkpoints/model.ckpt`.
- SHA-256 publicado e verificado:
  `76673d4289aae1a66984b3fee59157d484cda8fdf9b56279251b137321d448e6`.
- Checkpoint: 542707465 bytes. Runtime instalado: aproximadamente 5,6 GiB;
  fonte/checkpoint: 520 MiB, sem contar cache adicional do uv.
- Dependências travadas com hashes; Transformers 4.45.1, Lightning 2.4.0 e
  NumPy 1.26.4. O índice CUDA legado cu113 do exemplo não é utilizado.
- Configuração reconstruída a partir dos defaults da revisão usada na demo YMT3+.
  `load_state_dict(strict=True)` aprovou todas as chaves após remover pitchshift.
- Canais de decodificação não são automaticamente faixas individuais de instrumento.
- O token de bateria 128 é interno: deve virar `is_drum=true` e programa GM válido.
- Nomes seguem `GM_INSTR_EXT_CLASS_PLUS`, o vocabulário agrupado usado na exportação
  da demo YMT3+. Programas previstos são preservados; não se renomeia o grupo
  Strings para um instrumento individual como violino sem evidência do modelo.
- Os arquivos Python baixados contêm cabeçalhos Apache-2.0, como os metadados do
  Space. O GitHub principal declara GPL-3.0; são artefatos diferentes. Não foi
  encontrada uma declaração separada de licença do checkpoint. Esta integração
  para estudo pessoal não certifica direitos de uso comercial ou dados de treino.
- Pesos deserializados podem executar código: usar fontes confiáveis e revisões fixadas.

## Classes de saída

| Classe do checkpoint | Programas GM representados no vocabulário |
| --- | --- |
| Acoustic Piano | 0, 1, 3, 6, 7 |
| Electric Piano | 2, 4, 5 |
| Chromatic Percussion | 8-15 |
| Organ | 16-23 |
| Guitar (clean) | 24-27 |
| Guitar (distortion) | 28-31 |
| Bass | 32-39 |
| Strings | 40-55 |
| Brass | 56-63 |
| Reed | 64-71 |
| Pipe | 72-79 |
| Synth Lead | 80-87 |
| Synth Pad | 88-95 |
| Singing Voice | Token 100, exportado como GM 53 |
| Singing Voice (chorus) | Token 101, exportado como GM 52 |
| Drums | Flag de bateria, não programa tonal 128 |

O vocabulário não implica detecção confiável de todas essas classes. Fontes
distintas dentro de um grupo podem compartilhar a faixa ou receber classificações
incorretas. Não há suporte prometido para todos os 128 instrumentos General MIDI.

## Verificações realizadas

1. Instalação reproduzível, SHA-256 do checkpoint e manifesto da fonte verificados.
2. Carregamento estrito do modelo e inferência de smoke test na RTX 3070 Ti.
3. WAV estéreo/44,1 kHz de 12 segundos convertido pelo pipeline em CUDA e CPU.
4. MIDI reaberto: pitches 60/64/67 presentes, timestamps válidos e faixas exportadas.
5. WAV de 180 segundos: 88 segmentos e notas exportadas depois de 170 segundos,
   sem perder os timestamps absolutos. Segmentos mantidos na CPU e lotes na GPU.
6. Inferência executada com HF/Transformers offline e proxies HTTP/HTTPS indisponíveis.
7. Cleanup de intermediários e preservação dos logs validados na conversão real.

| Amostra | Dispositivo/lote | Inferência | Pico alocado pelo PyTorch |
| --- | --- | --- | --- |
| Acorde sintético, 12 s | CUDA / 4 | 0,478 s | 221,1 MiB |
| Acorde sintético, 12 s | CPU / 1 | 0,893 s | Não aplicável |
| Acorde repetido, 180 s | CUDA / 4 | 4,321 s | 223,0 MiB |

Tempos extraídos dos logs, excluindo carregamento de modelo e preparação de mídia.
Memória alocada pelo PyTorch não equivale à VRAM total usada pelo processo/driver.
Áudio simples gera poucos tokens; esses valores não estimam custo de música densa.

## Limites e avaliação pendente

Na amostra sintética, o modelo identificou percussão cromática e bateria, com
pitches corretos para o acorde mas falsos positivos de bateria e erros de merge
registrados. Portanto, esses testes demonstram inferência e exportação reais,
não identificação perfeita de timbre, separação de todas as fontes ou F1 aprovado.
Voz usa programas GM de substituição; dinâmica é fixa em 100.

Faltam gravações autorizadas/anotadas com vários instrumentos e bateria para
medir F1/onsets/offsets, erros de classificação e continuidade de notas sustentadas.
Download real do YouTube e Deno também continuam sem validação neste ambiente.
Demucs + Basic Pitch não substitui esse requisito. Se o modelo não apresentar
qualidade suficiente, avaliar MT3 separadamente sem reduzir o requisito para stems.

Reproduzir após `uv run yt-midi setup-model --device cuda`:

```bash
YT_MIDI_RUN_MODEL_TESTS=1 uv run pytest tests/test_yourmt3.py -m model
```
