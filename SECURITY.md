# Segurança e privacidade

## Processamento

O backend executa localmente. Não há API externa, analytics, telemetria, CDN obrigatório nem armazenamento em nuvem. O servidor de desenvolvimento documentado no README escuta em `127.0.0.1`, e a aplicação só aceita requisições com cabeçalho Host local (`127.0.0.1`, `localhost`; configurável por `BI_ALLOWED_HOSTS`), o que mitiga ataques de DNS rebinding. Não exponha a porta em interfaces de rede sem adicionar controles apropriados.

## Arquivos

- Extensões aceitas: `.csv`, `.xlsx` e `.xlsm`. Arquivos com macros podem ser lidos como dados, mas macros nunca são carregadas para execução.
- O limite inicial é 100 MB por arquivo, configurável por `BI_MAX_FILE_SIZE_MB`.
- A amostra de profiling em workbook tem um limite combinado de 1.000.000 de células por padrão (`BI_MAX_XLSX_PROFILE_CELLS`).
- Lotes aceitam até 50 arquivos e 500 MB no total, ajustáveis por `BI_MAX_FILES_PER_BATCH` e `BI_MAX_BATCH_SIZE_MB`.
- Nomes relativos enviados pelo navegador são tratados apenas como rótulos. Nenhum nome recebido é usado para abrir ou criar caminhos.
- O backend lê o upload na memória; o parser multipart usa arquivos temporários limitados ao spool e os fecha em `finally`. Não há cópia persistente do arquivo.
- XLSX/XLSM devem ter a estrutura ZIP esperada. Conteúdo DTD/ENTITY, estrutura corrompida, metadados de relacionamento inválidos ou tamanho expandido acima do limite são recusados. A presença de macros, definições de conexão, links externos, ActiveX ou objetos incorporados é registrada e não bloqueia por si só a leitura das células.
- OpenPyXL abre cada workbook em modo somente leitura (`read_only=True`, `keep_vba=False`, `keep_links=False`, `data_only=True`). Não executa macros/fórmulas, não recalcula fórmulas e não atualiza nem segue conexões externas. Apenas valores armazenados em cache são lidos; fórmulas sem cache podem aparecer como ausentes.
- Abas são processadas sob limites de tabelas, linhas, colunas, células e tempo. Uma falha de leitura em uma aba é registrada como status de aba; outras abas legíveis continuam no relatório. Falha na abertura do pacote inteiro ainda impede a análise.
- CSV detecta encoding, delimitador, separador decimal e cabeçalho; a interface permite substituir as três últimas configurações.
- A inferência de cabeçalho usa sinais do schema e transições estáveis de tipo; quando ainda houver ambiguidade, a interface pergunta se a primeira linha é cabeçalho ou dado, podendo manter nomes genéricos. Nenhum valor de célula é promovido silenciosamente a nome no relatório.
- A comparação de relacionamentos entre CSVs usa apenas uma amostra limitada em memória durante o lote, ignora colunas classificadas como potencialmente sensíveis e descarta os quadros temporários ao final. Nenhum valor comparado aparece no relatório.
- Logs técnicos registram somente tipo de erro; nunca conteúdo de células, caminhos ou linhas do arquivo.
- O relatório não contém prévia de linhas ou rótulos de categoria. Estatísticas e valores frequentes são suprimidos quando o nome da coluna indica dado pessoal: documentos (CPF, CNPJ, RG, CNH, passaporte, PIS/NIS), e-mail, telefone/celular, nome de pessoa (`nome`, `nome_cliente`, `nome_completo`; não `nome_produto`), remuneração (salário, remuneração, proventos), dados bancários (agência, conta bancária/corrente, PIX, cartão), data de nascimento e endereço; e quando os valores têm formato consistente de e-mail. A regra está em `app/analyzers/schema_analyzer.py` e é verificada por `tests/unit/test_v301_regressions.py`. Essa proteção heurística não substitui revisão: nomes de coluna não detectados ainda podem conter informação sensível em métricas agregadas.
- O relatório inclui nome do arquivo, hash SHA-256, esquema, métricas agregadas e timestamp. Cabeçalhos são schema e permanecem visíveis; valores das células não são publicados. Exportações só são criadas localmente quando solicitadas pelo usuário.

## Ameaças consideradas e limites

São tratados extensão incorreta, arquivo vazio/corrompido, caminho malicioso, DTD/ENTITY XML, relacionamentos malformados e excesso de tamanho/expansão. A existência de conteúdo ativo detectável não significa que o arquivo seja malicioso: ele é registrado de forma neutra, não executado e não impede por si só o profiling de células. O profiling tem limites de linhas, colunas, células, tempo e tamanho do relatório; a comparação entre CSVs também tem um limite de células por lote. A análise é somente leitura; não altera os arquivos originais. O timeout é verificado entre etapas e não interrompe uma operação individual do Pandas/OpenPyXL que já esteja em execução. A detecção de sensibilidade e os papéis semânticos são heurísticos e podem não reconhecer nomes de campo incomuns. Não abra a aplicação em rede não confiável; não há autenticação nem isolamento de processo.

## Recomendações

Mantenha dependências atualizadas, execute com uma conta sem privilégios administrativos, revise relatórios antes de compartilhá-los e analise apenas arquivos autorizados. Não trate este protótipo como ambiente multiusuário ou serviço exposto à internet.
