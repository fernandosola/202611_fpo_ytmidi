# Desenvolvimento

## Ambiente

Use Python 3.11 pelo uv e mantenha as dependencias em `pyproject.toml`.
Versione `uv.lock`. Nao mantenha uma segunda lista de dependencias manual em
requirements.txt nem instale o modelo no ambiente da CLI.

```bash
uv sync --locked --group dev
```

Depois que houver um repositorio Git inicializado, instale os hooks:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## Padroes

- Layout src, modulos pequenos, snake_case e classes em PascalCase.
- Type hints nas interfaces e contratos imutaveis com dataclasses.
- Ruff: lint, imports e formatacao; limite de 100 colunas e quatro espacos.
- mypy strict no codigo proprio. Excecoes de imports somente para bibliotecas sem stubs.
- Erros especificos por etapa, mensagens claras e logging padrao.
- Nenhum import de torch/JAX/TensorFlow em `--help` ou `doctor`.
- APIs/JSON estruturado para bibliotecas externas, sem interpretar stdout humano.
- Subprocessos sem shell; paths exclusivos por job; nao sobrescrever entrada ou saidas alheias.
- Sem refatoracoes nao relacionadas, segredos, grandes midias ou pesos no Git.

## Testes

Adicione testes perto da etapa alterada, reutilizando fixtures de `tests/conftest.py`.
As notas dos testes de MIDI e worker sao fixtures, nao predicoes de modelo.
Os testes FFmpeg usam WAV gerado localmente, sem material protegido.

Marcadores: `integration` para binarios locais, `network` para acesso externo,
`model` para pesos reais e `gpu` para hardware. Testes do modelo ou YouTube
nao entram na CI rapida. Ausencia de FFmpeg pula somente os testes dependentes;
a CI instala FFmpeg para executar essa integracao.

```bash
uv run pytest -m 'not model and not network and not gpu' --cov=youtube_midi
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

Mudancas no worker exigem contrato valido, programa GM 0..127, tempos finitos,
percussao explicita, ausencia de mudanca silenciosa de dispositivo e continuidade
de notas nas fronteiras dos segmentos. Avaliacao musical e separada dos testes
de software; registre checkpoint, classes, metricas e consumo de VRAM.

## Codigos de saida

| Codigo | Significado |
| --- | --- |
| 0 | Sucesso |
| 1 | Erro de sistema de arquivos |
| 2 | Argumentos invalidos |
| 3 | Dependencia ou worker ausente |
| 4 | Download/URL/metadados |
| 5 | Midia ou extracao de audio |
| 6 | Transcricao ou contrato do worker |
| 7 | Exportacao MIDI |
| 130 | Cancelamento |
