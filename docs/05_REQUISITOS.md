# 05 — Requisitos funcionais e não funcionais

Prioridade: **P0** obrigatória para o MVP · **P1** alta · **P2** média · **P3** evolução futura.
Status: ✅ atendido hoje · 🟡 parcial ou com defeito · ❌ não atendido.

## 1. Requisitos funcionais

| ID | Requisito | Módulo | Prioridade | Status hoje |
|---|---|---|---|---|
| RF-IMP-01 | Importar CSV, TXT delimitado, XLSX e XLSM | M1 | P0 | ✅ (TXT ❌) |
| RF-IMP-02 | Detectar encoding com confiança e avisar sobre caracteres suspeitos | M1 | P1 | 🟡 |
| RF-IMP-03 | Permitir sobrescrever delimitador, decimal, milhar, cabeçalho e formato de data | M1 | P0 | 🟡 (milhar e data ❌) |
| RF-IMP-04 | Prévia local opt-in com sensíveis mascarados | M1 | P1 | ❌ |
| RF-IMP-05 | Escolher quais abas importar | M1 | P2 | ❌ |
| RF-IMP-06 | Distinguir data ISO de `dd/mm/aaaa` e perguntar quando for ambíguo | M1 | **P0** | ❌ (D1) |
| RF-IMP-07 | Classificar código alfanumérico como código | M1 | **P0** | ❌ (D3) |
| RF-IMP-08 | Interpretar milhar brasileiro (`1.234`) | M1 | **P0** | ❌ (D4) |
| RF-PRO-01 | Perfilar 100% das linhas até 10 milhões | M2 | P1 | ❌ (D5) |
| RF-PRO-02 | Rotular corretamente o método de amostragem | M2 | **P0** | ❌ (D5) |
| RF-PRO-03 | Detectar máscara/padrão por coluna | M2 | P2 | ❌ |
| RF-PRO-04 | Suprimir estatísticas de colunas sensíveis (incluindo salário, nome e dados bancários) | M2 | **P0** | 🟡 (D2) |
| RF-QUA-01 | Problemas com regra, contagem, impacto e correção sugerida | M3 | P0 | 🟡 (falta impacto e correção) |
| RF-QUA-02 | Regras configuráveis | M3 | P2 | 🟡 (limiares por variável de ambiente) |
| RF-QUA-03 | Regras personalizadas (faixa, lista, regex) | M3 | P2 | ❌ |
| RF-QUA-04 | Veredito "Pode usar? Sim / Com ajustes / Não" | M3 | P1 | 🟡 (classificação existe) |
| RF-CLE-01 | Correções como operações declarativas em pipeline | M4 | P0 | ❌ |
| RF-CLE-02 | Prévia antes/depois com linhas afetadas | M4 | P0 | ❌ |
| RF-CLE-03 | Desfazer e refazer | M4 | P1 | ❌ |
| RF-CLE-04 | Exportar o pipeline como Power Query M | M4/M8 | P0 | ❌ |
| RF-CLE-05 | Exportar o arquivo limpo | M4 | P0 | ❌ |
| RF-CLE-06 | Log de transformações | M4/M9 | P0 | ❌ |
| RF-ITG-01 | Relacionamentos entre qualquer combinação CSV/XLSX | M7 | P1 | 🟡 |
| RF-ITG-02 | Cardinalidade e cobertura dos relacionamentos | M7 | P1 | 🟡 |
| RF-ITG-03 | Correspondência aproximada | M7 | P3 | ❌ |
| RF-BIA-01 | Modelo estrela sugerido | M8 | P0 | 🟡 (fato/dim pelo nome da aba) |
| RF-BIA-02 | Tabela Calendário e medidas DAX básicas | M8 | P1 | ❌ |
| RF-BIA-03 | Checklist "vai quebrar seu dashboard" | M8 | P1 | 🟡 |
| RF-BIA-04 | Blueprint de páginas e KPIs | M8 | P2 | ✅ |
| RF-REP-01 | Exportar JSON, HTML e PDF | M9 | P0 | ✅ |
| RF-REP-02 | Exportar relatório XLSX | M9 | P1 | ❌ |
| RF-REP-03 | Histórico de sessões (metadados) | M9 | P2 | ❌ |

## 2. Requisitos não funcionais

| ID | Categoria | Requisito | Verificação | Prioridade | Status hoje |
|---|---|---|---|---|---|
| RNF-PRI-01 | Privacidade | Nenhuma conexão de rede durante o uso | Teste com socket bloqueado (já existe) + varredura de imports | P0 | ✅ |
| RNF-PRI-02 | Privacidade | Nenhum valor de célula em relatório exportado ou log | Teste "canário": valores marcados no arquivo de entrada procurados nas saídas | P0 | 🟡 (o JSON expõe estatísticas de salário) |
| RNF-PRI-03 | Privacidade | Documentação de privacidade = comportamento real | Teste derivado do SECURITY.md | P0 | ❌ (D2) |
| RNF-SEG-01 | Segurança | Macros, fórmulas e links nunca executados | Testes existentes | P0 | ✅ |
| RNF-SEG-02 | Segurança | Servidor só em 127.0.0.1, com token de sessão e verificação de Host | Teste de requisição sem token → 401 | P1 | ❌ |
| RNF-SEG-03 | Segurança | Arquivo original nunca alterado | Hash SHA-256 antes/depois (teste existe) | P0 | ✅ |
| RNF-SEG-04 | Segurança | Arquivos temporários apagados ao fechar e na inicialização seguinte | Teste de ciclo de vida | P1 | n/a hoje |
| RNF-DES-01 | Desempenho | 1 milhão de linhas × 20 colunas perfilado (100%) em < 20 s | Benchmark no CI (máquina de referência) | P1 | 🟡 (7,9 s, mas só 2,5% das linhas) |
| RNF-DES-02 | Desempenho | Arquivo de 1 GB sem estourar 2 GB de RAM | Teste de memória | P2 | ❌ (tudo em memória) |
| RNF-DES-03 | Desempenho | Interface responsiva durante a análise (sem travar o servidor) | Health < 200 ms durante a análise | P1 | 🟡 (D6) |
| RNF-CON-01 | Confiabilidade | Falha numa aba ou arquivo não derruba o lote | Testes existentes | P0 | ✅ |
| RNF-CON-02 | Confiabilidade | Resultado determinístico | Mesmo arquivo → mesmo JSON (exceto ID e data) | P0 | ✅ (verificar após a migração) |
| RNF-MAN-01 | Manutenibilidade | Nenhuma função com mais de 80 linhas no domínio | ruff (PLR0915) | P1 | ❌ (`analyze_file` ~300) |
| RNF-MAN-02 | Manutenibilidade | Cobertura de testes ≥ 80% no domínio | pytest-cov no CI | P1 | ? (não medido) |
| RNF-MAN-03 | Manutenibilidade | Lint e format obrigatórios no CI | ruff | P0 | ❌ |
| RNF-USA-01 | Usabilidade | Instalar e rodar sem Python, em < 5 minutos | Teste em máquina limpa | P0 | ❌ |
| RNF-USA-02 | Usabilidade | Toda tela responde "o que está acontecendo" e "o que faço agora" | Revisão de UX | P1 | 🟡 |
| RNF-USA-03 | Acessibilidade | Contraste AA, navegação por teclado, `aria-live` no progresso | axe-core | P2 | 🟡 (`aria-live` existe) |
| RNF-POR-01 | Portabilidade | Windows 10 e 11, x64 | CI `windows-latest` + teste manual | P0 | ? |
| RNF-OBS-01 | Observabilidade | Log em arquivo rotativo, sem dados, com ID da sessão | Teste de log | P1 | 🟡 (só console) |
