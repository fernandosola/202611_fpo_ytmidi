# Instalação local

Rota para Ubuntu 22.04/24.04 x86_64, nativo ou no WSL2. Para executar tudo em
container, siga [Docker](docker.md): Python, uv, FFmpeg e Deno já estão na imagem.
O runtime fixado do modelo não é certificado para Windows Python nativo, macOS ou ARM.

## Checklist

| Pré-requisito | Uso | Tutorial |
| --- | --- | --- |
| curl, certificados e unzip | Instaladores HTTPS | [Ferramentas auxiliares](#ferramentas-auxiliares) |
| uv e Python 3.11 | Ambiente da CLI e do modelo | [uv e Python](#uv-e-python) |
| FFmpeg e ffprobe | Vídeo, extração e verificação de áudio | [FFmpeg](#ffmpeg) |
| Deno | Desafios JavaScript do YouTube no yt-dlp | [Deno](#deno) |
| Driver NVIDIA, opcional | Inferência CUDA | [GPU](#gpu-nvidia-opcional) |
| Dependências Python | Download, CLI e escrita MIDI | [Projeto](#dependências-do-projeto) |
| YourMT3+ | Transcrição para MIDI | [Modelo](#modelo-yourmt3) |

Comandos `sudo` alteram o sistema. Pule requisitos já instalados e inspecione os
instaladores oficiais antes de executá-los. Rode os comandos do projeto na sua raiz.

## Ferramentas auxiliares

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl unzip
curl --version
unzip -v
```

Erro de certificado: confira o relógio do sistema e os certificados/proxy da sua
rede. Não desabilite a verificação TLS.

## uv e Python

O [uv](https://docs.astral.sh/uv/getting-started/installation/) gerencia Python e
virtualenvs. Use a mesma versão do uv configurada na CI.

```bash
curl -LsSf https://astral.sh/uv/0.9.30/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.11
uv sync --locked --no-dev
uv run --no-dev python --version
```

Resultado esperado: uv 0.9.30 e Python 3.11.x. Não substitua o Python do sistema.
O projeto usa `.python-version` e `pyproject.toml` para selecionar a versão.

`uv: command not found`: abra outro terminal ou adicione o diretório acima ao
`PATH` do seu shell. No VS Code, selecione `.venv/bin/python` para desenvolver;
o interpretador do editor não é necessariamente o do terminal.

## FFmpeg

Instale os executáveis, não um pacote pip chamado `ffmpeg`.

```bash
sudo apt-get install -y ffmpeg
ffmpeg -version
ffprobe -version
```

Ambos precisam responder no mesmo terminal em que você executa `yt-midi`.
`doctor` indicando `not found`: verifique `command -v ffmpeg` e seu `PATH`.

## Deno

O yt-dlp usa Deno para resolver JavaScript do YouTube. Deno não participa da
transcrição MIDI ou do CUDA. Use Deno >=2.3.0; a imagem usa 2.9.8.

```bash
curl -fsSL https://deno.land/install.sh | sh -s -- v2.9.8
export PATH="$HOME/.deno/bin:$PATH"
deno --version
deno eval 'console.log("Deno OK")'
```

`deno: command not found`: abra outro terminal ou mantenha esse `PATH` na
configuração do shell. Os scripts `yt-dlp-ejs` são instalados pelo extra
`yt-dlp[default]` do projeto; não é necessário instalar Node.js.

Fonte: [instalação oficial](https://docs.deno.com/runtime/getting_started/installation/).

## GPU NVIDIA (opcional)

Para CPU, pule esta seção e use `--device cpu`. O PyTorch instalado pelo projeto
já inclui bibliotecas CUDA 12.4: não é necessário instalar o CUDA Toolkit completo
nem usar `nvcc`. Ainda é necessário um driver NVIDIA compatível no host.

### Ubuntu nativo

Se `nvidia-smi` já funciona e o modelo valida CUDA, não reinstale o driver.
Caso contrário, use o driver recomendado pelo Ubuntu:

```bash
sudo apt-get install -y ubuntu-drivers-common
ubuntu-drivers devices
sudo ubuntu-drivers install
```

Reinicie o computador após a instalação e verifique:

```bash
nvidia-smi
```

Secure Boot pode exigir inscrição da chave do driver durante a reinicialização.
Siga as instruções da distribuição em vez de desabilitá-lo automaticamente.

### Windows com WSL2

1. Instale/atualize o [driver NVIDIA para Windows](https://www.nvidia.com/en-us/drivers/).
2. No PowerShell, execute `wsl --update` e `wsl --list --verbose`; a distro deve usar WSL2.
3. No Ubuntu WSL, execute `nvidia-smi` ou `/usr/lib/wsl/lib/nvidia-smi`.
4. Se necessário, adicione `/usr/lib/wsl/lib` ao `PATH` e abra outro terminal.

Não execute `ubuntu-drivers install` nem instale um driver Linux dentro do WSL:
o driver é fornecido pelo Windows. Consulte [CUDA no WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).

Falha CUDA: confira driver, GPU e `setup-model --device cuda`. O número CUDA
exibido por `nvidia-smi` representa a capacidade do driver, não a versão do PyTorch.
Drivers atuais compatíveis com CUDA 12.4 são recomendados; versões antigas podem
ter restrições de compatibilidade.

## Dependências do projeto

```bash
uv sync --locked --no-dev
uv run --no-dev yt-midi --help
uv run --no-dev yt-midi doctor --json
```

O lock instala Typer, yt-dlp com seus extras e pretty-midi automaticamente.
Não mantenha outra lista manual de dependências nem instale bibliotecas ML na
`.venv` da CLI. Para desenvolvimento, use `uv sync --locked --group dev` e siga
[CONTRIBUTING](../CONTRIBUTING.md).

Antes do setup do modelo, `doctor` pode mostrar `model.ready: false`; isso é esperado.

## Modelo YourMT3+

Reserve pelo menos 12 GiB livres para instalação e caches, além de espaço para
vídeos e WAVs. Runtime e fonte/checkpoint ocupam aproximadamente 6 GiB; o cache
do uv pode aumentar esse consumo. Internet é necessária no primeiro setup.

```bash
uv run --no-dev yt-midi setup-model --device cuda
uv run --no-dev yt-midi doctor --json
uv run --no-dev yt-midi convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
```

Para CPU, substitua `cuda` por `cpu` tanto no setup quanto na conversão. `auto`
escolhe o dispositivo; CUDA solicitada explicitamente nunca é trocada por CPU.
O mesmo runtime CUDA é instalado mesmo quando você escolhe CPU.

O setup verifica hashes, carrega o modelo e executa inferência de verificação.
`doctor` mostra o último dispositivo validado; `convert` verifica disponibilidade atual.
Não se instala um pacote pip chamado `yourmt3`.

O cache padrão é `~/.cache/youtube-midi/yourmt3`, ou usa `XDG_CACHE_HOME`.
Para outro local, mantenha a mesma variável no setup e nas conversões:

```bash
export YT_MIDI_MODEL_DIR="$HOME/modelos/youtube-midi"
uv run --no-dev yt-midi setup-model --device cpu
uv run --no-dev yt-midi convert --audio-file /caminho/musica.wav --device cpu --batch-size 1
```

| Problema | Ação |
| --- | --- |
| Modelo ausente ou hash inválido | Execute setup-model no mesmo diretório configurado; não ignore a verificação |
| VRAM esgotada | Use `--batch-size 1`, feche outras aplicações ou escolha CPU |
| Vídeo excede o limite | Ajuste `--max-duration` em segundos, por exemplo `7200` para duas horas |
| Download muito grande | Ajuste `--max-download-size` explicitamente, em bytes |
| Vídeo indisponível/restrito | Escolha um vídeo público acessível; autenticação, lives e DRM não são suportados |

Baixe e processe somente mídias autorizadas, respeitando direitos e termos do YouTube.
`convert` permite uma hora por padrão; `prepare`, 900 segundos. Ambos limitam o
download a 1 GiB, ajustável explicitamente.
Para validar sem YouTube, use `--audio-file`. A inferência funciona sem rede após o
setup, mas baixar um vídeo continua exigindo internet. A qualidade musical é
[estimada, não certificada](model-evaluation.md).
