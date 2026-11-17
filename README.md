# Medical Resident Learning Assistant

A runnable medical-resident **learning support** system with FastAPI, Next.js, PostgreSQL persistence, authentication, and a read-only Neo4j learning library. Curriculum, source-linked knowledge, personal notes, reading progress, and ungraded self-study work without a running model server. See [the study workspace guide](docs/study-workspace.md) for current routes, setup, and limits.

> This project does not diagnose disease, recommend treatment, analyze real patient cases, or provide clinical decision support. The mock AI deliberately produces no medical answer. Do not upload real patient data.

## Current architecture

- **Frontend:** Next.js 16.2, React 19.2, TypeScript, App Router, and a small centralized fetch client.
- **Backend:** Python 3.12, FastAPI, async SQLAlchemy 2, Pydantic Settings, JWT, and Argon2 password hashing.
- **Database:** PostgreSQL 16 with pgvector. Alembic owns the initial schema migration.
- **Knowledge library:** read-only Neo4j queries, keyword search, Curriculum/HMU evidence, relationships, and authenticated source PDFs. No embeddings or model calls are used for browsing.
- **Storage:** local uploads through a `FileStorage` protocol, plus authenticated, allowlisted source PDFs for the knowledge library.
- **AI boundary:** provider/retriever protocols plus safe mock implementations. Business modules do not import a vendor SDK.
- **Deployment:** a three-service Docker Compose stack. Migration is an explicit one-shot command, avoiding startup races.

See [architecture details](docs/architecture.md) and [database notes](docs/database.md).

## Repository structure

```text
apps/backend/     FastAPI application, Alembic, seed and tests
apps/frontend/    Next.js application
data/uploads/     local development document storage (contents ignored)
docs/             architecture, database and roadmap documentation
infra/            reserved for later deployment configuration
scripts/          reserved for cross-platform project scripts
docker-compose.yml
Makefile
```

## Requirements and pinned baseline

- Docker Engine with Compose v2 (recommended), or PostgreSQL 16 + pgvector locally
- Python 3.12 for direct backend development
- Node.js 22 and npm 11 for direct frontend development

Key versions are constrained in `apps/backend/pyproject.toml` and locked in `apps/frontend/package-lock.json`. The frontend uses the stable Next.js 16.2 line documented by the [official Next.js release announcement](https://nextjs.org/blog/next-16-2).

## Configuration

```bash
cp .env.example .env
```

Replace `JWT_SECRET_KEY` and all local passwords outside disposable local development. `NEXT_PUBLIC_API_BASE_URL` is browser-visible by design and must point to the `/api/v1` backend URL. CORS origins are comma-separated. Uploaded file size is controlled by `MAX_UPLOAD_SIZE_MB`.

No AI API key is needed for the study workspace. Keep the application providers set to `mock`. Compose fixes `MODEL_CALLS_ENABLED=false`, and the backend blocks external model providers while this setting is false. Extraction CLI configuration is separate and is not invoked by the web application.

## Run with Docker

```bash
docker compose up --build -d db
docker compose run --rm backend alembic upgrade head
docker compose up --build backend frontend
```

Open `http://localhost:3000`; API documentation is at `http://localhost:8000/docs`. Migration is intentionally separate: multiple web containers must not race to alter the schema.

Equivalent convenience commands are `make up`, `make down`, `make logs`, `make migrate`, `make seed`, `make test`, and `make lint` on systems with Make.

## Seed local development data

After migration, set the `SEED_ADMIN_*` and `SEED_LEARNER_*` values in `.env`, then run:

```bash
docker compose run --rm backend python -m app.scripts.seed
```

The idempotent seed creates one admin, one learner, `Demo Specialty`, `Demo Topic 1`, and `Demo Topic 2`. Defaults shown in `.env.example` are for local development only and must be changed anywhere else.

## Direct development

Backend (set `DATABASE_URL` to a reachable PostgreSQL database):

```bash
cd apps/backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"  # Windows
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd apps/frontend
npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run dev
```

## API endpoints

All non-system endpoints require a bearer access token.

| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/health` | Public |
| GET | `/api/v1/ready` | Public; checks database |
| POST | `/api/v1/auth/register` | Public; creates learner |
| POST | `/api/v1/auth/login` | Public |
| GET | `/api/v1/auth/me` | Authenticated |
| GET | `/api/v1/topics` | Authenticated |
| POST | `/api/v1/topics` | Admin |
| GET | `/api/v1/topics/{topic_id}` | Authenticated |
| GET | `/api/v1/documents` | Authenticated |
| POST | `/api/v1/documents/upload` | Admin |
| GET | `/api/v1/documents/{document_id}` | Authenticated |
| POST | `/api/v1/ai/rag/query` | Authenticated; mock only |
| GET | `/api/v1/knowledge/status`, `/search`, `/node`, `/curriculum`, `/sources` | Authenticated; read-only Neo4j library |
| GET | `/api/v1/knowledge/pdf/{source_id}` | Authenticated; allowlisted source PDF |
| GET / PUT | `/api/v1/study/record` | Own notes, bookmarks and manual reading state |
| GET | `/api/v1/study/summary`, `/records`, `/sessions` | Own study activity |
| POST | `/api/v1/study/sessions` | Ungraded source-question snapshot; idempotent key |
| GET / PUT | `/api/v1/study/sessions/{id}` | Own draft answers / immutable submitted session |
| GET / POST | `/api/v1/study/reviews` | Read source-review history / admin adds a versioned review |

JWT refresh and account administration are not included.

## Tests and quality checks

```bash
cd apps/backend
.venv/Scripts/python -m ruff check app tests
.venv/Scripts/python -m pytest -q

cd ../frontend
npm run lint
npm run typecheck
npm run build
```

Backend integration tests use a temporary SQLite database for speed and isolation. PostgreSQL-specific extension/migration behavior must additionally be checked with Docker in an environment where Docker is installed.

## Implemented

- Full initial relational model and pgvector column
- Consistent error envelope, request IDs, JSON logs, validation, and hidden production traces
- Registration/login/current-user flow and admin dependency
- Topic read/create APIs
- validated PDF/TXT/Markdown upload through local storage
- LLM, embedding, reranker, retrieval, and storage interfaces
- safe mock RAG endpoint
- required frontend routes, auth forms, learning query, and admin upload form
- Dockerfiles, Compose, migration, seed, tests, lint, typecheck, and documentation

The prototype stores its access token in `localStorage`. This is simple for development but vulnerable to token theft if an XSS flaw exists; production should use a reviewed cookie/session design, CSP, refresh/revocation strategy, and CSRF controls where applicable.

## Intentionally not implemented

Automated background ingestion/OCR, adaptive recommendations, formal examinations, and validated mastery assessment remain outside the implemented study MVP. The repository now includes source retrieval, versioned grading packages and Medical/Teaching API transports; remote inference stays disabled until endpoints, credentials and model identities are configured and checked. Separate extraction/training outputs are not evidence of production AI grading or expert approval. `/exams` is ungraded self-study, and `/progress` records personal reading activity rather than competency scores. The learning graph still needs expert review and confirmed course syllabi.

## Next roadmap step

Confirm course syllabi and source/expert-review scope, then validate the configured Medical/Teaching deployment with real endpoints. Production authentication/session hardening, background ingestion jobs, formal assessment, and operational deployment remain separate work. See [study workspace](docs/study-workspace.md) and the historical [development roadmap](docs/development-roadmap.md).

## Current workspace and deployment

The student workspace includes exercise search, answering, source-linked results and saved history; administrators can author against excerpts, save drafts and publish separately. See the [UI handoff](docs/ui/ui-completion-report.md), [design system](docs/ui/design-system.md) and [RunPod model configuration](docs/runpod-model-api.md).

Create a local `.env` from `.env.example` and replace its credential placeholders. Source books, teacher materials, model/adapter weights, database contents and generated evidence/benchmark artifacts stay local. Cloning this repository does not restore the current learning database or Neo4j data; see [publication and data boundaries](docs/github-publication.md).

