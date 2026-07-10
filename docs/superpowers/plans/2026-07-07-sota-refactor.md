# Financial Tracker — Piano di Refactor "a regola d'arte" (SOTA)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare il Financial Tracker alla qualità strutturale del progetto AI Garage (fonte: `filippo-takeaways`), applicando le best practice SOTA dove i takeaways non coprono — senza rompere gli invarianti di produzione (dedup hash, cron Railway, webhook MacroDroid).

**Architecture:** Backend FastAPI a 3 livelli (router → service → storage) come vero package Python (`fintracker`), config con pydantic-settings, psycopg3 + connection pool + Alembic, denaro in `Decimal`. Frontend React con TanStack Query (pattern query-options factory), react-hook-form + zod, test Vitest/RTL, ESLint. CI GitHub Actions + pre-commit Lefthook/gitleaks come rete di sicurezza.

**Tech Stack:** Python 3.12, FastAPI, psycopg3 + psycopg_pool, Alembic, pydantic-settings, ruff, pyrefly, pytest · React 19, TypeScript strict, Vite 8, TanStack Query v5, react-hook-form + zod, Vitest + Testing Library · GitHub Actions, Lefthook, gitleaks.

## Global Constraints

- **Dedup hash EB immutabile**: `SHA-256(date[:10] + "|" + abs(amount) + "|" + desc_lower + "|" + currency)` — la stringa payload NON deve cambiare byte-per-byte (vedi Task 4.2 per lo shim float).
- **Tasker hash immutabile**: `SHA-256("tasker|" + %Y-%m-%dT%H:%M + "|" + abs(amount) + "|" + currency)`.
- **Manual hash immutabile**: `SHA-256("manual|" + booking_date[:19] + "|" + abs(amount) + "|" + currency)`.
- **Privacy categorizer**: solo `merchant_name` viene inviato all'API Claude — mai importi, date, account.
- **PSD2 rate limit**: 4 chiamate/account/24h — durante lo sviluppo NON invocare `/sync` o `fetch_transactions` contro l'API reale.
- **Railway cron fragile**: la schedule di `sync-cron` si perde silenziosamente se si tocca la config del servizio — il comando di avvio `uv run python pipeline.py` NON deve cambiare (per questo `pipeline.py` resta alla root come shim, Task 1.4).
- **Webhook MacroDroid**: l'URL `POST /webhook/tasker` su Railway è cablato nel telefono — resta NON versionato (fuori da `/v1`).
- **Secrets**: restano in `config/.env` (unica fonte); mai in codice o in file committati; `hmac.compare_digest` sempre per confronti di segreti.
- **Idempotenza**: `ON CONFLICT (dedup_hash) DO NOTHING` — ogni run ripetuto è sicuro.
- **Convenzioni repo**: ruff line-length 100; log via `logging.getLogger(__name__)`; niente `print()` fuori da `pipeline.py`; commit in inglese, imperativi, spiegano il *perché*.
- **Ogni fase termina con software funzionante e deployabile.** Le fasi sono in ordine di dipendenza; task nella stessa fase sono sequenziali salvo nota.

---

## 1. Confronto funzionale/logico: codebase vs takeaways

Analisi area per area. "Takeaway" = pratica documentata in `filippo-takeaways` (progetto AI Garage); "Stato attuale" = ciò che il codice fa oggi; "Azione" = fase di questo piano.

### 1.1 Backend

| Area | Takeaway (AI Garage) | Stato attuale (Financial Tracker) | Gap | Azione |
|---|---|---|---|---|
| **Layering** | Router = validazione + orchestrazione; Service = business logic (riceve session); Model = solo dati. «Business logic in routers» è nella lista *mistakes-to-avoid* | `routes/api.py` costruisce SQL, esegue query, fa shaping dei dati direttamente negli handler (218 righe). `webhook.py`/`sync.py` sono accettabili ma chiamano storage direttamente | **Alto** | Fase 3 |
| **Packaging** | Package installabile, import assoluti puliti | `sys.path.insert(0, root)` ripetuto in **18 file** — anti-pattern che rompe tooling (type checker, IDE) e richiede il `touch __init__.py` nel Dockerfile | **Alto** | Fase 1 |
| **Config** | `pydantic-settings` (`AppSettings(BaseSettings)`), tipizzata e validata | `config/settings.py` con globali di modulo e helper `_get`/`_require` manuali; nessuna validazione di tipo; secrets come `str` nudi | Medio | Fase 2 |
| **DB access** | Engine async + session injection, connection pooling, Alembic per migrazioni; «Sync database calls» in *mistakes-to-avoid* | psycopg2 sincrono, **una connessione nuova per ogni richiesta** (no pool), handler dichiarati `async def` con I/O bloccante → **bloccano l'event loop**. Schema gestito con DDL idempotente `ensure_schema` (niente storia delle migrazioni) | **Alto** | Fase 4 |
| **Denaro** | (non coperto dai takeaways — SOTA) | `float` per `amount`/`eur_amount` in modelli e parsing — errori di rappresentazione binaria su dati finanziari | Medio | Fase 4 |
| **API contract** | Envelope `{data: ...}` su tutte le risposte; versioning; error shape coerente | Nessun envelope, nessun `/v1`, errori = default FastAPI `{"detail"}`. Le regole di progetto (`.claude/rules/coding-guidelines.md`) prescrivono envelope + versioning "from day one" | Medio | Fase 3 |
| **Modelli API vs dominio** | «Mixing API contract models with domain models» da evitare | ✅ Rispettato: `ManualTransactionIn` sta nel router, `NormalizedTransaction` in `models/` | — | — |
| **Background work** | (pattern FastAPI standard) | `POST /sync` lancia `threading.Thread` raw invece di `BackgroundTasks` | Basso | Fase 3 |
| **Type checking** | pyrefly in CI e pre-commit | Assente | Medio | Fase 0 |
| **Lint** | Ruff (unico tool) | ✅ Ruff presente ma con sole regole `E,F,I` — mancano `B` (bugbear), `UP`, `SIM`, `C4`, `RUF` | Basso | Fase 0 |
| **Test** | Unit (`tests/units`, no DB) + integration (`-m integration`, PG reale in service container); factory helpers; test class per gruppo; 80% coverage | 13 file di unit test, ma i test dello storage **mockano la sequenza esatta di `fetchone`** (accoppiati all'ordine delle query, fragilissimi). Zero test d'integrazione contro PG reale. «Integration tests hit real infrastructure — don't mock what you're testing» (regola di progetto) violata | **Alto** | Fase 6 |
| **CI** | GitHub Actions: 4 job paralleli (lint, format, types, test con pgvector container) | **Nessuna CI.** L'unico gate è il hook Stop di Claude Code — non protegge commit manuali né push | **Alto** | Fase 0 |
| **Pre-commit** | Lefthook 6 job paralleli, incl. gitleaks (secret scanning) | Assente (i hook `.claude/` valgono solo nelle sessioni Claude Code) | Medio | Fase 0 |
| **Provider LLM** | Registry + Adapter (mai istanziare client nel service) | Un solo provider (Anthropic) istanziato in `categorize.py` — con un solo consumer il registry sarebbe over-engineering (i takeaways stessi: «wait for the second use») | — (rivalutare al 2° provider) | — |
| **Dipendenze** | Dichiarate = usate | `apscheduler`, `passlib`, `pgvector` (lib Python) **non importati da nessun file** — peso morto | Basso | Fase 7 |
| **Osservabilità** | OpenTelemetry completo | Log + alert Telegram | — (adeguato per single-user; OTel = YAGNI) | — |

### 1.2 Frontend

| Area | Takeaway (AI Garage) | Stato attuale | Gap | Azione |
|---|---|---|---|---|
| **Dipendenze** | package.json coerente | **`react` e `react-dom` NON sono dipendenze dirette** — arrivano solo come peer transitive: un `npm install` su lockfile rigenerato può rompere la build. `zustand` installato e mai usato. `@types/*` in `dependencies` invece che `devDependencies` | **Alto** | Task 5.1 |
| **Build** | `@vitejs/plugin-react` (Fast Refresh) | Vite senza plugin React: JSX funziona via esbuild ma **niente Fast Refresh** in dev | Basso | Task 5.1 |
| **Server state** | TanStack Query + query-options factory: i componenti spreadano `{...listX()}`, mai fetch inline; «Inline queryFn in components» da evitare | **Fetch manuale in `useEffect`** in tutte e 4 le pagine, con `.catch(() => {})` → **errori silenziati**, nessuno stato d'errore, refetch/cache assenti | **Alto** | Task 5.3–5.5 |
| **Form** | react-hook-form + zod ovunque; «mai useState per i campi» | `AddTransactionModal` gestisce i campi con `useState` | Medio | Task 5.6 |
| **Auth check** | (pattern dedicato) | `ProtectedRoute` verifica la sessione chiamando `transactions.list({page_size: 1})` — endpoint sbagliato usato come ping | Medio | Task 3.4 + 5.4 |
| **Test** | Vitest + Testing Library, query per ruolo (`getByRole`), QueryClientProvider con `retry:false`, coverage 80% | **Zero test, zero test runner** | **Alto** | Task 5.7 |
| **Lint/format** | ESLint + tsc in CI | **Nessun ESLint**; workaround tipo `_tab` per aggirare `noUnusedLocals` | Medio | Task 5.2 |
| **Struttura** | Domain-driven (`domains/`), atomic inside | `pages/` + `components/` piatti — **adeguato per 5 pagine** (domain-driven qui sarebbe cerimonias); la vera lacuna è il layer API/query | — | — |
| **Styling** | Tailwind 4 + design system | CSS Modules con design token custom — coerente e funzionante; migrare a Tailwind = churn cosmetico senza guadagno funzionale | — (non-obiettivo) | — |
| **Client API** | Classe `ApiClient` con unwrap envelope, redirect su 401 | Oggetto `api` su axios con interceptor 401 → ✅ concettualmente allineato; va aggiornato per envelope + `/v1` | Basso | Task 5.3 |

### 1.3 Processo

| Area | Takeaway | Stato attuale | Azione |
|---|---|---|---|
| Trunk-based, PR piccole, rebase | Sì | Commit diretti su `main` (progetto solo) — accettabile single-dev, ma **senza CI ogni commit è un rischio** | Fase 0 rende `main` protetto dai fatti (CI su push) |
| Wiki as code | `llm_wiki/` | ✅ `docs/` + `docs/superpowers/` già in repo | — |
| Task runner (`just`) | `just dev`, `just db-migrate` | Comandi PowerShell documentati in CLAUDE.md | Opzionale (Task 7.3) |
| Secret scanning (gitleaks) | In pre-commit | Assente | Task 0.4 |

### 1.4 Decisioni esplicite: dove NON seguo i takeaways (e perché)

1. **Niente ORM async (SQLModel/SQLAlchemy)**. AI Garage è multi-utente e concorrente; qui l'app è single-user con ~4 sync/giorno. Il valore dell'async è ≈0, il rischio di riscrivere lo storage con invarianti di dedup/riconciliazione è alto. Scelta: **psycopg3 sincrono + ConnectionPool + handler `def`** (FastAPI li esegue nel threadpool → l'event loop non si blocca più, che è il bug reale). KISS/YAGNI dalle regole di progetto.
2. **Niente Tailwind / design system**: il CSS Modules attuale è curato e coerente; migrazione = puro churn.
3. **Niente monorepo tooling (Turborepo/Nx)**: due deploy separati già funzionanti; il takeaway monorepo è già rispettato nella sostanza (frontend+backend nello stesso repo, nessun codice condiviso, contratto REST).
4. **Niente OpenTelemetry**: per un servizio single-user, log Railway + alert Telegram sono il giusto livello. Rivalutare se nasce il multi-source gateway.
5. **Niente registry/adapter per le sorgenti dati (per ora)**: esistono 3 sorgenti (EB pull, Tasker push, manual push) ma convergono già sul giunto giusto: `NormalizedTransaction` → `reconcile_or_insert`. Il registry si introduce quando arriva l'import CSV (2ª sorgente pull), non prima — «premature abstraction is worse than duplication» (mistakes-to-avoid).
6. **Envelope `{data}` senza `success` né `debug`**: i takeaways usano `{data, debug}`, le regole fullstack `{success, data}`. Per un'API single-consumer il campo `success` è ridondante (lo status HTTP basta) e `debug` è YAGNI: si adotta `{"data": ...}` / `{"error": {"code", "message"}}`.

---

## 2. Architettura target

```
Financial_tracker/
├── pipeline.py                     # shim 3 righe → fintracker.pipeline:main (Railway cron INVARIATO)
├── pyproject.toml                  # build-system hatchling, package fintracker
├── lefthook.yml                    # pre-commit: gitleaks, ruff, pyrefly, pytest
├── .github/workflows/
│   ├── backend.yml                 # lint / format / types / tests (4 job paralleli)
│   └── frontend.yml                # tsc / eslint / vitest / build
├── migrations/                     # Alembic (baseline = schema attuale)
├── config/                         # SOLO dati non versionati: .env, chiavi (invariato)
├── src/fintracker/                 # ← ex src/, ora vero package (niente sys.path hack)
│   ├── settings.py                 # pydantic-settings (ex config/settings.py)
│   ├── pipeline.py                 # ex pipeline.py root
│   ├── models/                     # invariato (transaction, tasker, reconciliation)
│   ├── ingestion/                  # invariato (fetch_transactions, tasker_parser)
│   ├── normalizer/                 # invariato (normalize, hash) — Decimal in Fase 4
│   ├── storage/                    # db.py (pool psycopg3), db_insert, reconcile
│   ├── categorizer/                # invariato
│   ├── notifications/              # invariato
│   ├── sync/                       # invariato (eb_sync)
│   ├── auth/                       # invariato (enable_banking_auth)
│   └── server/
│       ├── app.py                  # create_app + error handlers + /health
│       ├── deps.py                 # require_jwt, db_conn dependency
│       ├── services/               # transactions.py, stats.py, accounts.py (SQL + logica)
│       └── routes/                 # router sottili: api, auth, sync, webhook
└── frontend/
    ├── eslint.config.js
    ├── vite.config.ts              # + plugin-react + vitest
    └── src/
        ├── api/
        │   ├── client.ts           # axios + unwrap envelope {data}
        │   ├── queries.ts          # query-options factory (pattern AI Garage)
        │   └── types.ts
        ├── components/             # invariato
        ├── pages/                  # useQuery al posto di useEffect; RHF+zod nel modal
        └── tests/                  # Vitest + RTL
```

**Flusso richiesta API (target):**
`Route (valida input, dipendenze) → Service (SQL + shaping, riceve conn) → envelope {data} → client TS (unwrap) → TanStack Query (cache) → componente`

---

## 3. Fasi

Ordine: la Fase 0 crea la rete di sicurezza che protegge tutte le altre. Le Fasi 1→4 sono backend (ciascuna deployabile). La Fase 5 è frontend (indipendente da 1–4 tranne il Task 3.4). Le Fasi 6–7 chiudono.

| Fase | Contenuto | Stima |
|---|---|---|
| 0 | CI GitHub Actions, ruff esteso, pyrefly, Lefthook+gitleaks | 3–4 h |
| 1 | Package `fintracker`, rimozione sys.path hack, Dockerfile pulito | 3–4 h |
| 2 | pydantic-settings + SecretStr | 2–3 h |
| 3 | Service layer, envelope, `/v1`, error handler, `/auth/me`, BackgroundTasks | 4–6 h |
| 4 | psycopg3 + pool, Decimal, Alembic baseline | 6–8 h |
| 5 | Frontend: deps fix, ESLint, TanStack Query, RHF+zod, Vitest | 8–12 h |
| 6 | Test d'integrazione su PG reale | 4–6 h |
| 7 | Pulizia dipendenze, Dockerfile, docs, CLAUDE.md | 2 h |

---

### FASE 0 — Rete di sicurezza (CI + tooling)

Nessun refactor prima di avere gate automatici: da qui in poi ogni fase è protetta da lint, format, type check e test eseguiti su GitHub a ogni push.

#### Task 0.1: Estendere le regole ruff

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Aggiornare la sezione ruff**

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort
    "B",   # bugbear (bug reali: mutable default, loop var binding, ecc.)
    "UP",  # pyupgrade (sintassi moderna 3.12)
    "SIM", # simplify
    "C4",  # comprehensions
    "RUF", # regole ruff native
]
```

- [ ] **Step 2: Eseguire e correggere**

Run: `uv run ruff check . --fix` poi `uv run ruff check .`
Expected: correzioni automatiche applicate; le violazioni residue (tipicamente `B904` — `raise ... from exc` — e qualche `SIM`) si correggono a mano. Rivedere ogni fix: nessun cambio di comportamento.

- [ ] **Step 3: Verificare i test**

Run: `uv run pytest -q`
Expected: PASS (stessi risultati di prima del task).

- [ ] **Step 4: Commit**

```powershell
git add -A; git commit -m "chore: extend ruff to B/UP/SIM/C4/RUF and fix findings"
```

#### Task 0.2: Type checking con pyrefly

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Aggiungere pyrefly ai dev deps**

Run: `uv add --dev pyrefly`

- [ ] **Step 2: Prima esecuzione**

Run: `uv run pyrefly check`
Expected: elenco di errori di tipo. Correggerli dove sono bug reali (annotazioni mancanti sui return, `Any` impliciti); dove pyrefly è troppo rumoroso su codice legacy che le fasi successive riscrivono comunque (es. `db_insert.py`), sopprimere puntualmente con `# pyrefly: ignore` e un commento sul perché — MAI sopprimere file interi.
Nota: se pyrefly desse problemi su Windows, fallback equivalente: `uv add --dev mypy` + `uv run mypy src --ignore-missing-imports`; la CI (Task 0.3) usa comunque Linux dove pyrefly è collaudato (era il type checker di CI in AI Garage).

- [ ] **Step 3: Verificare che passi pulito**

Run: `uv run pyrefly check`
Expected: exit 0.

- [ ] **Step 4: Commit**

```powershell
git add -A; git commit -m "chore: add pyrefly type checking and fix findings"
```

#### Task 0.3: CI GitHub Actions

**Files:**
- Create: `.github/workflows/backend.yml`
- Create: `.github/workflows/frontend.yml`

- [ ] **Step 1: Workflow backend (4 job paralleli, come AI Garage)**

```yaml
# .github/workflows/backend.yml
name: backend

on:
  push:
    branches: [main]
    paths: ["src/**", "tests/**", "config/**", "pipeline.py", "pyproject.toml", "uv.lock", ".github/workflows/backend.yml"]
  pull_request:
    paths: ["src/**", "tests/**", "config/**", "pipeline.py", "pyproject.toml", "uv.lock", ".github/workflows/backend.yml"]

concurrency:
  group: backend-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run ruff check .

  format:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run ruff format --check .

  types:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run pyrefly check

  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run pytest -q
```

- [ ] **Step 2: Workflow frontend** (fallirà su lint/test finché la Fase 5 non li aggiunge — per ora solo `tsc` + `build`, si estende nel Task 5.7)

```yaml
# .github/workflows/frontend.yml
name: frontend

on:
  push:
    branches: [main]
    paths: ["frontend/**", ".github/workflows/frontend.yml"]
  pull_request:
    paths: ["frontend/**", ".github/workflows/frontend.yml"]

concurrency:
  group: frontend-${{ github.ref }}
  cancel-in-progress: true

defaults:
  run:
    working-directory: frontend

jobs:
  typecheck-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npx tsc --noEmit
      - run: npm run build
```

- [ ] **Step 3: Push e verifica**

Run: `git add .github; git commit -m "ci: add backend and frontend GitHub Actions workflows"; git push`
Expected: entrambi i workflow verdi su GitHub (tab Actions).

#### Task 0.4: Pre-commit con Lefthook + gitleaks

**Files:**
- Create: `lefthook.yml`

- [ ] **Step 1: Installare gli strumenti (host Windows)**

Run: `scoop install lefthook gitleaks` (oppure `winget install evilmartians.lefthook Gitleaks.Gitleaks`)

- [ ] **Step 2: Creare `lefthook.yml`** (versione ridotta dei 6 job AI Garage: niente `alembic check` finché la Fase 4 non introduce Alembic — si aggiunge lì)

```yaml
# lefthook.yml
pre-commit:
  parallel: true
  jobs:
    - name: secrets
      run: gitleaks git --pre-commit --redact --staged --verbose
    - name: lint
      glob: "*.py"
      run: uv run ruff check --fix {staged_files}
      stage_fixed: true
    - name: format
      glob: "*.py"
      run: uv run ruff format {staged_files}
      stage_fixed: true
    - name: typecheck
      glob: "*.py"
      run: uv run pyrefly check
    - name: tests
      glob: "*.py"
      run: uv run pytest -q
```

- [ ] **Step 3: Attivare e provare**

Run: `lefthook install` poi un commit di prova (es. modifica banale a un commento) e verificare che i 5 job girino.
Expected: commit passa; un file con una stringa tipo `aws_secret_access_key=AKIA...` viene bloccato da gitleaks.

- [ ] **Step 4: Commit**

```powershell
git add lefthook.yml; git commit -m "chore: add lefthook pre-commit with gitleaks, ruff, pyrefly, pytest"
```

---

### FASE 1 — Vero package Python (morte del sys.path hack)

Oggi ogni modulo apre con `sys.path.insert(0, root)`: 18 occorrenze, il Dockerfile deve fare `touch __init__.py`, i type checker faticano. Soluzione: layout src con package `fintracker` installato in editable da `uv sync`.

**Vincolo Railway**: `sync-cron` esegue `uv run python pipeline.py` e la sua config non va toccata (la schedule si perde silenziosamente). Quindi `pipeline.py` resta alla root come shim.

#### Task 1.1: pyproject → progetto installabile

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: package importabile `fintracker` (usato da tutti i task successivi); script console `pipeline` e `auth`.

- [ ] **Step 1: Aggiungere build-system e mapping del package**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fintracker"
version = "0.1.0"
description = "Personal finance hub: Revolut → Postgres via Enable Banking, AI categorization, dashboard"
readme = "README.md"
requires-python = ">=3.12"
# dependencies: INVARIATE (si puliscono in Fase 7)

[project.scripts]
pipeline = "fintracker.pipeline:main"
auth     = "fintracker.auth.enable_banking_auth:main"

[tool.hatch.build.targets.wheel]
packages = ["src/fintracker"]

[tool.ruff.lint.isort]
known-first-party = ["fintracker"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

#### Task 1.2: Spostare i moduli dentro `src/fintracker/`

**Files:**
- Move: `src/*` → `src/fintracker/*` (tutte le sottocartelle: auth, categorizer, ingestion, models, normalizer, notifications, server, storage, sync)
- Move: `config/settings.py` → `src/fintracker/settings.py`
- Move: `pipeline.py` (contenuto) → `src/fintracker/pipeline.py`

- [ ] **Step 1: Spostare con git mv (PowerShell)**

```powershell
New-Item -ItemType Directory src/fintracker
git mv src/auth src/fintracker/auth
git mv src/categorizer src/fintracker/categorizer
git mv src/ingestion src/fintracker/ingestion
git mv src/models src/fintracker/models
git mv src/normalizer src/fintracker/normalizer
git mv src/notifications src/fintracker/notifications
git mv src/server src/fintracker/server
git mv src/storage src/fintracker/storage
git mv src/sync src/fintracker/sync
git mv src/__init__.py src/fintracker/__init__.py
git mv config/settings.py src/fintracker/settings.py
git mv pipeline.py src/fintracker/pipeline.py
```

- [ ] **Step 2: Riscrivere gli import in tutti i file `.py`** (src, tests)

Sostituzioni meccaniche (usare l'editor o uno script, poi verificare col diff):
- `from src.` → `from fintracker.`
- `import config.settings as settings` → `import fintracker.settings as settings`
- Eliminare **ogni** blocco `sys.path.insert(0, ...)` e gli import `sys`/`Path` che servivano solo a quello; rimuovere i commenti `# noqa: E402` diventati inutili spostando gli import in testa.

In `src/fintracker/settings.py` aggiornare la radice del progetto (il file è sceso di un livello):

```python
ROOT = Path(__file__).resolve().parent.parent.parent  # src/fintracker/settings.py → project root
```

- [ ] **Step 3: Ricreare lo shim `pipeline.py` alla root** (il comando Railway resta identico)

```python
"""Entry-point shim: Railway cron runs `uv run python pipeline.py` — do not move."""

from fintracker.pipeline import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Installare e verificare**

Run: `uv sync` (installa `fintracker` in editable) poi `uv run pytest -q` e `uv run ruff check .` e `uv run pyrefly check`
Expected: tutti PASS. Poi smoke test: `uv run python pipeline.py --skip-fetch --skip-categorize` (richiede solo il DB locale: `docker compose up db -d`).

#### Task 1.3: Aggiornare Dockerfile e docker-compose

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml` (se monta/riferisce percorsi cambiati)

- [ ] **Step 1: Dockerfile — eliminare il blocco `touch __init__.py` e aggiornare i path**

```dockerfile
# ── Stage 1: dipendenze con uv ───────────────────────────────────
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 2: immagine finale ──────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY pipeline.py ./
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/src"
ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

CMD ["sh", "-c", "uvicorn fintracker.server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Note: `PYTHONPATH=/app:/app/src` copre sia lo shim root sia il package (il progetto non è installato nel venv di produzione, `--no-install-project`). `config/` non serve più nell'immagine: i secrets arrivano da env Railway e `load_dotenv` su file mancante è un no-op. La riga `mkdir /tmp/revolut_pipeline` era orfana — via.

- [ ] **Step 2: Build locale di verifica**

Run: `docker build -t fintracker-test .`
Expected: build OK.

- [ ] **Step 3: Commit (fine Fase 1 — commit unico coerente dei Task 1.1–1.3)**

```powershell
git add -A; git commit -m "refactor: make fintracker an installable package, drop sys.path hacks"
```

- [ ] **Step 4: Deploy e verifica produzione**

Run: `railway up --detach --service just-comfort` poi `curl https://just-comfort-production-4c96.up.railway.app/health`
Expected: `{"status":"ok"}`. Il servizio `sync-cron` usa la stessa immagine con lo stesso comando `uv run python pipeline.py` → nessuna modifica di config Railway.

#### Task 1.4: Aggiornare CLAUDE.md (comandi cambiati)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1:** Sostituire `uvicorn src.server.app:app` → `uvicorn fintracker.server.app:app`; `src/auth/enable_banking_auth.py` → `uv run auth` (script console); annotare nel paragrafo architettura che i moduli vivono in `src/fintracker/`.
- [ ] **Step 2: Commit**: `git add CLAUDE.md; git commit -m "docs: update commands for fintracker package layout"`

---

### FASE 2 — Config con pydantic-settings

Sostituisce i globali con una classe tipizzata e validata, `SecretStr` per i segreti (non finiscono nei log/repr). Semantica preservata: i secrets server-only restano validati in `create_app()`, non all'import (il pipeline gira senza credenziali dashboard).

#### Task 2.1: Riscrivere `settings.py`

**Files:**
- Modify: `src/fintracker/settings.py`
- Modify: tutti i call-site (`import fintracker.settings as settings` → `from fintracker.settings import settings`)
- Test: `tests/test_settings.py` (adattare)

**Interfaces:**
- Produces: singleton `settings: Settings` con campi UPPERCASE identici ai nomi attuali (`settings.TELEGRAM_TOKEN`, ecc. — i call-site cambiano solo la riga di import); i campi segreti diventano `SecretStr` → i call-site che li usano aggiungono `.get_secret_value()`.

- [ ] **Step 1: Aggiungere la dipendenza**

Run: `uv add pydantic-settings`

- [ ] **Step 2: Nuovo `settings.py` completo**

```python
import logging
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # UPPERCASE field names keep every call site (`settings.TELEGRAM_TOKEN`) unchanged.
    model_config = SettingsConfigDict(
        env_file=ROOT / "config" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Enable Banking
    ENABLE_BANKING_APP_ID: str = ""
    ENABLE_BANKING_PRIVATE_KEY_PATH: Path = Path("config/private_key.pem")
    ENABLE_BANKING_PRIVATE_KEY_B64: SecretStr = SecretStr("")
    ENABLE_BANKING_SESSION_ID: str = ""
    ENABLE_BANKING_ACCESS_TOKEN: SecretStr = SecretStr("")
    ENABLE_BANKING_ACCOUNT_IDS: list[str] = []

    # Anthropic — only the categorizer needs it; pipeline skips with a warning if unset
    ANTHROPIC_API_KEY: SecretStr = SecretStr("")

    # Database
    DATABASE_URL: str = "postgresql://user:changeme@localhost:5432/finance"

    # Pipeline
    FETCH_DAYS_BACK: int = 90
    LOG_LEVEL: str = "INFO"

    # Telegram — required by both server and pipeline (sync alerts)
    TELEGRAM_TOKEN: SecretStr
    TELEGRAM_CHAT_ID: str

    # Server-only secrets — validated in validate_server_settings() at create_app(),
    # not at import, so pipeline.py runs without dashboard credentials.
    WEBHOOK_SECRET: SecretStr = SecretStr("")
    APP_USERNAME: str = ""
    APP_PASSWORD_HASH: SecretStr = SecretStr("")
    JWT_SECRET: SecretStr = SecretStr("")

    # Cookies / CORS
    FRONTEND_URL: str = "http://localhost:5173"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"  # safe: the Vercel proxy makes API calls first-party

    @field_validator("ENABLE_BANKING_PRIVATE_KEY_PATH", mode="after")
    @classmethod
    def _resolve_key_path(cls, v: Path) -> Path:
        return v if v.is_absolute() else ROOT / v

    def validate_server_settings(self) -> None:
        missing = [
            key
            for key, val in {
                "WEBHOOK_SECRET": self.WEBHOOK_SECRET.get_secret_value(),
                "APP_USERNAME": self.APP_USERNAME,
                "APP_PASSWORD_HASH": self.APP_PASSWORD_HASH.get_secret_value(),
                "JWT_SECRET": self.JWT_SECRET.get_secret_value(),
            }.items()
            if not val
        ]
        if missing:
            raise EnvironmentError(f"Required env vars not set: {', '.join(missing)}")
        if len(self.WEBHOOK_SECRET.get_secret_value()) < 32:
            raise EnvironmentError("WEBHOOK_SECRET must be at least 32 characters")
        if len(self.JWT_SECRET.get_secret_value()) < 32:
            raise EnvironmentError("JWT_SECRET must be at least 32 characters")


settings = Settings()


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
```

- [ ] **Step 3: Aggiornare i call-site**

Sostituzione meccanica in `src/` e `tests/`:
- `import fintracker.settings as settings` → `from fintracker.settings import settings` (+ `from fintracker.settings import setup_logging` dove serve).
- `settings.validate_server_settings()` in `app.py` → invariato (ora è un metodo).
- Ai punti d'uso dei campi ora `SecretStr`, aggiungere `.get_secret_value()`. Punti esatti: `notifications/telegram.py` (token), `sync/eb_sync.py` (token passthrough — le firme `send_telegram(token=...)` continuano a ricevere `str`: passare `settings.TELEGRAM_TOKEN.get_secret_value()`), `ingestion/fetch_transactions.py` (B64 key), `server/routes/auth.py` (JWT_SECRET, APP_PASSWORD_HASH), `server/routes/sync.py` e `server/routes/webhook.py` (WEBHOOK_SECRET), `categorizer/categorize.py` e `fintracker/pipeline.py` (ANTHROPIC_API_KEY: il check "è settata?" diventa `settings.ANTHROPIC_API_KEY.get_secret_value()`).
- `ENABLE_BANKING_ACCOUNT_IDS`: pydantic-settings parsa i campi `list[str]` come JSON dall'env — identico al `json.loads` attuale; se la variabile non c'è, vale il default `[]`.

- [ ] **Step 4: Verifica completa**

Run: `uv run pytest -q; uv run pyrefly check; uv run ruff check .`
Expected: PASS. `tests/conftest.py` non cambia (le env impostate lì vengono lette da `Settings()` all'import, env > env_file).

- [ ] **Step 5: Commit**

```powershell
git add -A; git commit -m "refactor: typed settings via pydantic-settings with SecretStr"
```

---

### FASE 3 — Service layer, envelope, /v1, error handling

Estrae la logica dagli handler (`api.py` oggi fa SQL + shaping inline), introduce l'envelope `{data}`, il prefisso `/v1` per l'API dashboard, un error handler coerente, `/auth/me` per il check di sessione e `BackgroundTasks` al posto del thread raw.

**Strategia di rollout senza downtime:** il backend monta i router **sia** su `/v1` **sia** sui path legacy finché il frontend (Fase 5) non è deployato; poi si rimuove il mount legacy (Task 5.8). `/webhook/tasker`, `/sync` e `/health` restano non versionati per sempre (endpoint macchina: MacroDroid e curl manuale).

#### Task 3.1: Dipendenze condivise (`deps.py`)

**Files:**
- Create: `src/fintracker/server/deps.py`
- Modify: `src/fintracker/server/routes/api.py` (rimuovere `_require_jwt` locale)

**Interfaces:**
- Produces: `require_jwt` (dependency FastAPI, solleva 401), usata da tutte le route dashboard.

- [ ] **Step 1: Scrivere il test** (`tests/test_deps.py`)

```python
import jwt as pyjwt
import pytest
from fastapi import HTTPException

from fintracker.server.deps import require_jwt


def test_require_jwt_missing_cookie():
    with pytest.raises(HTTPException) as exc:
        require_jwt(jwt=None)
    assert exc.value.status_code == 401


def test_require_jwt_garbage_token():
    with pytest.raises(HTTPException) as exc:
        require_jwt(jwt="not-a-jwt")
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run test** — Expected: FAIL (`ModuleNotFoundError: fintracker.server.deps`)

- [ ] **Step 3: Implementare `deps.py`** (è il `_require_jwt` di api.py, promosso a modulo condiviso)

```python
import jwt as pyjwt
from fastapi import Cookie, HTTPException

from fintracker.server.routes.auth import verify_token


def require_jwt(jwt: str | None = Cookie(default=None)) -> dict:
    """Session guard for dashboard endpoints. Returns the JWT payload."""
    if not jwt:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return verify_token(jwt)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Unauthorized") from None
```

- [ ] **Step 4: Run test** — Expected: PASS. **Step 5: Commit** `feat: shared require_jwt dependency`

#### Task 3.2: Servizi transactions / stats / accounts

**Files:**
- Create: `src/fintracker/server/services/__init__.py`
- Create: `src/fintracker/server/services/transactions.py`
- Create: `src/fintracker/server/services/stats.py`
- Create: `src/fintracker/server/services/accounts.py`
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: `connection(...)`/pool da storage (in Fase 4 il context manager cambia implementazione, firma identica).
- Produces (usate dal Task 3.3):
  - `transactions.list_transactions(conn, *, page: int, page_size: int, days_back: int, category: str | None, direction: str | None, search: str | None) -> dict`
  - `transactions.create_manual(conn, data: dict) -> dict | None` (None = duplicato)
  - `stats.by_category(conn, days_back: int) -> list[dict]`
  - `stats.monthly(conn, months: int) -> list[dict]`
  - `accounts.balances(conn) -> dict`

- [ ] **Step 1: Scrivere `services/transactions.py`** — il codice è quello oggi dentro le route, trasferito 1:1 (stesso SQL, stessi filtri; il servizio riceve `conn` e non apre connessioni proprie — regola AI Garage "services receive session, never create their own"):

```python
import logging
from typing import Any

import psycopg2.extras

from fintracker.normalizer.hash import manual_dedup_hash
from fintracker.storage.db_insert import INSERT_SQL

log = logging.getLogger(__name__)

_INSERT_RETURN = (
    INSERT_SQL
    + """
RETURNING id, dedup_hash, booking_date, amount, currency, eur_amount,
          description, merchant_name, account_id, is_internal,
          category, subcategory, status, source, created_at
"""
)

_SELECT_COLS = """id, dedup_hash, booking_date, amount, currency, eur_amount,
                  description, merchant_name, account_id, is_internal,
                  category, subcategory, status, source, created_at"""


def list_transactions(
    conn,
    *,
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
) -> dict:
    conditions = ["booking_date >= NOW() - (%s * INTERVAL '1 day')"]
    params: list[Any] = [days_back]
    if category:
        conditions.append("category = %s")
        params.append(category)
    if direction == "income":
        conditions.append("amount > 0")
    elif direction == "expense":
        conditions.append("amount < 0")
    if search:
        conditions.append("(merchant_name ILIKE %s OR description ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM real_transactions WHERE {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"""SELECT {_SELECT_COLS}
                FROM real_transactions
                WHERE {where}
                ORDER BY booking_date DESC
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]

    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def create_manual(conn, data: dict) -> dict | None:
    """Insert a manual transaction. Returns the row, or None on duplicate."""
    data = {
        **data,
        "dedup_hash": manual_dedup_hash(
            data["booking_date"].isoformat(), data["amount"], data["currency"]
        ),
        "is_internal": False,
        "status": "verified",
        "source": "manual",
        "source_id": None,
    }
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(_INSERT_RETURN, data)
        row = cur.fetchone()
    conn.commit()
    return dict(row) if row else None
```

Nota: sparisce `_row_to_dict` (la conversione `isoformat` manuale) — l'encoder di FastAPI serializza già `datetime` e `Decimal`.

- [ ] **Step 2: Scrivere `services/stats.py` e `services/accounts.py`** — stesso trasferimento 1:1 delle query da `api.py`:

```python
# services/stats.py
import psycopg2.extras


def by_category(conn, days_back: int) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT COALESCE(category, 'Uncategorized') AS category,
                      ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                      COUNT(*) AS count
               FROM real_transactions
               WHERE amount < 0
                 AND booking_date >= NOW() - (%s * INTERVAL '1 day')
               GROUP BY category
               ORDER BY total DESC""",
            (days_back,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    grand_total = sum(float(r["total"]) for r in rows) or 1
    for r in rows:
        r["percentage"] = round(float(r["total"]) / grand_total * 100, 1)
    return rows


def monthly(conn, months: int) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM') AS month,
                      ROUND(SUM(CASE WHEN amount > 0 THEN eur_amount ELSE 0 END)::numeric, 2) AS income,
                      ROUND(SUM(CASE WHEN amount < 0 THEN ABS(eur_amount) ELSE 0 END)::numeric, 2) AS expenses
               FROM real_transactions
               GROUP BY DATE_TRUNC('month', booking_date)
               ORDER BY DATE_TRUNC('month', booking_date) DESC
               LIMIT %s""",
            (months,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["net"] = round(float(r["income"]) - float(r["expenses"]), 2)
    return rows
```

```python
# services/accounts.py
import psycopg2.extras


def balances(conn) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT account_id, ROUND(SUM(eur_amount)::numeric, 2) AS balance
               FROM real_transactions
               WHERE account_id IS NOT NULL
               GROUP BY account_id
               ORDER BY balance DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    accounts = [{"account_id": r["account_id"], "balance": float(r["balance"])} for r in rows]
    assets = round(sum(a["balance"] for a in accounts if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in accounts if a["balance"] < 0)), 2)
    return {"assets": assets, "liabilities": liabilities, "accounts": accounts}
```

- [ ] **Step 3: Test dei servizi** (`tests/test_services.py`) — unit leggeri sul shaping (i percorsi SQL veri li copre la Fase 6):

```python
from unittest.mock import MagicMock

from fintracker.server.services import accounts, stats


def _conn_returning(rows):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.fetchone.return_value = {"total": len(rows)}
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


def test_stats_by_category_adds_percentage():
    conn = _conn_returning([
        {"category": "Food", "total": 75.0, "count": 3},
        {"category": "Travel", "total": 25.0, "count": 1},
    ])
    rows = stats.by_category(conn, days_back=30)
    assert rows[0]["percentage"] == 75.0
    assert rows[1]["percentage"] == 25.0


def test_accounts_balances_splits_assets_liabilities():
    conn = _conn_returning([
        {"account_id": "a", "balance": 100.0},
        {"account_id": "b", "balance": -40.0},
    ])
    out = accounts.balances(conn)
    assert out["assets"] == 100.0
    assert out["liabilities"] == 40.0
```

- [ ] **Step 4: Run** `uv run pytest tests/test_services.py -v` — Expected: PASS. **Step 5: Commit** `refactor: extract transactions/stats/accounts services from routes`

#### Task 3.3: Route sottili + envelope + /v1 + error handler

**Files:**
- Modify: `src/fintracker/server/routes/api.py` (diventa ~80 righe)
- Modify: `src/fintracker/server/routes/auth.py` (envelope su login; endpoint `/auth/me`)
- Modify: `src/fintracker/server/routes/sync.py` (BackgroundTasks)
- Modify: `src/fintracker/server/app.py` (error handler, dual-mount /v1)
- Test: `tests/test_api_routes.py`, `tests/test_auth.py`, `tests/test_sync_route.py` (aggiornare per envelope + nuovi path)

- [ ] **Step 1: Nuovo `routes/api.py`**

```python
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fintracker.server.deps import require_jwt
from fintracker.server.services import accounts, stats, transactions
from fintracker.settings import settings
from fintracker.storage.db_insert import connection

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_jwt)])


class ManualTransactionIn(BaseModel):
    booking_date: datetime
    amount: float
    currency: str = "EUR"
    eur_amount: float
    merchant_name: str | None = None
    description: str | None = None
    account_id: str | None = None
    category: str | None = None
    subcategory: str | None = None


@router.get("/transactions")
def list_transactions(
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=500)] = 50,
    days_back: Annotated[int, Field(ge=1, le=365)] = 30,
    category: str | None = None,
    direction: str | None = Query(default=None, pattern="^(income|expense)$"),
    search: str | None = None,
) -> dict:
    with connection(settings.DATABASE_URL) as conn:
        data = transactions.list_transactions(
            conn, page=page, page_size=page_size, days_back=days_back,
            category=category, direction=direction, search=search,
        )
    return {"data": data}


@router.post("/transactions", status_code=201)
def create_transaction(body: ManualTransactionIn) -> dict:
    with connection(settings.DATABASE_URL) as conn:
        row = transactions.create_manual(conn, body.model_dump())
    if row is None:
        raise HTTPException(status_code=409, detail="Duplicate transaction")
    return {"data": row}


@router.get("/stats/categories")
def stats_categories(days_back: Annotated[int, Field(ge=1, le=365)] = 30) -> dict:
    with connection(settings.DATABASE_URL) as conn:
        return {"data": stats.by_category(conn, days_back)}


@router.get("/stats/monthly")
def stats_monthly(months: Annotated[int, Field(ge=1, le=24)] = 12) -> dict:
    with connection(settings.DATABASE_URL) as conn:
        return {"data": stats.monthly(conn, months)}


@router.get("/accounts")
def list_accounts() -> dict:
    with connection(settings.DATABASE_URL) as conn:
        return {"data": accounts.balances(conn)}
```

Cambi chiave: handler **`def`** (non `async def`) → FastAPI li esegue nel threadpool, l'I/O bloccante psycopg2 **non blocca più l'event loop** (bug fix reale, indipendente dalla Fase 4); auth via `dependencies=[Depends(require_jwt)]` sul router intero; envelope `{"data": ...}`.

- [ ] **Step 2: `/auth/me` + envelope in `routes/auth.py`**

Aggiungere (dopo `logout`):

```python
@router.get("/me")
def me(jwt: str | None = Cookie(default=None)) -> dict:
    if not jwt:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = verify_token(jwt)
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Unauthorized") from None
    return {"data": {"username": payload["sub"]}}
```

E in `login`, cambiare il return in `return {"data": {"ok": True}}`. (`logout` resta 204 senza body.)

- [ ] **Step 3: `routes/sync.py` — BackgroundTasks al posto del thread raw**

```python
import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import Field

from fintracker.settings import settings
from fintracker.sync.eb_sync import run_eb_sync

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/sync")
def trigger_sync(
    background: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None),
    days_back: Annotated[int, Field(ge=1, le=90)] = 2,
) -> dict:
    if not hmac.compare_digest(
        (x_webhook_secret or "").encode(),
        settings.WEBHOOK_SECRET.get_secret_value().encode(),
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    background.add_task(run_eb_sync, days_back)
    log.info("Manual EB sync triggered via /sync (days_back=%d)", days_back)
    return {"data": {"status": "started", "days_back": days_back}}
```

- [ ] **Step 4: `app.py` — error handler + dual-mount**

```python
import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from fintracker.server.routes.api import router as api_router
from fintracker.server.routes.auth import router as auth_router
from fintracker.server.routes.sync import router as sync_router
from fintracker.server.routes.webhook import router as webhook_router
from fintracker.settings import settings, setup_logging

setup_logging()
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings.validate_server_settings()
    app = FastAPI(
        title="Revolut Finance Ingestion", docs_url=None, redoc_url=None, openapi_url=None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # Financial data must never land in shared caches (Vercel proxy sits in front)
    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never leak validation internals to clients; details go to the log only.
        log.warning("Request validation failed: %s", exc.errors())
        return JSONResponse(
            status_code=422,
            content={"error": {"code": 422, "message": "Invalid request"}},
        )

    # Machine endpoints — permanently unversioned (MacroDroid + manual curl)
    app.include_router(webhook_router)
    app.include_router(sync_router)

    # Dashboard API — versioned. Legacy mount kept until the frontend ships /v1
    # (removed in Task 5.8).
    app.include_router(api_router, prefix="/v1")
    app.include_router(auth_router, prefix="/v1")
    app.include_router(api_router)
    app.include_router(auth_router)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
```

- [ ] **Step 5: Aggiornare i test** — nei test delle route: path invariati funzionano ancora (mount legacy) ma aggiornare le asserzioni per l'envelope (`resp.json()["data"]["items"]`, `["error"]["message"]`, ecc.) e aggiungere un test che gli stessi endpoint rispondano anche sotto `/v1`.

Run: `uv run pytest -q` — Expected: PASS.

- [ ] **Step 6: Commit + deploy**

```powershell
git add -A; git commit -m "refactor: thin routers over service layer; add {data} envelope, /v1 mount, error handlers, /auth/me"
railway up --detach --service just-comfort
```

Verifica: `curl https://.../health` → ok; il frontend attuale continua a funzionare (path legacy + il client legge `r.data` che ora contiene `{data: ...}`? **NO** — attenzione: l'envelope cambia la shape anche sui path legacy!).

**⚠ Correzione di rollout obbligatoria:** l'envelope sui path legacy romperebbe il frontend in produzione. Due opzioni; scegliere la **A**:
- **A (consigliata)**: gli handler legacy restano senza envelope. Implementazione: applicare l'envelope **solo** nel mount `/v1` usando un router wrapper. In pratica: i servizi restituiscono i dati puri; creare `routes/api.py` con **due** router che condividono le stesse funzioni — `router_legacy` restituisce i dati nudi (shape attuale), `router_v1` li avvolge in `{"data": ...}`. Sono ~10 righe di duplicazione dichiarata e **temporanea** (vive solo fino al Task 5.8, dove `router_legacy` viene cancellato).
- B: deploy backend+frontend coordinato accettando ~1 min di frontend rotto (app single-user). Meno lavoro ma sporca.

---

### FASE 4 — Data layer: psycopg3 + pool, Decimal, Alembic

#### Task 4.1: psycopg3 + ConnectionPool

**Files:**
- Modify: `pyproject.toml` (deps)
- Create: `src/fintracker/storage/db.py`
- Modify: `src/fintracker/storage/db_insert.py`, `src/fintracker/storage/reconcile.py`, `src/fintracker/server/services/*.py`, `src/fintracker/categorizer/categorize.py`, `src/fintracker/pipeline.py`, `src/fintracker/sync/eb_sync.py`

**Interfaces:**
- Produces: `db.db_conn()` context manager (connessione dal pool, commit-on-success), `db.get_pool()`; il pipeline usa `db.direct_connection()` (no pool, processo batch).

- [ ] **Step 1: Swap dipendenze**

Run: `uv remove psycopg2-binary` poi `uv add "psycopg[binary,pool]"`

- [ ] **Step 2: Nuovo `storage/db.py`**

```python
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from fintracker.settings import settings

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        # Single-user app behind one uvicorn worker: a tiny pool is plenty.
        _pool = ConnectionPool(settings.DATABASE_URL, min_size=1, max_size=4, open=True)
        log.info("DB connection pool opened")
    return _pool


@contextmanager
def db_conn() -> Iterator[psycopg.Connection]:
    """Pooled connection; commits on clean exit, rolls back on exception."""
    with get_pool().connection() as conn:
        yield conn


def direct_connection() -> psycopg.Connection:
    """Unpooled connection for batch jobs (pipeline.py)."""
    return psycopg.connect(settings.DATABASE_URL)
```

- [ ] **Step 3: Migrare i call-site psycopg2 → psycopg3**

Differenze meccaniche (nessun cambio di semantica):
- `import psycopg2` / `psycopg2.extras` → via.
- `conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)` → `conn.cursor(row_factory=dict_row)` con `from psycopg.rows import dict_row`.
- `psycopg2.extras.execute_batch(cur, INSERT_SQL, rows, page_size=200)` → `cur.executemany(INSERT_SQL, rows)` (psycopg3 lo esegue già in pipeline mode).
- I placeholder `%s` / `%(name)s` sono identici.
- `connection(settings.DATABASE_URL)` (context manager in `db_insert.py`) → sostituito ovunque da `db_conn()` (server) o `direct_connection()` (pipeline). I `conn.commit()` espliciti esistenti restano validi (il commit-on-exit del pool li rende ridondanti ma innocui — non rimuoverli in questo task, si semplifica dopo).
- In `server/services/*.py` sostituire l'import `psycopg2.extras` col nuovo `dict_row`.
- In `routes/api.py`: `with connection(settings.DATABASE_URL) as conn:` → `with db_conn() as conn:` (import da `fintracker.storage.db`).

- [ ] **Step 4: Verifica**

Run: `uv run pytest -q` (i mock dei test non sanno la differenza) poi smoke test reale: `docker compose up db -d; uv run python pipeline.py --skip-fetch --skip-categorize`
Expected: PASS + "Pipeline complete".

- [ ] **Step 5: Commit** `refactor: psycopg3 with pooled connections for the server`

#### Task 4.2: Denaro in Decimal (con protezione dell'hash)

Il rischio n.1 del piano. La formula hash usa `f"{abs(amount)}"` su **float**: `-12.50` → `"12.5"`. Passando a `Decimal`, `str(abs(Decimal("12.50")))` darebbe `"12.50"` → **hash diversi → duplicati in produzione**. Protezione: le funzioni hash continuano a ricevere/convertire **float**, i modelli e il DB viaggiano in `Decimal`.

**Files:**
- Modify: `src/fintracker/normalizer/hash.py`
- Modify: `src/fintracker/models/transaction.py`
- Modify: `src/fintracker/normalizer/normalize.py`
- Modify: `src/fintracker/ingestion/tasker_parser.py`
- Test: `tests/test_hash.py` (test di regressione PRIMA di toccare i modelli)

- [ ] **Step 1: Test di regressione sull'hash (scriverli e vederli passare PRIMA del cambio)**

Aggiungere a `tests/test_hash.py`:

```python
import hashlib
from decimal import Decimal

from fintracker.normalizer.hash import eb_dedup_hash, manual_dedup_hash, tasker_dedup_hash


class TestHashStabilityAcrossDecimalMigration:
    """The hash payload string must stay byte-identical to the historical float formula."""

    def test_eb_hash_payload_unchanged(self):
        # Historical formula: sha256(f"{date[:10]}|{abs(float)}|{desc.lower()}|{ccy}")
        expected = hashlib.sha256("2026-06-07|12.5|esselunga|EUR".encode()).hexdigest()
        assert eb_dedup_hash("2026-06-07", -12.50, "Esselunga", "EUR") == expected

    def test_eb_hash_decimal_input_matches_float_input(self):
        assert eb_dedup_hash("2026-06-07", Decimal("-12.50"), "Esselunga", "EUR") == \
            eb_dedup_hash("2026-06-07", -12.5, "Esselunga", "EUR")

    def test_manual_hash_decimal_matches_float(self):
        assert manual_dedup_hash("2026-07-01T10:00:00", Decimal("5.00"), "EUR") == \
            manual_dedup_hash("2026-07-01T10:00:00", 5.0, "EUR")
```

- [ ] **Step 2: Blindare `hash.py`** — le tre funzioni accettano `float | Decimal` e normalizzano a float PRIMA di formattare:

```python
import hashlib
from datetime import datetime
from decimal import Decimal


def _legacy_amount_repr(amount: float | Decimal) -> str:
    # Historical hashes were computed from Python float repr ("12.5", not "12.50").
    # float() first keeps every stored hash valid after the Decimal migration.
    return str(abs(float(amount)))


def eb_dedup_hash(date: str, amount: float | Decimal, description: str, currency: str) -> str:
    # SHA-256(date[:10] + "|" + abs(amount) + "|" + desc_lower + "|" + currency)
    # NEVER change this formula — it would invalidate all historical hashes.
    payload = f"{date[:10]}|{_legacy_amount_repr(amount)}|{description.lower()}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def tasker_dedup_hash(timestamp: datetime, amount: float | Decimal, currency: str) -> str:
    # Truncate to minute so 14:32:45 and 14:32:00 produce the same hash.
    minute = timestamp.strftime("%Y-%m-%dT%H:%M")
    payload = f"tasker|{minute}|{_legacy_amount_repr(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def manual_dedup_hash(booking_date: str, amount: float | Decimal, currency: str) -> str:
    payload = f"manual|{booking_date[:19]}|{_legacy_amount_repr(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

Run: `uv run pytest tests/test_hash.py -v` — Expected: PASS (tutti, inclusi i nuovi).

- [ ] **Step 3: `models/transaction.py` → Decimal**

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class NormalizedTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    dedup_hash: str
    booking_date: datetime
    amount: Decimal
    currency: str
    eur_amount: Decimal
    description: str | None = None
    merchant_name: str | None = None
    account_id: str | None = None
    is_internal: bool = False
    category: str | None = None
    subcategory: str | None = None
    status: Literal["pending", "verified"] = "verified"
    source: Literal["tasker", "enable_banking", "manual"] = "enable_banking"
    source_id: str | None = None
```

- [ ] **Step 4: `normalize.py` — parsing in Decimal**

Modifiche puntuali:
- `_parse_amount`: `amount = abs(Decimal(str(amount_data.get("amount", "0"))))` e ritorno `-amount` / `amount` (EB manda l'importo come stringa positiva: `Decimal(str(...))` è esatto).
- `_to_eur(amount: Decimal, currency, rates)`: `return amount / Decimal(str(rate))` (ramo EUR invariato).
- La chiamata all'hash resta `eb_dedup_hash(date_str, amount, description, currency)` — lo shim del Task 4.2/Step 2 garantisce l'equivalenza.

In `tasker_parser.py`: `raw_amount = abs(Decimal(payload.amount))`, la normalizzazione locale della stringa in `_parse_raw_text` produce `Decimal(amt_str)` invece di `float(amt_str)` (stesso try/except, `InvalidOperation` al posto di `ValueError`: `except (ValueError, InvalidOperation)`).

Nota JSON: nelle risposte API i `Decimal` passano dall'encoder FastAPI che li serializza come numeri — il frontend non vede differenze. psycopg3 adatta `Decimal` nativamente su colonne `NUMERIC` (che già usiamo).

- [ ] **Step 5: Aggiornare i test toccati e run completo**

I test che costruiscono `NormalizedTransaction(amount=-12.50, ...)` continuano a funzionare (pydantic coerce float→Decimal). Aggiornare eventuali assert di uguaglianza stretta (`== -12.5` funziona con Decimal; `is`-style no).

Run: `uv run pytest -q; uv run pyrefly check` — Expected: PASS.

- [ ] **Step 6: Commit** `refactor: money as Decimal end-to-end, hash formulas pinned to legacy float repr`

#### Task 4.3: Alembic (baseline dallo schema live)

**Files:**
- Create: `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_baseline.py`
- Modify: `src/fintracker/pipeline.py` (rimuovere `ensure_schema`), `src/fintracker/storage/db_insert.py` (rimuovere `_DDL`/`ensure_schema`), `lefthook.yml` (niente `alembic check`: senza ORM/autogenerate non ha nulla da confrontare)

- [ ] **Step 1:** `uv add alembic` poi `uv run alembic init migrations`

- [ ] **Step 2: `migrations/env.py`** — collegare l'URL dalle settings (siamo raw-SQL, niente `target_metadata`):

```python
from alembic import context
from sqlalchemy import create_engine

from fintracker.settings import settings

config = context.config


def run_migrations_offline() -> None:
    context.configure(url=settings.DATABASE_URL, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

(Alembic richiede SQLAlchemy come motore di esecuzione: arriva come sua dipendenza transitiva; il codice applicativo continua a NON usarlo.)

- [ ] **Step 3: Baseline `0001_baseline.py`** — trascrizione fedele del `_DDL` attuale:

```python
"""baseline: schema as deployed on Neon (2026-07)"""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pgcrypto;

    CREATE TABLE IF NOT EXISTS transactions (
        id            SERIAL PRIMARY KEY,
        dedup_hash    TEXT        NOT NULL UNIQUE,
        booking_date  TIMESTAMPTZ NOT NULL,
        amount        NUMERIC     NOT NULL,
        currency      CHAR(3)     NOT NULL,
        eur_amount    NUMERIC     NOT NULL,
        description   TEXT,
        merchant_name TEXT,
        account_id    TEXT,
        is_internal   BOOL        NOT NULL DEFAULT FALSE,
        category      TEXT,
        subcategory   TEXT,
        embedding     vector(1536),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        status        TEXT        NOT NULL DEFAULT 'verified',
        source        TEXT        NOT NULL DEFAULT 'enable_banking',
        source_id     TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_transactions_pending
        ON transactions (status, booking_date) WHERE status = 'pending';
    CREATE INDEX IF NOT EXISTS idx_tx_booking_date ON transactions (booking_date DESC);
    CREATE INDEX IF NOT EXISTS idx_tx_is_internal  ON transactions (is_internal);
    CREATE INDEX IF NOT EXISTS idx_tx_category     ON transactions (category);

    CREATE OR REPLACE VIEW real_transactions AS
        SELECT * FROM transactions WHERE is_internal = FALSE;
    """)


def downgrade() -> None:
    raise NotImplementedError("baseline is not reversible")
```

- [ ] **Step 4: Rimuovere il DDL runtime**

- `db_insert.py`: cancellare `_DDL` e `ensure_schema` (resta `INSERT_SQL`, `insert_transaction[s]`).
- `pipeline.py` (package): rimuovere `ensure_schema(conn)`; lo schema è responsabilità delle migrazioni, non di ogni run del cron. (La DDL era comunque idempotente: nessun comportamento perso, solo spostato.)

- [ ] **Step 5: Allineare i database**

- DB locale nuovo/Docker: `uv run alembic upgrade head`
- **Neon produzione (schema già esistente): `uv run alembic stamp head`** — registra la baseline senza eseguire nulla. Eseguire una sola volta, con `DATABASE_URL` di produzione nell'env della shell.

- [ ] **Step 6: Verifica + commit**

Run: `uv run pytest -q` e `docker compose up db -d; uv run alembic upgrade head; uv run python pipeline.py --skip-fetch --skip-categorize`
Expected: PASS.

```powershell
git add -A; git commit -m "feat: Alembic migrations with production baseline; drop runtime DDL"
```

Aggiornare CLAUDE.md (sezione comandi: `uv run alembic upgrade head`; invariante: "schema changes go through Alembic").

---

### FASE 5 — Frontend: fondamenta e pattern AI Garage

#### Task 5.1: Sistemare package.json e build

**Files:**
- Modify: `frontend/package.json`, `frontend/vite.config.ts`

- [ ] **Step 1: Dipendenze corrette**

```powershell
cd frontend
npm install react react-dom                        # BUG FIX: oggi sono solo peer transitive
npm install @tanstack/react-query react-hook-form zod @hookform/resolvers
npm uninstall zustand                              # mai importato
npm install -D @vitejs/plugin-react vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event eslint typescript-eslint eslint-plugin-react-hooks @eslint/js prettier
npm install -D @types/react @types/react-dom       # e rimuoverli da "dependencies"
```

`package.json` risultante (sezioni deps):

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint src",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@hookform/resolvers": "^5.0.0",
    "@tanstack/react-query": "^5.85.0",
    "axios": "^1.17.0",
    "framer-motion": "^12.40.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "react-hook-form": "^7.75.0",
    "react-router-dom": "^7.17.0",
    "recharts": "^3.8.1",
    "zod": "^4.0.0"
  },
  "devDependencies": {
    "@eslint/js": "^9.0.0",
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.3.0",
    "@testing-library/user-event": "^14.6.0",
    "@types/react": "^19.2.17",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^5.0.0",
    "eslint": "^9.0.0",
    "eslint-plugin-react-hooks": "^6.0.0",
    "jsdom": "^26.0.0",
    "prettier": "^3.5.0",
    "typescript": "~6.0.2",
    "typescript-eslint": "^8.0.0",
    "vite": "^8.0.12",
    "vitest": "^4.0.0"
  }
}
```

(Le versioni sono indicative `^`: usare quelle che npm risolve al momento dell'install.)

- [ ] **Step 2: `vite.config.ts` con plugin React e Vitest**

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'https://just-comfort-production-4c96.up.railway.app',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
        secure: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/tests/setup.ts',
    globals: true,
  },
});
```

- [ ] **Step 3: Verifica** — `npm run build` OK, `npm run dev` con Fast Refresh funzionante.
- [ ] **Step 4: Commit** `fix(frontend): declare react as direct dependency, drop zustand, add build/test toolchain`

#### Task 5.2: ESLint flat config + Prettier

**Files:**
- Create: `frontend/eslint.config.js`, `frontend/.prettierrc`

- [ ] **Step 1: `eslint.config.js`**

```js
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

export default tseslint.config(
  { ignores: ['dist'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
);
```

- [ ] **Step 2: `.prettierrc`**

```json
{ "singleQuote": true, "trailingComma": "all", "printWidth": 100 }
```

- [ ] **Step 3:** `npm run lint` → correggere i finding (il `CustomTooltip` con `any` in StatsPage va tipizzato; il `_tab` inutilizzato si risolve usandolo davvero o rimuovendo lo stato). **Step 4: Commit** `chore(frontend): eslint flat config + prettier`

#### Task 5.3: Client API con envelope + query-options factory

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/api/queries.ts`

**Interfaces:**
- Produces: `api.*` (chiamate raw, unwrap envelope) e factory `transactionQueries` / `statsQueries` / `accountQueries` / `authQueries` consumate con `useQuery({ ...factory() })` (pattern AI Garage).

- [ ] **Step 1: `client.ts` — path `/v1` + unwrap `{data}`**

```ts
import axios, { type AxiosError, type AxiosResponse } from 'axios';
import type {
  Transaction,
  TransactionsResponse,
  CategoryStat,
  MonthlyStat,
  TransactionFilters,
  AccountsResponse,
} from './types';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const http = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
});

http.interceptors.response.use(
  r => r,
  (err: AxiosError) => {
    if (err.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    return Promise.reject(err);
  },
);

// Backend wraps every response in { data: ... } — unwrap once here.
const unwrap = <T>(r: AxiosResponse<{ data: T }>): T => r.data.data;

export const api = {
  auth: {
    login: (data: { username: string; password: string }): Promise<{ ok: boolean }> =>
      http.post('/v1/auth/login', data).then(unwrap),
    logout: (): Promise<void> => http.post('/v1/auth/logout').then(() => undefined),
    me: (): Promise<{ username: string }> => http.get('/v1/auth/me').then(unwrap),
  },
  transactions: {
    list: (filters: TransactionFilters = {}): Promise<TransactionsResponse> =>
      http.get('/v1/transactions', { params: filters }).then(unwrap),
    create: (data: Partial<Transaction>): Promise<Transaction> =>
      http.post('/v1/transactions', data).then(unwrap),
  },
  stats: {
    categories: (params: { days_back?: number } = {}): Promise<CategoryStat[]> =>
      http.get('/v1/stats/categories', { params }).then(unwrap),
    monthly: (params: { months?: number } = {}): Promise<MonthlyStat[]> =>
      http.get('/v1/stats/monthly', { params }).then(unwrap),
  },
  accounts: {
    list: (): Promise<AccountsResponse> => http.get('/v1/accounts').then(unwrap),
  },
};
```

- [ ] **Step 2: `queries.ts` — factory (i componenti non scrivono mai queryFn inline)**

```ts
import { api } from './client';
import type { TransactionFilters } from './types';

export const authQueries = {
  me: () => ({
    queryKey: ['auth', 'me'] as const,
    queryFn: api.auth.me,
    retry: false,
  }),
};

export const transactionQueries = {
  list: (filters: TransactionFilters = {}) => ({
    queryKey: ['transactions', filters] as const,
    queryFn: () => api.transactions.list(filters),
  }),
  create: () => ({
    mutationKey: ['transactions', 'create'] as const,
    mutationFn: api.transactions.create,
  }),
};

export const statsQueries = {
  categories: (days_back = 30) => ({
    queryKey: ['stats', 'categories', days_back] as const,
    queryFn: () => api.stats.categories({ days_back }),
  }),
  monthly: (months = 12) => ({
    queryKey: ['stats', 'monthly', months] as const,
    queryFn: () => api.stats.monthly({ months }),
  }),
};

export const accountQueries = {
  list: () => ({
    queryKey: ['accounts'] as const,
    queryFn: api.accounts.list,
  }),
};
```

- [ ] **Step 3: `main.tsx` — QueryClientProvider**

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './styles/global.css';
import App from './App';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1 } },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

- [ ] **Step 4: Commit** `feat(frontend): envelope-aware client + TanStack Query options factories`

#### Task 5.4: ProtectedRoute su /auth/me

**Files:**
- Modify: `frontend/src/components/ProtectedRoute.tsx`

- [ ] **Step 1: Riscrittura**

```tsx
import { Navigate, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Sidebar } from './Sidebar';
import { BottomNav } from './BottomNav';
import { authQueries } from '../api/queries';
import styles from '../App.module.css';

export function ProtectedRoute() {
  const { isPending, isError } = useQuery({ ...authQueries.me() });

  if (isPending) return null;
  if (isError) return <Navigate to="/login" replace />;

  return (
    <div className={styles.shell}>
      <Sidebar />
      <main className={styles.content}>
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
```

- [ ] **Step 2: Commit** `refactor(frontend): session check via /auth/me instead of transactions ping`

#### Task 5.5: Pagine su useQuery (via i useEffect + catch silenziosi)

**Files:**
- Modify: `frontend/src/pages/Transactions/TransactionsPage.tsx`
- Modify: `frontend/src/pages/Stats/StatsPage.tsx`
- Modify: `frontend/src/pages/Accounts/AccountsPage.tsx`

Pattern identico per le tre pagine; qui il diff completo per TransactionsPage, replicarlo sulle altre.

- [ ] **Step 1: TransactionsPage — sostituire lo stato manuale**

Rimuovere:

```tsx
const [transactions, setTransactions] = useState<Transaction[]>([]);
const [loading, setLoading] = useState(true);

useEffect(() => {
  api.transactions
    .list({ days_back: 90, page_size: 500 })
    .then(r => setTransactions(r.items))
    .catch(() => {})
    .finally(() => setLoading(false));
}, []);
```

Con:

```tsx
const queryClient = useQueryClient();
const { data, isPending, isError } = useQuery({
  ...transactionQueries.list({ days_back: 90, page_size: 500 }),
});
const transactions = data?.items ?? [];
```

Import: `import { useQuery, useQueryClient } from '@tanstack/react-query';` e `import { transactionQueries } from '../../api/queries';` (via `api`/`useEffect` se non più usati).

Nel render, dove oggi c'è `{loading && <div className={styles.loadingMsg}>Loading…</div>}`:

```tsx
{isPending && <div className={styles.loadingMsg}>Loading…</div>}
{isError && <div className={styles.loadingMsg}>Impossibile caricare le transazioni — riprova.</div>}
```

E il callback del modal (oggi muta lo stato locale) diventa invalidazione cache:

```tsx
{showAdd && (
  <AddTransactionModal
    onClose={() => setShowAdd(false)}
    onAdd={() => queryClient.invalidateQueries({ queryKey: ['transactions'] })}
  />
)}
```

- [ ] **Step 2: StatsPage** — stesse sostituzioni: due `useQuery` (`statsQueries.categories(30)`, `statsQueries.monthly(12)`), rimozione del `useEffect` e dei due `useState` dei dati, stati `isError` visibili (un `<div>` di errore al posto del silenzio). Tipizzare `CustomTooltip` (via l'`any`):

```tsx
interface TooltipPayloadItem { name?: string; value?: number | string }
const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: TooltipPayloadItem[] }) => {
```

- [ ] **Step 3: AccountsPage** — `useQuery({ ...accountQueries.list() })`, stessa struttura.

- [ ] **Step 4: Verifica manuale** — `npm run dev`, login, tutte le pagine caricano; spegnere la rete → compaiono i messaggi d'errore (prima: pagina vuota silenziosa).

- [ ] **Step 5: Commit** `refactor(frontend): pages fetch via TanStack Query with visible error states`

#### Task 5.6: AddTransactionModal con react-hook-form + zod

**Files:**
- Modify: `frontend/src/pages/Transactions/AddTransactionModal.tsx`

- [ ] **Step 1: Schema + form** (sostituire gli `useState` dei campi; l'aspetto/CSS resta identico)

```tsx
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { transactionQueries } from '../../api/queries';

const schema = z.object({
  booking_date: z.string().min(1, 'Data obbligatoria'),
  amount: z.coerce.number().refine(v => v !== 0, 'Importo diverso da zero'),
  merchant_name: z.string().min(1, 'Nome obbligatorio'),
  category: z.string().optional(),
  description: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

// dentro il componente:
const form = useForm<FormValues>({
  resolver: zodResolver(schema),
  defaultValues: { booking_date: new Date().toISOString().slice(0, 10), amount: 0, merchant_name: '' },
});

const mutation = useMutation({
  ...transactionQueries.create(),
  onSuccess: tx => {
    onAdd(tx);
    onClose();
  },
});

const onSubmit = form.handleSubmit(values =>
  mutation.mutate({
    booking_date: `${values.booking_date}T00:00:00Z`,
    amount: values.amount,
    eur_amount: values.amount,
    currency: 'EUR',
    merchant_name: values.merchant_name,
    category: values.category || null,
    description: values.description || null,
  }),
);
```

Gli input passano a `{...form.register('amount')}` ecc.; gli errori di validazione si mostrano da `form.formState.errors.<campo>?.message`; l'errore di mutazione (`mutation.isError`, es. 409 duplicato) si mostra sopra il submit. Adattare i campi effettivamente presenti nel modal attuale mantenendo il markup/classi CSS.

- [ ] **Step 2: Verifica manuale + commit** `refactor(frontend): AddTransactionModal on react-hook-form + zod`

#### Task 5.7: Test Vitest + Testing Library

**Files:**
- Create: `frontend/src/tests/setup.ts`
- Create: `frontend/src/tests/ProtectedRoute.test.tsx`
- Create: `frontend/src/tests/TransactionsPage.test.tsx`
- Modify: `.github/workflows/frontend.yml` (aggiungere lint + test)

- [ ] **Step 1: `setup.ts`**

```ts
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
```

- [ ] **Step 2: Test ProtectedRoute** (pattern AI Garage: QueryClientProvider con `retry:false`, MemoryRouter, query per testo/ruolo)

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ProtectedRoute } from '../components/ProtectedRoute';

vi.mock('../api/client', () => ({
  api: { auth: { me: vi.fn().mockRejectedValue({ response: { status: 401 } }) } },
}));

function renderProtected() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/transactions']}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/transactions" element={<div>private content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProtectedRoute', () => {
  it('redirects to /login when the session check fails', async () => {
    renderProtected();
    await waitFor(() => expect(screen.getByText('login page')).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Test TransactionsPage** (happy path + errore visibile)

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { TransactionsPage } from '../pages/Transactions/TransactionsPage';

const tx = {
  id: 1, dedup_hash: 'x', booking_date: '2026-07-01T00:00:00Z', amount: -12.5,
  currency: 'EUR', eur_amount: -12.5, description: null, merchant_name: 'Esselunga',
  account_id: null, is_internal: false, category: 'Groceries', subcategory: null,
  status: 'verified' as const, source: 'enable_banking', created_at: '2026-07-01T00:00:00Z',
};

vi.mock('../api/client', () => ({
  api: {
    transactions: {
      list: vi.fn().mockResolvedValue({ items: [tx], total: 1, page: 1, page_size: 500 }),
    },
  },
}));

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TransactionsPage />
    </QueryClientProvider>,
  );
}

describe('TransactionsPage', () => {
  it('renders fetched transactions', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Esselunga')).toBeInTheDocument());
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
  });
});
```

(Nota: se il modal è montato nel tree, mockare anche `transactionQueries` non serve — le factory chiamano `api.*` già mockato.)

- [ ] **Step 4: Run** `npm run test` — Expected: PASS.

- [ ] **Step 5: Estendere la CI frontend** — nel job aggiungere dopo `tsc`:

```yaml
      - run: npm run lint
      - run: npm run test
```

- [ ] **Step 6: Commit** `test(frontend): vitest + testing-library setup with ProtectedRoute and TransactionsPage tests`

#### Task 5.8: Deploy coordinato e rimozione dei path legacy

- [ ] **Step 1:** Push su main → Vercel deploya il frontend `/v1`-aware. Verificare login + pagine su `fimbook.vercel.app`.
- [ ] **Step 2:** Rimuovere dal backend il mount legacy (in `app.py`: cancellare `app.include_router(api_router)` e `app.include_router(auth_router)` senza prefix, e il `router_legacy` se s'è usata l'opzione A del Task 3.3). `railway up --detach --service just-comfort`.
- [ ] **Step 3:** Verifica: `curl https://.../transactions` → 404; `https://.../v1/transactions` senza cookie → 401 con `{"error": ...}`; dashboard funzionante.
- [ ] **Step 4: Commit** `chore: drop legacy unversioned API mounts after frontend cutover`

---

### FASE 6 — Test d'integrazione su Postgres reale

I test attuali di `reconcile.py` mockano la sequenza di `fetchone` — si rompono a ogni modifica dell'ordine delle query pur non verificando il SQL. Regola di progetto: «don't mock what you're testing».

#### Task 6.1: Marker + fixture DB

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/conftest.py`
- Create: `tests/integration/__init__.py`, `tests/integration/conftest.py`

- [ ] **Step 1: Configurare i marker**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["integration: requires a real Postgres (docker compose up db -d)"]
addopts = "-m 'not integration'"   # default: solo unit; CI e locale girano integration esplicitamente
```

- [ ] **Step 2: `tests/integration/conftest.py`**

```python
import os

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance_test"
)


@pytest.fixture()
def db_conn():
    try:
        conn = psycopg.connect(TEST_DATABASE_URL, autocommit=False)
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable — start it with: docker compose up db -d")
    from fintracker.settings import settings

    # Apply the real schema via Alembic against the test DB
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    settings.DATABASE_URL = TEST_DATABASE_URL  # env.py reads settings
    command.upgrade(cfg, "head")

    with conn.cursor() as cur:
        cur.execute("TRUNCATE transactions RESTART IDENTITY")
    conn.commit()
    yield conn
    conn.close()
```

(Prerequisito: creare una volta il DB `finance_test` nel container: `docker compose exec db psql -U user -c "CREATE DATABASE finance_test"` — documentarlo nel README.)

#### Task 6.2: Test d'integrazione della riconciliazione

**Files:**
- Create: `tests/integration/test_reconcile_pg.py`

- [ ] **Step 1: Scrivere i test** (coprono i 3 esiti + il caso "EB hash già presente")

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fintracker.models.transaction import NormalizedTransaction
from fintracker.storage.db_insert import insert_transaction
from fintracker.storage.reconcile import reconcile_or_insert

pytestmark = pytest.mark.integration


def _eb_tx(**kw) -> NormalizedTransaction:
    base = dict(
        dedup_hash="ebhash1",
        booking_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        amount=Decimal("-12.50"),
        currency="EUR",
        eur_amount=Decimal("-12.50"),
        description="Esselunga",
        merchant_name="Esselunga",
        account_id="acc1",
        status="verified",
        source="enable_banking",
    )
    base.update(kw)
    return NormalizedTransaction(**base)


def _pending_tasker_tx(**kw) -> NormalizedTransaction:
    base = dict(
        dedup_hash="taskerhash1",
        booking_date=datetime(2026, 7, 1, 14, 32, tzinfo=timezone.utc),
        amount=Decimal("-12.50"),
        currency="EUR",
        eur_amount=Decimal("-12.50"),
        description="You paid EUR12.50 at Esselunga",
        merchant_name="Esselunga",
        status="pending",
        source="tasker",
    )
    base.update(kw)
    return NormalizedTransaction(**base)


def test_inserts_fresh_transaction(db_conn):
    result = reconcile_or_insert(db_conn, _eb_tx())
    assert result.action == "inserted"
    with db_conn.cursor() as cur:
        cur.execute("SELECT status, source FROM transactions WHERE dedup_hash = 'ebhash1'")
        assert cur.fetchone() == ("verified", "enable_banking")


def test_skips_already_verified(db_conn):
    reconcile_or_insert(db_conn, _eb_tx())
    result = reconcile_or_insert(db_conn, _eb_tx())
    assert result.action == "skipped"


def test_reconciles_pending_tasker_row(db_conn):
    insert_transaction(db_conn, _pending_tasker_tx())
    result = reconcile_or_insert(db_conn, _eb_tx())
    assert result.action == "reconciled"
    with db_conn.cursor() as cur:
        cur.execute("SELECT status, dedup_hash, source FROM transactions")
        rows = cur.fetchall()
    assert rows == [("verified", "ebhash1", "enable_banking")]


def test_keeps_tasker_hash_when_eb_hash_already_exists(db_conn):
    insert_transaction(db_conn, _eb_tx(dedup_hash="ebhash1", amount=Decimal("-99")))
    insert_transaction(db_conn, _pending_tasker_tx())
    result = reconcile_or_insert(db_conn, _eb_tx())  # ebhash1 already taken by another row
    assert result.action == "reconciled"
    with db_conn.cursor() as cur:
        cur.execute("SELECT dedup_hash FROM transactions WHERE status = 'verified' ORDER BY id")
        hashes = [r[0] for r in cur.fetchall()]
    assert "taskerhash1" in hashes  # pending row kept its own hash (no UniqueViolation)
```

- [ ] **Step 2: Run** `docker compose up db -d; uv run pytest -m integration -v` — Expected: PASS (4 test).

- [ ] **Step 3: Snellire i vecchi mock-test** — in `tests/test_reconcile.py` tenere solo i casi che testano *logica* non coperta (nessuno? allora sostituire il file con un rimando ai test d'integrazione). Non tenere doppioni fragili.

- [ ] **Step 4: CI con service container** (aggiornare `.github/workflows/backend.yml`, job `tests`):

```yaml
  tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: user
          POSTGRES_PASSWORD: changeme
          POSTGRES_DB: finance_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U user" --health-interval 5s
          --health-timeout 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run pytest -q
      - run: uv run pytest -m integration -q
        env:
          TEST_DATABASE_URL: postgresql://user:changeme@localhost:5432/finance_test
```

- [ ] **Step 5: Commit** `test: real-Postgres integration tests for reconciliation; pg service container in CI`

---

### FASE 7 — Pulizia finale e documentazione

#### Task 7.1: Dipendenze morte

- [ ] **Step 1:** `uv remove apscheduler passlib pgvector` (verificato: zero import nel codice; `passlib` fu sostituita da `bcrypt` diretto — che arriva ora come dipendenza esplicita: `uv add bcrypt`).
- [ ] **Step 2:** `uv run pytest -q` + smoke test pipeline. **Step 3: Commit** `chore: drop unused dependencies (apscheduler, passlib, pgvector), make bcrypt explicit`

#### Task 7.2: Documentazione

- [ ] **Step 1: CLAUDE.md** — aggiornare: comandi (`uvicorn fintracker.server.app:app`, `uv run alembic upgrade head`, `npm run test`/`lint`), architettura (layout `src/fintracker`, service layer, envelope `/v1`), invarianti (aggiungere: "schema via Alembic", "hash functions pinned to legacy float repr — see `_legacy_amount_repr`", "API dashboard versionata `/v1`, machine endpoints no"). Mantenerlo ≤ ~200 righe (regola meta-management): il dettaglio sta in questo piano e nel README.
- [ ] **Step 2: README** — sezione Quick start (uv sync, docker compose up db, alembic upgrade, pipeline, frontend), sezione Test (unit/integration/frontend), link a questo piano.
- [ ] **Step 3: Commit** `docs: update CLAUDE.md and README for the refactored layout`

#### Task 7.3 (opzionale): Justfile

Solo se `just` è gradito su Windows (`scoop install just`): ricette `dev`, `test`, `test-int`, `lint`, `db-migrate`, `deploy-api`, `deploy-cron` che avvolgono i comandi già documentati. Nessuna logica dentro le ricette.

---

## 4. Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Cambio accidentale del payload hash durante la migrazione Decimal | Duplicati su tutte le transazioni future | Test di regressione **prima** del cambio (Task 4.2 Step 1) pinnano la stringa payload byte-per-byte; shim `_legacy_amount_repr` |
| Railway `sync-cron` perde la schedule | Sync fermi silenziosamente | Non toccare la config del servizio: `pipeline.py` shim mantiene invariato il comando; dopo ogni deploy verificare il run successivo del cron (o trigger manuale `/sync`) |
| Envelope/`/v1` rompe il frontend live | Dashboard giù | Dual-mount legacy+v1 (Task 3.3) finché il frontend non è deployato; cutover in Task 5.8 |
| `alembic stamp head` sul DB sbagliato | Storia migrazioni incoerente | Comando one-shot esplicito con `DATABASE_URL` verificato a mano; la baseline è comunque `IF NOT EXISTS` (idempotente) |
| pyrefly incompatibile col codice legacy | Fase 0 si impantana | Soppressioni puntuali con commento; il debito si riassorbe nelle fasi 3–4 che riscrivono i moduli peggiori |
| Rate limit PSD2 bruciato dai test | Sync reali falliti per 24h | Mai chiamare EB reale nei test; smoke test solo con `--skip-fetch` |
| Rigenerazione lockfile npm senza react diretto | Build frontend rotta | Task 5.1 è il primo task frontend proprio per questo |

## 5. Ordine di esecuzione consigliato

```
Fase 0 (safety net) ──► Fase 1 (package) ──► Fase 2 (settings) ──► Fase 3 (layering+v1)
                                                                        │
Fase 5 (frontend) ◄── richiede /auth/me e /v1 dal Task 3.3/3.4 ◄────────┘
      │
      └──► Task 5.8 (cutover legacy)          Fase 4 (DB) può correre in parallelo alla 5
                                              Fase 6 dopo la 4 · Fase 7 per ultima
```

Ogni fase = una sessione di lavoro autonoma con deploy verificabile. Con esecuzione subagent-driven: un task per subagent, review tra i task.
