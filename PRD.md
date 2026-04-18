# PRD — DocAudit
### Sistema de Análise e Auditoria de Documentos com IA

**Versão:** 1.0  
**Data:** Abril de 2026  
**Status:** Rascunho  

---

## 1. Visão Geral do Produto

**DocAudit** é uma aplicação web interna para análise automatizada de documentos fiscais e financeiros. O sistema recebe arquivos TXT via upload, extrai campos estruturados com auxílio de IA (OpenRouter), detecta anomalias automaticamente e apresenta os resultados em uma interface tabular com flags visuais. Tudo é rastreável via log de auditoria exportável.

### Problema que resolve
Processos manuais de conferência de notas fiscais, aprovações e pagamentos são lentos, propensos a erros humanos e difíceis de auditar. O DocAudit automatiza essa conferência, detecta inconsistências em segundos e mantém um rastro auditável de todas as análises realizadas.

### Público-alvo
Equipes financeiras, de compliance e auditoria interna de pequenas e médias empresas.

---

## 2. Objetivos e Métricas de Sucesso

| Objetivo | Métrica |
|---|---|
| Reduzir tempo de conferência manual | < 30 segundos por documento analisado |
| Detectar anomalias com precisão | Taxa de falsos positivos < 10% |
| Rastreabilidade completa | 100% das análises logadas com timestamp |
| Exportação acessível | Exportar CSV/Excel em < 2 cliques |

---

## 3. Stack Tecnológica

### Frontend
- HTML5, CSS3, JavaScript puro (sem frameworks)
- Estilo minimalista, responsivo, com feedback visual claro

### Backend
- **Python 3.11+**
- **FastAPI** — framework principal para a API REST
- **SQLAlchemy** — ORM para mapeamento de modelos
- **Alembic** — migrations de banco de dados
- **PostgreSQL** — banco de dados relacional principal
- **Celery + Redis** — processamento assíncrono de documentos (fila de tarefas)
- **OpenRouter API** — integração com modelos de IA (extração de campos e análise)
- **openpyxl / pandas** — geração de arquivos Excel e CSV
- **python-multipart** — upload de arquivos via FastAPI
- **Pydantic v2** — validação de dados e serialização

### Infraestrutura
- Docker + Docker Compose (desenvolvimento local)
- Variáveis de ambiente via `.env` (segredos da API OpenRouter, string de conexão do banco)

---

## 4. Módulos do Sistema

### 4.1 Módulo de Upload de Arquivos
**Responsabilidade:** Receber, validar e armazenar os arquivos enviados pelo usuário.

**Comportamento:**
- Aceitar arquivos `.txt` via drag-and-drop ou seleção manual
- Validar tamanho máximo (ex: 5 MB por arquivo) e extensão
- Suportar upload múltiplo (batch) — até 20 arquivos por vez
- Exibir barra de progresso individual por arquivo
- Gerar um `upload_id` único por sessão de upload
- Salvar o arquivo temporariamente no servidor e registrar no banco

**Regras:**
- Rejeitar arquivos com extensão diferente de `.txt` (com mensagem de erro clara)
- Rejeitar arquivos vazios
- Não sobrescrever arquivos com mesmo nome — usar UUID no armazenamento

---

### 4.2 Módulo de Extração via IA (OpenRouter)
**Responsabilidade:** Enviar o conteúdo dos arquivos para a API de IA e extrair campos estruturados.

**Comportamento:**
- Ler o conteúdo do arquivo TXT
- Montar um prompt estruturado solicitando extração dos seguintes campos:
  - Número da NF
  - CNPJ do emitente
  - CNPJ do destinatário
  - Data de emissão da NF
  - Data de pagamento
  - Valor total
  - Nome do aprovador
  - Descrição do produto/serviço
- Retornar um JSON com os campos extraídos e nível de confiança por campo
- Registrar o resultado bruto da IA no banco para auditoria
- Processar de forma assíncrona via Celery (não bloquear o usuário)

**Modelo sugerido:** `mistralai/ministral-3b-2512` (via OpenRouter, configurável)

**Tratamento de erros:**
- Se a IA não conseguir extrair um campo, marcar como `null` com flag `extraction_failed`
- Retentar até 2 vezes em caso de timeout
- Notificar o usuário se o processamento falhar após as retentativas

---

### 4.3 Módulo de Detecção de Anomalias
**Responsabilidade:** Aplicar regras de negócio sobre os campos extraídos e gerar flags de anomalia.

**Regras implementadas:**

| Código | Anomalia | Lógica |
|---|---|---|
| `DUP_NF` | NF duplicada | Mesmo número de NF já existe no banco para o mesmo CNPJ emitente |
| `CNPJ_DIV` | CNPJ divergente | CNPJ do emitente não bate com o cadastro interno do fornecedor |
| `DATA_INV` | Data inválida | Data de emissão da NF é posterior à data de pagamento |
| `APROV_NR` | Aprovador não reconhecido | Nome do aprovador não consta na lista de aprovadores autorizados |
| `VALOR_ZERO` | Valor zerado | Valor total da NF é zero ou negativo |
| `NF_FUTURA` | NF com data futura | Data de emissão da NF é posterior à data atual |
| `CNPJ_INVALIDO` | CNPJ com formato inválido | CNPJ não passa na validação de dígitos verificadores |
| `CAMPO_VAZIO` | Campo obrigatório ausente | Campos críticos não foram extraídos (NF, CNPJ, valor, data) |

**Comportamento:**
- Cada documento pode ter zero ou múltiplas flags
- Severidade por flag: `CRÍTICA`, `ALTA`, `MÉDIA` (configurável)
- Flags críticas bloqueiam a exportação sem confirmação explícita do usuário
- As regras devem ser configuráveis via arquivo de configuração ou tabela no banco

---

### 4.4 Módulo de Exibição dos Resultados
**Responsabilidade:** Apresentar os documentos analisados em tabela com flags visuais.

**Funcionalidades da tabela:**
- Colunas: Nome do arquivo, NF, CNPJ emitente, Data NF, Data pagamento, Valor, Aprovador, Status, Flags
- Coluna de flags com badges coloridos por severidade (vermelho = crítica, amarelo = alta, cinza = média)
- Filtros: por status (com anomalia / sem anomalia / todos), por tipo de flag, por data de upload
- Busca por nome de arquivo ou número de NF
- Ordenação por qualquer coluna
- Paginação (20 registros por página)
- Ao clicar em uma linha, abrir painel lateral com detalhes completos do documento e todas as flags

**Estados visuais:**
- Processando (spinner + "Analisando com IA...")
- Concluído sem anomalias (ícone verde)
- Concluído com anomalias (ícone vermelho + contador de flags)
- Erro de processamento (ícone laranja + mensagem)

---

### 4.5 Módulo de Exportação
**Responsabilidade:** Gerar arquivos exportáveis dos resultados.

**Formatos suportados:**
- **CSV:** campos separados por ponto-e-vírgula, encoding UTF-8 com BOM (compatível com Excel Brasil)
- **Excel (.xlsx):** planilha formatada com cabeçalho em negrito, células coloridas para flags, aba separada para o log de auditoria

**Escopo de exportação:**
- Exportar seleção atual (filtros ativos) ou todos os registros
- Exportar somente documentos com anomalias
- Exportar log de auditoria separadamente

**Campos exportados:**
Todos os campos da tabela + detalhamento de cada flag (código, descrição, severidade, timestamp de detecção)

---

### 4.6 Módulo de Log de Auditoria
**Responsabilidade:** Registrar todas as operações realizadas no sistema de forma rastreável.

**Eventos logados:**
- Upload de arquivo (usuário, timestamp, nome do arquivo, hash SHA-256)
- Início e fim do processamento por IA (modelo usado, tokens consumidos, duração)
- Resultado da detecção de anomalias (flags geradas)
- Exportações realizadas (formato, quantidade de registros, timestamp)
- Alterações manuais feitas pelo usuário (se houver revisão manual de campos)

**Campos do log:**
`id`, `evento`, `entidade_id`, `entidade_tipo`, `usuario`, `ip`, `payload_antes`, `payload_depois`, `timestamp`

**Exportação do log:**
- CSV ou Excel
- Filtro por período, por tipo de evento, por arquivo específico

---

## 5. Modelo de Banco de Dados

```sql
-- Arquivos enviados
CREATE TABLE uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_arquivo VARCHAR(255) NOT NULL,
    caminho_arquivo TEXT NOT NULL,
    hash_sha256 CHAR(64) NOT NULL,
    tamanho_bytes INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pendente',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Documentos extraídos
CREATE TABLE documentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    numero_nf VARCHAR(100),
    cnpj_emitente VARCHAR(18),
    cnpj_destinatario VARCHAR(18),
    data_emissao DATE,
    data_pagamento DATE,
    valor_total NUMERIC(15, 2),
    aprovador VARCHAR(255),
    descricao TEXT,
    conteudo_bruto TEXT,
    resposta_ia JSONB,
    modelo_ia VARCHAR(100),
    tokens_consumidos INTEGER,
    status_extracao VARCHAR(50) NOT NULL DEFAULT 'pendente',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Flags de anomalia
CREATE TABLE anomalias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    documento_id UUID NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    codigo VARCHAR(50) NOT NULL,
    descricao TEXT NOT NULL,
    severidade VARCHAR(20) NOT NULL CHECK (severidade IN ('CRITICA', 'ALTA', 'MEDIA')),
    resolvida BOOLEAN NOT NULL DEFAULT false,
    resolvida_em TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Aprovadores autorizados
CREATE TABLE aprovadores_autorizados (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    ativo BOOLEAN NOT NULL DEFAULT true,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fornecedores cadastrados
CREATE TABLE fornecedores (
    id SERIAL PRIMARY KEY,
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    razao_social VARCHAR(255) NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT true,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Log de auditoria
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento VARCHAR(100) NOT NULL,
    entidade_tipo VARCHAR(100),
    entidade_id TEXT,
    usuario VARCHAR(255),
    ip INET,
    payload JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 6. Endpoints da API (FastAPI)

### Upload
| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/uploads` | Envia um ou mais arquivos TXT |
| `GET` | `/api/v1/uploads` | Lista todos os uploads (paginado) |
| `GET` | `/api/v1/uploads/{id}` | Detalhes de um upload específico |

### Documentos
| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/documentos` | Lista documentos analisados (filtros, paginação) |
| `GET` | `/api/v1/documentos/{id}` | Detalhes completos de um documento |
| `PATCH` | `/api/v1/documentos/{id}` | Revisão manual de campos extraídos |

### Anomalias
| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/anomalias` | Lista anomalias (filtro por severidade, status) |
| `PATCH` | `/api/v1/anomalias/{id}/resolver` | Marca uma anomalia como resolvida |

### Exportação
| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/exportar/csv` | Exporta resultados em CSV |
| `GET` | `/api/v1/exportar/excel` | Exporta resultados em Excel |
| `GET` | `/api/v1/exportar/log` | Exporta log de auditoria |

### Configuração
| Método | Rota | Descrição |
|---|---|---|
| `GET/POST` | `/api/v1/aprovadores` | Gerencia lista de aprovadores autorizados |
| `GET/POST` | `/api/v1/fornecedores` | Gerencia cadastro de fornecedores (CNPJ) |

### Health
| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/health` | Status da aplicação e dependências |

#### 6.6 Documentação (Swagger)
A API deve ser auto-documentada utilizando o padrão OpenAPI 3.0.

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/docs` | Swagger UI (documentação interativa) |
| `GET` | `/redoc` | ReDoc (documentação detalhada) |
| `GET` | `/openapi.json` | Schema OpenAPI puro |

---

## 7. Fluxo de Processamento

```
Usuário faz upload do TXT
        ↓
FastAPI recebe e valida o arquivo
        ↓
Salva no sistema de arquivos + registra no banco (status: pendente)
        ↓
Enfileira tarefa no Celery (via Redis)
        ↓
Worker Celery processa:
    1. Lê o conteúdo do arquivo
    2. Monta prompt e chama OpenRouter API
    3. Faz parse da resposta JSON da IA
    4. Salva campos extraídos no banco
    5. Executa as regras de detecção de anomalias
    6. Salva flags de anomalia
    7. Atualiza status do documento
    8. Registra evento no audit_log
        ↓
Frontend consulta status via polling (GET /documentos)
        ↓
Exibe resultado na tabela com flags visuais
```

---

## 8. Telas do Frontend

### 8.1 Tela Principal (Dashboard)
- Header com logo e botão de exportação
- Área de drag-and-drop para upload
- Cards de resumo: total de documentos, documentos com anomalias, anomalias críticas
- Tabela principal com filtros e busca
- Indicador de processamento em tempo real

### 8.2 Painel de Detalhes (sidebar)
- Abre ao clicar em uma linha da tabela
- Exibe todos os campos extraídos com indicador de confiança
- Lista de anomalias encontradas com severidade e descrição
- Botão para marcar anomalias como resolvidas
- Link para baixar o arquivo original

### 8.3 Tela de Configurações
- Gerenciar lista de aprovadores autorizados (adicionar/remover)
- Gerenciar cadastro de fornecedores (CNPJ + razão social)
- Configurar modelo de IA utilizado
- Configurar limites de upload

---

## 9. Regras Não-Funcionais

| Categoria | Requisito |
|---|---|
| Performance | Resposta do upload em < 2s; processamento em < 30s por documento |
| Segurança | Validação de extensão e MIME type no upload; sanitização de inputs |
| Confiabilidade | Reprocessamento automático em caso de falha na API de IA (até 2 retentativas) |
| Rastreabilidade | 100% das ações registradas no audit_log com IP e timestamp |
| Usabilidade | Interface funcional sem autenticação no MVP (adicionar auth na Fase 2) |
| Escalabilidade | Suporte a pelo menos 100 documentos simultâneos via workers Celery |

---

## 10. Roadmap de Desenvolvimento

### Fase 1 — MVP (3-4 semanas)
- [ ] Estrutura do projeto FastAPI + PostgreSQL + Docker
- [ ] Modelo de banco de dados e migrations com Alembic
- [ ] Endpoint de upload de arquivos TXT
- [ ] Integração com OpenRouter (extração de campos)
- [ ] Motor de detecção de anomalias (regras básicas)
- [ ] API REST com endpoints principais
- [ ] Frontend: upload + tabela + flags de anomalia
- [ ] Exportação em CSV

### Fase 2 — Consolidação (2-3 semanas)
- [ ] Processamento assíncrono com Celery + Redis
- [ ] Painel de detalhes com sidebar
- [ ] Exportação em Excel com formatação
- [ ] Log de auditoria completo e exportável
- [ ] Tela de configuração de aprovadores e fornecedores

### Fase 3 — Melhorias (contínuo)
- [ ] Autenticação com JWT
- [ ] Suporte a outros formatos (PDF, XML de NF-e)
- [ ] Dashboard com gráficos de tendência de anomalias
- [ ] Webhook/notificação por e-mail em anomalias críticas
- [ ] API de bulk re-análise de documentos antigos

---

## 11. Estrutura de Pastas do Projeto

```
docaudit/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── upload.py
│   │   │   ├── documento.py
│   │   │   ├── anomalia.py
│   │   │   └── audit_log.py
│   │   ├── schemas/
│   │   │   ├── upload.py
│   │   │   ├── documento.py
│   │   │   └── anomalia.py
│   │   ├── routers/
│   │   │   ├── uploads.py
│   │   │   ├── documentos.py
│   │   │   ├── anomalias.py
│   │   │   └── exportar.py
│   │   ├── services/
│   │   │   ├── ia_service.py        # Integração OpenRouter
│   │   │   ├── anomalia_service.py  # Motor de regras
│   │   │   ├── export_service.py    # CSV e Excel
│   │   │   └── audit_service.py     # Log de auditoria
│   │   └── workers/
│   │       └── tasks.py             # Tarefas Celery
│   ├── alembic/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       ├── upload.js
│       ├── tabela.js
│       └── api.js
├── docker-compose.yml
└── .env.example
```

---

## 12. Exemplo de Prompt para a IA

```
Você é um extrator de dados de documentos fiscais brasileiros.
Analise o texto abaixo e extraia os campos em formato JSON.
Se um campo não for encontrado, retorne null para ele.
Retorne APENAS o JSON, sem explicações.

Campos a extrair:
- numero_nf: número da nota fiscal
- cnpj_emitente: CNPJ de quem emitiu (formato: XX.XXX.XXX/XXXX-XX)
- cnpj_destinatario: CNPJ do destinatário
- data_emissao: data de emissão da NF (formato: YYYY-MM-DD)
- data_pagamento: data de pagamento (formato: YYYY-MM-DD)
- valor_total: valor total em reais (número decimal)
- aprovador: nome completo do aprovador
- descricao: descrição resumida do produto ou serviço

Texto do documento:
---
{conteudo_do_arquivo}
---
```

---

## 13. Decisões em Aberto

| Decisão | Opções | Status |
|---|---|---|
| Modelo de IA padrão | `gpt-4o-mini` vs `mixtral-8x7b` vs `gemma-3` | Em aberto |
| Armazenamento de arquivos | Local (filesystem) vs S3-compatible | Local no MVP |
| Autenticação | Nenhuma no MVP vs JWT básico | Sem auth no MVP |
| Deploy inicial | VPS + Docker vs Railway vs Render | Em aberto |
| Suporte a PDF | Fora do escopo do MVP | Fase 3 |
