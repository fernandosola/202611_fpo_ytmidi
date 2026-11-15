# Execucao com Docker

Container Linux **amd64**, com Python 3.11, uv, FFmpeg/ffprobe, Deno e CLI.
CPU e GPU usam a mesma imagem. O modelo e instalado uma vez no volume persistente
`youtube-midi-models`; ele nao faz parte da imagem.

## Instalar Docker no host

Escolha uma rota: Ubuntu nativo com Docker Engine, ou Windows/WSL2 com Docker Desktop.
Nao instale as duas solucoes na mesma distro WSL. Pule os passos ja configurados.

### Ubuntu: Docker Engine e Compose

Em Ubuntu 22.04/24.04, configure o repositorio oficial:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl start docker
sudo docker run --rm hello-world
```

Se ja existem pacotes como `docker.io`, `podman-docker` ou `containerd` de outra
origem, examine os [conflitos documentados](https://docs.docker.com/engine/install/ubuntu/)
antes de migrar. Nao remova servicos ou dados usados por outros projetos sem avaliar impacto.

Opcionalmente, permita o uso sem `sudo`:

```bash
sudo usermod -aG docker "$USER"
```

Saia e entre novamente na sessao. **O grupo docker concede privilegios equivalentes
a root no host.** Nao use `chmod 777` no socket. Como alternativa, use `sudo docker`
nos comandos abaixo, preservando os valores do UID/GID do seu usuario no build.

```bash
docker version
docker compose version
docker run --rm hello-world
```

### Windows: Docker Desktop com WSL2

1. Instale/atualize WSL2: no PowerShell, `wsl --install` quando necessario e `wsl --update`.
2. Confira `wsl --list --verbose`: a distro Ubuntu deve aparecer com versao 2.
3. Instale [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
4. Ative **Use WSL 2 based engine** e **Resources > WSL Integration > Ubuntu**.
5. Use Linux containers. No terminal Ubuntu, execute `docker version` e `docker compose version`.
6. Execute `docker run --rm hello-world` e os comandos do projeto pelo terminal WSL.

Use WSL atualizado (minimo 2.1.5 segundo a documentacao). Nao instale um segundo
daemon Engine dentro da distro integrada.
Fonte: [Docker Desktop e WSL2](https://docs.docker.com/desktop/features/wsl/).

## GPU NVIDIA (opcional)

Para CPU, pule esta secao. Para GPU, o driver do host precisa funcionar primeiro;
siga [o tutorial do driver](installation.md#gpu-nvidia-opcional). Nao instale
driver ou CUDA Toolkit dentro da imagem.

### Engine Linux: NVIDIA Container Toolkit

Somente no host que executa o daemon Docker Engine Linux:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Os ultimos dois comandos alteram a configuracao do daemon e o reiniciam, podendo
interromper containers ativos. Planeje essa operacao. Docker rootless tem
[configuracao propria](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html);
nao aplique os comandos do daemon rootful indiscriminadamente.

### Desktop Windows/WSL2

Atualize o driver NVIDIA **no Windows**, WSL e Docker Desktop; ative o backend WSL2.
Nao instale driver Linux ou configure um daemon separado na distro integrada.
O Desktop gerencia o acesso GPU, sem exigir Toolkit instalado dentro do Ubuntu WSL.
Fonte: [GPU no Docker Desktop](https://docs.docker.com/desktop/features/gpu/).

Depois de construir a imagem abaixo, confira:

```bash
docker run --rm --gpus all --entrypoint nvidia-smi youtube-midi:local
```

Isso verifica o driver no container; `setup-model --device cuda` e `convert`
tambem testam CUDA real no PyTorch. A ausencia de `nvidia` em `docker info`
isoladamente nao prova falta de GPU, especialmente no Docker Desktop.

## Construir a imagem

Na raiz do projeto, pelo terminal Linux/WSL:

```bash
mkdir -p output
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
docker compose config --quiet
docker compose build cpu
docker compose run --rm cpu --help
docker compose run --rm cpu doctor --json
```

O build atende tambem ao servico `gpu`. UID/GID iguais aos do host evitam resultados
root-owned. O container sempre executa como usuario `app`, nao-root; UID/GID zero
sao rejeitados. A pasta `output` precisa existir e pertencer ao seu usuario:
Compose nao a cria automaticamente para evitar diretorios criados como root.

## Instalar o modelo uma vez

GPU, apos configurar o host:

```bash
docker compose run --rm gpu setup-model --device cuda
docker compose run --rm gpu doctor --json
```

Ou CPU, sem necessidade de GPU/Toolkit:

```bash
docker compose run --rm cpu setup-model --device cpu
docker compose run --rm cpu doctor --json
```

Escolha uma rota; nao e preciso instalar duas vezes para alternar CPU/GPU.
Internet e necessaria no setup. O volume guarda `/models/yourmt3/runtime`,
fonte/checkpoint e manifesto. O lock com hashes e a revisao do modelo sao os
mesmos da instalacao local. Nao monte a `.venv` ou o runtime Python do host:
esses ambientes dependem dos caminhos e bibliotecas do sistema onde foram criados.

## Converter

URL publica autorizada, com GPU:

```bash
docker compose run --rm gpu convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
```

Sem GPU, use o servico `cpu` **e** `--device cpu`:

```bash
docker compose run --rm cpu convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cpu --batch-size 1
```

Audio local em outra pasta, montada somente para leitura:

```bash
export YT_MIDI_INPUT_DIR="/caminho/absoluto/da/pasta-com-audio"
docker compose run --rm gpu convert --audio-file '/input/musica.wav' --device cuda
```

Sem essa variavel, `output` tambem fica acessivel em `/input` somente para leitura.
O nome do arquivo e relativo a pasta montada, nao o caminho original do host.

Resultados ficam em `output/job-<id>/`: video, `midi/combined.mid`, MIDIs
individuais, `result.json` e `worker.log`. WAV/intermediarios sao removidos por
padrao; `--keep-intermediates` os preserva. Caminhos absolutos dentro do JSON
referem-se ao container; `/data/output/...` corresponde a `output/...` no host.

`convert` permite uma hora por padrao; `prepare`, 900 segundos. Ambos limitam o
download a 1 GiB. Para duas horas, acrescente `--max-duration 7200`; ajuste
`--max-download-size` em bytes somente se necessario.
`--batch-size 1` reduz pressao de VRAM. `prepare` pode ser usado sem modelo.

## Sem Compose

Os mounts e a imagem sao os mesmos:

```bash
docker build --platform linux/amd64 \
  --build-arg APP_UID="$(id -u)" --build-arg APP_GID="$(id -g)" \
  -t youtube-midi:local .
docker run --rm --init --gpus all \
  --mount type=volume,src=youtube-midi-models,dst=/models \
  youtube-midi:local setup-model --device cuda
docker run --rm --init --gpus all \
  --mount type=volume,src=youtube-midi-models,dst=/models \
  --mount "type=bind,src=$PWD/output,dst=/data/output" \
  youtube-midi:local convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
```

Para CPU, retire `--gpus all` e substitua `--device cuda` por `--device cpu`.
Para arquivo local, adicione um mount readonly para `/input` e use `--audio-file`.
O diretorio de saida deve existir, como no fluxo Compose.

Depois do setup, uma conversao de audio local pode rodar sem rede:

```bash
docker run --rm --init --network none \
  --mount type=volume,src=youtube-midi-models,dst=/models \
  --mount "type=bind,src=$PWD/output,dst=/data/output" \
  --mount "type=bind,src=$YT_MIDI_INPUT_DIR,dst=/input,readonly" \
  youtube-midi:local convert --audio-file /input/musica.wav --device cpu --batch-size 1
```

## Persistencia e permissoes

`--rm` remove somente o container. O volume de modelos e os arquivos do host
permanecem; nao se baixa o modelo em cada conversao.
Nao use `docker compose down -v` para limpeza rotineira: isso apaga o modelo.
O volume tem nome fixo e e compartilhado pelos servicos deste projeto.

Se mudar UID/GID, verifique o proprietario do volume antes de reutiliza-lo:

```bash
docker compose run --rm --entrypoint id cpu
docker compose run --rm --entrypoint stat cpu -c '%u:%g %n' /models /data/output
```

Para corrigir apenas o volume deste projeto, depois de confirmar que ele nao e
compartilhado com outros usuarios e exportar os UID/GID corretos:

```bash
docker run --rm --user 0 --entrypoint chown \
  --mount type=volume,src=youtube-midi-models,dst=/models \
  youtube-midi:local -R "$LOCAL_UID:$LOCAL_GID" /models
```

Isso e manutencao pontual, nao o usuario de execucao padrao. Nao use `chmod 777`.
Ao mudar a versao principal do Python/base ou arquitetura, prepare um novo
runtime compativel; nao reutilize um virtualenv incompativel nem remova dados
de outros projetos. Os pins de imagem sao explicitos para permitir atualizacoes
controladas, nao substituem atualizacoes de seguranca.

## Tamanho e verificacoes

Medicao local em 2026-11-15, imagens descomprimidas via `docker image inspect`:

| Variante com a mesma configuracao | Tamanho |
| --- | --- |
| Python 3.11.18 slim-bookworm | 837.120.690 bytes, cerca de 798 MiB |
| Python 3.11.18 slim-trixie, escolhida | 825.893.413 bytes, cerca de 788 MiB |

Trixie foi a menor entre as duas bases glibc testadas; nao se afirma minimo
absoluto entre todas as imagens possiveis. Alpine/musl nao atende aos wheels
PyTorch/CUDA fixados. A imagem final nao inclui compiladores, dependencias dev,
runtime ML ou pesos. FFmpeg e suas bibliotecas contribuem para o tamanho.
Python, uv e Deno estao fixados por versao/digest; pacotes apt podem mudar entre builds.

O volume do modelo medido ocupa 6,1 GiB adicionais, mesmo em CPU.
Reserve pelo menos 12 GiB livres para setup, alem da imagem, cache de build e midias.
UV_NO_CACHE evita reter uma segunda copia dos wheels no volume.

```bash
docker image inspect youtube-midi:local --format '{{.Size}}'
docker compose run --rm --entrypoint du cpu -sh /models/yourmt3
```

Build, ferramentas, escrita nao-root, setup e conversao de audio sintetico
de 12 s foram verificados em CPU, CUDA e com `--network none`, reutilizando o
volume. MIDI e notas devem ser conferidos; isso nao certifica qualidade musical.
O download real do YouTube continua uma verificacao separada, nao executada
nesta entrega. A CI testa somente imagem/CLI/preparo local, sem pesos ou GPU.

## Diagnostico rapido

| Erro | Acao |
| --- | --- |
| Cannot connect to Docker daemon | Inicie Desktop/Engine e confira `docker version` |
| Permission denied no socket | Revise acesso ao daemon; nao altere o socket para 777 |
| GPU device driver indisponivel | Confira driver, backend WSL2 ou Toolkit no host correto |
| CUDA requested but unavailable | Use servico gpu/`--gpus all` e valide CUDA; CPU deve ser explicita |
| Modelo nao configurado | Execute setup-model montando o mesmo volume |
| Bind source path does not exist | Crie output ou corrija YT_MIDI_INPUT_DIR |
| Permission denied nos dados | Confira UID/GID e ownership, nao execute convert como root |
| VRAM esgotada | Use `--batch-size 1`, feche outros apps ou escolha CPU |
| YouTube falha, mesmo com Deno | Confira acesso/limites/restricoes da origem; nao ha autenticacao ou DRM |
