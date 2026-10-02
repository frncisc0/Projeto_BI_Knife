# Segurança e privacidade

## Processamento

O backend executa localmente. Não há API externa, analytics, telemetria, CDN obrigatório nem armazenamento em nuvem. O servidor de desenvolvimento documentado escuta em `127.0.0.1`. Não exponha a porta em interfaces de rede sem adicionar controles apropriados.

## Arquivos

- Extensões aceitas: `.csv` e `.xlsx`; formatos com macros não são aceitos.
- O limite inicial é 100 MB por arquivo, configurável por `BI_MAX_FILE_SIZE_MB`.
- Lotes aceitam até 50 arquivos e 500 MB no total, ajustáveis por `BI_MAX_FILES_PER_BATCH` e `BI_MAX_BATCH_SIZE_MB`.
- Nomes relativos enviados pelo navegador são tratados apenas como rótulos. Nenhum nome recebido é usado para abrir ou criar caminhos.
- O backend lê o upload na memória; o parser multipart usa arquivos temporários limitados ao spool e os fecha em `finally`. Não há cópia persistente do arquivo.
- XLSX deve ter a estrutura ZIP esperada; macros, conexões, conteúdo incorporado, relacionamentos externos e declarações XML DTD/ENTITY são recusados antes do profiling. O XML é verificado em fluxo e o limite expandido é configurável por `BI_MAX_XLSX_UNCOMPRESSED_MB`.
- OpenPyXL lê valores em cache (`data_only`) e desativa links (`keep_links=False`); macros e fórmulas não são executadas nem recalculadas.
- CSV detecta encoding, delimitador, separador decimal e cabeçalho; a interface permite substituir as três últimas configurações.
- A inferência de cabeçalho usa sinais do schema e transições estáveis de tipo; quando ainda houver ambiguidade, a interface pergunta se a primeira linha é cabeçalho ou dado, podendo manter nomes genéricos. Nenhum valor de célula é promovido silenciosamente a nome no relatório.
- A comparação de relacionamentos entre CSVs usa apenas uma amostra limitada em memória durante o lote, ignora colunas classificadas como potencialmente sensíveis e descarta os quadros temporários ao final. Nenhum valor comparado aparece no relatório.
- Logs técnicos registram somente tipo de erro; nunca conteúdo de células, caminhos ou linhas do arquivo.
- O relatório não contém prévia de linhas ou rótulos de categoria. Estatísticas são suprimidas quando o nome de coluna sugere CPF/CNPJ, e-mail, telefone, nome, salário ou dados bancários. Essa proteção heurística não substitui revisão: nomes de coluna não detectados ainda podem conter informação sensível em métricas agregadas.
- O relatório inclui nome do arquivo, hash SHA-256, esquema, métricas agregadas e timestamp. Cabeçalhos são schema e permanecem visíveis; valores das células não são publicados. Exportações só são criadas localmente quando solicitadas pelo usuário.

## Ameaças consideradas e limites

São tratados extensão incorreta, arquivo vazio/corrompido, caminho malicioso, recursos XLSX ativos/externos e excesso de tamanho/expansão. O profiling tem limites de linhas, colunas, células, tempo e tamanho do relatório; a comparação entre CSVs também tem um limite de células por lote. A análise é somente leitura; não altera os arquivos originais. O timeout é verificado entre etapas e não interrompe uma operação individual do Pandas/OpenPyXL que já esteja em execução. A detecção de sensibilidade e os papéis semânticos são heurísticos e podem não reconhecer nomes de campo incomuns. Não abra a aplicação em rede não confiável; não há autenticação nem isolamento de processo.

## Recomendações

Mantenha dependências atualizadas, execute com uma conta sem privilégios administrativos, revise relatórios antes de compartilhá-los e analise apenas arquivos autorizados. Não trate este protótipo como ambiente multiusuário ou serviço exposto à internet.
