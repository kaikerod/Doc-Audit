# Deploy na Vercel

Este projeto agora possui um caminho de deploy compativel com a Vercel para o backend FastAPI.

## Resumo da arquitetura na Vercel

- o backend roda como uma unica Vercel Function Python
- o frontend continua sendo servido pelo proprio FastAPI
- o processamento de uploads muda para o modo sincrono
- Redis/Celery deixam de ser obrigatorios nesse ambiente
- Postgres externo continua obrigatorio para persistencia

## Diferenca em relacao ao ambiente local

No ambiente local com `docker compose`, o fluxo continua orientado por fila:

- API FastAPI
- PostgreSQL
- Redis
- worker Celery

Na Vercel, o projeto entra automaticamente em modo `sync` quando detecta o ambiente Vercel, ou voce pode definir isso explicitamente:

```env
DOC_AUDIT_PROCESSING_MODE=sync
```

Esse modo e indicado para demonstracao, homologacao e cargas menores. Para lotes grandes e workers persistentes, mantenha uma infraestrutura separada da Vercel.

## Pre-requisitos

1. Conta na Vercel
2. Banco Postgres externo
3. Chave da OpenRouter

## Banco recomendado

O caminho mais direto na Vercel e usar Neon via Marketplace:

```bash
vercel integration add neon
```

Isso simplifica o provisionamento do Postgres e injeta variaveis como `POSTGRES_URL`
e `POSTGRES_URL_NON_POOLING` no projeto. O backend aceita essas chaves
automaticamente na Vercel, mesmo sem duplicar manualmente `DATABASE_URL`.

## Variaveis de ambiente

Configure pelo menos estas variaveis no projeto da Vercel:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=mistralai/ministral-3b-2512
OPENROUTER_REFERER=https://seu-projeto.vercel.app
OPENROUTER_TITLE=DocAudit
DOC_AUDIT_PROCESSING_MODE=sync
UPLOAD_MAX_FILES=5
```

Se voce nao usar a integracao Neon/Marketplace, defina manualmente uma destas opcoes:

```env
DATABASE_URL=postgresql+psycopg://...
# ou
POSTGRES_URL=postgresql://...
```

`UPLOAD_MAX_FILES=5` e uma recomendacao pratica para evitar requests longas demais no modo sincrono.

## Comandos de deploy

```bash
vercel link
vercel env pull .env.local --yes
vercel --prod
```

## Validacao apos deploy

1. Acesse `/api/v1/health`
2. Confirme `database: ok`
3. Confirme `ai: ok`
4. Faça upload de poucos arquivos por vez
5. Valide a exportacao CSV/Excel

## Arquivos de configuracao adicionados

- `index.py`: entrypoint FastAPI para a Vercel
- `requirements.txt`: dependencias de runtime no root
- `vercel.json`: configuracao da function Python
- `.python-version`: pin de Python
