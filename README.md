# BI Swiss Knife

Aplicação local para diagnosticar arquivos `.xlsx`, `.xlsm` e `.csv`. A versão **0.3.0** aprofunda o profiling e a análise de qualidade, mantendo o processamento local e relatórios sem valores de células.

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
- Campos com nomes que sugerem dados pessoais ou financeiros têm estatísticas suprimidas.
- Interface em português e sem recursos externos obrigatórios.

## Verificação

```powershell
python -m pytest
```

Os dados de teste são sintéticos. Consulte [docs/architecture.md](docs/architecture.md), [docs/xlsx-ingestion.md](docs/xlsx-ingestion.md), [SECURITY.md](SECURITY.md) e [docs/roadmap.md](docs/roadmap.md).

## Limitações atuais

O relatório usa amostragem limitada para profiling em arquivos grandes e identifica quando isso ocorre; a contagem total de linhas é obtida separadamente. Ainda não há análise incremental exata de todas as estatísticas. A inferência de tipos, score de qualidade, classificação de tabelas e relacionamentos são heurísticos. A detecção de dados sensíveis é baseada em nomes de colunas e não é um classificador de conteúdo. Não há persistência de histórico ou IA.
