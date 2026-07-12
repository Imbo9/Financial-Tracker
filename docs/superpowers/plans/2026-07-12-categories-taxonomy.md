# MoneyManager Categories Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three drifted hardcoded category lists with the user's MoneyManager taxonomy (20 expense + 8 income categories, 139 subcategories) defined once in `src/fintracker/taxonomy.py` and consumed by the categorizer prompt, API validation, `GET /v1/categories`, and the frontend picker/colors.

**Architecture:** One plain-Python module is the single source of truth. The categorizer renders its prompt list from it, the API validates manual transactions against it and serves it under `/v1/categories`, the frontend fetches it once (staleTime Infinity) for the Add-Transaction picker (dependent category→subcategory selects) and for stable category colors. A one-shot script remaps/reset existing rows, then the existing pipeline re-categorizes via Claude.

**Tech Stack:** Python 3 + FastAPI + pydantic v2 + psycopg3 (backend), React 18 + TS + TanStack Query + react-hook-form/zod + vitest (frontend), pytest (backend tests).

**Spec:** `docs/superpowers/specs/2026-07-12-categories-taxonomy-design.md` (the taxonomy tables there are normative).

## Global Constraints

- Ruff line-length 100; `uv run ruff check .` and `uv run pyrefly check` must stay clean; lefthook gates every commit (ruff, pyrefly, pytest, gitleaks).
- Backend tests: `uv run pytest -q` (unit only). Frontend: `cd frontend && npm run test`, `npm run lint`, `npm run build` — all green before each commit.
- Dashboard API only under `/v1`, envelope `{"data": ...}`; errors `{"error": {code, message}}`.
- **No schema change** — no Alembic revision in this plan; DB `category`/`subcategory` stay TEXT.
- Privacy invariant: categorizer sends **only `merchant_name`** to the Claude API — do not touch that call shape.
- New/changed route handlers keep the `-> dict` annotation style; any numeric DB value returned must be cast `float()` at the service boundary (not applicable to taxonomy strings — noted to prevent regressions).
- Commit messages: one line, imperative, explain why. TDD: never write implementation before its failing test.
- Windows host: run backend commands from repo root, frontend commands from `frontend/`.

---

### Task 1: `taxonomy.py` — the single source of truth

**Files:**
- Create: `src/fintracker/taxonomy.py`
- Test: `tests/test_taxonomy.py`

**Interfaces:**
- Produces: `EXPENSE_CATEGORIES: dict[str, tuple[str, ...]]`, `INCOME_CATEGORIES: dict[str, tuple[str, ...]]`, `is_valid(category: str, subcategory: str | None = None) -> bool`, `prompt_block() -> str`. Later tasks import as `from fintracker import taxonomy`.

- [ ] **Step 1: Write the failing test** — `tests/test_taxonomy.py`:

```python
from fintracker import taxonomy


def test_sides_have_expected_sizes():
    assert len(taxonomy.EXPENSE_CATEGORIES) == 20
    assert len(taxonomy.INCOME_CATEGORIES) == 8
    assert sum(len(s) for s in taxonomy.EXPENSE_CATEGORIES.values()) == 109
    assert sum(len(s) for s in taxonomy.INCOME_CATEGORIES.values()) == 30


def test_no_name_overlap_between_sides():
    assert not set(taxonomy.EXPENSE_CATEGORIES) & set(taxonomy.INCOME_CATEGORIES)


def test_no_duplicate_subcategories_within_a_category():
    for cats in (taxonomy.EXPENSE_CATEGORIES, taxonomy.INCOME_CATEGORIES):
        for cat, subs in cats.items():
            assert len(subs) == len(set(subs)), f"duplicate subcategory in {cat}"


def test_canonical_order_starts_as_screenshotted():
    assert next(iter(taxonomy.EXPENSE_CATEGORIES)) == "Groceries"
    assert next(iter(taxonomy.INCOME_CATEGORIES)) == "Salary"


def test_is_valid_accepts_category_alone():
    assert taxonomy.is_valid("Car")
    assert taxonomy.is_valid("Salary", None)


def test_is_valid_accepts_own_subcategory():
    assert taxonomy.is_valid("Car", "Fuel")
    assert taxonomy.is_valid("Windfall", "Found money")


def test_is_valid_rejects_unknown_category():
    assert not taxonomy.is_valid("Food & Dining")


def test_is_valid_rejects_foreign_subcategory():
    assert not taxonomy.is_valid("Car", "Supermarket")


def test_income_other_has_no_subcategories():
    assert taxonomy.INCOME_CATEGORIES["Other"] == ()


def test_prompt_block_contains_every_category():
    block = taxonomy.prompt_block()
    for cat in (*taxonomy.EXPENSE_CATEGORIES, *taxonomy.INCOME_CATEGORIES):
        assert f"- {cat}" in block
    assert "Expense categories:" in block
    assert "Income categories:" in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_taxonomy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fintracker.taxonomy'`

- [ ] **Step 3: Write the module** — `src/fintracker/taxonomy.py` (names copied 1:1 from the spec tables; dict insertion order **is** the canonical order):

```python
"""Single source of truth for the category taxonomy (MoneyManager replica, 2026-07-12).

Every consumer derives from this module: categorizer prompt, API validation,
GET /v1/categories, frontend picker and colors. To add/rename/remove a category
edit ONLY this file (renames also need a one-off UPDATE on transactions labels —
see docs/superpowers/specs/2026-07-12-categories-taxonomy-design.md, playbook).
"""

EXPENSE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Groceries": ("Supermarket", "Market & Fresh produce", "Household supplies"),
    "Car": (
        "Fuel", "Insurance & Road tax", "Maintenance & Service", "Tolls & Parking",
        "Fines", "Wash & Detailing", "Accessories & Parts", "Car rental",
    ),
    "Eating Out": (
        "Restaurants & Pizzerias", "Cafés & Breakfast", "Work Lunch", "Delivery",
        "Drinks & Aperitifs", "Street food & Quick bites",
    ),
    "Personal shopping": (
        "Clothing", "Shoes", "Accessories", "Electronics & Gadgets", "Impulse buys",
    ),
    "Personal care": (
        "Hair & Barber", "Cosmetics & Skincare", "Fragrances", "Laundry & Tailoring",
    ),
    "Health": (
        "Doctor visits & Specialists", "Pharmacy", "Dentist", "Optical",
        "Tests & Lab works", "Health Insurance", "Medical therapies",
    ),
    "Wellness & Fitness": (
        "Gym", "Nutritionist & Dietitian", "Supplements",
        "Treatments (massage, spa, aesthetics)", "Basic fitness gear",
    ),
    "Main hobby": ("Equipment", "Consumables", "Courses & Lessons", "Events & Community"),
    "Sport & Outdoor": (
        "Equipment", "Lift passes & Entry fees", "Lessons & Guides", "Activity transport",
        "Activity lodging", "Activity meals", "Memberships & Fees",
    ),
    "Entertainment": (
        "Music streaming", "Video streaming", "Cinema & Theatre", "Concerts & Events",
        "Books & Comics", "Video games & Apps", "Podcasts & Audiobooks",
        "Tech gadgets & Experiential",
    ),
    "Partner": (
        "Shared experiences", "Shared shopping", "Recurring expenses",
        "Anniversaries & Milestones",
    ),
    "Family": (
        "Shared experiences", "Contributions & Support", "Care & Assistance", "Family events",
    ),
    "Gifts": ("Birthdays", "Holidays", "Special occasions", "Group gifts"),
    "Social life": ("Events & Activities", "Memberships & Dues", "Hosting & Treats"),
    "Transit": (
        "Urban public transport", "Trains & Long distance", "Taxi & Ride-sharing",
        "Sharing services (car, bike, scooter)",
    ),
    "Travel": (
        "Flights", "Lodging", "Local transport", "Food while traveling",
        "Activities & Experiences", "Souvenirs & Travel shopping", "Documents & Visas",
    ),
    "Connectivity": ("Mobile phone", "Home internet", "Roaming & eSIM", "VoIP & Cloud telephony"),
    "Digital services": (
        "AI & Productivity", "Cloud & Storage", "Creative tools", "Security",
        "Reading & News", "Domains & Hosting", "Development & Tools",
    ),
    "Career & Professional development": (
        "Courses & Certifications", "Technical books & Manuals", "Conferences & Events",
        "Professional subscriptions", "Career tools", "Networking & Community",
        "Relocation & Job mobility", "Languages",
    ),
    "Finance & Admin": (
        "Bank fees", "Taxes & Stamps", "Personal documents", "Insurance (non-vehicle)",
        "Donations & Charity", "Professional consulting (accountant, legal)",
        "Miscellaneous & Unexpected",
    ),
}

INCOME_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Salary": (
        "Base salary", "Overtime & Extra hours", "Variable & Bonus", "Benefits & Perks",
        "Equity & Stock", "Severance & End-of-employment",
    ),
    "Freelance & Side income": (
        "Consulting & Projects", "Content & Royalties", "Teaching & Workshops",
    ),
    "Investments": ("Dividends", "Interest", "Capital gains", "Crypto gains", "P2P & Alternative"),
    "Gifts received": ("From family", "From partner", "From others", "Occasions"),
    "Reimbursements": (
        "From Partner", "From Friends", "From Family", "Work expenses",
        "Returns & Refunds", "Insurance claims",
    ),
    "Tax & State": ("Tax refunds", "Public bonuses", "Subsidies & Grants"),
    "Windfall": ("Sales", "Winnings & Prizes", "Found money"),
    "Other": (),
}

_ALL_CATEGORIES = {**EXPENSE_CATEGORIES, **INCOME_CATEGORIES}


def is_valid(category: str, subcategory: str | None = None) -> bool:
    """True when the category exists and the subcategory (if given) belongs to it."""
    subs = _ALL_CATEGORIES.get(category)
    if subs is None:
        return False
    return subcategory is None or subcategory in subs


def _render(side_name: str, categories: dict[str, tuple[str, ...]]) -> list[str]:
    lines = [f"{side_name} categories:"]
    for cat, subs in categories.items():
        lines.append(f"- {cat}: {', '.join(subs)}" if subs else f"- {cat}")
    return lines


def prompt_block() -> str:
    """Category list rendered for the categorizer system prompt."""
    return "\n".join(
        [*_render("Expense", EXPENSE_CATEGORIES), "", *_render("Income", INCOME_CATEGORIES)]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_taxonomy.py -q`
Expected: 10 passed. Then full suite: `uv run pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/taxonomy.py tests/test_taxonomy.py
git commit -m "feat: taxonomy module — single source for MoneyManager categories"
```

---

### Task 2: Categorizer prompt derives from the taxonomy

**Files:**
- Modify: `src/fintracker/categorizer/categorize.py:13-35` (the `_SYSTEM_PROMPT` block only)
- Test: `tests/test_categorizer.py` (new file)

**Interfaces:**
- Consumes: `taxonomy.prompt_block()` from Task 1.
- Produces: module-level `_SYSTEM_PROMPT: str` (same name as today; `_categorize_batch` and `categorize_uncategorized` untouched).

- [ ] **Step 1: Write the failing test** — `tests/test_categorizer.py`:

```python
from fintracker import taxonomy
from fintracker.categorizer.categorize import _SYSTEM_PROMPT


def test_prompt_contains_every_taxonomy_category():
    for cat in (*taxonomy.EXPENSE_CATEGORIES, *taxonomy.INCOME_CATEGORIES):
        assert f"- {cat}" in _SYSTEM_PROMPT


def test_prompt_dropped_the_old_hardcoded_taxonomy():
    assert "Food & Dining" not in _SYSTEM_PROMPT
    assert "ATM/Cash" not in _SYSTEM_PROMPT


def test_prompt_keeps_null_fallback_and_json_contract():
    assert "null" in _SYSTEM_PROMPT
    assert '[{"category": "...", "subcategory": "..."}, ...]' in _SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_categorizer.py -q`
Expected: FAIL — old prompt lacks e.g. `- Groceries` line for every category (first assert on a new-only name like `- Main hobby` fails) and still contains `Food & Dining`.

- [ ] **Step 3: Replace the prompt** in `src/fintracker/categorizer/categorize.py` — delete the current `_SYSTEM_PROMPT = """..."""` (lines 13-35) and write:

```python
from fintracker import taxonomy

_SYSTEM_PROMPT = f"""You are a personal finance categorizer for Revolut transactions in Italy.
Given a JSON array of merchant names, assign each a category and optional subcategory.

Pick ONLY from these categories and subcategories:

{taxonomy.prompt_block()}

Rules:
- The merchant name alone decides: pick the single best fit from either side.
- Use null for subcategory when none fits the merchant.
- If NO category fits (e.g. ATM withdrawals, unrecognizable person-to-person transfers),
  use null for category too.
- Recognizable person-to-person transfers go by purpose: Partner, Family, Gifts or
  Social life when paying out; Reimbursements or Gifts received when money comes in.

Respond ONLY with a JSON array in the same order as the input:
[{{"category": "...", "subcategory": "..."}}, ...]"""
```

(The `from fintracker import taxonomy` import goes with the existing imports at the top; the doubled `{{ }}` keeps the literal JSON braces inside the f-string.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_categorizer.py tests/test_taxonomy.py -q` then `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/categorizer/categorize.py tests/test_categorizer.py
git commit -m "feat: categorizer prompt rendered from the taxonomy module"
```

---

### Task 3: `GET /v1/categories`

**Files:**
- Modify: `src/fintracker/server/routes/api.py` (new route at the end; import taxonomy)
- Test: `tests/test_api_routes.py` (new class)

**Interfaces:**
- Consumes: `taxonomy.EXPENSE_CATEGORIES` / `taxonomy.INCOME_CATEGORIES`.
- Produces: `GET /v1/categories` → `{"data": {"expense": {name: [subs...]}, "income": {...}}}`, JWT-guarded like every `router_v1` route. Frontend Task 5 consumes this exact shape.

- [ ] **Step 1: Write the failing test** — append to `tests/test_api_routes.py`:

```python
class TestCategories:
    def test_missing_auth_returns_401(self, client):
        resp = client.get("/v1/categories")
        assert resp.status_code == 401

    def test_returns_full_taxonomy(self, auth_client):
        resp = auth_client.get("/v1/categories")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["expense"]) == 20
        assert len(data["income"]) == 8
        assert data["expense"]["Car"][0] == "Fuel"
        assert data["income"]["Other"] == []
        # canonical order survives JSON round-trip
        assert next(iter(data["expense"])) == "Groceries"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_routes.py -q -k "Categories"`
Expected: FAIL — 404 on `/v1/categories` (route missing) → the 401 test also gets 404.

- [ ] **Step 3: Add the route** — in `src/fintracker/server/routes/api.py`, add `from fintracker import taxonomy` to the imports and append after `accounts_v1`:

```python
@router_v1.get("/categories")
def categories_v1() -> dict:
    return {"data": {"expense": taxonomy.EXPENSE_CATEGORIES, "income": taxonomy.INCOME_CATEGORIES}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_routes.py -q`
Expected: all pass (tuples serialize as JSON arrays; dict order is preserved).

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: GET /v1/categories serves the taxonomy to the dashboard"
```

---

### Task 4: Validate manual transactions against the taxonomy

**Files:**
- Modify: `src/fintracker/server/routes/api.py:20-29` (`ManualTransactionIn`)
- Test: `tests/test_api_routes.py` (extend `TestCreateTransaction`)

**Interfaces:**
- Consumes: `taxonomy.is_valid` from Task 1.
- Produces: POST `/v1/transactions` → 422 when category unknown, subcategory foreign to its category, or subcategory sent without category. Valid pairs and all-`None` unchanged (201).

- [ ] **Step 1: Write the failing tests** — inside `class TestCreateTransaction` in `tests/test_api_routes.py` add (reuse the file's existing `_mock_pool` / mock-cursor pattern from `test_create_returns_201` for the valid case):

```python
    def _valid_body(self, **overrides):
        body = {
            "booking_date": "2026-06-08T12:00:00Z",
            "amount": -12.50,
            "currency": "EUR",
            "eur_amount": -12.50,
            "merchant_name": "Esso",
        }
        body.update(overrides)
        return body

    def test_unknown_category_returns_422(self, auth_client):
        resp = auth_client.post(
            "/v1/transactions", json=self._valid_body(category="Food & Dining")
        )
        assert resp.status_code == 422

    def test_foreign_subcategory_returns_422(self, auth_client):
        resp = auth_client.post(
            "/v1/transactions",
            json=self._valid_body(category="Car", subcategory="Supermarket"),
        )
        assert resp.status_code == 422

    def test_subcategory_without_category_returns_422(self, auth_client):
        resp = auth_client.post(
            "/v1/transactions", json=self._valid_body(subcategory="Fuel")
        )
        assert resp.status_code == 422

    def test_valid_category_subcategory_pair_returns_201(self, auth_client):
        returned_row = dict(FAKE_ROW, category="Car", subcategory="Fuel")
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = returned_row
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        with patch("fintracker.storage.db.get_pool", return_value=_mock_pool(mock_conn)):
            resp = auth_client.post(
                "/v1/transactions",
                json=self._valid_body(category="Car", subcategory="Fuel"),
            )
        assert resp.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_routes.py -q -k "TestCreateTransaction"`
Expected: the three 422 tests FAIL (they currently get 201/500 because nothing validates); the valid-pair test passes already.

- [ ] **Step 3: Add the validator** — in `src/fintracker/server/routes/api.py`, extend the pydantic import to `from pydantic import BaseModel, Field, model_validator` and add to `ManualTransactionIn`:

```python
    @model_validator(mode="after")
    def _check_taxonomy(self) -> "ManualTransactionIn":
        if self.subcategory is not None and self.category is None:
            raise ValueError("subcategory requires a category")
        if self.category is not None and not taxonomy.is_valid(self.category, self.subcategory):
            raise ValueError("unknown category or subcategory")
        return self
```

(Existing behavior preserved: the global `RequestValidationError` handler already maps this to the 422 envelope without leaking details.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: all pass — note `test_create_returns_201` keeps passing because `Eating Out` exists in the new taxonomy.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: manual transactions validated against the taxonomy (422 on unknown labels)"
```

---

### Task 5: Frontend API layer for the taxonomy

**Files:**
- Modify: `frontend/src/api/types.ts` (append interface)
- Modify: `frontend/src/api/client.ts` (new `taxonomy` section)
- Modify: `frontend/src/api/queries.ts` (new factory)

**Interfaces:**
- Consumes: `GET /v1/categories` from Task 3 (via the `/api` proxy, envelope-unwrapped by `unwrap`).
- Produces: `interface Taxonomy { expense: Record<string, string[]>; income: Record<string, string[]> }`, `api.taxonomy.get(): Promise<Taxonomy>`, `taxonomyQueries.categories()` query-options factory. Tasks 6 and 7 spread `{ ...taxonomyQueries.categories() }`.

- [ ] **Step 1: types.ts** — append:

```ts
export interface Taxonomy {
  expense: Record<string, string[]>;
  income: Record<string, string[]>;
}
```

- [ ] **Step 2: client.ts** — add `Taxonomy` to the type import list and a new section inside `api` (after `stats`):

```ts
  taxonomy: {
    get: (): Promise<Taxonomy> =>
      http.get('/v1/categories').then(unwrap<Taxonomy>),
  },
```

- [ ] **Step 3: queries.ts** — append:

```ts
export const taxonomyQueries = {
  categories: () => ({
    queryKey: ['taxonomy'] as const,
    queryFn: api.taxonomy.get,
    staleTime: Infinity,
    gcTime: Infinity,
  }),
};
```

- [ ] **Step 4: Verify**

Run (from `frontend/`): `npm run lint && npm run build && npm run test`
Expected: all green (no consumer yet; this task is the typed contract the next two build on).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/queries.ts
git commit -m "feat(frontend): taxonomy query factory over GET /v1/categories"
```

---

### Task 6: Add-Transaction modal — dynamic picker with dependent subcategory

**Files:**
- Modify: `frontend/src/pages/Transactions/AddTransactionModal.tsx`
- Test: `frontend/src/tests/AddTransactionModal.test.tsx` (new file)

**Interfaces:**
- Consumes: `taxonomyQueries.categories()` (Task 5); existing `type` income/expense toggle in the modal.
- Produces: create payload now includes `subcategory: string | null`; hardcoded `CATEGORIES` array deleted.

- [ ] **Step 1: Write the failing test** — `frontend/src/tests/AddTransactionModal.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { AddTransactionModal } from '../pages/Transactions/AddTransactionModal';

vi.mock('../api/client', () => ({
  api: {
    taxonomy: {
      get: vi.fn().mockResolvedValue({
        expense: { Groceries: ['Supermarket'], Car: ['Fuel', 'Tolls & Parking'] },
        income: { Salary: ['Base salary'] },
      }),
    },
    transactions: { create: vi.fn().mockResolvedValue({}) },
  },
}));

function renderModal() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AddTransactionModal onClose={() => {}} onAdd={() => {}} />
    </QueryClientProvider>,
  );
}

describe('AddTransactionModal', () => {
  it('shows expense categories by default and income ones after the toggle', async () => {
    renderModal();
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Car' })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('option', { name: 'Salary' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Income' }));
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Salary' })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('option', { name: 'Car' })).not.toBeInTheDocument();
  });

  it('populates subcategories for the chosen category and resets on change', async () => {
    renderModal();
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Car' })).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Car' } });
    expect(await screen.findByLabelText('Subcategory')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Fuel' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Subcategory'), { target: { value: 'Fuel' } });
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Groceries' } });
    expect(screen.queryByRole('option', { name: 'Fuel' })).not.toBeInTheDocument();
    expect((screen.getByLabelText('Subcategory') as HTMLSelectElement).value).toBe('');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run src/tests/AddTransactionModal.test.tsx`
Expected: FAIL — `api.taxonomy` is never called (module still uses the hardcoded `CATEGORIES`), so `option { name: 'Car' }` (present) but 'Salary'-after-toggle assertions fail and there is no 'Subcategory' label. (First failure: `Car` IS in the old hardcoded list? No — old list has no 'Car'; the first `waitFor` itself fails.)

- [ ] **Step 3: Implement** — in `AddTransactionModal.tsx`:

1. Delete the `CATEGORIES` const (lines 12-15).
2. Extend imports: `import { useQuery, useMutation } from '@tanstack/react-query';` and `import { transactionQueries, taxonomyQueries } from '../../api/queries';`
3. Add `subcategory: z.string().optional(),` to the zod schema (after `category`) and `subcategory: ''` to `defaultValues`.
4. Inside the component, before the form markup:

```tsx
  const { data: taxonomy } = useQuery({ ...taxonomyQueries.categories() });
  const sideCategories = (type === 'income' ? taxonomy?.income : taxonomy?.expense) ?? {};
  const selectedCategory = form.watch('category');
  const subcategories = selectedCategory ? (sideCategories[selectedCategory] ?? []) : [];
```

5. The income/expense toggle buttons also clear both fields when switching side:

```tsx
                  onClick={() => {
                    setType(t);
                    form.setValue('category', '');
                    form.setValue('subcategory', '');
                  }}
```

6. Replace the category `<select>` and add the dependent subcategory select right after it:

```tsx
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Category</span>
                <select
                  className={styles.input}
                  {...form.register('category', {
                    onChange: () => form.setValue('subcategory', ''),
                  })}
                >
                  <option value="">Select category</option>
                  {Object.keys(sideCategories).map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>

              {subcategories.length > 0 && (
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Subcategory</span>
                  <select className={styles.input} {...form.register('subcategory')}>
                    <option value="">Select subcategory</option>
                    {subcategories.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>
              )}
```

7. Add `subcategory: values.subcategory || null,` to the `mutation.mutate({...})` payload after `category`.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npm run test && npm run lint && npm run build`
Expected: all green (existing TransactionsPage tests unaffected — the modal is not rendered there).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Transactions/AddTransactionModal.tsx frontend/src/tests/AddTransactionModal.test.tsx
git commit -m "feat(frontend): modal picker driven by the taxonomy with dependent subcategory"
```

---

### Task 7: Category colors from canonical order

**Files:**
- Modify: `frontend/src/pages/Transactions/TransactionsPage.tsx` (delete `CATEGORY_COLORS` + `categoryColor`, lines 38-51; thread a `color` prop into `TxRow`)
- Test: `frontend/src/tests/TransactionsPage.test.tsx` (extend mock + new test)

**Interfaces:**
- Consumes: `taxonomyQueries.categories()` (Task 5).
- Produces: `TxRow` signature becomes `{ tx, index, color }: { tx: Transaction; index: number; color: string }`.

- [ ] **Step 1: Extend the mock and write the failing test** — in `frontend/src/tests/TransactionsPage.test.tsx`, extend the `vi.mock('../api/client', ...)` factory's `api` object with:

```tsx
    taxonomy: {
      get: vi.fn().mockResolvedValue({
        expense: { Groceries: ['Supermarket'], Car: ['Fuel'] },
        income: { Salary: [] },
      }),
    },
```

and add the test (the fixture tx has `category: 'Groceries'`, index 0 in canonical order → `--chart-1`):

```tsx
  it('colors the row icon by canonical taxonomy order', async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText('Esselunga')).toBeInTheDocument());
    await waitFor(() => {
      const icon = container.querySelector('[class*=txIcon]') as HTMLElement;
      expect(icon.style.getPropertyValue('--cat-color')).toBe('var(--chart-1)');
    });
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run src/tests/TransactionsPage.test.tsx`
Expected: the new test FAILS — current `CATEGORY_COLORS` has no 'Groceries' entry, so the icon gets the fallback `var(--chart-1)`… **check**: old fallback is also `var(--chart-1)`, which would false-pass. Use `Car` instead: change the fixture copy for this test? Simpler deterministic red: assert on a category the old map colors differently — the fixture `Groceries` hits old fallback `var(--chart-1)` = new expected value. → **Adjust**: in the mock taxonomy, order `{ Car: ['Fuel'], Groceries: ['Supermarket'] }` so 'Groceries' is index 1 → expected `var(--chart-2)`, which the old code cannot produce. Expected: FAIL with `--cat-color` = `var(--chart-1)` (old fallback) ≠ `var(--chart-2)`.

- [ ] **Step 3: Implement** — in `TransactionsPage.tsx`:

1. Delete `CATEGORY_COLORS` and `categoryColor` (lines 38-51). Keep `categoryInitial`.
2. Import `taxonomyQueries` alongside `transactionQueries`.
3. In the component, after the transactions query:

```tsx
  const { data: taxonomy } = useQuery({ ...taxonomyQueries.categories() });
  const categoryOrder = useMemo(
    () => [...Object.keys(taxonomy?.expense ?? {}), ...Object.keys(taxonomy?.income ?? {})],
    [taxonomy],
  );
  const colorOf = (cat: string | null): string => {
    const i = cat ? categoryOrder.indexOf(cat) : -1;
    return i === -1 ? 'var(--text-muted)' : `var(--chart-${(i % 8) + 1})`;
  };
```

4. Both `TxRow` call sites (daily and monthly views): `<TxRow key={tx.id} tx={tx} index={i} color={colorOf(tx.category)} />`
5. `TxRow`: signature `function TxRow({ tx, index, color }: { tx: Transaction; index: number; color: string })`; delete `const color = categoryColor(tx.category);` (the `--cat-color` style line stays as is).

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npm run test && npm run lint && npm run build`
Expected: all green, including the older TransactionsPage tests (mock now provides taxonomy).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Transactions/TransactionsPage.tsx frontend/src/tests/TransactionsPage.test.tsx
git commit -m "feat(frontend): category colors from canonical taxonomy order, hardcoded map removed"
```

---

### Task 8: Data-migration script

**Files:**
- Create: `scripts/migrate_taxonomy.py`
- Test: `tests/test_migrate_taxonomy.py`

**Interfaces:**
- Consumes: `taxonomy` module; `fintracker.storage.db.direct_connection`.
- Produces: `migrate(conn) -> dict[str, int]` (label → affected rows); CLI entry `uv run python scripts/migrate_taxonomy.py`.

- [ ] **Step 1: Write the failing test** — `tests/test_migrate_taxonomy.py`:

```python
from unittest.mock import MagicMock

import scripts.migrate_taxonomy as mig


def _conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.rowcount = 3
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_remap_table_covers_all_legacy_modal_names():
    assert mig.MANUAL_REMAP == {
        "Transport": "Transit",
        "Career & Professional": "Career & Professional development",
        "Housing": None,
        "Other": None,
    }


def test_migrate_remaps_manual_then_resets_the_rest():
    conn, cur = _conn()
    counts = mig.migrate(conn)

    executed = [c.args for c in cur.execute.call_args_list]
    # 4 manual remaps + 1 manual catch-all + 1 non-manual reset
    assert len(executed) == 6
    assert executed[0][1] == ("Transit", "Transport")
    assert "source = 'manual'" in executed[0][0]
    assert "source != 'manual'" in executed[-1][0]
    assert conn.commit.called
    assert len(counts) == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_migrate_taxonomy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_taxonomy'`

- [ ] **Step 3: Write the script** — `scripts/migrate_taxonomy.py`:

```python
"""One-shot 2026-07 taxonomy migration: remap manual rows to the MoneyManager
names, reset every other row so the pipeline re-categorizes with the new prompt.

Run against prod with Railway env:
  railway run --service just-comfort -- uv run python scripts/migrate_taxonomy.py
Then re-categorize:
  railway run --service just-comfort -- uv run python pipeline.py --skip-fetch

Idempotent: every statement matches only rows still carrying legacy labels.
"""

import logging

from fintracker import taxonomy
from fintracker.storage.db import direct_connection

log = logging.getLogger(__name__)

# Legacy AddTransactionModal names → new taxonomy (None = leave uncategorized).
MANUAL_REMAP: dict[str, str | None] = {
    "Transport": "Transit",
    "Career & Professional": "Career & Professional development",
    "Housing": None,
    "Other": None,
}


def migrate(conn) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for old, new in MANUAL_REMAP.items():
            cur.execute(
                "UPDATE transactions SET category = %s, subcategory = NULL"
                " WHERE source = 'manual' AND category = %s",
                (new, old),
            )
            counts[f"manual {old} -> {new}"] = cur.rowcount

        valid = [*taxonomy.EXPENSE_CATEGORIES, *taxonomy.INCOME_CATEGORIES]
        cur.execute(
            "UPDATE transactions SET category = NULL, subcategory = NULL"
            " WHERE source = 'manual' AND category IS NOT NULL AND category != ALL(%s)",
            (valid,),
        )
        counts["manual unknown -> NULL"] = cur.rowcount

        cur.execute(
            "UPDATE transactions SET category = NULL, subcategory = NULL"
            " WHERE source != 'manual'"
        )
        counts["non-manual reset for re-categorization"] = cur.rowcount

    conn.commit()
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for label, n in migrate(direct_connection()).items():
        log.info("%-45s %5d rows", label, n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_migrate_taxonomy.py -q` then `uv run pytest -q && uv run ruff check . && uv run pyrefly check`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_taxonomy.py tests/test_migrate_taxonomy.py
git commit -m "feat: one-shot migration remapping manual rows and resetting the rest"
```

---

### Task 9: Deploy, migrate production data, verify live, document

**Files:**
- Modify: `CLAUDE.md` (Key invariants + Architecture mention)

**Interfaces:**
- Consumes: everything above, deployed.

- [ ] **Step 1: Document the invariant** — in `CLAUDE.md` under **Key invariants**, add:

```markdown
**Taxonomy**: `src/fintracker/taxonomy.py` is the only place categories/subcategories are
defined (20 expense + 8 income, MoneyManager replica). Categorizer prompt, API validation,
`/v1/categories`, and the frontend picker/colors all derive from it. Add = edit the dict.
Rename = edit + one-off `UPDATE transactions` on the old label (playbook in
docs/superpowers/specs/2026-07-12-categories-taxonomy-design.md). Never re-hardcode lists.
```

- [ ] **Step 2: Commit docs, push, deploy backend**

```bash
git add CLAUDE.md   # note: CLAUDE.md is gitignored in this repo — if `git add` refuses, skip the commit and keep the edit local
git commit -m "docs: taxonomy single-source invariant" || true
git push origin main
railway up --detach --service just-comfort
```

Vercel deploys the frontend from the push automatically.

- [ ] **Step 3: Wait for deploys, then migrate prod data**

Verify backend live: `GET https://fimbook.vercel.app/api/v1/categories` (from the authenticated browser tab) returns the taxonomy. Then:

```bash
railway run --service just-comfort -- uv run python scripts/migrate_taxonomy.py
railway run --service just-comfort -- uv run python pipeline.py --skip-fetch
```

Expected: migration prints per-label row counts; pipeline logs `Categorizing N transactions...` and finishes with no batch failures.

- [ ] **Step 4: Live verification (browser, DOM-based — MCP tab is often hidden)**

1. `/api/v1/stats/categories?days_back=30&direction=expense` → every `category` is one of the 20 (or `Uncategorized`).
2. `/stats` page: legend shows new names; donut sectors > 0.
3. `/transactions`: rows show new category labels with colors; no `NaN`.
4. Add-transaction modal: Expense side lists 20 categories; choosing `Car` offers `Fuel`; submit succeeds (201) and the row appears.
5. Console: zero uncaught errors.

- [ ] **Step 5: Final full-suite pass and wrap-up**

```bash
uv run pytest -q && uv run ruff check . && uv run pyrefly check
cd frontend && npm run test && npm run lint && npm run build
```

Expected: everything green. Report results to the user with evidence.

---

## Self-review notes

- Spec coverage: taxonomy data (T1), categorizer (T2), endpoint (T3), validation (T4), FE layer/picker/colors (T5-7), migration (T8), playbook documented in CLAUDE.md + spec (T9). Out-of-scope items (CRUD UI, per-subcategory stats) intentionally absent.
- `CLAUDE.md` is git-ignored in this repo (per its own "Files NOT in git" section) — Task 9 Step 2 accounts for the `git add` refusing.
- Type consistency: `taxonomy.EXPENSE_CATEGORIES`/`INCOME_CATEGORIES` names used identically in T2/T3/T8; `Taxonomy` TS interface shape matches T3's JSON; `TxRow` color prop consistent within T7.
