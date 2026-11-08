# 10 — Regras de qualidade de dados

Catálogo único de regras. **Toda** regra tem: ID estável, dimensão, como detecta, severidade padrão, impacto no BI, correção sugerida (operação do pipeline) e se já existe.

Severidade: 🔴 **crítica** (vai gerar número errado no dashboard) · 🟡 **atenção** (pode distorcer ou atrapalhar) · ⚪ **informativa**.

## 1. Score

- O score é calculado por coluna → tabela → arquivo, como média ponderada das dimensões aplicáveis (pesos atuais mantidos: completude 0,30, unicidade 0,25, validade 0,20, consistência 0,15, integridade 0,10; **padronização** entra com 0,10, e os pesos são renormalizados).
- **Teto por severidade:** se houver qualquer problema 🔴 aberto, o veredito é no máximo "Com ajustes", independentemente do número. Isso evita o caso "score 92, mas o total do dashboard está errado".
- Veredito: **Pronto** (sem 🔴 e score ≥ 90) · **Com ajustes** · **Não recomendado** (score < 65 ou 🔴 em chave/medida principal).

## 2. Regras

### Completude
| ID | Regra | Detecção | Sev. | Impacto no BI | Correção sugerida | Hoje |
|---|---|---|---|---|---|---|
| CMP-01 | Nulos acima do limiar | `% nulos > 5%` (atenção) / `> 20%` (alta) | 🟡 | Médias e contagens enganosas | `fill_null` ou marcar "(não informado)" | ✅ |
| CMP-02 | Coluna 100% vazia | todos nulos ou vazios | ⚪ | Poluição do modelo | `drop_column` | ✅ |
| CMP-03 | Nulo disfarçado | valores em {`-`, `n/d`, `NA`, `null`, `0000-00-00`, `#N/D`, ` `} | 🟡 | Contados como valor válido | `normalize_null` | ❌ |
| CMP-04 | Chave com nulo | coluna candidata a chave com nulos | 🔴 | Linhas "em branco" nos visuais | `fill_null` / revisar origem | 🟡 |

### Unicidade
| ID | Regra | Detecção | Sev. | Impacto | Correção | Hoje |
|---|---|---|---|---|---|---|
| UNI-01 | Linhas duplicadas exatas | `COUNT(*) - COUNT(DISTINCT *)` | 🟡 | Totais inflados | `drop_duplicates` (com confirmação) | ✅ (na amostra) |
| UNI-02 | Chave de dimensão duplicada | candidata a chave no lado "1" com duplicados | 🔴 | O Power BI recusa o relacionamento 1:N ou cria N:N | Revisar a origem; não há correção automática | 🟡 |
| UNI-03 | Duplicado "quase igual" | igual após trim/minúsculas/sem acento | 🟡 | Categorias repetidas no visual | `trim` + `case` | ❌ |

### Validade
| ID | Regra | Detecção | Sev. | Impacto | Correção | Hoje |
|---|---|---|---|---|---|---|
| VAL-01 | Medida armazenada como texto | papel `measure` + valores não numéricos > 0 | 🔴 | Soma = 0 ou erro | `parse_number_br` | 🟡 (detecta "inválido", sem impacto) |
| VAL-02 | Data inválida | não converte com o formato detectado | 🔴 | Linhas fora da linha do tempo | `parse_date` / marcar | 🟡 (D1 distorce) |
| VAL-03 | Datas em formatos misturados | ≥ 2 padrões (`dd/mm/aaaa`, ISO, serial Excel) | 🟡 | Interpretação errada de dia/mês | `parse_date` multiformato | ❌ |
| VAL-04 | CPF/CNPJ inválido | dígito verificador | 🟡 | Cadastro com erro | `validate_document` (marcar, nunca "corrigir") | ❌ |
| VAL-05 | E-mail inválido | regex | ⚪ | — | marcar | ❌ |
| VAL-06 | Fora de faixa plausível | data futura em "data_nascimento"; idade < 0 ou > 120; percentual > 100 | 🟡 | Outliers falsos | marcar | ❌ |
| VAL-07 | Negativo em medida tipicamente positiva | quantidade e valor < 0 | ⚪ | Pode ser estorno legítimo | Só informar | 🟡 (contagem existe) |

### Consistência
| ID | Regra | Detecção | Sev. | Impacto | Correção | Hoje |
|---|---|---|---|---|---|---|
| CON-01 | Tipos misturados na coluna | % dominante < 95% | 🟡 | Erro de tipo no Power Query | `cast` com tratamento | ✅ |
| CON-02 | Código numérico com zero à esquerda perdido | mistura de `0123` e `123` | 🟡 | Chaves não casam | `pad_left` | ❌ |
| CON-03 | Separador decimal inconsistente | `1.5` e `1,5` na mesma coluna | 🔴 | Valores 10×–1000× errados | `parse_number_br` | ❌ |
| CON-04 | Encoding corrompido | presença de `Ã©`, `Ã§`, `�` | 🟡 | Texto ilegível, categorias duplicadas | Reimportar com outro encoding | ❌ |

### Integridade
| ID | Regra | Detecção | Sev. | Impacto | Correção | Hoje |
|---|---|---|---|---|---|---|
| INT-01 | Chave estrangeira órfã | % de valores da fato sem correspondência na dimensão | 🔴 se > 5% | Linha "(em branco)" e totais por dimensão errados | Revisar a origem; opcional: dimensão "Desconhecido" | ✅ (cobertura) |
| INT-02 | Relacionamento N:N | os dois lados com duplicados | 🔴 | Ambiguidade e totais duplicados | Criar tabela ponte; revisar a chave | ❌ |
| INT-03 | Tipos incompatíveis entre chaves | texto × número | 🟡 | O relacionamento falha | `cast` | 🟡 |

### Padronização
| ID | Regra | Detecção | Sev. | Impacto | Correção | Hoje |
|---|---|---|---|---|---|---|
| PAD-01 | Espaços extras | `valor != trim(valor)` | 🟡 | Categorias duplicadas | `trim` | ❌ |
| PAD-02 | Caixa inconsistente | mesma palavra com caixas diferentes | 🟡 | Categorias duplicadas | `case` | ❌ |
| PAD-03 | Variações de UF/sigla | `SP`, `sp`, `São Paulo` | 🟡 | Mapa e filtros fragmentados | `map_values` (pós-MVP) | ❌ |
| PAD-04 | Nomes de colunas fora do padrão | espaços, acentos, maiúsculas mistas | ⚪ | DAX mais verboso | `rename_columns` | ❌ |
| PAD-05 | Documento sem padrão de máscara | CPF com e sem pontuação | ⚪ | Chaves não casam | `normalize_document` | ❌ |

## 3. Regras de privacidade associadas
Toda regra respeita a classificação do `07_SEGURANCA.md`: em coluna sensível, a regra reporta **contagens**, nunca exemplos de valores.

## 4. Como adicionar uma regra
1. Criar um ID novo (nunca reaproveitar).
2. Implementar em `domain/quality/rules/<dimensão>.py` como função pura `(ColumnProfile, Context) -> list[Issue]`.
3. Teste positivo e teste negativo no conjunto-ouro.
4. Se houver correção, a operação correspondente precisa existir no catálogo de M4, **com tradução M**.
5. Atualizar esta tabela.
