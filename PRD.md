# PRD - DocAudit

**Versão:** 1.0  
**Data:** Abril de 2026  
**Status:** Em uso

## 1. Visão Geral

DocAudit é uma aplicação web interna para análise automatizada de documentos fiscais e financeiros. O sistema recebe arquivos TXT, extrai campos estruturados com IA, aplica regras de anomalia e registra tudo em log de auditoria.

## 2. Objetivos

| Objetivo | Métrica |
|---|---|
| Reduzir conferência manual | Menos de 30 segundos por documento |
| Detectar inconsistências | Taxa de falsos positivos abaixo de 10% |
| Garantir rastreabilidade | 100% dos eventos logados |
| Exportar resultados | CSV e Excel em poucos cliques |

## 3. Stack

- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- OpenRouter
- openpyxl
- pandas
- Vanilla JavaScript

## 4. Escopo Funcional

### 4.1 Upload de arquivos

- Aceitar arquivos `.txt`
- Validar tamanho máximo e conteúdo
- Processar o arquivo na própria request
- Persistir upload, documento e anomalias

### 4.2 Extração via IA

- Ler o conteúdo do TXT
- Extrair número da NF, CNPJ, datas, valor, aprovador e descrição
- Retornar JSON estruturado
- Persistir a resposta da IA para auditoria

### 4.3 Regras de anomalia

| Código | Anomalia | Lógica |
|---|---|---|
| `DUP_NF` | NF duplicada | Mesmo número de NF já existe para o mesmo emitente |
| `CNPJ_DIV` | CNPJ divergente | CNPJ não bate com o cadastro interno |
| `DATA_INV` | Data inválida | Emissão posterior ao pagamento |
| `APROV_NR` | Aprovador não reconhecido | Nome fora da lista autorizada |
| `VALOR_ZERO` | Valor zerado | Valor total é zero ou negativo |
| `NF_FUTURA` | NF com data futura | Emissão posterior à data atual |
| `CNPJ_INVALIDO` | CNPJ inválido | Falha na validação de dígitos verificadores |
| `CAMPO_VAZIO` | Campo obrigatório ausente | Campos críticos não foram extraídos |

### 4.4 Exibição

- Tabela com filtros e ordenação
- Detalhe do documento selecionado
- Badges por severidade
- Status visual de erro, concluído e com anomalias

### 4.5 Exportação

- CSV
- Excel
- Log de auditoria

## 5. Fluxo de Processamento

1. Usuário envia o TXT.
2. FastAPI valida o arquivo.
3. A aplicação processa o conteúdo na própria request.
4. A IA extrai os campos.
5. As regras de negócio geram anomalias.
6. O banco recebe o documento final.
7. O frontend exibe o resultado.

## 6. Modelo de Dados

### uploads

- `id`
- `nome_arquivo`
- `caminho_arquivo`
- `hash_sha256`
- `tamanho_bytes`
- `status`
- `criado_em`
- `atualizado_em`

### documentos

- `id`
- `upload_id`
- `numero_nf`
- `cnpj_emitente`
- `cnpj_destinatario`
- `data_emissao`
- `data_pagamento`
- `valor_total`
- `aprovador`
- `descricao`
- `conteudo_bruto`
- `resposta_ia`
- `modelo_ia`
- `status_extracao`

### anomalias

- `id`
- `documento_id`
- `codigo`
- `descricao`
- `severidade`
- `resolvida`
- `resolvida_em`

### audit_log

- `id`
- `evento`
- `entidade_tipo`
- `entidade_id`
- `usuario`
- `ip`
- `payload`
- `timestamp`

## 7. Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/uploads` | Envia arquivos TXT |
| `GET` | `/api/v1/uploads` | Lista uploads |
| `GET` | `/api/v1/uploads/{id}` | Detalha upload |
| `GET` | `/api/v1/documentos` | Lista documentos |
| `GET` | `/api/v1/documentos/{id}` | Detalha documento |
| `PATCH` | `/api/v1/documentos/{id}` | Revisão manual |
| `GET` | `/api/v1/anomalias` | Lista anomalias |
| `PATCH` | `/api/v1/anomalias/{id}/resolver` | Resolve anomalia |
| `GET` | `/api/v1/exportar/csv` | Exporta CSV |
| `GET` | `/api/v1/exportar/excel` | Exporta Excel |
| `GET` | `/api/v1/exportar/log` | Exporta log |
| `GET` | `/api/v1/health` | Status da aplicação |

## 8. Requisitos Não Funcionais

| Categoria | Requisito |
|---|---|
| Performance | Upload com resposta rápida e processamento síncrono controlado |
| Segurança | Validação de extensão, tamanho e conteúdo |
| Confiabilidade | Reprocessar falhas de IA dentro da request quando aplicável |
| Rastreabilidade | 100% das ações no audit_log |
| Usabilidade | Interface simples, sem autenticação no MVP |

## 9. Estrutura de Pastas

```text
docaudit/
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
  docker-compose.yml
  .env.example
```

## 10. Decisões em Aberto

| Decisão | Status |
|---|---|
| Autenticação | Em aberto |
| Suporte a PDF/XML | Fora do MVP |
| Dashboard analítico | Em aberto |
| Deploy inicial | Vercel com backend síncrono |
