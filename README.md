# BI Swiss Knife

Aplicação local para diagnosticar estrutura e qualidade de arquivos `.xlsx`, `.xlsm` e `.csv`. O fluxo da V1 analisa cada arquivo uma vez e reutiliza o resultado estruturado para JSON, HTML e PDF; o processamento permanece local.

## Escopo da V1

A V1 responde o que existe no arquivo: abas, dimensões, colunas e tipos inferidos; possíveis identificadores e relações; ausência de valores, diferenças em relação aos tipos inferidos, duplicidades e anomalias estatísticas; score por dimensão; e sinais de conteúdo ativo ou relações externas. As classificações e sugestões são heurísticas e devem ser revistas com as regras do processo. Alta unicidade, sozinha, não confirma uma chave. Anomalia estatística não significa erro.

A camada de descoberta semântica produz sugestões explicáveis de análises, KPIs candidatos e um Dashboard Blueprint a partir do AnalysisResult. O blueprint é uma especificação para revisão: não cria dashboards, DAX, consultas Power Query nem modelos automaticamente.

## Requisitos

- Python 3.10 ou superior.
- Instalação inicial das dependências. Depois disso, a análise roda localmente e não precisa de internet.

## Instalação e execução

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000. O servidor escuta somente no loopback por padrão. Após instalar as dependências, a aplicação funciona sem internet.

Ao atualizar o projeto pelo GitHub, execute novamente `python -m pip install -r requirements.txt` no ambiente virtual antes de iniciar o servidor. Isso instala dependências adicionadas em atualizações, incluindo ReportLab para exportação de PDF.

## Analisar arquivos e abrir relatórios

1. Inicie a aplicação e abra o endereço local no navegador.
2. Selecione arquivos `.xlsx`, `.xlsm` ou `.csv`, ou arraste uma pasta/arquivos para a área de entrada. Para CSV, confira delimitador, separador decimal e presença de cabeçalho quando solicitado.
3. Ao concluir, a aplicação baixa o JSON estruturado. Ele é o registro completo dos metadados, abas, colunas, estatísticas agregadas, qualidade, alertas, identificadores sugeridos, anomalias, relações, segurança e configurações de amostragem.
4. Use os botões de exportação para salvar o resumo CSV, HTML ou PDF. Abra o HTML salvo em qualquer navegador; ele é autocontido e funciona offline. O PDF também é criado localmente. Essas exportações usam o resultado já calculado e não reabrem o arquivo de origem.
5. Interprete registros avaliados em conjunto com registros disponíveis e a indicação de amostragem. Um score baixo ou uma sugestão não confirma, por si só, um problema de negócio.

## Privacidade e segurança

Os arquivos são lidos localmente, em memória e em modo somente leitura. A aplicação não envia dados a serviços externos, não usa IA remota ou CDN e não executa macros, fórmulas, objetos incorporados ou conexões externas. Relatórios omitem valores brutos de células e suprimem estatísticas de colunas reconhecidas como potencialmente sensíveis. Essa identificação é heurística; revise nomes de colunas e resultados antes de compartilhar relatórios. Veja [SECURITY.md](SECURITY.md) para controles e limites detalhados.

### Configuração

As opções são lidas de variáveis de ambiente antes de iniciar o servidor:

| Variável | Padrão | Uso |
|---|---:|---|
| `BI_MAX_FILE_SIZE_MB` | 100 | Limite por arquivo |
| `BI_MAX_XLSX_UNCOMPRESSED_MB` | 500 | Limite expandido de um XLSX |
| `BI_MAX_FILES_PER_BATCH` | 50 | Limite de arquivos por lote |
| `BI_MAX_BATCH_SIZE_MB` | 500 | Limite do lote |
| `BI_MAX_ROWS_TO_ANALYZE` | 200000 | Limite rígido de linhas perfiladas |
| `BI_SAMPLE_SIZE` | 100000 | Amostra padrão quando sampling está ligado |
| `BI_MAX_COLUMNS_TO_ANALYZE` | 100 | Limite de colunas perfiladas |
| `BI_MAX_CELLS_TO_ANALYZE` | 250000 | Limite aproximado de células perfiladas por tabela |
| `BI_MAX_XLSX_PROFILE_CELLS` | 1000000 | Limite de células perfiladas em conjunto entre as abas de um workbook |
| `BI_MAX_TABLES_TO_ANALYZE` | 20 | Limite de abas analisadas por XLSX |
| `BI_MAX_RELATIONSHIP_VALUE_ROWS` | 10000 | Valores por coluna usados na verificação de relacionamentos |
| `BI_MAX_BATCH_RELATIONSHIP_CELLS` | 250000 | Limite total de células mantidas temporariamente para comparar relacionamentos em um lote |
| `BI_MAX_RELATIONSHIP_CANDIDATES` | 100 | Máximo de sugestões de relacionamento |
| `BI_ENABLE_SAMPLING` | `true` | Ativa o limite amostral padrão |
| `BI_ANALYSIS_TIMEOUT_SECONDS` | 300 | Limite de tempo verificado entre etapas |
| `BI_REPORT_MAX_BYTES` | 26214400 | Limite por relatório JSON |
| `BI_NULL_ATTENTION_THRESHOLD_PCT` | 5 | Limite superior da faixa de atenção |
| `BI_NULL_MODERATE_THRESHOLD_PCT` | 20 | Limite superior da faixa moderada |
| `BI_NULL_CRITICAL_THRESHOLD_PCT` | 20 | Acima deste limite, faixa crítica |
| `BI_PERCENTILES` | `10,90` | Percentis adicionais para estatísticas numéricas (0–100) |

Use `BI_QUALITY_*` para configurar os limites e pesos do score de qualidade; os nomes detalhados estão em `app/core/config.py`.

## Funcionalidades

- Upload local de CSV, XLSX e XLSM, inclusive ao soltar pastas, com descoberta de abas.
- Seleção de arquivos múltiplos ou pasta; subpastas também são percorridas ao arrastar a pasta (Chrome/Edge).
- Lotes de até 50 arquivos, 100 MB por arquivo e 500 MB no total por padrão; arquivos com erro são informados sem interromper os demais.
- Perfil de colunas com tipo físico, tipo inferido, papel semântico provável e confiança, valores ausentes, cardinalidade, possíveis chaves e valores inválidos.
- Estatísticas numéricas, sazonais de data e concentração categórica, sem rótulos de categoria nem prévia de linhas.
- Qualidade transparente por dimensão, duplicidades de linha, outliers IQR e sugestões explicáveis entre abas e arquivos CSV do mesmo lote.
- Configurações CSV para delimitador, separador decimal e cabeçalho, com detecção de encoding.
- Quando a presença de cabeçalho CSV é ambígua, a interface pergunta se a primeira linha é cabeçalho ou dado; também é possível manter nomes genéricos.
- Conteúdo potencialmente ativo em Excel é reportado sem execução; relações externas não são seguidas nem atualizadas. Abas legíveis continuam sendo analisadas quando macros, conexões ou objetos são detectados.
- O relatório JSON estruturado é baixado automaticamente ao concluir a análise; CSV-resumo, HTML offline expansível e PDF executivo local ficam disponíveis nos botões de exportação. HTML e PDF são derivados do resultado já calculado e não reabrem o arquivo fonte.
- A descoberta semântica adiciona dimensões, medidas, datas e identificadores elegíveis, sugestões de ranking/comparação/tendência/KPI, razões candidatas e blueprint. Cada sugestão informa campos, evidência, confiança, prioridade e justificativa; combinações sem campos compatíveis não são criadas.
- Campos com nomes que sugerem dados pessoais ou financeiros têm estatísticas suprimidas.
- Interface em português e sem recursos externos obrigatórios.

## Verificação

```powershell
python -m pytest
```

Os dados de teste são sintéticos. Consulte [docs/architecture.md](docs/architecture.md), [docs/xlsx-ingestion.md](docs/xlsx-ingestion.md), [SECURITY.md](SECURITY.md) e [docs/roadmap.md](docs/roadmap.md).

## Limitações atuais

O relatório usa amostragem limitada para profiling em arquivos grandes e identifica quando isso ocorre; a contagem total de linhas é obtida separadamente. Ainda não há análise incremental exata de todas as estatísticas. A inferência de tipos, score de qualidade, classificação de tabelas, relacionamentos e descoberta de análises são heurísticos. A detecção de dados sensíveis é baseada em nomes de colunas e não é um classificador de conteúdo. O blueprint não valida regras de negócio, não executa fórmulas, não contém DAX e não cria visuais finais. Não há persistência de histórico nem IA externa.
