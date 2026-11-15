# Arquitetura

## Fluxo

CLI -> opções tipadas -> preparação de mídia -> worker -> notas por instrumento
-> exportação MIDI -> relatório JSON.

`prepare` termina na preparação de mídia. `convert` usa YourMT3+ por padrão:
verifica fonte/checkpoint por SHA-256 e disponibilidade do dispositivo no runtime
antes de criar saídas ou baixar vídeo. Workers externos continuam como override
explícito, com verificação apenas do script e interpretador.

## Responsabilidades

| Módulo | Responsabilidade |
| --- | --- |
| cli | Argumentos, progresso, diagnóstico e códigos de saída |
| models | Opções, mídia, notas e instrumentos tipados |
| errors | Erros específicos por etapa |
| download | URL canônica, metadados, limites e vídeo com áudio |
| audio | ffprobe JSON e extração WAV PCM |
| transcription | Protocol, processo isolado e preflight do backend nativo |
| yourmt3 | Instalação do runtime, integridade de assets e adaptação de notas |
| yourmt3_worker | Carregamento YourMT3+, pré-processamento, inferência e merge |
| midi | MIDI combinado e individuais, sem inventar notas/instrumentos |
| pipeline | Orquestração, diretórios por job e relatórios |

Cada job usa UUID e evita sobrescrita. A publicação do WAV usa hard link no
mesmo sistema de arquivos para recusar de forma atômica um destino já existente.
O relatório é escrito em arquivo temporário e substituído dentro do próprio job.
Por padrão, uma conversão remove somente o WAV e o diretório intermediário que
ela criou; vídeo, MIDIs, relatório e log do worker são preservados.

O worker é um processo separado, com request/response JSON e log em arquivo,
sem transportar tensores entre ambientes. Timeout e cancelamento encerram seu
grupo de processos em Linux. Execução usa HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1
e WANDB_MODE=disabled;
o worker deve respeitar o contrato offline e não usar outros serviços de rede.
Essas variáveis não são uma sandbox de rede ou segurança.

## Estado da implementação

1. Fundação e ferramentas: implementadas.
2. Diagnóstico do hardware: implementado; CUDA validada no runtime do modelo.
3. Download: implementado e testado com simulações; smoke test online pendente.
4. Extração: implementada e testada com FFmpeg local.
5. Contrato, adapter e worker YourMT3+: implementados e testados com pesos reais.
6. Exportação MIDI: validada com fixtures e predições reais CPU/GPU.
7. CLI: prepare, convert, doctor e setup-model disponíveis.
8. Qualidade em música real/densa: pendente; testes sintéticos não certificam acurácia.

## Ambiente do modelo

`setup-model` cria um virtualenv no cache configurado, instala dependências por
lock com hashes e baixa somente código Python e um checkpoint de uma revisão fixa
do Space do autor. Não executa a UI, OAuth ou os scripts de treinamento do exemplo.
O manifesto é publicado somente após carregamento estrito e smoke test real.

O worker usa mono/16 kHz e segmentos de 32767 frames, seguindo o checkpoint T5.
Segmentação, detokenização e merge de ties reutilizam o upstream. Segmentos ficam
na RAM; `inference_file` transfere cada lote para GPU. O resultado é agrupado por
programa reconhecido, não por canal interno do decoder. Notas do padding final
são descartadas ou limitadas à duração real, com aviso para eventos inválidos.

## Próximas entregas

Avaliar áudio real autorizado, notas por instrumento, bateria,
continuidade, F1/onsets/offsets e memória. Incluir resultados de tempo por etapa
no relatório. Se YourMT3+ não atender, avaliar MT3; não criar dois backends sem
necessidade nem substituir identificação instrumental por stems genéricos.
