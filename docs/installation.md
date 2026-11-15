# Instalacao local

Rota para Ubuntu 22.04/24.04 x86_64, nativo ou no WSL2. Para executar tudo em
container, siga [Docker](docker.md): Python, uv, FFmpeg e Deno ja estao na imagem.
O runtime fixado do modelo nao e certificado para Windows Python nativo, macOS ou ARM.

## Checklist

| Pre-requisito | Uso | Tutorial |
| --- | --- | --- |
| curl, certificados e unzip | Instaladores HTTPS | [Ferramentas auxiliares](#ferramentas-auxiliares) |
| uv e Python 3.11 | Ambiente da CLI e do modelo | [uv e Python](#uv-e-python) |
| FFmpeg e ffprobe | Video, extracao e verificacao de audio | [FFmpeg](#ffmpeg) |
| Deno | Desafios JavaScript do YouTube no yt-dlp | [Deno](#deno) |
| Driver NVIDIA, opcional | Inferencia CUDA | [GPU](#gpu-nvidia-opcional) |
| Dependencias Python | Download, CLI e escrita MIDI | [Projeto](#dependencias-do-projeto) |
| YourMT3+ | Transcricao para MIDI | [Modelo](#modelo-yourmt3) |

Comandos `sudo` alteram o sistema. Pule requisitos ja instalados e inspecione os
instaladores oficiais antes de executa-los. Rode os comandos do projeto na sua raiz.

## Ferramentas auxiliares

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl unzip
curl --version
unzip -v
```

Erro de certificado: confira o relogio do sistema e os certificados/proxy da sua
rede. Nao desabilite a verificacao TLS.

## uv e Python

O [uv](https://docs.astral.sh/uv/getting-started/installation/) gerencia Python e
virtualenvs. Use a mesma versao do uv configurada na CI.

```bash
curl -LsSf https://astral.sh/uv/0.9.30/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.11
uv sync --locked --no-dev
uv run --no-dev python --version
```

Resultado esperado: uv 0.9.30 e Python 3.11.x. Nao substitua o Python do sistema.
O projeto usa `.python-version` e `pyproject.toml` para selecionar a versao.

`uv: command not found`: abra outro terminal ou adicione o diretorio acima ao
`PATH` do seu shell. No VS Code, selecione `.venv/bin/python` para desenvolver;
o interpretador do editor nao e necessariamente o do terminal.

## FFmpeg

Instale os executaveis, nao um pacote pip chamado `ffmpeg`.

```bash
sudo apt-get install -y ffmpeg
ffmpeg -version
ffprobe -version
```

Ambos precisam responder no mesmo terminal em que voce executa `yt-midi`.
`doctor` indicando `not found`: verifique `command -v ffmpeg` e seu `PATH`.

## Deno

O yt-dlp usa Deno para resolver JavaScript do YouTube. Deno nao participa da
transcricao MIDI ou do CUDA. Use Deno >=2.3.0; a imagem usa 2.9.8.

```bash
curl -fsSL https://deno.land/install.sh | sh -s -- v2.9.8
export PATH="$HOME/.deno/bin:$PATH"
deno --version
deno eval 'console.log("Deno OK")'
```

`deno: command not found`: abra outro terminal ou mantenha esse `PATH` na
configuracao do shell. Os scripts `yt-dlp-ejs` sao instalados pelo extra
`yt-dlp[default]` do projeto; nao e necessario instalar Node.js.

Fonte: [instalacao oficial](https://docs.deno.com/runtime/getting_started/installation/).

## GPU NVIDIA (opcional)

Para CPU, pule esta secao e use `--device cpu`. O PyTorch instalado pelo projeto
ja inclui bibliotecas CUDA 12.4: nao e necessario instalar o CUDA Toolkit completo
nem usar `nvcc`. Ainda e necessario um driver NVIDIA compativel no host.

### Ubuntu nativo

Se `nvidia-smi` ja funciona e o modelo valida CUDA, nao reinstale o driver.
Caso contrario, use o driver recomendado pelo Ubuntu:

```bash
sudo apt-get install -y ubuntu-drivers-common
ubuntu-drivers devices
sudo ubuntu-drivers install
```

Reinicie o computador apos a instalacao e verifique:

```bash
nvidia-smi
```

Secure Boot pode exigir inscricao da chave do driver durante a reinicializacao.
Siga as instrucoes da distribuicao em vez de desabilita-lo automaticamente.

### Windows com WSL2

1. Instale/atualize o [driver NVIDIA para Windows](https://www.nvidia.com/en-us/drivers/).
2. No PowerShell, execute `wsl --update` e `wsl --list --verbose`; a distro deve usar WSL2.
3. No Ubuntu WSL, execute `nvidia-smi` ou `/usr/lib/wsl/lib/nvidia-smi`.
4. Se necessario, adicione `/usr/lib/wsl/lib` ao `PATH` e abra outro terminal.

Nao execute `ubuntu-drivers install` nem instale um driver Linux dentro do WSL:
o driver e fornecido pelo Windows. Consulte [CUDA no WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).

Falha CUDA: confira driver, GPU e `setup-model --device cuda`. O numero CUDA
exibido por `nvidia-smi` representa a capacidade do driver, nao a versao do PyTorch.
Drivers atuais compativeis com CUDA 12.4 sao recomendados; versoes antigas podem
ter restricoes de compatibilidade.

## Dependencias do projeto

```bash
uv sync --locked --no-dev
uv run --no-dev yt-midi --help
uv run --no-dev yt-midi doctor --json
```

O lock instala Typer, yt-dlp com seus extras e pretty-midi automaticamente.
Nao mantenha outra lista manual de dependencias nem instale bibliotecas ML na
`.venv` da CLI. Para desenvolvimento, use `uv sync --locked --group dev` e siga
[CONTRIBUTING](../CONTRIBUTING.md).

Antes do setup do modelo, `doctor` pode mostrar `model.ready: false`; isso e esperado.

## Modelo YourMT3+

Reserve pelo menos 12 GiB livres para instalacao e caches, alem de espaco para
videos e WAVs. Runtime e fonte/checkpoint ocupam aproximadamente 6 GiB; o cache
do uv pode aumentar esse consumo. Internet e necessaria no primeiro setup.

```bash
uv run --no-dev yt-midi setup-model --device cuda
uv run --no-dev yt-midi doctor --json
uv run --no-dev yt-midi convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
```

Para CPU, substitua `cuda` por `cpu` tanto no setup quanto na conversao. `auto`
escolhe o dispositivo; CUDA solicitada explicitamente nunca e trocada por CPU.
O mesmo runtime CUDA e instalado mesmo quando voce escolhe CPU.

O setup verifica hashes, carrega o modelo e executa inferencia de verificacao.
`doctor` mostra o ultimo dispositivo validado; `convert` verifica disponibilidade atual.
Nao se instala um pacote pip chamado `yourmt3`.

O cache padrao e `~/.cache/youtube-midi/yourmt3`, ou usa `XDG_CACHE_HOME`.
Para outro local, mantenha a mesma variavel no setup e nas conversoes:

```bash
export YT_MIDI_MODEL_DIR="$HOME/modelos/youtube-midi"
uv run --no-dev yt-midi setup-model --device cpu
uv run --no-dev yt-midi convert --audio-file /caminho/musica.wav --device cpu --batch-size 1
```

| Problema | Acao |
| --- | --- |
| Modelo ausente ou hash invalido | Execute setup-model no mesmo diretorio configurado; nao ignore a verificacao |
| VRAM esgotada | Use `--batch-size 1`, feche outras aplicacoes ou escolha CPU |
| Video excede o limite | Ajuste `--max-duration` em segundos, por exemplo `7200` para duas horas |
| Download muito grande | Ajuste `--max-download-size` explicitamente, em bytes |
| Video indisponivel/restrito | Escolha um video publico acessivel; autenticacao, lives e DRM nao sao suportados |

Baixe e processe somente midias autorizadas, respeitando direitos e termos do YouTube.
`convert` permite uma hora por padrao; `prepare`, 900 segundos. Ambos limitam o
download a 1 GiB, ajustavel explicitamente.
Para validar sem YouTube, use `--audio-file`. A inferencia funciona sem rede apos o
setup, mas baixar um video continua exigindo internet. A qualidade musical e
[estimada, nao certificada](model-evaluation.md).
