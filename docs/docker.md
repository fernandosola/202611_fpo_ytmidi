# Execução com Docker

Container Linux **amd64**, com Python 3.11, uv, FFmpeg/ffprobe, Deno e CLI.
CPU e GPU usam a mesma imagem. O modelo é instalado uma vez no volume persistente
`youtube-midi-models`; ele não faz parte da imagem.

## Instalar Docker no host

Escolha uma rota: Ubuntu nativo com Docker Engine, ou Windows/WSL2 com Docker Desktop.
Não instale as duas soluções na mesma distro WSL. Pule os passos já configurados.

### Ubuntu: Docker Engine e Compose

Em Ubuntu 22.04/24.04, configure o repositório oficial:

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

Se já existem pacotes como `docker.io`, `podman-docker` ou `containerd` de outra
origem, examine os [conflitos documentados](https://docs.docker.com/engine/install/ubuntu/)
antes de migrar. Não remova serviços ou dados usados por outros projetos sem avaliar impacto.

Opcionalmente, permita o uso sem `sudo`:

```bash
sudo usermod -aG docker "$USER"
```

Saia e entre novamente na sessão. **O grupo docker concede privilégios equivalentes
a root no host.** Não use `chmod 777` no socket. Como alternativa, use `sudo docker`
nos comandos abaixo, preservando os valores do UID/GID do seu usuário no build.

```bash
docker version
docker compose version
docker run --rm hello-world
```

### Windows: Docker Desktop com WSL2

1. Instale/atualize WSL2: no PowerShell, `wsl --install` quando necessário e `wsl --update`.
2. Confira `wsl --list --verbose`: a distro Ubuntu deve aparecer com versão 2.
3. Instale [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
4. Ative **Use WSL 2 based engine** e **Resources > WSL Integration > Ubuntu**.
5. Use Linux containers. No terminal Ubuntu, execute `docker version` e `docker compose version`.
6. Execute `docker run --rm hello-world` e os comandos do projeto pelo terminal WSL.

Use WSL atualizado (mínimo 2.1.5 segundo a documentação). Não instale um segundo
daemon Engine dentro da distro integrada.
Fonte: [Docker Desktop e WSL2](https://docs.docker.com/desktop/features/wsl/).

## GPU NVIDIA (opcional)

Para CPU, pule esta seção. Para GPU, o driver do host precisa funcionar primeiro;
siga [o tutorial do driver](installation.md#gpu-nvidia-opcional). Não instale
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

Os últimos dois comandos alteram a configuração do daemon e o reiniciam, podendo
interromper containers ativos. Planeje essa operação. Docker rootless tem
[configuração própria](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html);
não aplique os comandos do daemon rootful indiscriminadamente.

### Desktop Windows/WSL2

Atualize o driver NVIDIA **no Windows**, WSL e Docker Desktop; ative o backend WSL2.
Não instale driver Linux ou configure um daemon separado na distro integrada.
O Desktop gerencia o acesso GPU, sem exigir Toolkit instalado dentro do Ubuntu WSL.
Fonte: [GPU no Docker Desktop](https://docs.docker.com/desktop/features/gpu/).

Depois de construir a imagem abaixo, confira:

```bash
docker run --rm --gpus all --entrypoint nvidia-smi youtube-midi:local
```

Isso verifica o driver no container; `setup-model --device cuda` e `convert`
também testam CUDA real no PyTorch. A ausência de `nvidia` em `docker info`
isoladamente não prova falta de GPU, especialmente no Docker Desktop.

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

O build atende também ao serviço `gpu`. UID/GID iguais aos do host evitam resultados
root-owned. O container sempre executa como usuário `app`, não-root; UID/GID zero
são rejeitados. A pasta `output` precisa existir e pertencer ao seu usuário:
Compose não a cria automaticamente para evitar diretórios criados como root.

## Instalar o modelo uma vez

GPU, após configurar o host:

```bash
docker compose run --rm gpu setup-model --device cuda
docker compose run --rm gpu doctor --json
```

Ou CPU, sem necessidade de GPU/Toolkit:

```bash
docker compose run --rm cpu setup-model --device cpu
docker compose run --rm cpu doctor --json
```

Escolha uma rota; não é preciso instalar duas vezes para alternar CPU/GPU.
Internet é necessária no setup. O volume guarda `/models/yourmt3/runtime`,
fonte/checkpoint e manifesto. O lock com hashes e a revisão do modelo são os
mesmos da instalação local. Não monte a `.venv` ou o runtime Python do host:
esses ambientes dependem dos caminhos e bibliotecas do sistema onde foram criados.

## Converter

URL pública autorizada, com GPU:

```bash
docker compose run --rm gpu convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cuda
```

Sem GPU, use o serviço `cpu` **e** `--device cpu`:

```bash
docker compose run --rm cpu convert 'https://www.youtube.com/watch?v=<ID_DO_VIDEO>' --device cpu --batch-size 1
```

Áudio local em outra pasta, montada somente para leitura:

```bash
export YT_MIDI_INPUT_DIR="/caminho/absoluto/da/pasta-com-audio"
docker compose run --rm gpu convert --audio-file '/input/musica.wav' --device cuda
```

Sem essa variável, `output` também fica acessível em `/input` somente para leitura.
O nome do arquivo é relativo à pasta montada, não o caminho original do host.

Resultados ficam em `output/job-<id>/`: vídeo, `midi/combined.mid`, MIDIs
individuais, `result.json` e `worker.log`. WAV/intermediários são removidos por
padrão; `--keep-intermediates` os preserva. Caminhos absolutos dentro do JSON
referem-se ao container; `/data/output/...` corresponde a `output/...` no host.

`convert` permite uma hora por padrão; `prepare`, 900 segundos. Ambos limitam o
download a 1 GiB. Para duas horas, acrescente `--max-duration 7200`; ajuste
`--max-download-size` em bytes somente se necessário.
`--batch-size 1` reduz pressão de VRAM. `prepare` pode ser usado sem modelo.

Antes de o worker finalizar, `setup-model` e `convert` retiram o modelo da GPU,
executam coleta de lixo e liberam o cache CUDA livre, inclusive em exceções e
interrupções Python. Isso é automático, sem flags; `worker.log` registra
`CUDA model unloaded; allocator cache cleared.` nas conversões CUDA.
O contexto CUDA restante é liberado quando o processo termina. Não se apagam
os pesos do volume nem se interfere na memória de outras aplicações.

## Sem Compose

Os mounts e a imagem são os mesmos:

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
O diretório de saída deve existir, como no fluxo Compose.

Depois do setup, uma conversão de áudio local pode rodar sem rede:

```bash
docker run --rm --init --network none \
  --mount type=volume,src=youtube-midi-models,dst=/models \
  --mount "type=bind,src=$PWD/output,dst=/data/output" \
  --mount "type=bind,src=$YT_MIDI_INPUT_DIR,dst=/input,readonly" \
  youtube-midi:local convert --audio-file /input/musica.wav --device cpu --batch-size 1
```

## Persistência e permissões

`--rm` remove somente o container. O volume de modelos e os arquivos do host
permanecem; não se baixa o modelo em cada conversão.
Não use `docker compose down -v` para limpeza rotineira: isso apaga o modelo.
O volume tem nome fixo e é compartilhado pelos serviços deste projeto.

Se mudar UID/GID, verifique o proprietário do volume antes de reutilizá-lo:

```bash
docker compose run --rm --entrypoint id cpu
docker compose run --rm --entrypoint stat cpu -c '%u:%g %n' /models /data/output
```

Para corrigir apenas o volume deste projeto, depois de confirmar que ele não é
compartilhado com outros usuários e exportar os UID/GID corretos:

```bash
docker run --rm --user 0 --entrypoint chown \
  --mount type=volume,src=youtube-midi-models,dst=/models \
  youtube-midi:local -R "$LOCAL_UID:$LOCAL_GID" /models
```

Isso é manutenção pontual, não o usuário de execução padrão. Não use `chmod 777`.
Ao mudar a versão principal do Python/base ou arquitetura, prepare um novo
runtime compatível; não reutilize um virtualenv incompatível nem remova dados
de outros projetos. Os pins de imagem são explícitos para permitir atualizações
controladas, não substituem atualizações de segurança.

## Tamanho e verificações

Medição local em 2026-11-15, imagens descomprimidas via `docker image inspect`:

| Variante com a mesma configuração | Tamanho |
| --- | --- |
| Python 3.11.18 slim-bookworm | 837.120.690 bytes, cerca de 798 MiB |
| Python 3.11.18 slim-trixie, escolhida | 825.893.413 bytes, cerca de 788 MiB |

Trixie foi a menor entre as duas bases glibc testadas; não se afirma mínimo
absoluto entre todas as imagens possíveis. Alpine/musl não atende aos wheels
PyTorch/CUDA fixados. A imagem final não inclui compiladores, dependências dev,
runtime ML ou pesos. FFmpeg e suas bibliotecas contribuem para o tamanho.
Python, uv e Deno estão fixados por versão/digest; pacotes apt podem mudar entre builds.

O volume do modelo medido ocupa 6,1 GiB adicionais, mesmo em CPU.
Reserve pelo menos 12 GiB livres para setup, além da imagem, cache de build e mídias.
UV_NO_CACHE evita reter uma segunda cópia dos wheels no volume.

```bash
docker image inspect youtube-midi:local --format '{{.Size}}'
docker compose run --rm --entrypoint du cpu -sh /models/yourmt3
```

Build, ferramentas, escrita não-root, setup e conversão de áudio sintético
de 12 s foram verificados em CPU, CUDA e com `--network none`, reutilizando o
volume. MIDI e notas devem ser conferidos; isso não certifica qualidade musical.
O download real do YouTube continua uma verificação separada, não executada
nesta entrega. A CI testa somente imagem/CLI/preparo local, sem pesos ou GPU.

## Diagnóstico rápido

| Erro | Ação |
| --- | --- |
| Cannot connect to Docker daemon | Inicie Desktop/Engine e confira `docker version` |
| Permission denied no socket | Revise acesso ao daemon; não altere o socket para 777 |
| GPU device driver indisponível | Confira driver, backend WSL2 ou Toolkit no host correto |
| CUDA requested but unavailable | Use serviço gpu/`--gpus all` e valide CUDA; CPU deve ser explícita |
| Modelo não configurado | Execute setup-model montando o mesmo volume |
| Bind source path does not exist | Crie output ou corrija YT_MIDI_INPUT_DIR |
| Permission denied nos dados | Confira UID/GID e ownership, não execute convert como root |
| VRAM esgotada | Use `--batch-size 1`, feche outros apps ou escolha CPU |
| YouTube falha, mesmo com Deno | Confira acesso/limites/restrições da origem; não há autenticação ou DRM |
