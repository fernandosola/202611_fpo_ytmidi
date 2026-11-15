# YouTube MIDI

Projeto Python para escolher um video pela URL, baixar o video com audio,
extrair WAV e gerar MIDI multifaixa por instrumento reconhecido.

## Estado atual

- Base Python, CLI, testes, lint, tipos, pre-commit e CI configurados.
- Download de um video com imagem e audio, limites e validacao de metadados.
- Extracao WAV com FFmpeg, preservando canais e taxa de amostragem.
- Backend YourMT3+ integrado, com fonte/checkpoint fixados e ambiente ML isolado.
- Inferencia real testada em GPU e CPU, incluindo audio sintetico de tres minutos.
- MIDI combinado e uma faixa por instrumento reconhecido, incluindo bateria.
- Contrato JSON tambem permite workers personalizados confiaveis.

`convert` usa o YourMT3+ instalado por padrao e verifica os assets antes de baixar
o video. A qualidade em musicas reais/densas ainda nao foi avaliada formalmente.
O download foi testado com simulacoes, nao com um video real do YouTube.

## Requisitos

- Linux e Python 3.11, gerenciado pelo [uv](https://docs.astral.sh/uv/).
- Executaveis FFmpeg e ffprobe no PATH, nao o pacote Python chamado ffmpeg.
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) para o suporte
  completo atual do YouTube no yt-dlp. Instale-o separadamente e confira com `doctor`.
- Para GPU: NVIDIA com driver compativel com CUDA 12.4. `setup-model` instala
  PyTorch/torchaudio 2.5.1+cu124 em ambiente separado; o modo CPU usa o mesmo runtime.
- Aproximadamente 6 GiB para runtime e fonte/checkpoint, mais cache de pacotes do uv.
  Internet e necessaria na instalacao, nao na inferencia apos preparo dos assets.

```bash
uv sync --locked --group dev
uv run yt-midi --help
uv run yt-midi doctor
uv run yt-midi doctor --json
```

O Python 3.10 do sistema nao precisa ser alterado. O uv usa a versao indicada
pela configuracao do projeto.

## Preparar video e audio

```bash
uv run yt-midi prepare 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>'
uv run yt-midi prepare --audio-file /caminho/musica.wav --output-dir output
```

Substitua o identificador por um video acessivel que voce tenha autorizacao
para baixar e processar, respeitando direitos autorais e termos do YouTube.
Nao ha suporte a playlists, canais, lives, DRM ou autenticacao.

Cada execucao cria um diretorio `output/job-<id>/` exclusivo, contendo o video
original, quando a entrada e uma URL, `audio.wav` e `result.json`. `prepare`
preserva o WAV e nao inicia um modelo.

Limites padrao: 900 segundos e 1 GiB de download. Podem ser ajustados com
`--max-duration` e `--max-download-size`, respectivamente em segundos e bytes.
Formatos da origem podem resultar em MKV, MP4 ou WebM; nao se presume uma extensao fixa.

## Instalar o modelo e converter

Instale o modelo uma vez. O comando verifica o SHA-256 publicado do checkpoint,
carrega os pesos e executa inferencia de verificacao no dispositivo escolhido.

```bash
uv run yt-midi setup-model --device cuda
uv run yt-midi convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
uv run yt-midi convert --audio-file /caminho/musica.wav --device cuda --batch-size 4
```

Para inferencia em CPU, use `--device cpu`. `auto` escolhe CUDA quando disponivel,
senao CPU; uma solicitacao explicita de CUDA nunca e substituida silenciosamente.
Se a VRAM esgotar, tente `--batch-size 1`, feche outras aplicacoes na GPU ou use CPU.

O modelo fica em `$XDG_CACHE_HOME/youtube-midi/yourmt3`, ou em
`~/.cache/youtube-midi/yourmt3`. `YT_MIDI_MODEL_DIR` permite mudar esse diretorio,
tanto em `setup-model` quanto em `convert`. Nao e necessario ativar o ambiente ML.
O script e o lock de dependencias estao incluidos no pacote; nao se usa um pacote
pip chamado `yourmt3`.

Um backend externo continua disponivel como alternativa explicita, desde que
implemente o [contrato do worker](docs/worker-contract.md):

```bash
uv run yt-midi convert --audio-file /caminho/musica.wav \
  --worker /caminho/worker.py \
  --worker-python /caminho/ambiente-modelo/bin/python \
  --device cuda --batch-size 4 --keep-intermediates
```

Tambem e possivel usar uma URL como argumento posicional em lugar de `--audio-file`.
Execute apenas scripts e pesos de fontes confiaveis; um worker executa codigo local.

Na conversao, `midi/combined.mid`, os MIDIs individuais e `result.json` sao os
resultados finais. O video e preservado; WAV e dados intermediarios sao removidos
por padrao, inclusive apos falha de transcricao. `--keep-intermediates` os preserva.
O log do worker permanece no diretorio do job. Arquivos de entrada nao sao removidos
ou sobrescritos. Jobs com falha registram `failed`, nunca `completed`.

## Limites musicais

Instrumentos dependem do vocabulario real do checkpoint. Duas fontes do mesmo
instrumento nao necessariamente viram duas faixas. Nao se fabricam instrumentos
ausentes. A identificacao pode ter falsos positivos ou omissoes, inclusive na bateria.
Os tokens de voz 100/101 sao exportados como Voice Oohs/Choir Aahs, mantendo os
nomes de voz nas faixas. O token interno de bateria 128 nao e um programa GM.

MIDI contem eventos musicais, nao o audio ou os timbres originais. O tempo nominal
e 120 BPM, ajustavel por `--bpm`; nao existe estimativa automatica de BPM nem
quantizacao. Timestamps e notas simultaneas sao preservados. Quando nao houver
velocidade inferida, o padrao e 100, sem alegar dinamica fiel.

Com mais de 15 instrumentos tonais, somente arquivos individuais sao gerados,
com aviso no relatorio, evitando reutilizar canais MIDI silenciosamente.
Transcricoes sem notas sao tratadas como erro.

## Desenvolvimento

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m 'not model and not network and not gpu' --cov=youtube_midi
uv build
```

Testes reais opcionais, depois da instalacao dos assets, sem downloads nos testes:

```bash
YT_MIDI_RUN_MODEL_TESTS=1 uv run pytest tests/test_yourmt3.py -m model
```

Ver [padroes de contribuicao](CONTRIBUTING.md), [arquitetura](docs/architecture.md)
e [evidencias e limites do modelo](docs/model-evaluation.md).
Midias, modelos, credenciais e artefatos de execucao nao devem ser versionados.
