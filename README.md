# DocAudit

Sistema web para análise automatizada de documentos fiscais e financeiros. O upload de arquivos `.txt` é validado, processado de forma síncrona com OpenRouter e persistido em PostgreSQL com trilha de auditoria.

## Visão Geral

O fluxo atual é direto:

1. Usuário envia um ou mais arquivos `.txt`.
2. A API valida extensão, tamanho e conteúdo.
3. O arquivo é processado na própria request.
4. A IA extrai campos estruturados.
5. As regras de anomalia são aplicadas.
6. O documento e o log de auditoria são persistidos.
7. O frontend lê os resultados via `/api/v1/documentos`.

## Stack

- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- OpenRouter
- openpyxl
- pandas
- Vanilla JavaScript

## Estrutura

```text
backend/
  app/
    main.py
    config.py
    database.py
    models/
    routers/
    schemas/
    services/
frontend/
  index.html
  css/
  js/
tests/
PRD.md
```

## Como rodar localmente

```bash
cp .env.example .env
docker compose up --build
docker compose exec web alembic upgrade head
```

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/uploads` | Envia arquivos `.txt` |
| `GET` | `/api/v1/uploads` | Lista uploads |
| `GET` | `/api/v1/uploads/{id}` | Detalha um upload |
| `GET` | `/api/v1/documentos` | Lista documentos processados |
| `GET` | `/api/v1/documentos/{id}` | Detalha um documento |
| `GET` | `/api/v1/anomalias` | Lista anomalias |
| `PATCH` | `/api/v1/anomalias/{id}/resolver` | Resolve uma anomalia |
| `GET` | `/api/v1/exportar/csv` | Exporta CSV |
| `GET` | `/api/v1/exportar/excel` | Exporta Excel |
| `GET` | `/api/v1/exportar/log` | Exporta o log de auditoria |
| `GET` | `/api/v1/health` | Status da aplicação |

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `DATABASE_URL` | String de conexão do banco |
| `POSTGRES_URL` | URL do banco injetada pela integração Supabase/Vercel |
| `POSTGRES_URL_NON_POOLING` | URL direta do banco; preferida quando disponível |
| `OPENROUTER_API_KEY` | Chave da OpenRouter |
| `OPENROUTER_MODEL` | Modelo usado na extração |
| `OPENROUTER_REFERER` | Referer enviado à OpenRouter |
| `OPENROUTER_TITLE` | Título enviado à OpenRouter |
| `UPLOAD_MAX_FILES` | Máximo de arquivos por envio |
| `DOC_AUDIT_AUTO_CREATE_SCHEMA` | Criação automática do schema no startup |
| `APP_NAME` | Nome da aplicação |
| `APP_VERSION` | Versão da aplicação |

Na Vercel, use `DOC_AUDIT_PROCESSING_MODE=sync`, mantenha
`DOC_AUDIT_AUTO_CREATE_SCHEMA=false` e prefira `POSTGRES_URL_NON_POOLING` se for
configurar a conexão manualmente.

## Testes

```bash
python -m pytest
```

## Deploy na Vercel

Veja [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md) para os detalhes de configuração e deploy.
