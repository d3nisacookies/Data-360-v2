# Data360

Data360 prepares trusted borrower data for credit memos. Upload exports from internal systems and vendor feeds (Excel or CSV). Data360 then:

- recognises the file layout and the borrowers in it;
- scores the data on seven quality criteria;
- cleans what it safely can, logging every change, and escalates the rest to named owners;
- publishes standard definitions (metrics, KPIs and a master record) for the credit memo.

This is **Phase 1** of the Data360 framework. Its steps are Source, Assess, Clean, Normalise and Credit memo; the credit memo is the next milestone. Phases 2 and 3 move over from the demo console in later milestones.

> The sample files in `seed/sample-files` are **hypothetical**. They are synthetic test data for a Singapore structured-debt desk, with deliberate defects, and contain no real bank, borrower, rating or compliance data.

---

## Run it

You only need **Docker**. Use Docker Desktop on Windows or macOS (on Windows, turn on the WSL 2 backend), or Docker Engine on Linux. Podman and Rancher Desktop also work.

```bash
git clone https://github.com/d3nisacookies/data-360-v2.git
cd data-360-v2
cp .env.example .env        # then change JWT_SECRET and ADMIN_PASSWORD
docker compose up -d --build
```

Open **http://localhost:8080** and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`. Then go to **Upload files** and drop in the files from `seed/sample-files` (or your own).

To load the sample files without the browser:

```bash
docker compose exec api python -m app.seed /seed/sample-files
```

Everything runs in containers, so it behaves the same on every machine. Apple Silicon is supported: CI publishes images for both `amd64` and `arm64`.

| Command | What it does |
|---|---|
| `docker compose up -d --build` | Build and start everything |
| `docker compose logs -f api` | Follow the API logs |
| `docker compose down` | Stop (data is kept in Docker volumes) |
| `docker compose down -v` | Stop and **delete all data** |

### Development mode (live reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The web app is at http://localhost:5173 and the interactive API docs are at http://localhost:8000/docs.

---

## How it is built

| Container | Technology | Job |
|---|---|---|
| `web` | React + TypeScript (Vite), served by nginx | The user interface; nginx also forwards `/api` to the API |
| `api` | Python 3.12 + FastAPI | Upload, layout detection, the engine, exports, sign-in, audit log |
| `db` | PostgreSQL 16 | Source values, runs and results, users, audit trail |

```
backend/
  app/ingest/   read files, detect the layout, map columns, recognise borrowers
  app/engine/   golden record, Assess, Clean, Normalise, Excel data pack
  app/api/      REST endpoints
  alembic/      database migrations (applied automatically on start)
  tests/        pytest, including a detection check against the sample answer key
frontend/src/   pages: Borrowers, Upload (with mapping review), Borrower workspace, Users & audit
e2e/            Playwright browser test of the full journey
seed/           sample files
```

### Different file layouts

Every value is stored in one long table (`observations`), whatever layout the file had, so the engine never depends on a particular file structure.

- **Data-dictionary layout** (one row per data element: ID, data source, category, element, data type, value). This is detected from its column names.
- **Record layout** (one row per source record, one column per field). Each column is matched to a Data360 field by exact name, a known synonym (for example *Obligor*, *Facility Limit* or *Drawn*), or a close match (fuzzy matching, for typos).
- Anything the system is unsure about waits in **Needs your review**. There you can pick the sheet, change any column's field, or set the borrower or source for the whole file. Unmapped columns are kept as they are, so no data is lost.
- **Borrowers are recognised** across files even when names differ in case, punctuation or legal suffix (`HarbourVest Inc.` matches `HarbourVest`), or when they share a facility ID.
- Uploading the **same file twice is detected** by its content fingerprint (SHA-256), and the copy is not loaded again.

`seed/sample-files/other-layouts` contains a CSV with entirely different column names, which shows the mapping at work.

### How the engine decides

- **Golden record.** For each field, the golden source wins (for example, Corporate Registry for the registration number, or Moody's for the rating), using its latest record that isn't flagged wrong, inconsistent or stale. If the golden source has no value, the value with the most support across sources wins, weighted by how reliable each source is. These rules are in `backend/app/engine/reference.py`.
- **Assess** detects issues from the data itself: disagreement with the golden source, conflicts between sources, values with the wrong format for their type, missing fields, records older than 90 days, and feeds that are behind their refresh cycle. Quality flags supplied by a data provider are used only as extra evidence. The sample dataset ships an answer key of seeded defects that the engine never reads, and `tests/test_engine.py` checks that **every seeded defect is detected**.
- **Clean** never edits the original data. It records changes, and replaying them produces version **v1.1 (cleaned)** while v1.0 (as sourced) is kept. **Assess** then scores the cleaned data and shows before and after. If new files arrive after a run, that run is marked **Out of date**.
- **Roles:**
  - **Admin:** everything, including users and the audit log;
  - **Analyst:** upload files and run steps;
  - **Viewer:** read only.

  Every sign-in, upload, run, export and user change is recorded in the audit log.

---

## Tests

```bash
# backend (needs a Postgres; easiest is the dev compose db on :5432)
cd backend && pip install -r requirements-dev.txt
DATABASE_URL=postgresql+psycopg://data360:data360@localhost:5432/data360_test pytest -q

# browser journey against a running stack
cd e2e && npm install && npx playwright install chromium
BASE_URL=http://localhost:8080 ADMIN_PASSWORD=<your password> npx playwright test
```

GitHub Actions runs on every push:

1. the backend tests and a migration round-trip;
2. the frontend build;
3. building the Docker images, starting the stack and running the browser journey against it;
4. on `main`, publishing multi-architecture images to GitHub Container Registry.

---

## Security notes

- Change `JWT_SECRET` and `ADMIN_PASSWORD` in `.env` before anyone else can reach the app. In production mode, the API will not start with the default secret.
- Uploaded files stay inside the `uploads` Docker volume, and data stays in the `db` volume. Nothing is sent outside the machine.
- `.env` is excluded from git (in `.gitignore`), so never commit real secrets.

## Roadmap

1. **Credit memo (step 5)** drafted from the golden record, with the **Rules & policies** checklist. Critical rules will be locked, and rule versions frozen with each memo.
2. **AI assistant**, turned off by default, with:
   - a free local model (Ollama) as the default provider;
   - optional providers set in the config file: Anthropic, AWS Bedrock or Google Vertex, in a region the bank approves;
   - an on/off switch per client;
   - redaction of names and IDs before anything leaves the server.
3. **Phases 2 and 3** (steps 6–13), moved over from the demo console.
4. **Background jobs and object storage** (Redis worker, S3/MinIO) for large folders, connectors (SharePoint, S3, databases), and bank single sign-on (OIDC, Azure AD or Okta).
