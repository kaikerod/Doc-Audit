# Deploy assíncrono de produção

Este caminho recoloca o DocAudit em `queue` sem trocar o frontend atual. O dashboard continua sendo servido pelo FastAPI em `/`, enquanto o processamento volta a acontecer via Celery + Redis.

## Arquitetura

- `api`: expõe o frontend atual e a API FastAPI
- `worker`: consome a fila Celery
- `Postgres` externo: persistência
- `Redis` externo: broker/backend das tasks
- volume `uploads_data`: compartilhado entre `api` e `worker` para que o worker leia os arquivos enviados

## Arquivos adicionados

- `docker-compose.prod.yml`: stack de produção para `api` + `worker`
- `.env.production.example`: referência de variáveis para produção

## Passos

1. Copie `.env.production.example` para `.env` no host de produção e ajuste os valores reais.
2. Garanta que `DATABASE_URL` e `REDIS_URL` apontem para serviços alcançáveis a partir dos containers.
3. Suba a stack:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. Valide a API e a fila:

```bash
curl http://localhost:8000/api/v1/health
```

O `health` esperado nesse cenário é:

- `features.processing_mode = "queue"`
- `checks.queue = "ok"`
- `features.uploads_enabled = true` quando IA, banco e Redis estiverem saudáveis

## Frontend atual

O frontend não foi trocado. A imagem da API continua copiando `frontend/` e servindo o dashboard em `/`.

Se você quiser hospedar o mesmo frontend em outro domínio sem alterar a lógica da UI:

1. Configure o backend com `CORS_ALLOW_ORIGINS=https://seu-frontend.example.com`
2. Preencha a meta tag `docaudit-api-base-url` do `frontend/index.html` com a URL pública da API

Sem isso, o frontend continua funcionando em same-origin quando servido pela própria API.

## Observações operacionais

- `DOC_AUDIT_PROCESSING_MODE=queue` fica explícito na stack de produção.
- O volume compartilhado de uploads é obrigatório; sem ele o worker não consegue abrir os arquivos persistidos pela API.
- O `backend/Dockerfile` agora sobe o `uvicorn` sem `--reload`, enquanto o `docker-compose.yml` de desenvolvimento continua forçando `--reload` só no ambiente local.
