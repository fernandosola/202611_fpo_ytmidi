# Contrato do worker

O worker YourMT3+ incluído usa este contrato e é selecionado por padrão após
`yt-midi setup-model`. Backends personalizados podem ser selecionados com
`--worker` e `--worker-python`. O adapter não é uma sandbox para scripts desconhecidos.

## Execução

O processo recebe `--request <arquivo>` e `--response <arquivo>`. Deve usar o
ambiente/modelo já preparados, não fazer downloads, registrar logs em stdout
ou stderr e retornar zero somente depois de escrever uma resposta válida.

Request:

```json
{
  "schema_version": 1,
  "audio": {
    "path": "/caminho/absoluto/job/audio.wav",
    "duration": 10.0,
    "sample_rate": 44100,
    "channels": 2
  },
  "device": "cuda",
  "batch_size": 4
}
```

O backend adapta áudio para a taxa/canais reais do checkpoint. O processamento
deve limitar lotes na GPU e preservar notas sustentadas entre segmentos.
`auto` pode escolher CPU/CUDA; `cuda` ou `cpu` explícitos não permitem troca silenciosa.

## Resposta

Exemplo ilustrativo de formato, **não resultado de um modelo real**. O hash
de zeros deve ser substituído pelo SHA-256 real dos pesos utilizados.

```json
{
  "schema_version": 1,
  "backend": {
    "name": "nome-do-modelo",
    "revision": "revisao-fixa-da-fonte",
    "checkpoint_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "device": "cuda",
  "tracks": [
    {
      "name": "Piano",
      "program": 0,
      "is_drum": false,
      "notes": [
        {"start": 0.5, "end": 1.2, "pitch": 60, "velocity": 100}
      ]
    }
  ],
  "warnings": []
}
```

- Schema version 1; resposta com limite de 16 MiB.
- Cada track representa uma classe de instrumento identificada, não um canal interno.
- Nomes não vazios; programa GM inteiro 0..127; percussão com booleano `is_drum`.
- Pitch inteiro 0..127; velocity inteiro 1..127, opcional com padrão 100.
- Start/end numéricos, finitos, em segundos; start >= 0 e end > start.
- Notas não podem exceder a duração do áudio em mais de 100 ms de tolerância.
- Tracks podem estar vazias; se não houver nenhuma nota, exportação falha claramente.
- Registrar limitações em warnings, sem fabricar instrumentos ausentes.
- O backend nativo verifica os hashes da fonte e do checkpoint antes da inferência.
  Para workers externos, a proveniência reportada é registrada, mas sua verificação
  real continua sob responsabilidade do backend personalizado.

Resposta inexistente/inválida, processo com erro, timeout ou troca de dispositivo
resultam em falha de transcrição. Logs permanecem em `worker.log` no job; request
e response são intermediários, preservados somente com `--keep-intermediates`.
