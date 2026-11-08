# 🔪 BI Swiss Knife

**BI Swiss Knife** é uma ferramenta local para análise, compreensão e preparação de dados para projetos de Business Intelligence.

A proposta é simples:

> **Pensar como um analista de dados, mas explicar como um professor.**

O sistema recebe arquivos de dados, analisa sua estrutura e qualidade, identifica possíveis papéis dos campos, sugere indicadores e análises e apresenta os resultados de forma clara, objetiva e didática.

O projeto foi desenvolvido com foco em **processamento local, privacidade e segurança dos dados**.

---

## ⚙️ Como executar

Requisitos: Windows 10/11 (ou Linux/macOS) e **Python 3.11+**.

```powershell
# na pasta do projeto (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra **http://127.0.0.1:8000** no navegador.

> ⚠️ Use sempre `--host 127.0.0.1`. A API não tem autenticação e não deve ficar acessível na rede.

### Testes

```powershell
python -m pip install -r requirements-dev.txt
ruff check app tests          # lint (regras em pyproject.toml)
python -m pytest --cov        # testes + cobertura
node --test tests/frontend/report_names.test.mjs
```

A integração contínua (`.github/workflows/ci.yml`) roda lint, testes em Windows e Linux com Python 3.11 e 3.12, testes do frontend e auditoria de dependências a cada pull request.

### Documentação do projeto

Visão do produto, arquitetura, roadmap por versões e auditoria técnica: **[BI_KNIFE_MASTER_PLAN.md](BI_KNIFE_MASTER_PLAN.md)**.

---

## 🎯 Objetivo

Muitas vezes, antes de criar um dashboard ou iniciar uma análise, é necessário descobrir:

- Que tipo de dados existem?
- Quantos registros existem?
- Quais campos são importantes?
- Existem valores ausentes?
- Quais campos podem ser usados como indicadores?
- Existem possíveis identificadores?
- Existem possíveis relacionamentos?
- O que a estrutura da tabela parece representar?
- Que análises podem ser interessantes?
- Quais cuidados devem ser tomados antes de usar os dados?

O BI Swiss Knife busca responder essas perguntas automaticamente.

A ideia não é apenas apresentar números.

A ferramenta procura **entender a estrutura dos dados e explicar o que encontrou em linguagem simples**.

---

# 🧠 Filosofia

O BI Swiss Knife segue uma regra central:

> **A complexidade fica no motor; a simplicidade fica na explicação.**

A análise interna pode utilizar conceitos de:

- análise exploratória;
- qualidade de dados;
- estatística;
- modelagem;
- análise semântica;
- identificação de padrões;
- relacionamentos entre tabelas;
- Business Intelligence.

Mas o usuário não precisa dominar esses conceitos para entender o relatório.

Por exemplo, em vez de simplesmente apresentar:

> `Cardinality: high`

o sistema procura explicar:

> **Este campo possui muitos valores diferentes e pode ser útil para diferenciar ou detalhar os registros.**

Quando um conceito técnico é importante, ele pode ser apresentado nos detalhes técnicos com uma explicação correspondente.

---

# 🚀 Principais funcionalidades

## 📂 Análise de arquivos

O BI Swiss Knife permite analisar arquivos de dados localmente.

Formatos atualmente suportados:

- `.CSV`
- `.XLSX`

### CSV

O sistema possui suporte para diferentes situações comuns:

- UTF-8;
- UTF-8 BOM;
- Windows-1252 / CP1252;
- Latin-1;
- separador `,`;
- separador `;`;
- TAB;
- arquivos com cabeçalho;
- arquivos sem cabeçalho;
- campos entre aspas;
- delimitadores dentro de campos entre aspas;
- células vazias;
- valores mistos;
- identificadores com zeros à esquerda.

O sistema também procura apresentar mensagens mais claras quando encontra problemas de estrutura no arquivo.

---

# 🔎 Análise estrutural

Uma das principais características do BI Swiss Knife é a tentativa de compreender a estrutura da tabela antes de tirar conclusões sobre o negócio.

O sistema pode identificar ou levantar hipóteses sobre:

- campos categóricos;
- campos descritivos;
- medidas;
- datas;
- identificadores;
- possíveis chaves;
- possíveis relacionamentos;
- cardinalidade;
- valores ausentes;
- padrões estruturais;
- possíveis tipos de tabela;
- possíveis características da granularidade.

### Importante

Essas classificações são **inferências**.

O BI Swiss Knife não assume que uma hipótese estrutural seja uma regra oficial do negócio.

Por exemplo:

> **Possível identificador**

é diferente de:

> **Chave primária confirmada**

Da mesma forma:

> **A tabela parece conter registros individuais**

não significa que o sistema conhece exatamente o significado empresarial de cada linha.

---

# 🧩 Compreensão estrutural da tabela

O sistema cria um perfil estrutural da tabela contendo informações como:

- quantidade de registros;
- quantidade de colunas;
- possíveis características da tabela;
- hipótese sobre o que uma linha representa;
- possíveis medidas;
- possíveis dimensões;
- possíveis identificadores;
- possíveis chaves;
- possíveis relacionamentos;
- evidências utilizadas;
- nível de confiança;
- limitações da análise.

Cada conclusão importante deve ser acompanhada, quando aplicável, por:

**Conclusão → Confiança → Evidências → Limitações**

Isso permite que o usuário entenda não apenas **o que o sistema concluiu**, mas também **por que chegou àquela conclusão**.

---

# 📊 Qualidade dos dados

O BI Swiss Knife realiza verificações relacionadas à qualidade dos dados.

Entre elas:

- completude;
- consistência;
- validade;
- unicidade;
- valores ausentes;
- registros duplicados;
- possíveis anomalias estatísticas;
- padrões inconsistentes.

O resultado é apresentado através de uma pontuação geral e de indicadores específicos.

### Importante

Uma anomalia estatística não significa necessariamente que exista um erro.

Por exemplo:

> "Foi identificado um valor fora do padrão estatístico."

não significa:

> "Este valor está errado."

O sistema trata esse tipo de situação como um **sinal para investigação**.

---

# 🧠 Modelo semântico

O BI Swiss Knife possui uma camada semântica que procura identificar o papel dos campos dentro da análise.

Exemplos:

### Categoria

Campo que pode ser utilizado para agrupar informações.

Exemplos possíveis:

- empresa;
- região;
- produto;
- categoria.

### Medida

Campo numérico que pode ser utilizado para criar indicadores ou agregações.

Exemplos possíveis:

- quantidade;
- valor;
- custo;
- volume.

### Campo descritivo

Campo utilizado principalmente para descrever um registro.

### Data

Campo que pode permitir análises temporais.

### Identificador

Campo que pode ajudar a identificar registros.

As classificações possuem níveis de confiança e evidências.

---

# 💡 Insights e KPIs

A partir da estrutura encontrada, o BI Swiss Knife pode sugerir:

- KPIs;
- perguntas analíticas;
- comparações;
- análises de distribuição;
- possíveis pontos de atenção;
- possíveis anomalias.

As sugestões são baseadas nas evidências encontradas nos dados.

O sistema não deve inventar uma regra de negócio que não esteja presente ou sustentada pelos dados.

---

# 📈 Blueprint de Dashboard

O BI Swiss Knife também pode gerar uma proposta inicial de dashboard.

Essa proposta pode incluir:

- páginas recomendadas;
- indicadores;
- medidas;
- dimensões;
- filtros;
- visuais sugeridos;
- perguntas de negócio;
- prioridades.

O objetivo é ajudar a responder:

> **"Se eu fosse transformar esses dados em um dashboard, por onde eu poderia começar?"**

O blueprint é uma **proposta baseada na estrutura encontrada**.

Ele não substitui a validação das regras de negócio.

---

# 📄 Relatórios

Os resultados podem ser exportados em diferentes formatos.

Entre eles:

- PDF;
- HTML;
- JSON;
- CSV.

Os nomes dos arquivos são contextualizados.

Exemplo:

```text
conjunto-dados_2026-10-14_23-20-18_BI-Swiss-Knife.pdf
