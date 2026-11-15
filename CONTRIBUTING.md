# Desenvolvimento

## Ambiente

Use Python 3.11 pelo uv e mantenha as dependências em `pyproject.toml`.
Versione `uv.lock`. Não mantenha uma segunda lista de dependências manual em
requirements.txt nem instale o modelo no ambiente da CLI.

```bash
uv sync --locked --group dev
```

Depois que houver um repositório Git inicializado, instale os hooks:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## Padrões

- Layout src, módulos pequenos, snake_case e classes em PascalCase.
- Type hints nas interfaces e contratos imutáveis com dataclasses.
- Ruff: lint, imports e formatação; limite de 100 colunas e quatro espaços.
- mypy strict no código próprio. Exceções de imports somente para bibliotecas sem stubs.
- Erros específicos por etapa, mensagens claras e logging padrão.
- Nenhum import de torch/JAX/TensorFlow em `--help` ou `doctor`.
- APIs/JSON estruturado para bibliotecas externas, sem interpretar stdout humano.
- Subprocessos sem shell; paths exclusivos por job; não sobrescrever entrada ou saídas alheias.
- Sem refatorações não relacionadas, segredos, grandes mídias ou pesos no Git.

## Testes

Adicione testes perto da etapa alterada, reutilizando fixtures de `tests/conftest.py`.
As notas dos testes de MIDI e worker são fixtures, não predições de modelo.
Os testes FFmpeg usam WAV gerado localmente, sem material protegido.

Marcadores: `integration` para binários locais, `network` para acesso externo,
`model` para pesos reais e `gpu` para hardware. Testes do modelo ou YouTube
não entram na CI rápida. Ausência de FFmpeg pula somente os testes dependentes;
a CI instala FFmpeg para executar essa integração.

```bash
uv run pytest -m 'not model and not network and not gpu' --cov=youtube_midi
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

Mudanças no worker exigem contrato válido, programa GM 0..127, tempos finitos,
percussão explícita, ausência de mudança silenciosa de dispositivo e continuidade
de notas nas fronteiras dos segmentos. Avaliação musical é separada dos testes
de software; registre checkpoint, classes, métricas e consumo de VRAM.

## Docker

Antes de alterar o empacotamento, execute:

```bash
mkdir -p output
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
docker compose config --quiet
docker compose build cpu
docker compose run --rm cpu --help
docker compose run --rm cpu doctor --json
```

A CI também verifica ferramentas, escrita não-root e preparo de mídia sintética.
Não inclua pesos, GPU ou download YouTube nesse gate rápido. Ao alterar worker
ou isolamento de ambientes, valide modelo real CPU/GPU separadamente, incluindo
instalação via wheel e inferência sem rede. [Comandos e requisitos](docs/docker.md).

## Códigos de saída

| Código | Significado |
| --- | --- |
| 0 | Sucesso |
| 1 | Erro de sistema de arquivos |
| 2 | Argumentos inválidos |
| 3 | Dependência ou worker ausente |
| 4 | Download/URL/metadados |
| 5 | Mídia ou extração de áudio |
| 6 | Transcrição ou contrato do worker |
| 7 | Exportação MIDI |
| 130 | Cancelamento |
