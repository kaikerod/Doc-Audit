# Deploy na Vercel com Supabase + Redis

Este projeto possui um caminho de deploy compativel com a Vercel para o backend FastAPI.

## Resumo da arquitetura na Vercel

- o backend roda como uma unica Vercel Function Python
- o frontend continua sendo servido pelo proprio FastAPI
- o processamento de uploads roda de forma assincrona via Celery + Redis
- o worker Celery precisa rodar fora da Vercel, apontando para o mesmo Redis
- o conteudo bruto do TXT fica em staging temporario no Redis para o worker conseguir processar o upload fora do filesystem efemero da Vercel
- o Supabase fornece o Postgres persistente usado pela aplicacao
- o Redis e obrigatorio para a fila de processamento, cooldown/rate limit e observabilidade compartilhada
- sem um banco persistente configurado, o deploy falha ao iniciar em vez de cair em SQLite temporario

## Diferenca em relacao ao ambiente local

No ambiente local com `docker compose`, o fluxo continua orientado por fila:

- API FastAPI
- PostgreSQL
- Redis
- worker Celery

Na Vercel, o projeto entra automaticamente em modo `queue` quando detecta `REDIS_URL`, ou voce pode definir isso explicitamente:

```env
DOC_AUDIT_PROCESSING_MODE=queue
```

Esse modo e o recomendado para a Vercel. O upload responde rapido, grava o registro e enfileira o processamento no Redis. O worker deve ficar em um processo separado, fora da Vercel.
Como a Vercel oferece apenas filesystem efemero na function, o backend tambem faz staging temporario do payload do upload no Redis ate a task terminar.

## Pre-requisitos

1. Conta na Vercel
2. Integracao Supabase provisionada no projeto
3. Integracao Redis provisionada no projeto
4. Chave da OpenRouter

## Integracoes esperadas

O projeto deve exibir as integracoes abaixo:

```bash
vercel integration ls
```

Resultado esperado:

- `supabase` para Postgres e env vars publicos/privados do workspace Supabase
- `redis` para `REDIS_URL`

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
REDIS_URL=rediss://...
```

Configure manualmente pelo menos estas variaveis de aplicacao:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=mistralai/ministral-3b-2512
OPENROUTER_REFERER=https://seu-projeto.vercel.app
OPENROUTER_TITLE=DocAudit
DOC_AUDIT_PROCESSING_MODE=queue
UPLOAD_MAX_FILES=5
UPLOAD_QUEUE_PAYLOAD_TTL_SECONDS=86400
```

O backend aceita automaticamente `DATABASE_URL`, `POSTGRES_URL`,
`POSTGRES_URL_NON_POOLING` e `POSTGRES_PRISMA_URL`. Com a integracao Supabase,
na pratica o deploy usa `POSTGRES_URL` e `POSTGRES_URL_NON_POOLING` sem exigir
duplicacao manual para `DATABASE_URL`.

Se voce nao usar a integracao do Marketplace, defina manualmente uma destas opcoes:

```env
DATABASE_URL=postgresql+psycopg://...
# ou
POSTGRES_URL=postgresql://...
```

Se nenhuma dessas variaveis estiver definida, a aplicacao aborta a inicializacao na Vercel.

`UPLOAD_MAX_FILES=5` continua sendo uma recomendacao pratica para evitar requests longas demais,
mesmo com processamento assíncrono.
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
3. Confirme `processing_mode: queue`
4. Confirme que `REDIS_URL` esta presente e acessivel
5. Confirme `ai: ok`
6. Faca upload de poucos arquivos por vez
7. Valide a exportacao CSV/Excel

## Arquivos de configuracao

- `index.py`: entrypoint FastAPI para a Vercel
- `requirements.txt`: dependencias de runtime no root
- `vercel.json`: configuracao da function Python
- `.python-version`: pin de Python
