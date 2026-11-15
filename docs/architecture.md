# Arquitetura

## Fluxo

CLI -> opcoes tipadas -> preparacao de midia -> worker -> notas por instrumento
-> exportacao MIDI -> relatorio JSON.

`prepare` termina na preparacao de midia. `convert` usa YourMT3+ por padrao:
verifica fonte/checkpoint por SHA-256 e disponibilidade do dispositivo no runtime
antes de criar saidas ou baixar video. Workers externos continuam como override
explicito, com verificacao apenas do script e interpretador.

## Responsabilidades

| Modulo | Responsabilidade |
| --- | --- |
| cli | Argumentos, progresso, diagnostico e codigos de saida |
| models | Opcoes, midia, notas e instrumentos tipados |
| errors | Erros especificos por etapa |
| download | URL canonica, metadados, limites e video com audio |
| audio | ffprobe JSON e extracao WAV PCM |
| transcription | Protocol, processo isolado e preflight do backend nativo |
| yourmt3 | Instalacao do runtime, integridade de assets e adaptacao de notas |
| yourmt3_worker | Carregamento YourMT3+, preprocessamento, inferencia e merge |
| midi | MIDI combinado e individuais, sem inventar notas/instrumentos |
| pipeline | Orquestracao, diretorios por job e relatorios |

Cada job usa UUID e evita sobrescrita. A publicacao do WAV usa hard link no
mesmo sistema de arquivos para recusar de forma atomica um destino ja existente.
O relatorio e escrito em arquivo temporario e substituido dentro do proprio job.
Por padrao, uma conversao remove somente o WAV e o diretorio intermediario que
ela criou; video, MIDIs, relatorio e log do worker sao preservados.

O worker e um processo separado, com request/response JSON e log em arquivo,
sem transportar tensores entre ambientes. Timeout e cancelamento encerram seu
grupo de processos em Linux. Execucao usa HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1
e WANDB_MODE=disabled;
o worker deve respeitar o contrato offline e nao usar outros servicos de rede.
Essas variaveis nao sao uma sandbox de rede ou seguranca.

## Estado da implementacao

1. Fundacao e ferramentas: implementadas.
2. Diagnostico do hardware: implementado; CUDA validada no runtime do modelo.
3. Download: implementado e testado com simulacoes; smoke test online pendente.
4. Extracao: implementada e testada com FFmpeg local.
5. Contrato, adapter e worker YourMT3+: implementados e testados com pesos reais.
6. Exportacao MIDI: validada com fixtures e predicoes reais CPU/GPU.
7. CLI: prepare, convert, doctor e setup-model disponiveis.
8. Qualidade em musica real/densa: pendente; testes sinteticos nao certificam acuracia.

## Ambiente do modelo

`setup-model` cria um virtualenv no cache configurado, instala dependencias por
lock com hashes e baixa somente codigo Python e um checkpoint de uma revisao fixa
do Space do autor. Nao executa a UI, OAuth ou os scripts de treinamento do exemplo.
O manifesto e publicado somente apos carregamento estrito e smoke test real.

O worker usa mono/16 kHz e segmentos de 32767 frames, seguindo o checkpoint T5.
Segmentacao, detokenizacao e merge de ties reutilizam o upstream. Segmentos ficam
na RAM; `inference_file` transfere cada lote para GPU. O resultado e agrupado por
programa reconhecido, nao por canal interno do decoder. Notas do padding final
sao descartadas ou limitadas a duracao real, com aviso para eventos invalidos.

## Proximas entregas

Avaliar audio real autorizado, notas por instrumento, bateria,
continuidade, F1/onsets/offsets e memoria. Incluir resultados de tempo por etapa
no relatorio. Se YourMT3+ nao atender, avaliar MT3; nao criar dois backends sem
necessidade nem substituir identificacao instrumental por stems genericos.
