# Deploy na Vercel com Supabase

Este projeto possui um caminho de deploy compatível com a Vercel para o backend FastAPI.

## Resumo da arquitetura na Vercel

- o backend roda como uma única Vercel Function Python
- o frontend continua sendo servido pelo próprio FastAPI
- o processamento de uploads roda de forma síncrona dentro da própria request
- a function não executa `create_all()` na Vercel; schema deve existir previamente no banco persistente
- o Supabase fornece o Postgres persistente usado pela aplicação
- sem um banco persistente configurado, o deploy falha ao iniciar em vez de cair em SQLite temporário

## Diferença em relação ao ambiente local

No ambiente local com `docker compose`, o fluxo continua síncrono:

- API FastAPI
- PostgreSQL

Na Vercel, o projeto entra automaticamente em modo `sync`:

```env
DOC_AUDIT_PROCESSING_MODE=sync
```

Esse modo é o recomendado para a Vercel. O upload processa o arquivo na própria request, grava o registro e persiste o resultado sem depender de worker externo ou Redis.

## Pré-requisitos

1. Conta na Vercel
2. Integração Supabase provisionada no projeto
3. Chave da OpenRouter

## Integrações esperadas

O projeto deve exibir as integrações abaixo:

```bash
vercel integration ls
```

Resultado esperado:

- `supabase` para Postgres e env vars públicos/privados do workspace Supabase

## Variáveis de ambiente

As integrações devem provisionar automaticamente variáveis como:

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

Configure manualmente pelo menos estas variáveis de aplicação:

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
`POSTGRES_URL_NON_POOLING` e `POSTGRES_PRISMA_URL`. Com a integração Supabase,
o deploy normalmente recebe `POSTGRES_URL` e `POSTGRES_URL_NON_POOLING`
automaticamente, sem exigir duplicação manual para `DATABASE_URL`.
O resolver de configuração prefere `POSTGRES_URL_NON_POOLING` quando ele está
disponível, porque esse é o caminho mais previsível para conexões persistentes em
ambientes serverless.
As conexões `postgresql+psycopg` desabilitam prepared statements automáticos
(`prepare_threshold=None`) para evitar erros de compatibilidade com poolers
serverless, como os usados por Supabase/Vercel.

`DOC_AUDIT_AUTO_CREATE_SCHEMA=false` é o padrão recomendado na Vercel. Em ambiente serverless,
o startup da function não deve executar DDL automaticamente; use migrations ou outro processo
controlado para preparar o schema antes de publicar.

Se você não usar a integração do Marketplace, defina manualmente uma destas opções:

```env
DATABASE_URL=postgresql+psycopg://...
# ou
POSTGRES_URL_NON_POOLING=postgresql://...
```

Se nenhuma dessas variáveis estiver definida, a aplicação aborta a inicialização na Vercel.

`UPLOAD_MAX_FILES=5` continua sendo uma recomendação prática para evitar requests longas demais,
mesmo com processamento síncrono.
O frontend web divide seleções maiores em várias requisições sequenciais, respeitando esse limite por request.

Depois de adicionar ou alterar env vars na Vercel, faça um novo deploy.
O deployment em execução não passa a enxergar variáveis criadas depois que ele foi publicado.

## Comandos de deploy

```bash
vercel link
vercel env pull .env.local --yes
vercel --prod
```

Para diagnóstico rápido:

```bash
vercel integration ls
vercel env ls
vercel logs --environment production --since 1h --level error --expand
```

## Validação após deploy

1. Acesse `/api/v1/health`
2. Confirme `database: ok`
3. Confirme `processing_mode: sync`
4. Confirme `ai: ok`
5. Faça upload de poucos arquivos por vez
6. Valide a exportação CSV/Excel

## Arquivos de configuração

- `index.py`: entrypoint FastAPI para a Vercel
- `requirements.txt`: dependências de runtime no root
- `vercel.json`: configuração da function Python
- `.python-version`: pin de Python
