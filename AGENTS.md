# Repository Guidelines

## Project Structure & Module Organization
This repository is currently documentation-first. [`PRD.md`](/C:/Users/Kaike/Documents/Doc-Audit/PRD.md) is the source of truth for scope, architecture, and planned folder layout; [`LICENSE`](/C:/Users/Kaike/Documents/Doc-Audit/LICENSE) contains the MIT license.

When implementation begins, follow the structure defined in the PRD:
- `backend/app/` for FastAPI application code, split into `models/`, `schemas/`, `routers/`, `services/`, and `workers/`
- `backend/alembic/` for database migrations
- `frontend/` for the static web UI (`index.html`, `css/`, `js/`)
- project-root files such as `docker-compose.yml` and `.env.example` for local infrastructure and configuration

## Build, Test, and Development Commands
There is no runnable app in the repository yet. When scaffolding starts, prefer the commands below and document any additions in the PR:
- `docker compose up --build` to start FastAPI, PostgreSQL, Redis, and workers locally
- `uvicorn backend.app.main:app --reload` to run the API without Docker
- `alembic upgrade head` to apply database migrations
- `pytest` to run backend tests

Keep commands copy-pasteable and aligned with the structure in `PRD.md`.

## Coding Style & Naming Conventions
Use 4 spaces for Python and 2 spaces for HTML, CSS, and JavaScript. Prefer `snake_case` for Python modules, functions, and variables; use `PascalCase` for Pydantic and SQLAlchemy classes; use lowercase, descriptive filenames such as `anomalia_service.py` or `upload.js`.

Format Python with `black` and sort imports with `isort`. Keep frontend JavaScript framework-free unless the PRD is updated.

## Testing Guidelines
Add tests alongside implementation. Use `pytest` for backend logic and place tests under `backend/tests/` with names like `test_uploads.py` and `test_anomalia_service.py`. Focus coverage on anomaly rules, API validation, and export behavior. Include at least one happy-path and one failure-path test for each new service or endpoint.

## Commit & Pull Request Guidelines
Current history uses short, imperative commit subjects, for example: `Create PRD.md` and `Initial commit`. Continue with concise, action-first messages such as `Add upload router` or `Implement CNPJ validator`.

Each pull request should include:
- a brief summary of the change
- links to related issues or PRD sections
- test evidence (`pytest`, manual API check, or UI screenshots when applicable)
- notes on config, schema, or migration changes

## Security & Configuration Tips
Do not commit `.env` files, API keys, sample fiscal documents, or database dumps. Keep secrets in environment variables and provide safe defaults in `.env.example`.
