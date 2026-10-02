# Segurança e privacidade

## Processamento

O backend executa localmente. Não há API externa, analytics, telemetria, CDN obrigatório nem armazenamento em nuvem. O servidor de desenvolvimento documentado escuta em `127.0.0.1`. Não exponha a porta em interfaces de rede sem adicionar controles apropriados.

## Arquivos

- Extensões aceitas: `.csv` e `.xlsx`; formatos com macros não são aceitos.
- O limite inicial é 100 MB, configurável por `BI_MAX_FILE_SIZE_MB`.
- O nome informado nunca é usado para criar caminho de arquivo: o conteúdo é processado em memória e nomes de caminho são reduzidos ao nome-base.
- CSV passa por decodificação e validação de cabeçalho. XLSX precisa ter estrutura ZIP esperada e vínculos externos são recusados.
- A leitura usa bibliotecas de dados; macros ou fórmulas não são executadas.
- Conteúdo de célula não é enviado nos logs. O relatório exportado é salvo pelo próprio navegador somente quando o usuário solicita.

## Ameaças consideradas e limites

São tratados extensão incorreta, arquivo vazio/corrompido, caminho malicioso e excesso de tamanho. O limite de bytes reduz abuso simples, mas processamento em memória ainda pode consumir recursos; XLSX compactado pode expandir muito. Não abra a aplicação em uma rede não confiável. O protótipo ainda não possui autenticação, quotas por cliente ou isolamento de processo.

## Recomendações

Mantenha dependências atualizadas, execute com uma conta sem privilégios administrativos e analise apenas arquivos autorizados. Não trate este protótipo como ambiente multiusuário ou serviço exposto à internet.
