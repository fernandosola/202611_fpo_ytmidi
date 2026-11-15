# Avaliacao do modelo

Status: **integracao funcional validada com pesos reais; qualidade musical ainda
nao certificada**. O backend nativo produz MIDI em CPU/GPU sem downloads durante
a inferencia. Os testes musicais usam uma composicao sintetica propria, nao um
benchmark de musicas comerciais ou gravacoes com anotacoes por instrumento.

## Ambiente observado em 2026-11-15

| Item | Evidencia |
| --- | --- |
| Sistema | Linux em ambiente WSL, nvidia-smi em /usr/lib/wsl/lib |
| Python do terminal | 3.10.12 |
| Python do projeto | CPython 3.11.14 selecionado pelo uv |
| uv | 0.9.30 |
| GPU | NVIDIA GeForce RTX 3070 Ti Laptop GPU |
| VRAM | 8192 MiB reportados pelo driver |
| Driver | 617.42 reportado por nvidia-smi |
| FFmpeg/ffprobe | Binarios presentes; extracao local testada |
| Deno | Nao encontrado no PATH |
| Runtime ML | Python 3.11, torch/torchaudio 2.5.1+cu124 em virtualenv isolado |
| CUDA em PyTorch | Operacao CUDA, carregamento e inferencia real aprovados |

`doctor --json` mostra o ultimo dispositivo validado na instalacao, sem importar
ML. `convert` verifica a disponibilidade atual antes de preparar midia.

## Backend instalado

- Referencia: [YourMT3](https://github.com/mimbres/YourMT3).
- Fonte de inferencia: [Space YourMT3+](https://huggingface.co/spaces/mimbres/YourMT3).
- A fonte principal nao oferece um pacote Python instalavel completo.
- Revisao da fonte: `5e66c1ea173a8186e0d20432b841d3180cc015b5`.
- Modelo: YMT3+ com encoder/decoder T5 e tarefa `mt3_full_plus`.
- Checkpoint: `notask_all_cross_v6_xk2_amp0811_gm_ext_plus_nops_b72/checkpoints/model.ckpt`.
- SHA-256 publicado e verificado:
  `76673d4289aae1a66984b3fee59157d484cda8fdf9b56279251b137321d448e6`.
- Checkpoint: 542707465 bytes. Runtime instalado: aproximadamente 5,6 GiB;
  fonte/checkpoint: 520 MiB, sem contar cache adicional do uv.
- Dependencias travadas com hashes; Transformers 4.45.1, Lightning 2.4.0 e
  NumPy 1.26.4. O indice CUDA legado cu113 do exemplo nao e utilizado.
- Configuracao reconstruida a partir dos defaults da revisao usada na demo YMT3+.
  `load_state_dict(strict=True)` aprovou todas as chaves apos remover pitchshift.
- Canais de decodificacao nao sao automaticamente faixas individuais de instrumento.
- O token de bateria 128 e interno: deve virar `is_drum=true` e programa GM valido.
- Nomes seguem `GM_INSTR_EXT_CLASS_PLUS`, o vocabulario agrupado usado na exportacao
  da demo YMT3+. Programas previstos sao preservados; nao se renomeia o grupo
  Strings para um instrumento individual como violino sem evidencia do modelo.
- Os arquivos Python baixados contem cabecalhos Apache-2.0, como os metadados do
  Space. O GitHub principal declara GPL-3.0; sao artefatos diferentes. Nao foi
  encontrada uma declaracao separada de licenca do checkpoint. Esta integracao
  para estudo pessoal nao certifica direitos de uso comercial ou dados de treino.
- Pesos deserializados podem executar codigo: usar fontes confiaveis e revisoes fixadas.

## Classes de saida

| Classe do checkpoint | Programas GM representados no vocabulario |
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
| Drums | Flag de bateria, nao programa tonal 128 |

O vocabulario nao implica deteccao confiavel de todas essas classes. Fontes
distintas dentro de um grupo podem compartilhar a faixa ou receber classificacoes
incorretas. Nao ha suporte prometido para todos os 128 instrumentos General MIDI.

## Verificacoes realizadas

1. Instalacao reproduzivel, SHA-256 do checkpoint e manifesto da fonte verificados.
2. Carregamento estrito do modelo e inferencia de smoke test na RTX 3070 Ti.
3. WAV estereo/44,1 kHz de 12 segundos convertido pelo pipeline em CUDA e CPU.
4. MIDI reaberto: pitches 60/64/67 presentes, timestamps validos e faixas exportadas.
5. WAV de 180 segundos: 88 segmentos e notas exportadas depois de 170 segundos,
   sem perder os timestamps absolutos. Segmentos mantidos na CPU e lotes na GPU.
6. Inferencia executada com HF/Transformers offline e proxies HTTP/HTTPS indisponiveis.
7. Cleanup de intermediarios e preservacao dos logs validados na conversao real.

| Amostra | Dispositivo/lote | Inferencia | Pico alocado pelo PyTorch |
| --- | --- | --- | --- |
| Acorde sintetico, 12 s | CUDA / 4 | 0,478 s | 221,1 MiB |
| Acorde sintetico, 12 s | CPU / 1 | 0,893 s | Nao aplicavel |
| Acorde repetido, 180 s | CUDA / 4 | 4,321 s | 223,0 MiB |

Tempos extraidos dos logs, excluindo carregamento de modelo e preparacao de midia.
Memoria alocada pelo PyTorch nao equivale a VRAM total usada pelo processo/driver.
Audio simples gera poucos tokens; esses valores nao estimam custo de musica densa.

## Limites e avaliacao pendente

Na amostra sintetica, o modelo identificou percussao cromatica e bateria, com
pitches corretos para o acorde mas falsos positivos de bateria e erros de merge
registrados. Portanto, esses testes demonstram inferencia e exportacao reais,
nao identificacao perfeita de timbre, separacao de todas as fontes ou F1 aprovado.
Voz usa programas GM de substituicao; dinamica e fixa em 100.

Faltam gravacoes autorizadas/anotadas com varios instrumentos e bateria para
medir F1/onsets/offsets, erros de classificacao e continuidade de notas sustentadas.
Download real do YouTube e Deno tambem continuam sem validacao neste ambiente.
Demucs + Basic Pitch nao substitui esse requisito. Se o modelo nao apresentar
qualidade suficiente, avaliar MT3 separadamente sem reduzir o requisito para stems.

Reproduzir apos `uv run yt-midi setup-model --device cuda`:

```bash
YT_MIDI_RUN_MODEL_TESTS=1 uv run pytest tests/test_yourmt3.py -m model
```
