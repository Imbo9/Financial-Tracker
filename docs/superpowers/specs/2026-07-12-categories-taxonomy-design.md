# Categories Taxonomy — Design

**Date**: 2026-07-12
**Status**: approved pending user review
**Source of truth for names**: MoneyManager screenshots (Drive folders `12VA8KpUsIO9HvDBAKsRWEJhps-XnvsQx` expense, `1rvbk16EHW2mFF6ZXnc6Kk3vuRmGNf03_` income), extracted 2026-07-12.

## Goal

Replace the three drifted, hardcoded category lists (categorizer prompt, `AddTransactionModal.tsx::CATEGORIES`, `TransactionsPage.tsx::CATEGORY_COLORS`) with the user's real MoneyManager taxonomy, defined **once**, consumed everywhere. Categories and subcategories must be addable, renamable, and removable by touching a single file, with every consumer following automatically.

## Requirements

1. Replicate the MoneyManager taxonomy 1:1 — 20 expense + 8 income categories, 139 subcategories total. No invented additions (no housing/utilities category, no synthetic "Other" on the expense side).
2. Single source of truth; no duplicated constants anywhere (backend or frontend).
3. Taxonomy changes (add / rename / remove) require editing one file only; categorizer prompt, API validation, and frontend picker derive from it.
4. Existing rows migrate: manual rows remapped deterministically, EB/Tasker rows re-categorized by Claude with the new taxonomy.
5. Privacy invariant unchanged: the categorizer sends **only `merchant_name`** to the Claude API.
6. Idempotence and existing invariants (dedup hashes, statuses, Alembic-only DDL) untouched — this change involves **no schema change**.

## Taxonomy (canonical order)

### Expense (20 categories, 109 subcategories)

| Category | Subcategories |
|---|---|
| Groceries | Supermarket · Market & Fresh produce · Household supplies |
| Car | Fuel · Insurance & Road tax · Maintenance & Service · Tolls & Parking · Fines · Wash & Detailing · Accessories & Parts · Car rental |
| Eating Out | Restaurants & Pizzerias · Cafés & Breakfast · Work Lunch · Delivery · Drinks & Aperitifs · Street food & Quick bites |
| Personal shopping | Clothing · Shoes · Accessories · Electronics & Gadgets · Impulse buys |
| Personal care | Hair & Barber · Cosmetics & Skincare · Fragrances · Laundry & Tailoring |
| Health | Doctor visits & Specialists · Pharmacy · Dentist · Optical · Tests & Lab works · Health Insurance · Medical therapies |
| Wellness & Fitness | Gym · Nutritionist & Dietitian · Supplements · Treatments (massage, spa, aesthetics) · Basic fitness gear |
| Main hobby | Equipment · Consumables · Courses & Lessons · Events & Community |
| Sport & Outdoor | Equipment · Lift passes & Entry fees · Lessons & Guides · Activity transport · Activity lodging · Activity meals · Memberships & Fees |
| Entertainment | Music streaming · Video streaming · Cinema & Theatre · Concerts & Events · Books & Comics · Video games & Apps · Podcasts & Audiobooks · Tech gadgets & Experiential |
| Partner | Shared experiences · Shared shopping · Recurring expenses · Anniversaries & Milestones |
| Family | Shared experiences · Contributions & Support · Care & Assistance · Family events |
| Gifts | Birthdays · Holidays · Special occasions · Group gifts |
| Social life | Events & Activities · Memberships & Dues · Hosting & Treats |
| Transit | Urban public transport · Trains & Long distance · Taxi & Ride-sharing · Sharing services (car, bike, scooter) |
| Travel | Flights · Lodging · Local transport · Food while traveling · Activities & Experiences · Souvenirs & Travel shopping · Documents & Visas |
| Connectivity | Mobile phone · Home internet · Roaming & eSIM · VoIP & Cloud telephony |
| Digital services | AI & Productivity · Cloud & Storage · Creative tools · Security · Reading & News · Domains & Hosting · Development & Tools |
| Career & Professional development | Courses & Certifications · Technical books & Manuals · Conferences & Events · Professional subscriptions · Career tools · Networking & Community · Relocation & Job mobility · Languages |
| Finance & Admin | Bank fees · Taxes & Stamps · Personal documents · Insurance (non-vehicle) · Donations & Charity · Professional consulting (accountant, legal) · Miscellaneous & Unexpected |

### Income (8 categories, 30 subcategories)

| Category | Subcategories |
|---|---|
| Salary | Base salary · Overtime & Extra hours · Variable & Bonus · Benefits & Perks · Equity & Stock · Severance & End-of-employment |
| Freelance & Side income | Consulting & Projects · Content & Royalties · Teaching & Workshops |
| Investments | Dividends · Interest · Capital gains · Crypto gains · P2P & Alternative |
| Gifts received | From family · From partner · From others · Occasions |
| Reimbursements | From Partner · From Friends · From Family · Work expenses · Returns & Refunds · Insurance claims |
| Tax & State | Tax refunds · Public bonuses · Subsidies & Grants |
| Windfall | Sales · Winnings & Prizes · Found money |
| Other | *(no subcategories)* |

## Architecture

### `src/fintracker/taxonomy.py` — the single source

```python
EXPENSE_CATEGORIES: dict[str, tuple[str, ...]]   # insertion order = canonical order
INCOME_CATEGORIES: dict[str, tuple[str, ...]]

def is_valid(category: str, subcategory: str | None) -> bool
def prompt_block() -> str   # renders "- Category: Sub1, Sub2, ..." for the LLM prompt
```

Plain dicts, no classes, no I/O. Dict insertion order is the canonical display/color order.

### Categorizer (`categorizer/categorize.py`)

`_SYSTEM_PROMPT` becomes a template; the category list is injected from `taxonomy.prompt_block()` (expense + income merged — the model sees only `merchant_name`, never the amount sign, so it picks from the full set). Explicit instruction: *if no category fits, return null* (ATM withdrawals and unrecognizable P2P land on `NULL` → shown as "Uncategorized"; recognizable outgoing P2P goes by purpose: Partner, Family, Gifts, Social life). Prompt caching (`cache_control: ephemeral`) still applies — the rendered prompt is a stable string.

### API (`server/routes/api.py`)

- **New** `GET /v1/categories` (JWT-guarded, `{"data": {"expense": {cat: [subs]}, "income": {...}}}`). Static payload; clients cache it.
- `ManualTransactionIn`: pydantic `model_validator` checks `category`/`subcategory` against `taxonomy.is_valid` → 422 on unknown category or subcategory not belonging to the category. Both fields stay optional (`None` allowed).
- DB stays `TEXT`, no CHECK constraint: validation lives at the boundaries (API, categorizer), keeping taxonomy edits schema-free.

### Frontend

- `api/client.ts` + `api/queries.ts`: `taxonomy.categories()` query (staleTime `Infinity`, `gcTime` long) returning the two maps.
- `AddTransactionModal.tsx`: category `<select>` populated from the side matching the existing income/expense toggle; **new dependent subcategory `<select>`** (reset on category change, optional). Hardcoded `CATEGORIES` deleted. Manual payload now carries `subcategory` too.
- `TransactionsPage.tsx`: `CATEGORY_COLORS` deleted; `categoryColor(cat)` = stable index of `cat` in the canonical order → `var(--chart-{1..8})` (cycled), same for Stats legend colors (which already cycle by index). Unknown/legacy label → neutral `var(--text-muted)`.

## Data migration (one-shot, after deploy)

`scripts/migrate_taxonomy.py` (runs with `direct_connection()`, same env as pipeline):

1. Manual rows (`source='manual'`) — deterministic remap of old modal names: `Transport`→`Transit`, `Career & Professional`→`Career & Professional development`, `Housing`→`NULL`, `Other`→`NULL`; `Eating Out`, `Groceries`, `Health`, `Personal shopping`, `Connectivity`, `Entertainment` unchanged. Subcategories of remapped rows set to `NULL` (old free-text subs are not part of the new tree).
2. All other rows (`source != 'manual'`): `category=NULL, subcategory=NULL`.
3. Operator then runs `uv run python pipeline.py --skip-fetch` → Claude re-categorizes everything with the new prompt (~300 rows ≈ cents on Haiku).

Script is idempotent (pure UPDATEs on matching labels; second run is a no-op) and committed to `scripts/` for audit.

## Taxonomy change playbook (the "senza problemi" requirement)

| Operation | Steps |
|---|---|
| **Add** category/subcategory | Add the line in `taxonomy.py` → deploy. Prompt, validation, picker, colors follow. |
| **Rename** | Edit the line + one-off `UPDATE transactions SET category='New' WHERE category='Old'` (same for subcategory) → deploy. |
| **Remove** | Delete the line → deploy. Historical rows keep the old label (readable, colored neutral) or get the rename treatment to a successor category. |

Color stability caveat: colors derive from canonical order, so inserting a category mid-list shifts colors of later categories — acceptable (purely cosmetic), append to the end when neutrality matters.

Future evolution (out of scope now): swap the module for `categories`/`subcategories` DB tables + CRUD + MorePage editor. `GET /v1/categories` contract stays identical, so no frontend consumer changes.

## Testing

- `tests/test_taxonomy.py`: no duplicate names within a side; every category has a tuple (possibly empty); `is_valid` accepts (cat, None), (cat, own sub) and rejects unknown cat / foreign sub; `prompt_block` contains all 28 categories.
- `tests/test_categorizer.py`: rendered system prompt includes taxonomy categories (no hardcoded leftovers).
- `tests/test_api_routes.py`: `GET /v1/categories` → 200, envelope, both sides present with exact counts (20/8); POST `/v1/transactions` → 422 on unknown category, 422 on subcategory not in category, 201 on valid pair, 201 with both `None`.
- Frontend (`src/tests/`): modal shows expense categories for expense type and income ones after toggle; selecting a category populates its subcategories; submit sends `category` + `subcategory`. StatsPage/TransactionsPage color function: stable mapping, unknown label falls back.
- Migration script: unit test for the remap mapping (mocked cursor, asserts SQL and parameters).

## Out of scope

- CRUD UI for categories (MorePage "Manage categories") — future C-evolution, unblocked by design.
- Per-subcategory stats views (data is stored; UI drill-down is a separate feature).
- Budgets per category.

## Decisions log

- Approach A (Python module + `/v1/categories`) chosen over TS codegen (build step, drift risk) and DB tables (heavier; deferred until an in-app editor is wanted). User requirement 2026-07-12: taxonomy must be freely editable — satisfied by the single-file playbook above.
- Existing data: reset + Claude re-categorization for EB/Tasker rows; deterministic remap for manual rows (user choice 2026-07-12).
- ATM withdrawals / unrecognizable outgoing P2P: no dedicated category → `NULL` ("Uncategorized").
- No "Other" expense category: MoneyManager set has none; `NULL` plays that role.
