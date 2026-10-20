# Data360

Data360 prepares trusted borrower data for credit memos. Upload exports from internal systems and vendor feeds (Excel or CSV). Data360 then:

- recognises the file layout and the borrowers in it;
- scores the data on seven quality criteria;
- cleans what it safely can, logging every change, and escalates the rest to named owners;
- publishes standard definitions (metrics, KPIs and a master record) for the credit memo;
- builds the credit memo, with a source on every value, compliance checks and an approval chain;
- plans and tracks the fixes: gaps, a costed roadmap, project plans and a fix list by uploaded file.

The console follows the three-phase Data360 framework. Each phase unlocks when the one before it is signed off:

| Phase | Steps | Cleared when |
|---|---|---|
| 1 · Assess & Improve | 1 Source (Collector, Seeker, source tasks) · 2 Assess · 3 Clean · 4 Normalise · 5 Credit memo (5.1 Prepare to 5.5 Review and retain) | every step is current and the memo is retained (SHA-256 fingerprint) |
| 2 · Improve & Plan | 6 Gap analysis · 7 Recommendations · 8 Confidence by domain · 9 Roadmap and business case | the roadmap is approved |
| 3 · Transform | 10 Stabilise · 11 Standardise · 12 Optimise · 13 Transform, each with a project plan | all four stages are completed |

Alongside: an executive summary and detailed source report (Word or HTML), the **Rules & policies** checklist (65 rules; switching one off removes its checks from the memo), and the **fix plan**, which maps every change and open issue back to the uploaded file it came from. Reports and plans download as Word and Excel files; source files are never changed.

If an earlier step is re-run (new files, a new Clean or Normalise run), the work built on it starts again: the memo returns to draft, and Phases 2 and 3 relock until it is retained again.

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
  app/engine/   golden record, Assess, Clean, Normalise, pick-list extras, credit memo,
                Phase 2, Phase 3, fix plan, project plans, reports (Word via python-docx, Excel via openpyxl)
  app/workspace.py  per-borrower memo / Phase 2 / Phase 3 state and phase gating
  app/api/      REST endpoints
  alembic/      database migrations (applied automatically on start)
  tests/        pytest, including a detection check against the sample answer key
frontend/src/   pages: About, Console (dashboard), Phase 1, credit memo, Phase 2, Phase 3, Fix plan, Upload, Users & audit.
                Later-step screens are described by the API as sections and drawn by one renderer (components/sections.tsx).
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

- **Source: Collector.** You choose which uploaded sources are in scope and which credit-memo outputs you need (borrower profile, facility summary, KYC and sanctions, and so on). It shows the coverage of each output: which evidence is held, where, and what is missing. It can also add an out-of-scope source and run again. Assess, Clean and Normalise then use only the sources in scope.
- **Source: Seeker.** It searches every uploaded file for identity attributes (registration number, legal name, country, beneficial owner and others, including attributes you type yourself) and shows every value, where it was found, and whether the sources agree. Missing attributes can be marked as requested from an outside source (GLEIF, ACRA and others). Its findings feed Completeness and Consistency in Assess, and Clean escalates anything missing or unresolved.
- **Golden record.** For each field, the golden source wins (for example, Corporate Registry for the registration number, or Moody's for the rating), using its latest record that isn't flagged wrong, inconsistent or stale. If the golden source has no value, the value with the most support across sources wins, weighted by how reliable each source is. These rules are in `backend/app/engine/reference.py`.
- **Assess** detects issues from the data itself: disagreement with the golden source, conflicts between sources, values with the wrong format for their type, missing fields, records older than 90 days, and feeds that are behind their refresh cycle. Quality flags supplied by a data provider are used only as extra evidence. The sample dataset ships an answer key of seeded defects that the engine never reads, and `tests/test_engine.py` checks that **every seeded defect is detected**.
- **Clean** never edits the original data. It records changes, and replaying them produces version **v1.1 (cleaned)** while v1.0 (as sourced) is kept. **Assess** then scores the cleaned data and shows before and after. If new files arrive after a run, that run is marked **Out of date**.
- **Roles:**
  - **Admin:** everything, including users and the audit log;
  - **Analyst:** upload files and run steps;
  - **Viewer:** read only.

  Every sign-in, upload, run, export and user change is recorded in the audit log.

---

## The assistant ("Ask Data 360")

A chat panel on every page answers questions about the selected client (the credit memo decision, which sources disagree, which files to fix first) and general credit and regulatory questions. It looks facts up through server-side lookups; it never sees the database directly.

**Controls**

- **Off for every client until an administrator switches it on** (in the panel). The switch, and every question, are recorded in the audit log.
- **Redaction:** client names, identifiers, people's names, emails and phone numbers are replaced with tokens such as `[CLIENT-1]` before anything reaches the model, and put back in the answer. Personal-data values are masked in lookups. Turn off with `AI_REDACT=false` only for a model that runs on your own servers.
- **Provider and region set on the server only.** No key ever reaches the browser.

**Use the free local model (default)**

```bash
docker compose --profile ai up -d   # starts Ollama and downloads qwen2.5:7b (about 5 GB) the first time
```

It needs about 8 GB of free memory and answers in 10 to 60 seconds on a CPU. On a smaller machine set `AI_MODEL=qwen2.5:3b` in `.env`, then run the command again.

**Use a cloud provider instead** (set in `.env`, then `docker compose up -d`):

| `AI_PROVIDER` | Also set | Credentials |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | the key |
| `bedrock` | `AI_MODEL` (the model ID enabled in your AWS account), `AWS_REGION` | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, or an instance role |
| `vertex` | `AI_MODEL`, `VERTEX_PROJECT`, `VERTEX_REGION` | Google application default credentials (mount a service-account file and set `GOOGLE_APPLICATION_CREDENTIALS`) |

Pick a region your bank approves (for example `ap-southeast-1` or `asia-southeast1` for Singapore). Set `AI_PROVIDER=off` to remove the assistant entirely.

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
- Uploaded files stay inside the `uploads` Docker volume, and data stays in the `db` volume. Nothing is sent outside the machine unless you choose a cloud provider for the assistant and switch it on for a client; even then names and identifiers are redacted first.
- `.env` is excluded from git (in `.gitignore`), so never commit real secrets.

## Roadmap

1. **Memo versioning**: keep earlier retained memos when inputs change, lock critical rules, and freeze the rule set with each memo.
2. **Background jobs and object storage** (Redis worker, S3/MinIO) for large folders, connectors (SharePoint, S3, databases), and bank single sign-on (OIDC, Azure AD or Okta).
