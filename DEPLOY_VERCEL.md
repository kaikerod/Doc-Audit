# Deploy na Vercel com Supabase

Este projeto possui um caminho de deploy compativel com a Vercel para o backend FastAPI.

## Resumo da arquitetura na Vercel

- o backend roda como uma unica Vercel Function Python
- o frontend continua sendo servido pelo proprio FastAPI
- o processamento de uploads roda de forma sincrona dentro da propria request
- a function nao executa `create_all()` na Vercel; schema deve existir previamente no banco persistente
- o Supabase fornece o Postgres persistente usado pela aplicacao
- sem um banco persistente configurado, o deploy falha ao iniciar em vez de cair em SQLite temporario

## Diferenca em relacao ao ambiente local

No ambiente local com `docker compose`, o fluxo continua sincrono:

- API FastAPI
- PostgreSQL

Na Vercel, o projeto entra automaticamente em modo `sync`:

```env
DOC_AUDIT_PROCESSING_MODE=sync
```

Esse modo e o recomendado para a Vercel. O upload processa o arquivo na propria request, grava o registro e persiste o resultado sem depender de worker externo ou Redis.

## Pre-requisitos

1. Conta na Vercel
2. Integracao Supabase provisionada no projeto
3. Chave da OpenRouter

## Integracoes esperadas

O projeto deve exibir as integracoes abaixo:

```bash
vercel integration ls
```

Resultado esperado:

- `supabase` para Postgres e env vars publicos/privados do workspace Supabase

## Variaveis de ambiente

As integracoes devem provisionar automaticamente variaveis como:

```env
POSTGRES_URL=postgresql://...
POSTGRES_URL_NON_POOLING=postgresql://...
POSTGRES_PRISMA_URL=postgresql://...
POSTGRES_HOST=db.<project-ref>.supabase.co
POSTGRES_DATABASE=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_PUBLISHABLE_KEY=...
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SECRET_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...
```

Configure manualmente pelo menos estas variaveis de aplicacao:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=mistralai/ministral-3b-2512
OPENROUTER_REFERER=https://seu-projeto.vercel.app
OPENROUTER_TITLE=DocAudit
DOC_AUDIT_PROCESSING_MODE=sync
DOC_AUDIT_AUTO_CREATE_SCHEMA=false
UPLOAD_MAX_FILES=5
```

O backend aceita automaticamente `DATABASE_URL`, `POSTGRES_URL`,
`POSTGRES_URL_NON_POOLING` e `POSTGRES_PRISMA_URL`. Com a integracao Supabase,
na pratica o deploy usa `POSTGRES_URL` e `POSTGRES_URL_NON_POOLING` sem exigir
duplicacao manual para `DATABASE_URL`.

`DOC_AUDIT_AUTO_CREATE_SCHEMA=false` e o padrao recomendado na Vercel. Em ambiente serverless,
o startup da function nao deve executar DDL automaticamente; use migrations ou outro processo
controlado para preparar o schema antes de publicar.

Se voce nao usar a integracao do Marketplace, defina manualmente uma destas opcoes:

```env
DATABASE_URL=postgresql+psycopg://...
# ou
POSTGRES_URL=postgresql://...
```

Se nenhuma dessas variaveis estiver definida, a aplicacao aborta a inicializacao na Vercel.

`UPLOAD_MAX_FILES=5` continua sendo uma recomendacao pratica para evitar requests longas demais,
mesmo com processamento sincrono.
O frontend web divide selecoes maiores em varias requisicoes sequenciais, respeitando esse limite por request.

Depois de adicionar ou alterar env vars na Vercel, faca um novo deploy.
O deployment em execucao nao passa a enxergar variaveis criadas depois que ele foi publicado.

## Comandos de deploy

```bash
vercel link
vercel env pull .env.local --yes
vercel --prod
```

Para diagnostico rapido:

```bash
vercel integration ls
vercel env ls
vercel logs --environment production --since 1h --level error --expand
```

## Validacao apos deploy

1. Acesse `/api/v1/health`
2. Confirme `database: ok`
3. Confirme `processing_mode: sync`
4. Confirme `ai: ok`
5. Faca upload de poucos arquivos por vez
6. Valide a exportacao CSV/Excel

## Arquivos de configuracao

- `index.py`: entrypoint FastAPI para a Vercel
- `requirements.txt`: dependencias de runtime no root
- `vercel.json`: configuracao da function Python
- `.python-version`: pin de Python
