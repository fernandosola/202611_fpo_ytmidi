# YouTube MIDI

Transcricao musical de videos do YouTube ou arquivos de audio locais para MIDI,
com uma faixa por classe de instrumento reconhecida e um arquivo combinado.

A CLI Python baixa um video com imagem e audio, extrai WAV, executa o YourMT3+
e exporta eventos musicais para estudo, analise e edicao em uma DAW. O video
original e preservado quando a entrada e uma URL. **Nao e um separador de
stems:** a saida e MIDI, nao audio separado por instrumento.

**Estado:** fluxo implementado, com inferencia real verificada em CPU e GPU
NVIDIA, inclusive via Docker. A precisao em musicas reais/densas ainda nao foi
avaliada formalmente. O download YouTube foi testado com simulacoes, nao com um
video real; nao se considera essa integracao validada em producao.

## Sumario

- [Funcionalidades e arquitetura](#funcionalidades-e-arquitetura)
- [Requisitos](#requisitos)
- [Inicio rapido com Docker](#inicio-rapido-com-docker)
- [Execucao local](#execucao-local)
- [Comandos e configuracao](#comandos-e-configuracao)
- [Resultados](#resultados)
- [Modelo e memoria GPU](#modelo-e-memoria-gpu)
- [Diagnostico](#diagnostico)
- [Limitacoes e validacao](#limitacoes-e-validacao)
- [Desenvolvimento](#desenvolvimento)
- [Direitos e licencas](#direitos-e-licencas)
- [Documentacao](#documentacao)

## Funcionalidades e arquitetura

- Entrada por URL de um video publico ou arquivo local com audio.
- Download com imagem e audio, limites e validacao de metadados.
- Extracao WAV PCM via FFmpeg, preservando canais e taxa de amostragem nesta etapa.
- YourMT3+ T5 com notas simultaneas, classes de instrumentos e bateria.
- MIDI combinado e arquivos individuais por classe reconhecida, nao por stem.
- Relatorio JSON com estado do job, dispositivo, arquivos, instrumentos e avisos.
- Ambiente ML isolado, com dependencias, fonte e checkpoint fixados.
- Execucao CPU/CUDA local ou Docker nao-root, com dados persistentes.
- Liberacao automatica do modelo da GPU e suporte a workers externos confiaveis.

```mermaid
flowchart LR
    URL["URL do YouTube"] --> Download["yt-dlp + Deno"]
    Download --> Video["Video preservado"]
    Video --> Audio["FFmpeg: WAV PCM"]
    Local["Audio local"] --> Audio
    Audio --> Worker["YourMT3+: worker isolado"]
    Worker --> Tracks["Notas por classe"]
    Tracks --> MIDI["MIDIs combinado e individuais"]
    MIDI --> Report["result.json"]
```

A CLI invoca um subprocesso no ambiente Python do modelo. O worker adapta o
audio para mono/16 kHz, processa segmentos em lotes e junta eventos nas fronteiras.
A exportacao preserva timestamps e separa bateria de instrumentos tonais.
O modelo nao fica residente entre conversoes.

`prepare` encerra depois da extracao WAV. `convert` verifica o backend antes
de baixar/preparar a midia e executa o fluxo completo.

## Requisitos

Ambiente validado: Linux x86_64, nativo ou Ubuntu no WSL2. O container e Linux
amd64. O runtime ML fixado nao foi certificado para ARM, macOS ou Python nativo
no Windows.

| Requisito | Execucao local | Docker |
| --- | --- | --- |
| Python 3.11 e uv 0.9.30 | No host; uv gerencia os ambientes | Incluidos na imagem |
| FFmpeg e ffprobe | Executaveis no `PATH` | Incluidos na imagem |
| Deno | No `PATH`, para JavaScript do YouTube/yt-dlp | Deno 2.9.8 incluido |
| Docker e Compose | Nao necessarios | Instalados no host |
| NVIDIA, opcional | Driver compativel com CUDA 12.4 | Driver e acesso GPU pelo Docker |
| Internet | Setup inicial e download YouTube | Build/setup inicial e download YouTube |

CPU nao exige GPU. Ambos os modos instalam PyTorch/torchaudio 2.5.1+cu124;
nao e necessario instalar o CUDA Toolkit completo. Nao substitua o Python do
sistema nem instale ML na `.venv` da CLI. Deno nao participa da transcricao/CUDA.

Imagem Docker medida: cerca de **788 MiB descomprimidos**, com Python 3.11.18
slim-trixie, a menor entre as duas bases glibc testadas. O volume do modelo
ocupa cerca de **6,1 GiB adicionais**, inclusive em CPU. Reserve ao menos
12 GiB livres para setup, alem de imagem, caches de build e midias.

Tutoriais por pre-requisito: [docs/installation.md](docs/installation.md).
Docker Engine/Desktop, WSL2, Toolkit NVIDIA e permissoes:
[docs/docker.md](docs/docker.md).

## Inicio rapido com Docker

Execute na raiz do repositorio, pelo terminal Linux/WSL. Docker e Compose
devem estar funcionando; GPU tambem exige o acesso NVIDIA configurado no host.
Substitua `<ID_DO_VIDEO>` por um video acessivel e autorizado.

### GPU NVIDIA

```bash
mkdir -p output
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
docker compose build cpu
docker compose run --rm gpu setup-model --device cuda
docker compose run --rm gpu doctor --json
docker compose run --rm gpu convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
```

O build de `cpu` gera a imagem compartilhada pelos dois servicos. Execute
`setup-model` uma vez; nas proximas conversoes, reutilize o volume.

### CPU, sem GPU

Apos o mesmo build, use o servico `cpu` e o dispositivo `cpu`:

```bash
docker compose run --rm cpu setup-model --device cpu
docker compose run --rm cpu convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cpu --batch-size 1
```

Nao e necessario instalar outro modelo para alternar CPU/GPU.

### Arquivo local

Com imagem e modelo ja preparados:

```bash
export YT_MIDI_INPUT_DIR="/caminho/absoluto/da/pasta-com-audio"
docker compose run --rm gpu convert --audio-file '/input/musica.wav' --device cuda
```

Para CPU, troque `gpu` por `cpu` e `--device cuda` por `--device cpu`.
A pasta de entrada precisa existir e e montada somente para leitura.
Sem `YT_MIDI_INPUT_DIR`, `output` tambem fica acessivel em `/input`.

Saidas ficam em `output/job-<id>/` no host; modelos no volume
`youtube-midi-models`, em `/models/yourmt3` no container. `--rm` remove o
container, nao esses dados. **Nao use `docker compose down -v` para limpeza
rotineira:** isso apaga o runtime e os pesos.

Comandos `docker run`, inferencia sem rede e manutencao de UID/GID:
[docs/docker.md](docs/docker.md).

## Execucao local

Depois de instalar uv/Python, FFmpeg e Deno, na raiz do repositorio:

```bash
uv sync --locked --no-dev
uv run --no-dev yt-midi --help
uv run --no-dev yt-midi setup-model --device cuda
uv run --no-dev yt-midi doctor --json
uv run --no-dev yt-midi convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
```

Para CPU, use `--device cpu` no setup e nas conversoes. `--no-dev` dispensa
ferramentas de desenvolvimento; nao e necessario ativar um virtualenv.

```bash
uv run --no-dev yt-midi convert --audio-file /caminho/musica.wav --device cpu --batch-size 1
uv run --no-dev yt-midi prepare 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>'
uv run --no-dev yt-midi prepare --audio-file /caminho/musica.wav --output-dir output
```

`prepare` nao exige modelo e preserva o WAV. Para etapas separadas, use esse
WAV como `--audio-file` de uma nova conversao; isso cria outro job.

## Comandos e configuracao

| Comando | Finalidade |
| --- | --- |
| `yt-midi --help` / `yt-midi --version` | Mostrar comandos / versao |
| `yt-midi doctor --json` | Mostrar ferramentas, manifesto do modelo e driver |
| `yt-midi setup-model --device cuda` | Instalar/verificar assets e executar inferencia de verificacao |
| `yt-midi prepare <URL>` | Baixar video e extrair WAV, sem transcricao |
| `yt-midi convert <URL>` | Gerar MIDIs pelo backend instalado |
| `yt-midi convert --audio-file <arquivo>` | Converter midia local, sem download YouTube |

Use o prefixo `uv run --no-dev` localmente, ou `docker compose run --rm <cpu|gpu>`
no container. URL e `--audio-file` sao entradas alternativas, nao simultaneas.

| Opcao | Padrao da CLI | Uso |
| --- | --- | --- |
| `--output-dir` | `output` | Diretorio pai dos jobs |
| `--max-duration` | `prepare`: 900 s; `convert`: 3600 s | Limite de duracao aceito |
| `--max-download-size` | 1073741824 bytes, 1 GiB | Limite do download, nao do WAV/MIDI |
| `--device` | `auto` | Em setup/convert: `auto`, `cpu` ou `cuda` |
| `--batch-size` | 4 | Lotes de segmentos na inferencia; 1 reduz pressao de VRAM |
| `--bpm` | 120 | Tempo nominal do MIDI, nao BPM estimado |
| `--keep-intermediates` | Desativado | Em convert: preservar WAV e dados intermediarios |

Para permitir ate duas horas, por exemplo:

```bash
uv run --no-dev yt-midi convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda --max-duration 7200
```

Confira restricoes com `yt-midi prepare --help` e `yt-midi convert --help`.
No Docker, use caminhos montados, como `/input/musica.wav` e `/data/output`.

O worker tem timeout fixo de 3600 segundos de execucao, sem opcao correspondente
na CLI. Ele e independente de `--max-duration`, que limita a duracao da midia.
Permitir uma entrada maior nao aumenta o tempo disponivel para transcreve-la;
conversoes longas, especialmente em CPU, podem terminar por timeout.

## Resultados

Cada execucao cria um job exclusivo, sem sobrescrever a entrada. Uma conversao
bem-sucedida com entrada YouTube pode gerar esta estrutura ilustrativa:

```text
output/
  job-<id>/
    video/
    midi/
      combined.mid
      001_<instrumento>.mid
      002_<instrumento>.mid
    result.json
    worker.log
```

Os nomes dependem das classes reconhecidas; o video pode ser MKV, MP4 ou WebM.

| Artefato | Comportamento |
| --- | --- |
| Video original | Preservado quando a entrada e URL |
| `midi/combined.mid` | Faixas tonais e bateria, quando os canais permitem |
| MIDIs individuais | Um por classe reconhecida, nao por fonte sonora fisica |
| `result.json` | Estado, opcoes, midia, backend/checkpoint, dispositivo, instrumentos e avisos |
| `worker.log` | Saida e diagnosticos do worker, quando ele e iniciado |
| `audio.wav` e `transcription/` | Removidos apos convert, inclusive em falhas de transcricao, salvo `--keep-intermediates` |

`prepare` preserva WAV e relatorio, sem produzir MIDI. Uma conversao concluida
usa `status: completed`; falhas usam `failed`, interrupcoes tratadas usam
`cancelled`. Erros no preflight podem impedir a criacao do job, portanto nem
todo erro produz relatorio.

Abra os MIDIs em uma DAW, editor de partitura ou sintetizador MIDI e confira as
notas. Os timbres dependem do sintetizador/soundfont, nao do audio original.
Com mais de 15 classes tonais, os individuais permanecem, `midi.combined` e nulo
e o relatorio registra um aviso, evitando reutilizacao silenciosa de canais.

No Docker, caminhos absolutos do JSON referem-se ao container:
`/data/output/...` corresponde a `output/...` no host.

## Modelo e memoria GPU

YourMT3+ T5 usa a tarefa `mt3_full_plus`, com fonte e checkpoint de uma revisao
fixa do Space `mimbres/YourMT3`. O setup verifica SHA-256, carrega os pesos
estritamente e executa inferencia antes de declarar o modelo pronto.
Fonte, checkpoint e evidencias: [docs/model-evaluation.md](docs/model-evaluation.md).

O cache local usa `$XDG_CACHE_HOME/youtube-midi/yourmt3`, ou
`~/.cache/youtube-midi/yourmt3`. Para mudar de local, mantenha a mesma variavel
no setup e nas conversoes:

```bash
export YT_MIDI_MODEL_DIR="$HOME/modelos/youtube-midi"
uv run --no-dev yt-midi setup-model --device cpu
uv run --no-dev yt-midi convert --audio-file /caminho/musica.wav --device cpu
```

Nao se instala um pacote pip chamado `yourmt3` nem se mistura o lock ML com a
CLI. Audio local pode ser transcrito sem rede depois do setup; baixar videos
continua exigindo internet.

`auto` escolhe CUDA quando disponivel, senao CPU. CUDA explicitamente solicitada
nunca e substituida silenciosamente por CPU. Na finalizacao normal e em excecoes
Python dentro do worker, o modelo volta para CPU, o coletor de lixo roda e o
cache CUDA livre e liberado. O contexto CUDA remanescente termina com o processo;
os pesos persistentes e outras aplicacoes nao sao afetados.

No cancelamento da CLI ou timeout, o supervisor envia `SIGTERM` ao grupo do
worker e pode usar `SIGKILL` apos 3 segundos. Atualmente esses sinais nao
executam o `finally` Python do worker: a liberacao nesses casos depende do
encerramento do processo, nao da rotina explicita de limpeza.

### Worker personalizado

Um worker externo deve implementar [docs/worker-contract.md](docs/worker-contract.md):

```bash
uv run --no-dev yt-midi convert --audio-file /caminho/musica.wav \
  --worker /caminho/worker.py \
  --worker-python /caminho/ambiente-modelo/bin/python \
  --device cuda --batch-size 4 --keep-intermediates
```

`--worker-python` exige `--worker`. Execute apenas codigo e pesos confiaveis.
A disponibilidade/limpeza GPU de workers externos depende de sua implementacao;
as garantias do backend integrado nao se estendem a eles.

## Diagnostico

Comece por `doctor --json`, pelo erro no terminal e por `result.json`/
`worker.log`, quando existirem. `doctor` nao importa ML nem testa CUDA atual:
mostra o ultimo dispositivo validado no setup. `convert` verifica a disponibilidade
atual antes de baixar/preparar a midia.

| Sintoma | Acao |
| --- | --- |
| FFmpeg/ffprobe/Deno ausentes | Instalar executaveis e conferir `PATH` ou imagem usada |
| Modelo ausente/invalido | Executar setup-model com o mesmo cache/volume; nao ignorar hashes |
| CUDA indisponivel | Conferir driver; no Docker usar servico gpu ou `--gpus all` |
| VRAM esgotada | Usar `--batch-size 1`, fechar outras aplicacoes ou escolher CPU |
| Permission denied nos dados | Conferir output e UID/GID; nao usar `chmod 777`/convert como root |
| Limites excedidos | Ajustar duracao/tamanho explicitamente, conforme recursos disponiveis |
| Nenhuma nota detectada | Tentar trecho musical audivel; transcricao vazia nao e sucesso |
| YouTube indisponivel/restrito | Escolher midia publica autorizada; autenticacao/lives/DRM nao suportados |

Tutoriais: [docs/installation.md](docs/installation.md) e [docs/docker.md](docs/docker.md).
Codigos de saida: [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitacoes e validacao

- Classes sao as do checkpoint; algumas agrupam familias, nao instrumentos especificos.
- Duas fontes do mesmo instrumento nao necessariamente viram duas faixas.
  Ha falsos positivos e omissoes, inclusive na bateria e em misturas densas.
- MIDI nao contem audio/timbres originais; nao ha separacao de stems.
- Nao ha estimativa de BPM, quantizacao automatica ou dinamica fiel certificada.
  Neste backend a velocidade padrao das notas e 100.
- Voz 100/101 e mapeada para Voice Oohs/Choir Aahs; bateria usa percussao MIDI,
  nao um programa GM 128. Mais de 15 classes tonais impedem o arquivo combinado.
- Interface web, playlists, canais, lives, DRM e autenticacao estao fora do escopo.
- Videos longos aumentam armazenamento/RAM; lote menor reduz VRAM, nao o custo
  de manter segmentos em memoria. O limite de uma hora nao certifica desempenho nessa duracao.

Evidencias locais registradas em 2026-11-15:

| Superficie | Evidencia | Limite |
| --- | --- | --- |
| CLI, contratos e pipeline | 103 testes rapidos; Ruff, mypy, build e hooks aprovados | Nao medem qualidade musical |
| Modelo real | Acorde sintetico de 12 s em CPU/CUDA e inferencia CUDA de 180 s | Nao representa musica densa/anotada |
| Docker | Build, ferramentas, nao-root, preparo e conversao CPU/CUDA/offline aprovados | Validacao local, nao todos os hosts |
| Liberacao GPU | Parametros/buffers voltam para CPU antes do fim do worker | Contexto CUDA pode reter memoria interna |
| YouTube | Validacao e limites testados com simulacoes | Download real ainda nao verificado |
| CI | Workflow Python e gate Docker configurados; gate Docker executado localmente | Execucao remota nao verificada |

Proximas verificacoes prioritarias: download real de video autorizado, avaliacao
musical com audios anotados e metricas por classe, e recursos em musicas longas/densas.
Sao pendencias de validacao, nao garantias de precisao. Nao ha F1 certificado.
Melhorias tecnicas identificadas: encerramento gracioso por sinais e timeout do
worker configuravel, com testes que exercitem cancelamento pelo supervisor.

## Desenvolvimento

Layout `src`, Python `>=3.11,<3.12`, empacotamento Hatchling. Dependencias core:
[pyproject.toml](pyproject.toml) e [uv.lock](uv.lock). Lock ML com hashes:
[src/youtube_midi/assets/yourmt3-requirements.txt](src/youtube_midi/assets/yourmt3-requirements.txt).

| Local | Responsabilidade |
| --- | --- |
| [src/youtube_midi/cli.py](src/youtube_midi/cli.py) | Comandos e diagnostico |
| [src/youtube_midi/pipeline.py](src/youtube_midi/pipeline.py) | Jobs, relatorios e intermediarios |
| [src/youtube_midi/download.py](src/youtube_midi/download.py) | URLs, metadados e download |
| [src/youtube_midi/audio.py](src/youtube_midi/audio.py) | FFprobe e extracao PCM |
| [src/youtube_midi/transcription.py](src/youtube_midi/transcription.py) | Contrato e execucao de workers |
| [src/youtube_midi/yourmt3_worker.py](src/youtube_midi/yourmt3_worker.py) | Modelo e ciclo de vida GPU |
| [src/youtube_midi/midi.py](src/youtube_midi/midi.py) | Exportacao de MIDIs |
| [Dockerfile](Dockerfile) e [compose.yaml](compose.yaml) | Imagem e execucao CPU/GPU |

```bash
uv sync --locked --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m 'not model and not network and not gpu' --cov=youtube_midi
uv run yt-midi --help
uv build
```

Testes reais opcionais, apos preparar assets, sem downloads nos testes:

```bash
YT_MIDI_RUN_MODEL_TESTS=1 uv run pytest tests/test_yourmt3.py -m model
```

A suite completa de modelos inclui GPU e exige CUDA. Para somente CPU, use
`-m 'model and not gpu'`. Instale hooks com `uv run pre-commit install`.
Regras e gates Docker: [CONTRIBUTING.md](CONTRIBUTING.md).
Nao versione midias, modelos, credenciais, caches ou resultados.

## Direitos e licencas

Baixe/processe apenas midias autorizadas, respeitando direitos autorais, termos
do YouTube e licencas das ferramentas/modelos. O backend executa codigo de
terceiros e carrega checkpoint: use somente fontes confiaveis.

Licencas do Space, repositorio upstream e checkpoint precisam ser analisadas
separadamente; uso comercial e redistribuicao de pesos nao estao certificados
por este projeto. Consulte [docs/model-evaluation.md](docs/model-evaluation.md).

Este repositorio ainda nao declara uma licenca propria em arquivo LICENSE ou
nos metadados do pacote. Essa definicao e pendente; nao presuma permissao de
redistribuicao apenas por ter acesso ao codigo.

## Documentacao

- [docs/installation.md](docs/installation.md): instalacao local por pre-requisito.
- [docs/docker.md](docs/docker.md): Docker/WSL2/GPU, mounts, persistencia e permissoes.
- [docs/architecture.md](docs/architecture.md): arquitetura e decisoes tecnicas.
- [docs/worker-contract.md](docs/worker-contract.md): integracao de outros backends.
- [docs/model-evaluation.md](docs/model-evaluation.md): checkpoint e evidencias musicais.
- [CONTRIBUTING.md](CONTRIBUTING.md): desenvolvimento, verificacao e codigos de saida.
