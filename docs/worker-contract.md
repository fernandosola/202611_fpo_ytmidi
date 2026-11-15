# Contrato do worker

O worker YourMT3+ incluido usa este contrato e e selecionado por padrao apos
`yt-midi setup-model`. Backends personalizados podem ser selecionados com
`--worker` e `--worker-python`. O adapter nao e uma sandbox para scripts desconhecidos.

## Execucao

O processo recebe `--request <arquivo>` e `--response <arquivo>`. Deve usar o
ambiente/modelo ja preparados, nao fazer downloads, registrar logs em stdout
ou stderr e retornar zero somente depois de escrever uma resposta valida.

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

O backend adapta audio para a taxa/canais reais do checkpoint. O processamento
deve limitar lotes na GPU e preservar notas sustentadas entre segmentos.
`auto` pode escolher CPU/CUDA; `cuda` ou `cpu` explicitos nao permitem troca silenciosa.

## Resposta

Exemplo ilustrativo de formato, **nao resultado de um modelo real**. O hash
de zeros deve ser substituido pelo SHA-256 real dos pesos utilizados.

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
- Cada track representa uma classe de instrumento identificada, nao um canal interno.
- Nomes nao vazios; programa GM inteiro 0..127; percussao com booleano `is_drum`.
- Pitch inteiro 0..127; velocity inteiro 1..127, opcional com padrao 100.
- Start/end numericos, finitos, em segundos; start >= 0 e end > start.
- Notas nao podem exceder a duracao do audio em mais de 100 ms de tolerancia.
- Tracks podem estar vazias; se nao houver nenhuma nota, exportacao falha claramente.
- Registrar limitacoes em warnings, sem fabricar instrumentos ausentes.
- O backend nativo verifica os hashes da fonte e do checkpoint antes da inferencia.
  Para workers externos, a proveniencia reportada e registrada, mas sua verificacao
  real continua sob responsabilidade do backend personalizado.

Resposta inexistente/invalida, processo com erro, timeout ou troca de dispositivo
resultam em falha de transcricao. Logs permanecem em `worker.log` no job; request
e response sao intermediarios, preservados somente com `--keep-intermediates`.
