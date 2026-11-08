# 14 — Avaliação estratégica (crítica, sem concordância automática)

## 1. O BI Knife tem potencial para se tornar um produto profissional?

**Sim, como produto de nicho; não como "canivete suíço" genérico.** A base técnica é melhor que a média para um projeto individual (validação, privacidade testada, heurísticas explicáveis). O risco não é técnico, é de **posicionamento**.

O concorrente mais perigoso não é outra startup: é o **próprio Power Query**. Dentro do Power BI Desktop e do Excel, ele já oferece *Column quality*, *Column distribution* e *Column profile*, além de todas as transformações, de graça e na ferramenta que o público já usa. Outras alternativas: ydata-profiling e Data Wrangler (para quem programa), OpenRefine (limpeza), Tableau Prep e Alteryx (pagos e corporativos).

O BI Knife só ganha onde o Power Query é fraco:
- **Não explica nada:** mostra "3% de erro", mas não diz o que isso faz com o dashboard nem o que fazer.
- **Perfila só as primeiras 1.000 linhas por padrão.**
- **Não olha o modelo inteiro:** não avalia relacionamentos, chaves órfãs ou N:N **antes** de você montar o modelo.
- **Não entende o Brasil por padrão:** locale, CPF/CNPJ.
- **Não gera documentação** da qualidade para entregar ao gestor ou ao cliente.

## 2. Quais funcionalidades realmente diferenciariam?

| Diferencia de verdade | Não diferencia (o Power Query já faz) |
|---|---|
| **Diagnóstico do modelo inteiro** antes de importar (chaves, órfãos, N:N, estrela sugerida) | Remover duplicados, trocar tipo, trim |
| **Explicação de impacto** ("isso vai fazer o total por cliente ficar errado") | Merge, append, agrupar |
| **Script M gerado** a partir do diagnóstico (a ponte para a ferramenta do usuário) | Colunas calculadas |
| Relatório de qualidade **entregável** (PDF/XLSX) com hash e configuração | Editor visual de transformação |
| Privacidade **comprovável** para dados de RH e finanças | — |
| Brasil nativo: datas, números, documentos, cp1252 | — |

**Questionamento direto do briefing:** os módulos **M4 (limpeza completa)** e **M5 (transformação)**, do jeito que foram propostos, fariam o BI Knife competir de frente com o Power Query e perder. A recomendação é inverter: **o BI Knife diagnostica e escreve o M; o Power Query executa.** Assim o produto complementa a ferramenta do usuário em vez de tentar substituí-la. O arquivo limpo exportado fica como conveniência, não como centro.

## 3. Essencial para o MVP
1. Diagnóstico **correto** (D1–D6): sem isso, nada mais importa.
2. Perfil sobre 100% dos dados.
3. Privacidade cumprida e testada.
4. Problema → correção sugerida → **script M**.
5. Modelo estrela + checklist do que vai quebrar o dashboard.
6. Relatório entregável.
7. Instalador.

## 4. Adiar
- Transformação completa (M5): talvez nunca, se o M gerado resolver.
- Fuzzy matching e conflitos: valor real, mas custo alto; pós-MVP.
- Regras personalizadas com editor: P2.
- **IA:** qualquer IA. Não há problema do MVP que a estatística não resolva melhor (determinística, explicável, rápida, privada). Ver ADR-07.
- Conectores de banco e SharePoint: reabrem toda a discussão de segurança e credenciais.
- Gerar `.pbix`.

## 5. Tecnologias que podem trazer problemas de manutenção
| Tecnologia | Risco | Mitigação |
|---|---|---|
| **pandas `engine="python"` + `format="mixed"`** | Lento; comportamento de parsing de datas muda entre versões (a origem do D1) | Migrar perfil e parsing para DuckDB + formato explícito |
| **Faixas de versão amplas** (`pandas>=2.2,<4.0`) | O pandas 3.0 muda o tipo de string padrão (pyarrow) e pode quebrar heurísticas silenciosamente | Lockfile com versões exatas; atualizar de forma deliberada |
| **Frontend com templates `innerHTML`** | Cresce mal; um escape esquecido vira XSS | Módulos agora; framework só na tela de transformação |
| **ReportLab** | Layout de PDF trabalhoso de manter | Aceitável; alternativa: gerar o PDF a partir do HTML (WeasyPrint) |
| **pywebview / WebView2** | Depende do runtime do Edge (presente no Windows 10/11 atualizados) | Fallback para o navegador padrão |
| **Electron, Tauri, React** (se fossem adotados) | Segunda toolchain para um desenvolvedor solo | **Não adotar** |

## 6. Maiores riscos técnicos
1. **Diagnóstico errado com aparência de certo** (como D1 e D4). É o risco nº 1 porque destrói a confiança, que é o produto. → Conjunto-ouro.
2. **Divergência entre o resultado do DuckDB e o M gerado.** O usuário aplica o M e obtém outro resultado. → Validação de equivalência por operação.
3. **Privacidade prometida e não cumprida** (já aconteceu: D2). → Teste por afirmação do SECURITY.md.
4. **Antivírus corporativo bloquear o executável.** → onedir, hash, assinatura.
5. **Escopo:** tentar ser canivete suíço com um desenvolvedor em meio período. → Este documento.

## 7. Como garantir desempenho com arquivos grandes
- DuckDB *out-of-core* (dados em Parquet temporário, não em RAM).
- Upload em stream para disco; validação em streaming.
- Perfil em **uma passada SQL por tabela** (hoje o CSV é lido 4 vezes).
- Amostra só acima de um limite alto (≥ 10 milhões de linhas), **aleatória** e declarada.
- Leitura de XLSX: openpyxl read-only é o gargalo; avaliar `python-calamine` (Rust), muito mais rápido.
- Benchmarks no CI noturno com metas (doc 11).

## 8. Como evoluir sem comprometer a estabilidade
- Conjunto-ouro + regressão: todo bug vira teste.
- Contratos versionados (`schema_version` no JSON e no pipeline).
- Strangler: código novo na estrutura nova, o antigo migra aos poucos, sempre verde.
- *Feature flags* em `config.toml` para funcionalidades experimentais.
- Releases pequenos e frequentes (SemVer) com CHANGELOG honesto.

## 9. Como preparar para empresas
1. Instalação **sem admin** e silenciosa.
2. **Ficha de segurança de 1 página** para a TI (o que faz, o que não faz, onde grava, como verificar).
3. Assinatura de código.
4. Configuração padronizável (`config.toml`).
5. Comprovação pública de privacidade (testes abertos no GitHub; o código aberto é um argumento de venda aqui).
6. Política de suporte e versões.

> **Observação honesta:** muitas empresas só permitem software homologado, e um executável de desenvolvedor individual dificilmente passa sem patrocínio interno. O caminho realista para chegar a empresas é **um analista usar, provar valor e pedir a homologação**. Isso reforça o foco na persona "analista de BI".

## 10. Os próximos passos mais inteligentes
1. **Corrigir D1–D5 agora (Fase 0.5).** É pouco esforço (~25 h) e muito ganho de credibilidade.
2. **Escrever o README "como rodar"** e trocar o estilo das mensagens de commit. Quem avalia o seu GitHub vai olhar isso primeiro.
3. **Validar a tese do script M antes de construir a Fase 3:** escrever à mão o M para 3 problemas reais e mostrar a 3 analistas de BI. Se eles disserem "eu usaria", siga. Se não, ajuste.
4. **Fase 1 (fundação)**, sem pular para funcionalidades novas.

## 11. Leitura estratégica adicional: produto e portfólio
Hoje o BI Knife tem dois papéis, e vale assumir os dois:
- **Como portfólio**, ele já é forte. Mostra raciocínio de analista (qualidade, modelo, explicação), engenharia (testes, segurança) e produto (personas, roadmap). Os documentos desta pasta também contam como evidência de maturidade.
- **Como produto**, o caminho de menor risco é **open source para analistas de BI brasileiros**: distribuição pelo GitHub, comunidade de Power BI no LinkedIn e feedback real. A monetização (se houver) vem depois, com versão corporativa (configuração central, suporte, assinatura).

Os dois papéis apontam para a mesma prioridade: **um núcleo pequeno, correto e muito bem explicado**.
