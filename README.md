<div align="center">

# 🔍 DocAudit

**Sistema de Análise e Auditoria de Documentos Fiscais com IA**  
**AI-Powered Fiscal Document Analysis and Audit System**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-316192?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

---

🇧🇷 [Português](#-português) &nbsp;|&nbsp; 🇺🇸 [English](#-english)

</div>

---

# 🇧🇷 Português

## Visão Geral

**DocAudit** é uma aplicação web interna para **análise automatizada de documentos fiscais e financeiros**. O sistema recebe arquivos `.txt` via upload, extrai campos estruturados com auxílio de IA (via [OpenRouter](https://openrouter.ai)), detecta anomalias automaticamente e apresenta os resultados em uma interface tabular com flags visuais — tudo rastreável por um log de auditoria exportável.

### O problema que resolve

Processos manuais de conferência de notas fiscais, aprovações e pagamentos são lentos, propensos a erros humanos e difíceis de auditar. O DocAudit automatiza essa conferência, detecta inconsistências em segundos e mantém um rastro auditável de todas as análises realizadas.

### Público-alvo

Equipes financeiras, de compliance e auditoria interna de pequenas e médias empresas.

---

## ✨ Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| 📤 **Upload de Arquivos** | Drag-and-drop ou seleção manual de até 20 arquivos `.txt` por vez, com barra de progresso individual |
| 🤖 **Extração via IA** | Campos extraídos automaticamente (NF, CNPJ, datas, valor, aprovador) via OpenRouter |
| 🚨 **Detecção de Anomalias** | 8 regras de negócio com severidade CRÍTICA, ALTA e MÉDIA |
| 📊 **Dashboard de Resultados** | Tabela filtrável, pesquisável e com badges coloridos por severidade de flag |
| 📁 **Exportação** | CSV (UTF-8 com BOM) e Excel (.xlsx) com formatação e aba de auditoria |
| 📋 **Log de Auditoria** | 100% das ações registradas com timestamp, IP, usuário e payload |
| ⚙️ **Configurações** | Gerenciamento de aprovadores autorizados e fornecedores cadastrados |

---

## 🚩 Regras de Detecção de Anomalias

| Código | Anomalia | Severidade | Lógica |
|--------|----------|------------|--------|
| `DUP_NF` | NF duplicada | 🔴 CRÍTICA | Mesmo número de NF já existe para o mesmo CNPJ emitente |
| `CNPJ_DIV` | CNPJ divergente | 🔴 CRÍTICA | CNPJ do emitente não bate com o cadastro interno do fornecedor |
| `DATA_INV` | Data inválida | 🟡 ALTA | Data de emissão da NF é posterior à data de pagamento |
| `APROV_NR` | Aprovador não reconhecido | 🟡 ALTA | Nome do aprovador não consta na lista de aprovadores autorizados |
| `VALOR_ZERO` | Valor zerado | 🟡 ALTA | Valor total da NF é zero ou negativo |
| `NF_FUTURA` | NF com data futura | 🟠 MÉDIA | Data de emissão da NF é posterior à data atual |
| `CNPJ_INVALIDO` | CNPJ inválido | 🟠 MÉDIA | CNPJ não passa na validação de dígitos verificadores |
| `CAMPO_VAZIO` | Campo obrigatório ausente | 🟠 MÉDIA | Campos críticos não foram extraídos (NF, CNPJ, valor, data) |

---

## 🛠️ Stack Tecnológica

### Backend
- **Python 3.11+** — linguagem principal
- **FastAPI** — framework REST assíncrono
- **SQLAlchemy 2.0** — ORM
- **Alembic** — migrations de banco de dados
- **PostgreSQL 16** — banco de dados relacional
- **Celery + Redis** — processamento assíncrono (fila de tarefas)
- **OpenRouter API** — integração com modelos de IA
- **openpyxl / pandas** — geração de relatórios
- **Pydantic v2** — validação e serialização de dados
- **httpx** — cliente HTTP assíncrono

### Frontend
- **HTML5 + CSS3 + JavaScript puro** — sem frameworks, responsivo e minimalista

### Infraestrutura
- **Docker + Docker Compose** — orquestração local
- **`.env`** — gerenciamento de segredos

---

## 📁 Estrutura do Projeto

```
docaudit/
├── backend/
│   ├── app/
│   │   ├── main.py              # Entrypoint FastAPI
│   │   ├── config.py            # Configurações via Pydantic Settings
│   │   ├── database.py          # Configuração do SQLAlchemy
│   │   ├── models/              # Modelos SQLAlchemy
│   │   │   ├── upload.py
│   │   │   ├── documento.py
│   │   │   ├── anomalia.py
│   │   │   └── audit_log.py
│   │   ├── schemas/             # Schemas Pydantic (request/response)
│   │   │   ├── upload.py
│   │   │   ├── documento.py
│   │   │   └── anomalia.py
│   │   ├── routers/             # Endpoints da API
│   │   │   ├── uploads.py
│   │   │   ├── documentos.py
│   │   │   ├── anomalias.py
│   │   │   └── exportar.py
│   │   ├── services/            # Lógica de negócio
│   │   │   ├── ia_service.py        # Integração OpenRouter
│   │   │   ├── anomalia_service.py  # Motor de regras de anomalia
│   │   │   ├── export_service.py    # Geração de CSV e Excel
│   │   │   └── audit_service.py     # Log de auditoria
│   │   └── workers/
│   │       └── tasks.py             # Tarefas Celery (processamento assíncrono)
│   ├── alembic/                 # Migrations do banco de dados
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html               # Dashboard principal
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js               # Inicialização e estado global
│       ├── upload.js            # Lógica de upload e drag-and-drop
│       ├── tabela.js            # Renderização e filtros da tabela
│       └── api.js               # Comunicação com o backend
├── tests/                       # Testes backend (pytest)
├── docker-compose.yml
├── .env.example
└── PRD.md                       # Documento de requisitos do produto
```

---

## 🚀 Como Rodar Localmente

### Pré-requisitos

- [Docker](https://www.docker.com/get-started) e Docker Compose
- [Git](https://git-scm.com/)
- Chave de API do [OpenRouter](https://openrouter.ai/) (gratuita)

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/docaudit.git
cd docaudit
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
```

Edite o arquivo `.env` e preencha:

```env
OPENROUTER_API_KEY=sk-or-v1-sua-chave-aqui
OPENROUTER_MODEL=minimax/minimax-m2.5:free   # ou outro modelo disponível
OPENROUTER_REFERER=http://localhost:8000     # URL da sua aplicação
```

### 3. Suba os serviços com Docker Compose

```bash
docker compose up --build
```

Isso irá iniciar:
- **FastAPI** em `http://localhost:8000`
- **PostgreSQL** em `localhost:5432`
- **Redis** em `localhost:6379`

### 4. Aplique as migrations do banco de dados

```bash
docker compose exec web alembic upgrade head
```

### 5. Acesse a aplicação

| Serviço | URL |
|---------|-----|
| Frontend (Dashboard) | `http://localhost:8000` |
| API Docs (Swagger) | `http://localhost:8000/docs` |
| API Docs (ReDoc) | `http://localhost:8000/redoc` |
| Health Check | `http://localhost:8000/api/v1/health` |

---

## 📖 Documentação da API (Swagger)

A API do DocAudit é totalmente documentada via **Swagger/OpenAPI**. Você pode acessar a documentação interativa para testar os endpoints diretamente pelo navegador:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs) — Interface interativa (recomendado).
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc) — Documentação estática e detalhada.

---

## 🌐 Endpoints da API

### Uploads
| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/uploads` | Envia um ou mais arquivos `.txt` |
| `GET` | `/api/v1/uploads` | Lista todos os uploads (paginado) |
| `GET` | `/api/v1/uploads/{id}` | Detalhes de um upload específico |

### Documentos
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/documentos` | Lista documentos analisados (filtros, paginação) |
| `GET` | `/api/v1/documentos/{id}` | Detalhes completos de um documento |
| `PATCH` | `/api/v1/documentos/{id}` | Revisão manual de campos extraídos |

### Anomalias
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/anomalias` | Lista anomalias (filtro por severidade/status) |
| `PATCH` | `/api/v1/anomalias/{id}/resolver` | Marca uma anomalia como resolvida |

### Exportação
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/exportar/csv` | Exporta resultados em CSV |
| `GET` | `/api/v1/exportar/excel` | Exporta resultados em Excel (.xlsx) |
| `GET` | `/api/v1/exportar/log` | Exporta o log de auditoria |

### Configuração
| Método | Rota | Descrição |
|--------|------|-----------|
| `GET/POST` | `/api/v1/aprovadores` | Gerencia aprovadores autorizados |
| `GET/POST` | `/api/v1/fornecedores` | Gerencia fornecedores (CNPJ) |
| `GET` | `/api/v1/health` | Status da aplicação e dependências |

---

## 🔄 Fluxo de Processamento

```
Usuário faz upload do TXT
        ↓
FastAPI valida (extensão, tamanho, conteúdo)
        ↓
Salva arquivo + registra no banco (status: pendente)
        ↓
Enfileira tarefa no Celery via Redis
        ↓
Worker Celery processa:
  1. Lê conteúdo do arquivo
  2. Monta prompt → chama OpenRouter API
  3. Faz parse do JSON retornado pela IA
  4. Salva campos extraídos no banco
  5. Executa as 8 regras de anomalia
  6. Salva flags geradas
  7. Atualiza status do documento
  8. Registra evento no audit_log
        ↓
Frontend consulta status via polling (GET /documentos)
        ↓
Exibe resultado na tabela com flags visuais
```

---

## 🧪 Testes

```bash
# Rodar todos os testes
pytest

# Com verbose e cobertura
pytest -v --tb=short

# Rodar um arquivo específico
pytest tests/test_anomalia_service.py
```

Os testes ficam em `tests/` e seguem a convenção `test_<módulo>.py`.

---

## ⚙️ Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATABASE_URL` | String de conexão do banco de dados | `postgresql+psycopg://...` |
| `REDIS_URL` | URL do Redis | `redis://redis:6379/0` |
| `OPENROUTER_API_KEY` | Chave da API OpenRouter | *(obrigatório)* |
| `OPENROUTER_MODEL` | Modelo de IA a utilizar | `minimax/minimax-m2.5:free` |
| `OPENROUTER_REFERER` | URL de referência para o OpenRouter | — |
| `OPENROUTER_TITLE` | Título da aplicação no OpenRouter | `DocAudit` |
| `APP_NAME` | Nome da aplicação | `DocAudit` |
| `APP_VERSION` | Versão da aplicação | `0.1.0` |
| `POSTGRES_DB` | Nome do banco (Docker) | `docaudit` |
| `POSTGRES_USER` | Usuário do banco (Docker) | `docaudit` |
| `POSTGRES_PASSWORD` | Senha do banco (Docker) | `docaudit` |

> ⚠️ **Nunca commite o arquivo `.env` com segredos reais.** Use sempre o `.env.example` como template.

---

## 🗺️ Roadmap

### ✅ Fase 1 — MVP
- [x] Estrutura FastAPI + PostgreSQL + Docker
- [x] Modelos de banco e migrations (Alembic)
- [x] Endpoint de upload de arquivos TXT
- [x] Integração com OpenRouter (extração de campos)
- [x] Motor de detecção de anomalias
- [x] API REST com endpoints principais
- [x] Frontend: upload + tabela + flags de anomalia
- [x] Exportação em CSV

### 🚧 Fase 2 — Consolidação
- [ ] Processamento assíncrono com Celery + Redis
- [ ] Painel de detalhes (sidebar) ao clicar em um documento
- [ ] Exportação em Excel com formatação
- [ ] Log de auditoria completo e exportável
- [ ] Tela de configuração de aprovadores e fornecedores

### 🔮 Fase 3 — Melhorias
- [ ] Autenticação com JWT
- [ ] Suporte a PDF e XML de NF-e
- [ ] Dashboard com gráficos de tendência de anomalias
- [ ] Webhook / notificação por e-mail em anomalias críticas
- [ ] API de bulk re-análise de documentos antigos

---

## 🤝 Contribuindo

1. Faça um fork do repositório
2. Crie uma branch: `git checkout -b feature/minha-feature`
3. Commit com mensagens imperativas: `Add upload router`, `Fix CNPJ validator`
4. Abra um Pull Request descrevendo:
   - O que foi alterado e por quê
   - Link para a seção do PRD relacionada
   - Evidência de testes (`pytest`, screenshots ou check manual da API)
   - Notas sobre mudanças de schema ou migrations

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.

---

<br><br>

---

# 🇺🇸 English

## Overview

**DocAudit** is an internal web application for **automated analysis of fiscal and financial documents**. The system receives `.txt` files via upload, extracts structured fields using AI (via [OpenRouter](https://openrouter.ai)), automatically detects anomalies, and presents results in a tabular interface with visual flags — all traceable through an exportable audit log.

### The problem it solves

Manual processes for reviewing invoices, approvals, and payments are slow, error-prone, and hard to audit. DocAudit automates this review, detects inconsistencies in seconds, and maintains an auditable trail of every analysis performed.

### Target audience

Finance, compliance, and internal audit teams at small and medium-sized businesses.

---

## ✨ Features

| Module | Description |
|--------|-------------|
| 📤 **File Upload** | Drag-and-drop or manual selection of up to 20 `.txt` files at a time, with per-file progress bars |
| 🤖 **AI Extraction** | Fields extracted automatically (invoice number, CNPJ, dates, amount, approver) via OpenRouter |
| 🚨 **Anomaly Detection** | 8 business rules with CRITICAL, HIGH, and MEDIUM severity levels |
| 📊 **Results Dashboard** | Filterable, searchable table with colored severity badges |
| 📁 **Export** | CSV (UTF-8 with BOM) and Excel (.xlsx) with formatting and a dedicated audit tab |
| 📋 **Audit Log** | 100% of actions recorded with timestamp, IP, user, and payload |
| ⚙️ **Settings** | Management of authorized approvers and registered suppliers |

---

## 🚩 Anomaly Detection Rules

| Code | Anomaly | Severity | Logic |
|------|---------|----------|-------|
| `DUP_NF` | Duplicate invoice | 🔴 CRITICAL | Same invoice number already exists for the same issuer CNPJ |
| `CNPJ_DIV` | Divergent CNPJ | 🔴 CRITICAL | Issuer CNPJ does not match the internal supplier registry |
| `DATA_INV` | Invalid date | 🟡 HIGH | Invoice issue date is later than the payment date |
| `APROV_NR` | Unrecognized approver | 🟡 HIGH | Approver name is not in the authorized approvers list |
| `VALOR_ZERO` | Zero value | 🟡 HIGH | Total invoice value is zero or negative |
| `NF_FUTURA` | Future-dated invoice | 🟠 MEDIUM | Invoice issue date is later than today |
| `CNPJ_INVALIDO` | Invalid CNPJ | 🟠 MEDIUM | CNPJ fails check-digit validation |
| `CAMPO_VAZIO` | Missing required field | 🟠 MEDIUM | Critical fields were not extracted (NF, CNPJ, value, date) |

---

## 🛠️ Technology Stack

### Backend
- **Python 3.11+** — primary language
- **FastAPI** — async REST framework
- **SQLAlchemy 2.0** — ORM
- **Alembic** — database migrations
- **PostgreSQL 16** — relational database
- **Celery + Redis** — async task queue
- **OpenRouter API** — AI model integration
- **openpyxl / pandas** — report generation
- **Pydantic v2** — data validation and serialization
- **httpx** — async HTTP client

### Frontend
- **HTML5 + CSS3 + Vanilla JavaScript** — no frameworks, responsive and minimalist

### Infrastructure
- **Docker + Docker Compose** — local orchestration
- **`.env`** — secrets management

---

## 📁 Project Structure

```
docaudit/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # Settings via Pydantic Settings
│   │   ├── database.py          # SQLAlchemy configuration
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── upload.py
│   │   │   ├── documento.py
│   │   │   ├── anomalia.py
│   │   │   └── audit_log.py
│   │   ├── schemas/             # Pydantic schemas (request/response)
│   │   │   ├── upload.py
│   │   │   ├── documento.py
│   │   │   └── anomalia.py
│   │   ├── routers/             # API endpoints
│   │   │   ├── uploads.py
│   │   │   ├── documentos.py
│   │   │   ├── anomalias.py
│   │   │   └── exportar.py
│   │   ├── services/            # Business logic
│   │   │   ├── ia_service.py        # OpenRouter integration
│   │   │   ├── anomalia_service.py  # Anomaly rules engine
│   │   │   ├── export_service.py    # CSV and Excel generation
│   │   │   └── audit_service.py     # Audit log
│   │   └── workers/
│   │       └── tasks.py             # Celery tasks (async processing)
│   ├── alembic/                 # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html               # Main dashboard
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js               # Initialization and global state
│       ├── upload.js            # Upload and drag-and-drop logic
│       ├── tabela.js            # Table rendering and filters
│       └── api.js               # Backend communication
├── tests/                       # Backend tests (pytest)
├── docker-compose.yml
├── .env.example
└── PRD.md                       # Product Requirements Document
```

---

## 🚀 Getting Started

### Prerequisites

- [Docker](https://www.docker.com/get-started) and Docker Compose
- [Git](https://git-scm.com/)
- An [OpenRouter](https://openrouter.ai/) API key (free tier available)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/docaudit.git
cd docaudit
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=minimax/minimax-m2.5:free   # or another available model
OPENROUTER_REFERER=http://localhost:8000     # your application URL
```

### 3. Start services with Docker Compose

```bash
docker compose up --build
```

This will start:
- **FastAPI** at `http://localhost:8000`
- **PostgreSQL** at `localhost:5432`
- **Redis** at `localhost:6379`

### 4. Apply database migrations

```bash
docker compose exec web alembic upgrade head
```

### 5. Access the application

| Service | URL |
|---------|-----|
| Frontend (Dashboard) | `http://localhost:8000` |
| API Docs (Swagger UI) | `http://localhost:8000/docs` |
| API Docs (ReDoc) | `http://localhost:8000/redoc` |
| Health Check | `http://localhost:8000/api/v1/health` |

---

## 📖 API Documentation (Swagger)

DocAudit's API is fully documented via **Swagger/OpenAPI**. You can access the interactive documentation to test endpoints directly through your browser:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs) — Interactive interface (recommended).
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc) — Detailed static documentation.

---

## 🌐 API Endpoints

### Uploads
| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/api/v1/uploads` | Upload one or more `.txt` files |
| `GET` | `/api/v1/uploads` | List all uploads (paginated) |
| `GET` | `/api/v1/uploads/{id}` | Details of a specific upload |

### Documents
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/v1/documentos` | List analyzed documents (filters, pagination) |
| `GET` | `/api/v1/documentos/{id}` | Full details of a document |
| `PATCH` | `/api/v1/documentos/{id}` | Manually review extracted fields |

### Anomalies
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/v1/anomalias` | List anomalies (filter by severity/status) |
| `PATCH` | `/api/v1/anomalias/{id}/resolver` | Mark an anomaly as resolved |

### Export
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/v1/exportar/csv` | Export results as CSV |
| `GET` | `/api/v1/exportar/excel` | Export results as Excel (.xlsx) |
| `GET` | `/api/v1/exportar/log` | Export the audit log |

### Configuration
| Method | Route | Description |
|--------|-------|-------------|
| `GET/POST` | `/api/v1/aprovadores` | Manage authorized approvers |
| `GET/POST` | `/api/v1/fornecedores` | Manage suppliers (CNPJ) |
| `GET` | `/api/v1/health` | Application and dependency status |

---

## 🔄 Processing Flow

```
User uploads a TXT file
        ↓
FastAPI validates (extension, size, content)
        ↓
Saves file + registers in DB (status: pending)
        ↓
Enqueues task in Celery via Redis
        ↓
Celery worker processes:
  1. Reads file content
  2. Builds prompt → calls OpenRouter API
  3. Parses the JSON returned by AI
  4. Saves extracted fields to DB
  5. Runs all 8 anomaly rules
  6. Saves generated flags
  7. Updates document status
  8. Logs event to audit_log
        ↓
Frontend polls status (GET /documentos)
        ↓
Displays results in table with visual flags
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Verbose with short tracebacks
pytest -v --tb=short

# Run a specific test file
pytest tests/test_anomalia_service.py
```

Tests live in `tests/` and follow the `test_<module>.py` convention.

---

## ⚙️ Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `postgresql+psycopg://...` |
| `REDIS_URL` | Redis URL | `redis://redis:6379/0` |
| `OPENROUTER_API_KEY` | OpenRouter API key | *(required)* |
| `OPENROUTER_MODEL` | AI model to use | `minimax/minimax-m2.5:free` |
| `OPENROUTER_REFERER` | Referrer URL for OpenRouter | — |
| `OPENROUTER_TITLE` | Application title in OpenRouter | `DocAudit` |
| `APP_NAME` | Application name | `DocAudit` |
| `APP_VERSION` | Application version | `0.1.0` |
| `POSTGRES_DB` | Database name (Docker) | `docaudit` |
| `POSTGRES_USER` | Database user (Docker) | `docaudit` |
| `POSTGRES_PASSWORD` | Database password (Docker) | `docaudit` |

> ⚠️ **Never commit your `.env` file with real secrets.** Always use `.env.example` as the template.

---

## 🗺️ Roadmap

### ✅ Phase 1 — MVP
- [x] FastAPI + PostgreSQL + Docker project scaffold
- [x] Database models and migrations (Alembic)
- [x] TXT file upload endpoint
- [x] OpenRouter integration (field extraction)
- [x] Anomaly detection engine
- [x] REST API with core endpoints
- [x] Frontend: upload + table + anomaly flags
- [x] CSV export

### 🚧 Phase 2 — Consolidation
- [ ] Async processing with Celery + Redis
- [ ] Document details panel (sidebar on row click)
- [ ] Excel export with formatting
- [ ] Full exportable audit log
- [ ] Approver and supplier configuration screen

### 🔮 Phase 3 — Enhancements
- [ ] JWT authentication
- [ ] Support for PDF and XML (NF-e) formats
- [ ] Anomaly trend dashboard with charts
- [ ] Webhook / email notifications for critical anomalies
- [ ] Bulk re-analysis API for historical documents

---

## 🤝 Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/my-feature`
3. Commit with imperative messages: `Add upload router`, `Fix CNPJ validator`
4. Open a Pull Request describing:
   - What changed and why
   - Link to the relevant PRD section
   - Test evidence (`pytest`, screenshots, or manual API checks)
   - Notes on schema or migration changes

---

## 📄 License

Distributed under the **MIT** License. See [LICENSE](LICENSE) for details.
