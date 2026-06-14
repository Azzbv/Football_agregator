# Football Data Platform

A modular-monolith async platform that ingests open football data from multiple
sources (StatsBomb, openfootball, FBref, Understat), stores **raw** and
**unified** representations in MongoDB, and exposes a REST API and UI to browse,
edit and transform both.

It also provides a **declarative ETL transform + pipeline orchestration layer**
and a **NiceGUI UI** to build pipelines and inspect the raw-to-unified mapping
with full field-level lineage.

## Features

- **Multi-source ingestion** — StatsBomb, openfootball, FBref, Understat behind
  a single `SourcePort` Protocol; each source independently enabled and configured.
- **Raw + unified storage** — source documents stored verbatim in `raw_{source}`
  collections; an anti-corruption layer maps them onto source-agnostic unified
  DTOs in normalized collections.
- **Declarative ETL** — 12 built-in transform steps composed into pipelines that
  are themselves data; add a step type with a single decorator and zero UI changes.
- **Field-level lineage** — every transform records before/after for every field,
  queryable per unified record.
- **Match aggregates** — a denormalized "everything about one match" document
  materialized from the normalized collections.
- **Browser + JSON editor UI** — browse raw/unified/aggregate data in a VS Code-like
  JSON editor with pagination; edit raw payloads in place.
- **Single entry point** — API (`/api`), UI (`/ui`) and health (`/health`) served
  by one Uvicorn process in one container.

## Architecture

Modular monolith, single deployable async app, DDD bounded contexts, hexagonal
ingestion, anti-corruption layer (ACL) for raw-to-unified. Six installable
packages (plain pip, editable), one composition root:

| Package           | Responsibility                                                                             |
|-------------------|--------------------------------------------------------------------------------------------|
| `fdp-shared`      | Domain DTOs, config, Mongo client/indices, logging, exceptions, query primitives           |
| `fdp-ingestion`   | `SourcePort` Protocol + adapters, polite HTTP, runner, raw repository, status               |
| `fdp-unification` | ACL mappers; transform engine (steps + registry); pipeline orchestration; match aggregates  |
| `fdp-api`         | FastAPI routers (browse, raw edit, tools, pipelines, runs, lineage, aggregate), problem+json |
| `fdp-ui`          | NiceGUI pages mounted on the same FastAPI app (builder, data browser/editor, lineage)        |
| `fdp-app`         | Composition root: wiring, ASGI app, `fdp` console script                                     |

Contexts talk only through public package interfaces. Raw-ingest publishes an
in-process `RawIngested` event that the unification service consumes, so
ingestion never imports unification.

### Transform + orchestration layer

- **Transform steps** are single-purpose, declaratively-configured units sharing
  one contract: `apply(ctx) -> StepResult`. Each is built from a typed Pydantic
  config model (whose JSON schema drives the UI form) and emits structured
  lineage for every change. Built-ins: `extract, rename, duplicate, constant,
  default, cast, trim, lookup, concat, split, drop, filter`. A `StepRegistry`
  maps `type -> (class, config model)`; adding a step is one `@registry.register`
  with no orchestrator or UI change (the UI discovers it via `GET /api/tools`).
- **Pipelines** are declarative documents (`pipelines` collection):
  `Pipeline(name, source_collection, target_collection, steps[], upsert_key[])`.
- **`PipelineExecutor`** interprets a pipeline per source record, threading a
  working record through the steps and accumulating lineage. Preview/dry-run
  returns input-to-output plus lineage with no writes; a commit run upserts
  unified records by `upsert_key`, persists per-record lineage, and records a
  `pipeline_runs` status document.
- **Lineage storage** uses a dedicated `lineage` collection (keyed by
  `target_collection + target_id`). This is chosen over embedding a `_lineage`
  field so unified docs stay clean and queryable and lineage can be large
  without bloating them; it is still fetched in one indexed lookup per record.
- **Match aggregates** are materialized into `match_aggregates` by joining the
  normalized collections on `match_id` (players resolved from the ids referenced
  by events and player_stats), so the grouped read is one indexed lookup.

## Project layout

```
packages/
  shared/        fdp_shared      domain DTOs, config, mongo, logging, query
  ingestion/     fdp_ingestion   adapters, http, runner, raw_repository, status
  unification/   fdp_unification mappers, transform/, orchestration/, aggregate
  api/           fdp_api         routers/, dependencies, errors, schemas, params
  ui/            fdp_ui          app, pages, layout, forms, client
  app/           fdp_app         factory (composition root), main, cli
docs/
  api.md         full REST API reference
Dockerfile  docker-compose.yml  Makefile  requirements*.txt  .env.template
```

## Prerequisites

- Python 3.12+ and `pip` (the standard `venv` module is used; no uv).
- Docker + Docker Compose.
- A MongoDB reachable at `localhost:27171` (the default target is the **host**
  instance; see compose for the optional self-contained Mongo).

## Quick start

```bash
make up           # copies .env.template -> .env if absent, then docker compose up --build
# or directly:
cp .env.template .env
docker compose up --build
```

The app comes up on `http://localhost:8000` and connects to host Mongo at
`:27171` via `MONGODB_URI` (config only, no code changes). Switching to a
compose-managed Mongo is a one-line `.env` edit (uncomment the `mongo` service).

- UI: `http://localhost:8000/ui` (root `/` redirects there)
- API: `http://localhost:8000/api/*`
- OpenAPI docs: `http://localhost:8000/docs`

First end-to-end run:

```bash
curl -X POST http://localhost:8000/api/ingestion/run   # ingest enabled sources
curl -X POST http://localhost:8000/api/aggregate/rebuild  # materialize aggregates
# then open http://localhost:8000/ui/data to browse
```

## Local development

Dependencies are plain `requirements.txt` files; each package is installed
editable with `pip install -e`, in dependency order. One command sets it up:

```bash
make venv          # python -m venv .venv + pip install everything (editable)
```

Or by hand (cross-platform helper scripts are provided):

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt  # runtime + test/lint tooling
scripts/install.sh --dev             # Windows: .\scripts\install.ps1 -Dev
```

Common targets:

```bash
make run          # serve API + UI locally against host Mongo (the `fdp` entry point)
make dev          # uvicorn --reload (API + NiceGUI hot-reload)
make lint         # ruff check + format --check
make typecheck    # strict mypy over all packages
make test         # pytest (integration tests auto-skip without Docker)
```

## Configuration

All configuration is environment-driven (`pydantic-settings`); nothing is
hard-coded. Copy `.env.template` to `.env` and edit. Key variables:

| Variable                 | Default                                            | Purpose                                       |
|--------------------------|----------------------------------------------------|-----------------------------------------------|
| `APP_PROFILE`            | `local`                                            | `local` (console logs) or `prod` (JSON logs)  |
| `LOG_LEVEL`              | `INFO`                                             | Log level                                     |
| `MONGODB_URI`            | `mongodb://localhost:27171/?directConnection=true` | Full Mongo connection string                  |
| `MONGODB_DATABASE`       | `football`                                         | Database name                                 |
| `INGESTION_ENABLED`      | `true`                                             | Global ingestion master switch                |
| `INGESTION_BATCH_SIZE`   | `500`                                              | Raw records buffered before flush + unify     |
| `SOURCE_*_ENABLED`       | varies                                             | Per-source enable flags (FBref/Understat off) |

The Mongo connection is described entirely by `MONGODB_URI`; no host or port is
assembled in code, so pointing at host Mongo versus a compose Mongo is a
config-only change. For production set `APP_PROFILE=prod` (JSON logs) and supply
a `MONGODB_URI` for your managed cluster. See `.env.template` for the full set,
including per-source URLs, dataset/competition selection and rate limits.

## Using the platform

### Trigger ingestion

```bash
curl -X POST http://localhost:8000/api/ingestion/run            # all enabled sources
curl -X POST "http://localhost:8000/api/ingestion/run?source=statsbomb"
curl http://localhost:8000/api/ingestion/runs                   # audit trail
```

FBref and Understat are **disabled by default** (`SOURCE_*_ENABLED=false`);
enable them deliberately in `.env`. FBref is hard-capped at 10 req/min or fewer
with at least 6s spacing.

### Build, preview and run a pipeline

Build it in the UI (Pipeline Builder), or via the API. A pipeline is just data:

```bash
# 1. Create a pipeline that maps raw_understat -> matches.
curl -X POST http://localhost:8000/api/pipelines -H 'content-type: application/json' -d '{
  "name": "understat-matches",
  "source_collection": "raw_understat",
  "target_collection": "matches",
  "upsert_key": ["match_id"],
  "steps": [
    {"type": "extract",  "config": {"source_path": "payload.id",      "target_path": "match_id"}},
    {"type": "extract",  "config": {"source_path": "payload.h.title", "target_path": "home"}},
    {"type": "constant", "config": {"target_path": "source", "value": "understat"}},
    {"type": "filter",   "config": {"target_path": "match_id", "op": "exists"}}
  ]
}'
# -> 201 {"id":"<pipeline_id>", ...}

# 2. Dry-run preview (NO writes): input -> output + lineage for N samples.
curl -X POST "http://localhost:8000/api/pipelines/<pipeline_id>/preview?limit=3"

# 3. Commit run: upserts unified records + persists per-record lineage.
curl -X POST http://localhost:8000/api/pipelines/<pipeline_id>/run \
     -H 'content-type: application/json' -d '{"error_mode": "skip"}'
# -> {"status":"success","input_count":2,"output_count":2,"skipped_count":0,...}

# 4. View the lineage for one unified record.
curl "http://localhost:8000/api/lineage?target=matches&id=1001"
```

### Match aggregates

A **match aggregate** is the denormalized "everything about one match in a single
object" view: the fixture with its `team_stats`, `player_stats`, `events` and the
referenced `players` embedded, joined on `match_id`. It is materialized into a
dedicated `match_aggregates` collection, so reads are a single indexed lookup.

The aggregate is rebuilt on demand (idempotent). Run a rebuild after ingestion or
a pipeline run, then read:

```bash
curl -X POST http://localhost:8000/api/aggregate/rebuild          # all (or ?match_id=...)
curl http://localhost:8000/api/aggregate/matches/statsbomb:1      # one grouped match
curl "http://localhost:8000/api/aggregate/matches?page=1&size=20" # page over all
```

### Edit raw data

A single raw document's payload can be edited in place, addressed by its natural
key `(entity, source_ref)`:

```bash
curl -X PUT http://localhost:8000/api/raw/understat -H 'content-type: application/json' -d '{
  "entity": "match",
  "source_ref": "1001",
  "payload": { "id": "1001", "h": { "title": "Team A" } }
}'
```

Only the `payload` is editable; the natural key is immutable and an `edited_at`
marker is set. A later ingestion run for the same key overwrites the edit, by
design — raw stays a faithful mirror of the source.

## The UI

NiceGUI is mounted onto the **same** FastAPI app via `ui.run_with(app)`, so
`/api/*` and `/ui*` are served by one Uvicorn process in one container. Pages:

| Page                | Path           | What it does                                                                 |
|---------------------|----------------|------------------------------------------------------------------------------|
| Data                | `/ui/data`     | Browse raw / unified / aggregate data in a VS Code-like JSON editor, paginated; edit and save raw payloads |
| Pipeline Builder    | `/ui`          | Schema-driven step forms, reorder, save a pipeline                           |
| Mapping / Lineage   | `/ui/lineage`  | Two-column source-to-target field map plus ordered before/after changes      |
| Dry-Run / Preview   | `/ui/preview`  | Run a saved pipeline against N samples (input/output side by side, no writes) |
| Runs                | `/ui/runs`     | Pipeline run history                                                          |

Scheduling is out of scope; it would hook in by wrapping `PipelineExecutor.run`
in a Prefect/Dagster flow, and the on-demand `POST /api/pipelines/{id}/run` is
the manual trigger.

## API reference

Full reference: **[docs/api.md](docs/api.md)**. Interactive OpenAPI docs are
served at `/docs` and the machine-readable schema at `/openapi.json`. Summary:

| Method               | Path                          | Description                          |
| -------------------- | ----------------------------- | ------------------------------------ |
| `GET`                | `/health`, `/health/ready`    | Liveness / readiness probes          |
| `POST`               | `/api/ingestion/run`          | Trigger ingestion (all or `?source=`)|
| `GET`                | `/api/ingestion/runs`         | Ingestion audit trail                |
| `GET`                | `/api/tools`                  | Available transform step descriptors |
| `GET` `POST`         | `/api/pipelines`              | List / create pipelines              |
| `GET` `PUT` `DELETE` | `/api/pipelines/{id}`         | Read / update / delete a pipeline    |
| `POST`               | `/api/pipelines/{id}/preview` | Dry-run (no writes)                  |
| `POST`               | `/api/pipelines/{id}/run`     | Commit run (upsert + lineage)        |
| `GET`                | `/api/pipeline-runs`          | Pipeline run history                 |
| `GET`                | `/api/lineage?target=&id=`    | Lineage for one unified record       |
| `GET` `PUT`          | `/api/raw/{source}`           | Browse / edit raw documents          |
| `GET`                | `/api/unified/{collection}`   | Browse unified documents             |
| `GET`                | `/api/matches`, `/api/events` | Typed unified collections (paged)    |
| `POST`               | `/api/aggregate/rebuild`      | (Re)materialize match aggregates     |
| `GET`                | `/api/aggregate/matches`      | Page over / read match aggregates    |

## Testing

```bash
make test    # or: pytest
```

Unit tests run anywhere. Integration tests spin up a real MongoDB via
testcontainers (`mongo:7`) and **auto-skip** if Docker/testcontainers is
unavailable, so a green run always reflects real Mongo behaviour. Quality gates:

```bash
make lint        # ruff lint + format check
make typecheck   # strict mypy over the shipped source
```