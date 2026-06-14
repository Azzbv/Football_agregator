# API Reference

REST API for the Football Data Platform. All endpoints are served by the single
app process under `http://<host>:8000`. Interactive OpenAPI docs are available at
`/docs` (Swagger UI) and the machine-readable schema at `/openapi.json`.

- **Base URL**: `/` (API under `/api`, UI under `/ui`, health at `/health`)
- **Content type**: `application/json` for requests and responses
- **Errors**: `application/problem+json` (RFC 9457), see [Errors](#errors)
- **Version**: `0.1.0`

## Conventions

### Pagination

Typed browse endpoints return a `PageResponse` envelope; generic browse returns
a `DocPage`. Both use 1-indexed paging.

| Param  | Type | Default | Range  | Description                                   |
|--------|------|---------|--------|-----------------------------------------------|
| `page` | int  | `1`     | `>= 1` | 1-indexed page number                         |
| `size` | int  | `20`    | `1..200` | Page size                                   |
| `sort` | str  | —       | —      | `field:asc\|desc`, comma-separated, e.g. `match_date:desc,source:asc` |

Response envelope fields: `items`, `page`, `size`, `total`, `pages`.

Only allow-listed fields may be used for `sort` and equality filters on each
endpoint; unknown fields return `422`.

### Identifiers

Unified records use a deterministic `match_id` / `player_id` / etc. of the form
`{source}:{source_ref}`. Raw records are addressed by their natural key
`(entity, source_ref)` within a `raw_{source}` collection.

---

## Health

### `GET /health`

Liveness probe. Returns `200` whenever the process is up.

```json
{ "status": "ok" }
```

### `GET /health/ready`

Readiness probe. Pings MongoDB; returns `200` only when the database responds.

---

## Ingestion

Ingestion is API-driven. Each enabled source adapter fetches from its upstream,
stores raw documents, and triggers unification in-process.

### `POST /api/ingestion/run`

Trigger an ingestion run for all enabled sources, or one named source.

| Param    | In    | Required | Description                                   |
|----------|-------|----------|-----------------------------------------------|
| `source` | query | no       | One of `statsbomb`, `openfootball`, `fbref`, `understat`. Omit for all enabled. |

**Response** `RunResult` — written counts per source:

```json
{ "written": { "statsbomb": 120, "openfootball": 38 } }
```

Unknown `source` returns `422`.

### `GET /api/ingestion/runs`

Recent ingestion audit records, newest first.

| Param   | In    | Default | Range    |
|---------|-------|---------|----------|
| `limit` | query | `50`    | `1..200` |

**Response** `IngestionRun[]`:

```json
[
  {
    "source": "statsbomb",
    "status": "success",
    "record_count": 120,
    "started_at": "2026-06-13T14:00:00Z",
    "finished_at": "2026-06-13T14:01:12Z",
    "error_summary": null
  }
]
```

`status` is one of `success`, `failure`, `partial`.

---

## Raw data

Raw documents are stored verbatim per source in `raw_{source}` collections,
keyed by `(entity, source_ref)`.

### `GET /api/raw/{source}`

Browse raw documents for a source (generic JSON page).

| Param    | In    | Required | Description                                   |
|----------|-------|----------|-----------------------------------------------|
| `source` | path  | yes      | `statsbomb` / `openfootball` / `fbref` / `understat` |
| `page`   | query | no       | See [pagination](#pagination)                 |
| `size`   | query | no       | See [pagination](#pagination)                 |
| `sort`   | query | no       | Sortable: `match_id`, `player_id`, `team_id`, `match_date`, `source`, `source_ref` |
| `filter` | query | no       | JSON object of equality filters, e.g. `{"entity":"match"}` |

**Response** `DocPage` (each item is a raw document with `entity`, `source_ref`,
`payload`, `fetched_at`, and possibly `edited_at`).

### `PUT /api/raw/{source}`

Edit one raw document's **payload**, addressed by its natural key. Only the
payload is mutable; `(entity, source_ref)` is immutable and an `edited_at`
marker is set.

> A subsequent ingestion run for the same `(entity, source_ref)` overwrites a
> manual edit by design — raw stays a faithful mirror of the source.

**Body** `RawPayloadEdit`:

```json
{
  "entity": "match",
  "source_ref": "1001",
  "payload": { "id": "1001", "home": { "title": "Team A" } }
}
```

**Response** `200` the full updated raw document, or `404` if no document
matches the key.

### `GET /api/raw/{source}/{entity}`

Typed raw browse scoped to one entity, returning `RawDocument` items.

| Param        | In    | Required | Description                |
|--------------|-------|----------|----------------------------|
| `source`     | path  | yes      | Source name                |
| `entity`     | path  | yes      | Logical entity, e.g. `match` |
| `source_ref` | query | no       | Exact-match filter         |
| `page`/`size`/`sort` | query | no | See [pagination](#pagination) |

---

## Unified data

The unification anti-corruption layer maps raw, source-shaped documents onto
source-agnostic unified DTOs in normalized collections.

### Typed collections

Each returns a `PageResponse` of the corresponding DTO and supports equality
filters on the listed fields.

| Endpoint            | Item DTO      | Filterable fields                                              |
|---------------------|---------------|---------------------------------------------------------------|
| `GET /api/matches`      | `Match`       | `source`, `league_id`, `season_id`, `competition`, `match_id`, `match_date` |
| `GET /api/events`       | `Event`       | `match_id`, `player_id`, `event_type`, `team_id`, `source`    |
| `GET /api/players`      | `Player`      | `player_id`, `country`, `position`, `source`, `name`          |
| `GET /api/team-stats`   | `TeamStats`   | `team_id`, `match_id`, `season_id`, `league_id`, `source`     |
| `GET /api/player-stats` | `PlayerStats` | `player_id`, `match_id`, `team_id`, `season_id`, `league_id`, `source` |

Example:

```bash
curl "http://localhost:8000/api/matches?competition=PL&sort=match_date:desc&size=10"
```

### `GET /api/unified/{collection}`

Generic JSON browse over any unified collection (`matches`, `events`,
`players`, `team_stats`, `player_stats`). Same params as
`GET /api/raw/{source}`; returns a `DocPage`. Unknown collection returns `422`.

---

## Match aggregates

A denormalized "everything about one match" document, materialized into the
`match_aggregates` collection by joining the unified collections on `match_id`
(players are resolved from the ids referenced by events and player_stats).

### `POST /api/aggregate/rebuild`

(Re)materialize aggregates. Idempotent. Run after ingestion or a pipeline run.

| Param      | In    | Required | Description                          |
|------------|-------|----------|--------------------------------------|
| `match_id` | query | no       | Rebuild only this match; omit for all |

**Response** `RebuildResult`:

```json
{ "written": 42 }
```

### `GET /api/aggregate/matches`

Page over materialized aggregates.

| Param | In | Description |
|-------|----|-------------|
| `page`/`size`/`sort` | query | See [pagination](#pagination); sortable by `match_id` |

**Response** `PageResponse<MatchAggregate>`.

### `GET /api/aggregate/matches/{match_id}`

One fully-grouped match. Returns `404` if not yet materialized (rebuild first).

**Response** `MatchAggregate`:

```json
{
  "match_id": "statsbomb:1",
  "match": { "match_id": "statsbomb:1", "home_team": { "team_id": "t1", "name": "Home" }, "...": "..." },
  "team_stats": [ { "team_id": "t1", "match_id": "statsbomb:1", "...": "..." } ],
  "player_stats": [ { "player_id": "p1", "match_id": "statsbomb:1", "...": "..." } ],
  "events": [ { "event_id": "e1", "match_id": "statsbomb:1", "event_type": "shot", "...": "..." } ],
  "players": [ { "player_id": "p1", "name": "Player One", "...": "..." } ],
  "total_events": 1,
  "built_at": "2026-06-13T14:05:00Z"
}
```

---

## Transform tools

### `GET /api/tools`

Descriptors for all registered transform step types, used by the UI to render
schema-driven config forms.

**Response** `ToolDescriptor[]`:

```json
[
  { "type": "extract", "title": "ExtractConfig", "config_schema": { "...": "JSON Schema" } }
]
```

Built-in step types: `extract`, `rename`, `duplicate`, `constant`, `default`,
`cast`, `trim`, `lookup`, `concat`, `split`, `drop`, `filter`.

---

## Pipelines

A pipeline is a declarative document mapping a source collection to a target
collection through an ordered list of transform steps.

### `GET /api/pipelines`

List all pipelines. **Response** `Pipeline[]`.

### `POST /api/pipelines`

Create a pipeline. **Body** `Pipeline` (without `id`). **Response** `201` with
the created `Pipeline`.

```json
{
  "name": "understat-matches",
  "source_collection": "raw_understat",
  "target_collection": "matches",
  "upsert_key": ["match_id"],
  "steps": [
    { "type": "extract",  "config": { "source_path": "payload.id", "target_path": "match_id" } },
    { "type": "constant", "config": { "target_path": "source", "value": "understat" } },
    { "type": "filter",   "config": { "target_path": "match_id", "op": "exists" } }
  ]
}
```

### `GET /api/pipelines/{pipeline_id}`

Fetch one pipeline. `404` if absent.

### `PUT /api/pipelines/{pipeline_id}`

Replace a pipeline. **Body** `Pipeline`. **Response** updated `Pipeline`.

### `DELETE /api/pipelines/{pipeline_id}`

Delete a pipeline. **Response** `204`.

### `POST /api/pipelines/{pipeline_id}/preview`

Dry-run against sample source records. **No writes.**

| Param   | In    | Default | Range    |
|---------|-------|---------|----------|
| `limit` | query | `10`    | `1..100` |

**Response** `PreviewItem[]` — for each record: `input`, `output` (or `null` if
dropped), `dropped`, `drop_reason`, and per-step `lineage`.

### `POST /api/pipelines/{pipeline_id}/run`

Execute and upsert into the target collection; persist per-record lineage and a
run-status document.

**Body** (optional): `{ "error_mode": "skip" }` — `skip` (record and continue)
or `fail_fast` (abort on first error).

**Response** `PipelineRun`:

```json
{
  "id": "…",
  "pipeline_id": "…",
  "status": "success",
  "started_at": "2026-06-13T14:10:00Z",
  "finished_at": "2026-06-13T14:10:03Z",
  "input_count": 2,
  "output_count": 2,
  "skipped_count": 0,
  "errors": []
}
```

`status` is one of `success`, `failure`, `partial`.

---

## Pipeline runs & lineage

### `GET /api/pipeline-runs`

Run history, newest first.

| Param         | In    | Default | Range    |
|---------------|-------|---------|----------|
| `pipeline_id` | query | —       | filter to one pipeline |
| `limit`       | query | `50`    | `1..200` |

**Response** `PipelineRun[]`.

### `GET /api/pipeline-runs/{run_id}`

One run by id. `404` if absent.

### `GET /api/lineage`

Field-level lineage for a single unified record.

| Param    | In    | Required | Description                |
|----------|-------|----------|----------------------------|
| `target` | query | yes      | Target collection, e.g. `matches` |
| `id`     | query | yes      | Target record id (upsert-key value) |

**Response** `LineageDoc` — `entries[]` each with `step_type`, `source_paths`,
`target_path`, `before_value`, `after_value`, `note`.

---

## Errors

All errors use `application/problem+json` (RFC 9457):

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "no match aggregate for match_id 'x' (rebuild first)",
  "instance": "http://localhost:8000/api/aggregate/matches/x"
}
```

| Status | When                                                          |
|--------|---------------------------------------------------------------|
| `400`  | Malformed request (FastAPI request validation)                |
| `404`  | Resource not found (`NotFoundError`)                          |
| `422`  | Domain/validation failure — unknown source/collection, bad sort/filter field, invalid step config (`ValidationFailedError`) |
| `500`  | Unhandled domain error (`FdpError`)                           |

---

## Schemas

Key field shapes (`*` = required; `| null` = nullable). Every unified DTO also
carries provenance: `source` (enum `statsbomb`/`openfootball`/`fbref`/
`understat`), `source_ref`, and `ingested_at`.

### Team
- `team_id*`: string
- `name*`: string

### Match
- `match_id*`: string — `{source}:{source_ref}`
- `league_id`, `season_id`, `competition`: string | null
- `match_date`: datetime | null
- `home_team*`, `away_team*`: `Team`
- `home_score`, `away_score`: int | null

### Event
- `event_id*`, `match_id*`: string
- `minute`, `second`: int | null
- `team_id`, `player_id`: string | null
- `event_type*`: string
- `x`, `y`: float | null

### Player
- `player_id*`, `name*`: string
- `country`, `position`: string | null

### TeamStats
- `team_id*`: string; `match_id`, `league_id`, `season_id`: string | null
- `goals`, `shots`: int | null; `xg`, `possession`: float | null

### PlayerStats
- `player_id*`: string; `team_id`, `match_id`, `league_id`, `season_id`: string | null
- `minutes`, `goals`, `assists`, `shots`: int | null; `xg`: float | null

### MatchAggregate
- `match_id*`: string; `match*`: `Match`
- `team_stats`, `player_stats`, `events`, `players`: arrays of the respective DTOs
- `total_events`: int; `built_at`: datetime | null

### Pipeline
- `id`: string (assigned on create)
- `name*`, `source_collection*`, `target_collection*`: string
- `steps`: array of `StepConfig` (`{ id?, type*, config }`)
- `upsert_key`: array of string
- `created_at`, `updated_at`: datetime | null

### PreviewItem
- `source_id`: string | null
- `input*`: object; `output*`: object | null
- `dropped`: bool; `drop_reason`: string | null
- `lineage`: array of `LineageEntry`

### PipelineRun
- `id`, `pipeline_id*`: string
- `status*`: enum `success`/`failure`/`partial`
- `started_at*`, `finished_at`: datetime
- `input_count`, `output_count`, `skipped_count`: int
- `errors`: array of `RecordError` (`{ source_id, message }`)

### LineageDoc
- `target_collection*`, `target_id*`, `source_collection*`, `pipeline_id*`, `run_id*`: string
- `source_id`: string | null
- `entries`: array of `LineageEntry` (`step_id`, `step_type`, `source_paths[]`, `target_path`, `before_value`, `after_value`, `note`)

### RawPayloadEdit
- `entity*`, `source_ref*`: string
- `payload*`: any JSON
