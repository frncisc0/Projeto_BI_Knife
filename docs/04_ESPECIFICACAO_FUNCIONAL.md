# 04 — Especificação funcional dos módulos

Cada módulo traz: objetivo, problema, funcionalidades, requisitos (funcionais e não funcionais), regras de negócio, fluxo, entradas e saídas, dependências, critérios de aceitação, testes e complexidade.
**Estado atual** = o que existe hoje (ver `01_DIAGNOSTICO_TECNICO.md`). **MVP** indica se o item entra na primeira versão profissional.

Escala de complexidade: **P** (dias) · **M** (1–2 semanas) · **G** (3–6 semanas) · **GG** (> 6 semanas), considerando 1 desenvolvedor em meio período.

---

## M1 — Data Import

| Item | Especificação |
|---|---|
| **Objetivo** | Carregar arquivos de forma segura e interpretá-los corretamente, sem intervenção na maioria dos casos |
| **Problema** | CSV brasileiro tem `;`, vírgula decimal, cp1252; Excel tem cabeçalho fora da linha 1, abas vazias e macros |
| **Estado atual** | Funcional, com defeitos de tipos (D1, D3, D4) e codificação (fallback latin-1 silencioso) |
| **Funcionalidades** | CSV/XLSX/XLSM; várias abas e arquivos; detecção de encoding, delimitador, decimal e cabeçalho; detecção de **formato de data** e de **padrão numérico BR**; prévia local opt-in; tipos detectados |
| **RF** | RF-IMP-01 aceitar `.csv`, `.txt` delimitado, `.xlsx`, `.xlsm` · RF-IMP-02 detectar encoding entre UTF-8, UTF-8-BOM, cp1252 e latin-1, **com score de confiança e aviso de caracteres suspeitos** · RF-IMP-03 permitir sobrescrever delimitador, decimal, milhar, cabeçalho e formato de data · RF-IMP-04 prévia das primeiras 100 linhas na tela, com colunas sensíveis mascaradas · RF-IMP-05 listar abas e permitir escolher quais importar |
| **RNF** | Nunca executar macro, fórmula ou link · Arquivo original aberto só para leitura · Importar 1 milhão de linhas e 20 colunas em < 15 s numa máquina de referência (i5, 16 GB) |
| **Regras de negócio** | RN-IMP-01 coluna com letras e números (`P12`, `AB-1001`) é **código**, nunca número · RN-IMP-02 coluna com zero à esquerda (`00123`) é código · RN-IMP-03 `1.234` em coluna onde outros valores têm `,dd` = 1234 · RN-IMP-04 data `AAAA-MM-DD` é sempre ISO; `dd/mm/aaaa` é o padrão para `/`; se houver ambiguidade (todos os dias ≤ 12), perguntar ao usuário |
| **Fluxo** | Soltar arquivos → validar → detectar opções → (se ambíguo) perguntar → importar → mostrar resumo da importação |
| **Entradas e saídas** | Entrada: arquivos + opções. Saída: `Dataset` (tabelas no engine) + `ImportReport` (opções detectadas, confiança, avisos) |
| **Dependências** | `security`, `privacy` (para a prévia) |
| **Critérios de aceitação** | Os 30 arquivos do conjunto-ouro importados com tipos 100% corretos · ISO e BR distinguidos · Nenhum `P12` vira número |
| **Testes** | Conjunto-ouro de formatos; *property-based* (Hypothesis) para números BR; fuzzing de CSV malformado; arquivo de 1 milhão de linhas (performance) |
| **Complexidade** | **M** (as correções são P; prévia e engine somam o restante) |
| **MVP** | ✅ |

## M2 — Data Profiling

| Item | Especificação |
|---|---|
| **Objetivo** | Descrever cada tabela e coluna com precisão, sobre **todas** as linhas |
| **Problema** | Hoje o CSV perfila só as primeiras 25 mil linhas (2,5% de um arquivo de 1 milhão), com viés |
| **Estado atual** | Funcional para métricas básicas; amostragem enviesada (D5) |
| **Funcionalidades** | Linhas, colunas, tipos (físico, inferido, semântico), nulos, vazios, únicos, cardinalidade, duplicados, min/max/média/mediana/quartis/desvio, distribuição (histograma por faixas), datas (período, granularidade, lacunas), comprimento de texto, padrões (máscaras como `999.999.999-99`) |
| **RF** | RF-PRO-01 perfilar 100% das linhas até 10 milhões; acima disso, amostra **aleatória** documentada · RF-PRO-02 reportar `sampling_method` correto · RF-PRO-03 detectar padrões de máscara por coluna · RF-PRO-04 estatísticas suprimidas para colunas sensíveis |
| **RNF** | 1 milhão de linhas × 20 colunas em < 20 s · Memória < 2 GB para arquivo de 1 GB (out-of-core) |
| **Regras de negócio** | Toda métrica informa se veio de amostra · Coluna sensível mostra só contagens, nunca valores nem estatísticas |
| **Fluxo** | Automático após a importação; recálculo após cada correção aplicada |
| **Entradas e saídas** | `Dataset` → `ProfileReport` (por tabela e coluna) |
| **Dependências** | M1, `engine`, `privacy` |
| **Critérios de aceitação** | Métricas idênticas às calculadas manualmente no conjunto-ouro · `sampling_method` coerente com `sampled` |
| **Testes** | Comparação com cálculo de referência; teste de memória; teste de amostragem aleatória (seed fixa) |
| **Complexidade** | **M** (migração para DuckDB) |
| **MVP** | ✅ |

## M3 — Data Quality

| Item | Especificação |
|---|---|
| **Objetivo** | Dizer **se** a base é confiável, **onde** não é e **quanto** isso importa |
| **Problema** | O score atual é bom, mas validade = "parece com o tipo inferido", e não há padronização |
| **Estado atual** | Funcional: 5 dimensões ponderadas, alertas com recomendação |
| **Funcionalidades** | 6 dimensões (completude, unicidade, consistência, validade, integridade, padronização); regras do catálogo (doc 10); score por coluna, tabela e arquivo; **problemas priorizados por impacto no BI** |
| **RF** | RF-QUA-01 cada problema tem: regra, coluna, contagem, %, severidade, impacto ("totais vão somar errado"), correção sugerida · RF-QUA-02 regras configuráveis (ligar, desligar e limiar) · RF-QUA-03 regras personalizadas simples (faixa, lista, regex) — P2 |
| **RNF** | Regras determinísticas, com resultado igual em todas as execuções |
| **Regras de negócio** | RN-QUA-01 severidade crítica = vai gerar número errado no dashboard (chave duplicada em dimensão, medida como texto, datas inválidas) · RN-QUA-02 o score nunca aparece sem explicação |
| **Fluxo** | Perfil → aplicar regras → priorizar → mostrar "Pode usar? Sim / Com ajustes / Não" |
| **Entradas e saídas** | `ProfileReport` → `QualityReport` (score, dimensões, `Issue[]`) |
| **Dependências** | M2 |
| **Critérios de aceitação** | Cada regra do doc 10 tem um teste positivo e um negativo · Os problemas do conjunto-ouro são 100% detectados |
| **Testes** | Unitários por regra; regressão do score |
| **Complexidade** | **M** |
| **MVP** | ✅ |

## M4 — Data Cleaning (recorte MVP: correções sugeridas)

| Item | Especificação |
|---|---|
| **Objetivo** | Corrigir os problemas encontrados **com controle total do usuário** e entregar a correção em dois formatos: arquivo limpo e script Power Query M |
| **Problema** | O analista sabe o que está errado, mas precisa reescrever as correções à mão no Power Query |
| **Estado atual** | **Não existe** |
| **Funcionalidades (MVP)** | Converter tipo; interpretar data com formato; interpretar número BR; trim e espaços duplos; maiúsculas/minúsculas; remover duplicados exatos; preencher ou marcar nulos (valor fixo); padronizar CPF/CNPJ (máscara e dígito verificador); renomear colunas (snake_case ou padrão do usuário) |
| **Funcionalidades (futuras)** | Substituir valores por mapeamento; dividir e combinar colunas; regras condicionais; deduplicação aproximada |
| **RF** | RF-CLE-01 cada correção é uma operação declarativa no pipeline · RF-CLE-02 prévia "antes/depois" com a contagem de linhas afetadas · RF-CLE-03 desfazer e refazer · RF-CLE-04 exportar o pipeline como script M · RF-CLE-05 exportar o arquivo limpo (CSV UTF-8 ou XLSX) · RF-CLE-06 log de transformações no relatório |
| **RNF** | **O original nunca é alterado** (verificado por hash SHA-256 antes e depois) · Aplicar um pipeline de 10 operações em 1 milhão de linhas em < 10 s |
| **Regras de negócio** | RN-CLE-01 nenhuma operação é aplicada sem aceitação explícita · RN-CLE-02 operações que removem linhas exigem confirmação, mostrando quantas · RN-CLE-03 CPF/CNPJ inválido é **marcado**, nunca "corrigido" · RN-CLE-04 cada operação tem tradução M equivalente; se não tiver, ela não entra no catálogo |
| **Fluxo** | Problema → "Corrigir" → prévia → aceitar → pipeline atualizado → score recalculado |
| **Entradas e saídas** | `Issue` + parâmetros → `Operation`; `Pipeline` → arquivo limpo + `.pq` (M) + log |
| **Dependências** | M3, `engine`, `session`, `assistant/powerbi` |
| **Critérios de aceitação** | Para cada operação, o resultado no DuckDB = o resultado do M gerado executado no Power BI (validado manualmente em 10 casos e automaticamente por comparação de semântica) |
| **Testes** | Unitário por operação; teste de equivalência SQL × M (snapshot do M); hash do original |
| **Complexidade** | **G** |
| **MVP** | ✅ (recorte) |

## M5 — Data Transformation

| Item | Especificação |
|---|---|
| **Objetivo** | Moldar a base (merge, append, agrupamento, colunas calculadas) |
| **Recomendação** | **Adiar.** O Power Query já faz isso, de graça e bem, dentro da ferramenta que o público usa. Reimplementar é caro e não diferencia. Só reavaliar se usuários pedirem com frequência; mesmo assim, o caminho é **gerar M**, não um motor próprio |
| **Exceções no MVP** | Renomear e alterar tipo (já cobertos por M4) |
| **Complexidade** | **GG** |
| **MVP** | ❌ |

## M6 — Data Intelligence

| Item | Especificação |
|---|---|
| **Objetivo** | Apontar padrões que merecem atenção |
| **Estado atual** | IQR para outliers; contagem por mês e lacunas; relevância de insights |
| **Estatística resolve (manter e ampliar)** | Outliers (IQR, MAD robusto); tendência mensal (regressão simples / Mann-Kendall); sazonalidade simples; quebra de série (mês sem dados); concentração (Pareto 80/20); correlação entre medidas (Spearman) |
| **Onde IA se justificaria (P3, opt-in, local)** | Só para **redigir** explicações em linguagem natural e sugerir **nomes amigáveis** de colunas. Nunca para calcular ou decidir |
| **RF** | RF-INT-01 cada achado mostra o método, a evidência e uma ressalva |
| **Critérios de aceitação** | Achados reproduzíveis (mesmo arquivo, mesmo resultado) |
| **Complexidade** | **M** |
| **MVP** | 🟡 Manter o atual e corrigir as datas (D1); ampliações em P2 |

## M7 — Data Integration

| Item | Especificação |
|---|---|
| **Objetivo** | Mostrar como as tabelas se conectam e onde a conexão falha |
| **Estado atual** | Chaves simples e compostas; relacionamentos entre abas e entre CSVs, com cobertura |
| **Funcionalidades (MVP)** | Relacionamentos entre **qualquer** combinação CSV/XLSX; cardinalidade (1:1, 1:N, N:N); cobertura (% de chaves órfãs); alerta de N:N e de chave duplicada no lado "1" |
| **Funcionalidades (futuras)** | Correspondência aproximada (nomes de clientes); detecção de conflitos (mesmo ID com atributos diferentes) |
| **Regras de negócio** | RN-ITG-01 relacionamento só é "alta confiança" com cobertura ≥ 95% e lado 1 sem duplicados · RN-ITG-02 colunas sensíveis nunca são comparadas por valor |
| **Critérios de aceitação** | O conjunto-ouro estrela (1 fato + 3 dimensões) tem os 3 relacionamentos detectados com a cardinalidade correta |
| **Complexidade** | **M** (MVP) · **G** (fuzzy) |
| **MVP** | ✅ (sem fuzzy) |

## M8 — BI Assistant (foco do diferencial)

| Item | Especificação |
|---|---|
| **Objetivo** | Transformar o diagnóstico em **modelo e código prontos para o Power BI** |
| **Estado atual** | Modelo semântico, insights, KPIs e blueprint de páginas: bons, mas não acionáveis |
| **Funcionalidades (MVP)** | Modelo estrela sugerido (fatos, dimensões, chaves, direção do filtro); **tabela Calendário** sugerida (DAX); medidas DAX básicas (soma, contagem, média, variação mês a mês) para as medidas detectadas; script M completo de importação + correções; checklist "isso vai quebrar seu dashboard" (N:N, chave duplicada, data como texto, medida como texto, alta cardinalidade em visual) |
| **RF** | RF-BIA-01 o DAX e o M gerados devem ser sintaticamente válidos · RF-BIA-02 cada sugestão tem um "por quê" |
| **Regras de negócio** | RN-BIA-01 só sugerir medida para coluna com papel `measure` e confiança ≥ média · RN-BIA-02 nunca inventar regra de negócio (ex.: "receita líquida") sem evidência no nome da coluna |
| **Critérios de aceitação** | O M colado no Power Query Desktop importa o conjunto-ouro sem erro; o DAX passa no DAX Formatter |
| **Complexidade** | **G** |
| **MVP** | ✅ |

## M9 — Reports & Export

| Item | Especificação |
|---|---|
| **Estado atual** | JSON, HTML e PDF (backend); CSV resumo (frontend) |
| **Funcionalidades (MVP)** | Manter JSON, HTML e PDF; **adicionar** relatório XLSX (abas: Resumo, Colunas, Problemas, Transformações); arquivo limpo; script `.pq`; log de transformações; **histórico de sessões** (metadados, sem valores) |
| **Regras de negócio** | RN-REP-01 nenhum relatório exportado contém valores de células · RN-REP-02 todo relatório traz versão do BI Knife, hash do arquivo, data e configurações usadas (já existe) |
| **Critérios de aceitação** | Teste automatizado: nenhum valor do arquivo de entrada aparece em JSON, HTML, PDF ou XLSX exportado (exceto nomes de colunas) |
| **Complexidade** | **M** |
| **MVP** | ✅ |
