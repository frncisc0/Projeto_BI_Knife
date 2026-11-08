# 07 — Estratégia de segurança, privacidade e confiabilidade

> O `SECURITY.md` da raiz continua sendo a política pública. Este documento é a **estratégia interna**: o que avaliar, o que mudar e **como provar** que as promessas são cumpridas.

## 1. Situação atual por tema (FATO)

| Tema | Hoje | Avaliação |
|---|---|---|
| Processamento 100% local | Sem clientes HTTP no código; teste com rede bloqueada; `NoAIProvider` | 🟢 Forte e verificado por teste |
| Ausência de transmissão | Nenhum CDN, telemetria ou fonte externa no frontend | 🟢 |
| Arquivos temporários | Nenhum criado pela aplicação; o multipart pode gerar spool, que é fechado | 🟢 hoje / ⚠️ vai mudar com a sessão (Parquet temporário) |
| Importação segura | Extensão por lista branca; OOXML validado (DTD/ENTITY, zip bomb, `.rels`); `openpyxl` sem VBA nem links | 🟢 Acima da média |
| Arquivos malformados | CSV com largura inconsistente rejeitado; XLSX corrompido rejeitado; falha por aba isolada | 🟢 |
| Tratamento de erros | Mensagens genéricas; só o tipo da exceção nos logs | 🟢 |
| Logs sem dados sensíveis | Testado | 🟢, mas só no console |
| Integridade do original | Teste de hash antes/depois | 🟢 |
| **Dados sensíveis no relatório** | Detecção só por cpf/cnpj/telefone/email/rg/documento | 🔴 **Abaixo do que o SECURITY.md promete (D2)** |
| Memória | Upload inteiro em `bytes` + texto decodificado + DataFrame; lote com progresso guarda tudo | 🟠 Risco com arquivos de 100 MB e lotes de 500 MB |
| Arquivos grandes | Limites e timeout entre etapas; amostra de 25 mil linhas | 🟡 Protegido, mas à custa da precisão |
| Exposição da API local | Sem verificação de Host/Origin, sem token | 🟠 Risco baixo, mas real em ambiente corporativo |

## 2. Modelo de ameaças (resumido)

| Ameaça | Vetor | Mitigação atual | Mitigação proposta |
|---|---|---|---|
| Planilha maliciosa | Macro, DDE, link externo, XXE, zip bomb | Validação OOXML + openpyxl read-only | Manter; adicionar fuzzing no CI |
| CSV malicioso | Fórmula injetada (`=HYPERLINK(...)`) que executa **quando o arquivo limpo exportado** for aberto no Excel | n/a (não há exportação de dados hoje) | **Ao exportar CSV/XLSX, neutralizar células iniciadas por `= + - @`** (CSV injection) |
| Vazamento por relatório | Relatório compartilhado contém salários e nomes | Parcial (D2) | Política de privacidade baseada em classificação de colunas + teste canário |
| Vazamento por log | Exceção do pandas inclui conteúdo da linha | Só o tipo é logado | Manter; filtro de log anti-PII como segunda camada |
| Página maliciosa no navegador | DNS rebinding, CSRF para `127.0.0.1:porta` | Nenhuma | Porta aleatória + token de sessão + `TrustedHostMiddleware` + checagem de `Origin` |
| Outro usuário da mesma máquina | Acessa a porta local | Nenhuma | Token de sessão (passado à janela pelo launcher) |
| Temporários esquecidos | Cópia de dados em `%TEMP%` após crash | n/a | Pasta própria + limpeza ao fechar **e** na inicialização seguinte; permissões só para o usuário |
| Dependência comprometida | Pacote PyPI | Versões com faixa | Lockfile com hashes (`uv lock` / `pip-tools --generate-hashes`) + `pip-audit` no CI |
| Executável adulterado | Instalador modificado | n/a | Assinatura de código (quando houver distribuição externa) + SHA-256 publicado no release |

## 3. Política de classificação de colunas (corrige D2)

| Nível | Exemplos (nome ou padrão) | O que pode aparecer |
|---|---|---|
| **Identificador pessoal direto** | cpf, cnpj de pessoa, rg, cnh, passaporte, pis, título, e-mail, telefone, celular, nome, nome_completo, endereço, cep + número | Só contagens (nulos, únicos); **nenhuma** estatística nem prévia sem máscara |
| **Dado pessoal sensível ou financeiro** | salário, remuneração, proventos, bônus, conta, agência, pix, cartão, data_nascimento, idade, sexo, raça, religião, saúde, cid | Contagens; **estatísticas ocultas por padrão** (o usuário pode habilitar localmente, com aviso, mas elas **nunca** entram no relatório exportado) |
| **Quase-identificador** | matrícula, cargo + lotação, cidade + data | Estatísticas permitidas; aviso de reidentificação em combinações |
| **Não sensível** | demais | Tudo, exceto valores no relatório (regra geral) |

Detecção por: (1) nome normalizado, sem acentos e com tokens; (2) padrão de conteúdo (máscara de CPF/CNPJ com dígito verificador, e-mail, telefone BR); (3) **o usuário pode marcar ou desmarcar** uma coluna como sensível, e a escolha fica registrada no relatório.

## 4. Mecanismos de verificação das premissas

Promessas de privacidade só valem se forem **testáveis**. Proposta:

| Premissa | Mecanismo de verificação | Onde roda |
|---|---|---|
| "Nenhum dado sai do computador" | (a) teste com `socket` bloqueado (existe); (b) varredura estática que proíbe `requests`, `httpx`, `urllib.request` e `socket.connect` em `src/` (existe, ampliar); (c) **modo auditoria**: o app registra toda tentativa de conexão e mostra "0 conexões" na tela Configurações | CI + produto |
| "Relatórios não contêm valores" | **Teste canário:** gerar arquivos com valores únicos e rastreáveis (`CANARIO_7f3a…`) e procurá-los em JSON, HTML, PDF (texto extraído), XLSX e logs | CI |
| "SECURITY.md é verdade" | Cada afirmação do SECURITY.md vira um teste nomeado (`test_security_claim_salary_suppressed`) | CI |
| "Original intocado" | Hash SHA-256 antes e depois (existe) + abertura do arquivo só em modo `rb` | CI |
| "Macros nunca executam" | Arquivo de teste com macro de efeito observável (escrever arquivo); verificar que o arquivo não existe depois | CI (Windows) |
| "Temporários são apagados" | Teste de ciclo de vida: abrir sessão → matar o processo → reiniciar → pasta vazia | CI |
| "Memória controlada" | Benchmark com arquivo de 1 GB e limite de RAM (`ulimit` / Job Object) | CI noturno |

## 5. Arquivos grandes e memória

1. Receber o upload em **stream para arquivo temporário** (não em `bytes`).
2. Validar por amostra e streaming (sem decodificar o arquivo inteiro em memória).
3. Converter para Parquet via DuckDB (*out-of-core*) e perfilar com SQL.
4. Limites continuam existindo, mas como **proteção**, não como **mecanismo de amostragem**: arquivo de 5 GB → aviso + amostra aleatória documentada.
5. O lote processa um arquivo por vez e libera a memória entre eles.

## 6. Mudanças propostas no `SECURITY.md` (precisam de autorização)
- Corrigir a lista de colunas sensíveis para refletir a política acima (ou, até a correção do código, **remover a promessa** que não é cumprida).
- Documentar como executar com segurança (`127.0.0.1`, que hoje é citado mas não está no README).
- Acrescentar a seção "Como verificar estas garantias" apontando para os testes.
