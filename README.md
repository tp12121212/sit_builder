# SIT Builder

Purview-style Sensitive Information Type (SIT) builder with a FastAPI backend and React frontend.

## Current capabilities

- Scan workbench with two scan types:
  - `Classic NLP (Current)`: local extraction + local candidate discovery.
  - `SentenceTransformer`: PowerShell `Test-TextExtraction` + `scripts/keyword_extraction.py`.
- Multi-file upload and drag/drop (including recursive folder drop in supported browsers).
- Scan progress tracking (phase, percent, current file), auto-refresh, and scan deletion.
- Candidate results with file mapping and metadata columns:
  - `SIT Category`
  - `Scan Module`
  - `OCR`
- SIT draft creation and rulepack generation/export.
- WebSocket scan status endpoint at `/v1/ws/scans/{scan_id}`.

## Architecture notes

- Backend: FastAPI + SQLAlchemy + PostgreSQL.
- Frontend: React + Vite.
- Storage: local filesystem under `data/` by default.
- Redis/Celery config exists, but local/dev scan execution is currently started via a background thread in the API (`create_scan` calls `process_scan.run(...)`) so scans run without a separate worker process.

## Repository layout

- `/backend/app/main.py`: FastAPI app and startup.
- `/backend/app/api/v1/endpoints/`: REST endpoints.
- `/backend/app/workers/tasks.py`: scan pipeline.
- `/backend/app/services/`: extraction, sentence-transformer bridge, candidate generation, rulepack builder.
- `/frontend/src/`: React app.
- `/scripts/textExctraction.ps1`: PowerShell extraction pipeline.
- `/scripts/keyword_extraction.py`: SentenceTransformer keyword scoring.
- `/docker-compose.yml`: local container stack.

## Local development

### 1) Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
export PYTHONPATH=$(pwd)/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If PostgreSQL/Redis run in Docker, ensure backend env points to localhost ports:

- `DATABASE_URL=postgresql+psycopg://sitbuilder:sitbuilder@localhost:5432/sitbuilder`
- `CELERY_BROKER_URL=redis://localhost:6379/0`
- `CELERY_RESULT_BACKEND=redis://localhost:6379/1`

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Default dev behavior from current config:

- Host: `0.0.0.0`
- Port: `443` (set via `VITE_DEV_PORT`, default `443`)
- HTTPS enabled only when certificate files exist and are configured.

## Frontend env config

Create `/frontend/.env` from `/frontend/.env.example`.

Key variables:

- `VITE_API_BASE=/v1` (recommended; uses Vite proxy to backend)
- `VITE_AZURE_CLIENT_ID=<entra-app-client-id>`
- `VITE_AZURE_TENANT_ID=<tenant-id-or-organizations>`
- `VITE_AZURE_REDIRECT_URI=<exact frontend origin>`
- `VITE_AZURE_SCOPES=openid,profile,offline_access,https://outlook.office365.com/.default`
- `VITE_DEV_HTTPS_CERT_PATH=./certs/dev-cert.pem`
- `VITE_DEV_HTTPS_KEY_PATH=./certs/dev-key.pem`
- `VITE_DEV_PORT=443`

Use relative cert/key paths for portability.

## HTTPS + mobile (iPhone/tablet) testing

To use Microsoft auth reliably on mobile/LAN origins:

1. Install and trust mkcert local CA:
   - `mkcert -install`
2. Generate cert for localhost + LAN IP:
   - `scripts/generate-dev-cert.sh <lan-ip>`
3. Ensure frontend `.env` has the cert/key paths and HTTPS origin redirect URI.
4. Add matching redirect URI(s) in Entra app registration.
5. Trust the mkcert root CA on the mobile device, then browse to your HTTPS origin.

Mobile auth behavior:

- Mobile browsers use redirect flow.
- Desktop browsers use popup flow.
- On mobile + `SentenceTransformer`, file selection is hidden until Microsoft auth succeeds.

## SentenceTransformer scan requirements

`SentenceTransformer` scan type requires on the machine running backend:

- `pwsh` installed and on `PATH`
- Exchange Online PowerShell module available
- Python dependencies from `backend/requirements.txt`
- Scripts available at configured paths:
  - `SENTENCE_TRANSFORMER_POWERSHELL_SCRIPT`
  - `SENTENCE_TRANSFORMER_PYTHON_SCRIPT`

Important:

- Browser/mobile clients do not need PowerShell installed.
- Docker images in this repo do not currently install PowerShell/Exchange module by default, so SentenceTransformer scans in containers may fail unless you extend the image.

## Scan behavior notes

- `Force OCR extraction` is only applicable for `Classic NLP`.
- For `SentenceTransformer`, `Force OCR` is disabled and result column shows `OCR = N/A`.
- `SIT Category`, extraction module, and OCR flags are persisted in candidate metadata for scan results.

## Docker

```bash
docker compose up --build
```

Default exposed services:

- API: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

## API quick examples

Create scan:

```bash
curl -X POST \
  -F "name=Sample Scan" \
  -F "files=@/path/to/file.txt" \
  http://localhost:8000/v1/scans
```

Create SIT:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"name":"Custom Employee ID","confidence_level":85}' \
  http://localhost:8000/v1/sits
```

Create rulepack:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"name":"Q1 Rulepack","sit_ids":["<sit-id>"]}' \
  http://localhost:8000/v1/rulepacks
```

## Security and production note

Current auth in backend uses a development shim (`X-Tenant-ID`, `X-User-ID` optional headers, or seeded default user). Replace with proper Entra/OIDC JWT validation before production deployment.
