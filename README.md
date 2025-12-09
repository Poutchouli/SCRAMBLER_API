# TLDR:

-git clone repro
-docker compose up -d


open the frontend.html or the ugly view at http://localhost:18062/ with most browsers
API doc at http://localhost:18062/docs if you fancy adding to other tools

# Scrambler API

FastAPI + CLI service to profile CSVs and generate synthetic CSVs that match the original schema constraints. Includes HTML demo, Docker, and CLI tooling.

## Features
- Upload CSV (public, no auth) with hard limits: 50 MB, 100k rows.
- Automatic encoding detection (charset-normalizer) and delimiter sniffing (`,` `;` `\t` `|` heuristics).
- Two parsing modes: `fast` (sampled) and `strict` (full scan).
- Constraint inference: type, min/max length, numeric ranges, nullability, small cardinality allowed values.
- Synthetic generation with optional seed; high-entropy scrambling (strings mutated even when allowed values exist) while respecting inferred constraints and null rates.
- Simple HTML report + download page at `/` and standalone `frontend.html` (auto API base detection).
- CLI parity for profile/generate.

## Quickstart (local)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PORT=58008 uvicorn app.main:app --reload --host 0.0.0.0 --port ${PORT}
```
Open http://localhost:8000 (or `/docs` for OpenAPI).

## Docker Compose
Listens on host port 18062 (maps to container 58008 by default).
```bash
docker compose up -d --build
# Health check
curl http://localhost:18062/health
```
Stop with `docker compose down`.

### Standalone frontend
Open `frontend.html` locally or on another host; it will auto-target the API origin. You can override with `?api=http://<host>:18062` or a `<meta name="api-base">` tag.

### Environment
- `PORT` (default `58008`)
- `CORS_ORIGINS` comma-separated (default `*`)
Copy `.env.example` to `.env` to override locally.

## CLI
```bash
# Profile a CSV
python -m cli.main profile data.csv --mode strict

# Generate synthetic CSV
python -m cli.main generate data.csv --rows 5000 --seed 42 --mode fast --output synthetic.csv
```

## API
- `POST /api/profile` multipart form: `file` (CSV), optional `mode` (`fast`|`strict`). Returns inferred profile.
- `POST /api/generate` multipart form: `file`, `rows` (int), optional `mode`, `seed`. Streams `text/csv` attachment.
- `GET /` HTML demo; `GET /health` status.

## Limits & Validation
- Rejects files over 50 MB or more than 100k rows.
- MIME gate: only `text/csv`, `application/vnd.ms-excel`, `application/csv`.
- CORS: `*` by default (see `app/config.py`), adjust for production.

## Testing
```bash
python -m pytest
```

## Project Layout
- `app/` FastAPI app, services, models, config
- `templates/` HTML report page
- `cli/` Typer CLI entrypoints
- `tests/` Pytest coverage for profiling/generation
- `docker-compose.yml`, `Dockerfile`, `requirements.txt`

## Notes
- The fast parser samples first 5k rows; strict scans full file within limits.
- Synthetic output aims to stay within inferred ranges/lengths; randomness is seedable for repeatability.
