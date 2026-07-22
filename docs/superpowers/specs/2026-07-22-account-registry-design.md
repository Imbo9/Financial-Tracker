# SP-1 — Account Registry (design)

*2026-07-22 · first sub-project of the multi-source gateway · driver: manual accounts + CSV import*

## Context

The multi-source gateway was decomposed (driver chosen: **manual accounts + CSV/Excel
import**) into two value slices over one shared foundation:

- **SP-1 — Account registry** (this spec): turn `accounts` from an EB-calibration table
  into a first-class registry that can hold non-API accounts (cash, savings, cards
  without Open Banking), and wire the *already-built* manual-entry form to it.
- **SP-2 — CSV/Excel import** (later spec): bulk-import a bank export into a registered
  account. Reuses SP-1's dedup/insert/account-binding plumbing.

Downstream features unlocked by SP-1 but **out of scope** here: AC1 grouped presentation
+ subtotals, S2 account selector/filter, A1 transfers with fees, A2 recurrences.

### What already exists (do not rebuild)

- Backend manual path is ~80% done: `ManualTransactionIn` (already carries an
  `account_id` field), `POST /v1/transactions` → `transactions.create_manual()`,
  `manual_dedup_hash`, taxonomy validation, 409 on duplicate.
- Frontend `AddTransactionModal.tsx` — full Income/Expense form (amount, merchant, date,
  dependent category/subcategory select, note), wired to `transactionQueries.create()`.
  It **does not send `account_id`** and has **no account picker** (lines ~57–66).
- `accounts` table (migration 0002): `account_uid` PK, `display_name`, `opening_balance`,
  `eb_balance`, `calibrated_at`. No type, no manual/EB discriminator, no CRUD.
- `calibrate_balances.py` populates EB rows but **never sets `display_name`** → today
  AccountsPage renders raw account UIDs (`acc.display_name ?? acc.account_id`).
- `accounts.balances()` uses `INNER JOIN transactions` → an account with zero
  transactions would not appear.

## Goals

1. Register non-API accounts (cash / bank / card / savings) with a user-set balance and
   have them show up in net worth and per-account balances.
2. Attach manual transactions to a chosen account via the existing add-transaction form.
3. Let the user rename and type any account, including EB ones (fixes the raw-UID display).

## Non-goals

Grouped presentation + subtotals (AC1), account selector/filter (S2), transfers (A1),
recurrences (A2), CSV import (SP-2), date+time on entry (A4), Save & Continue (A6),
multi-currency manual accounts.

## Data model — migration 0003

Add to `accounts` (hand-written `op.execute`, no autogenerate; nothing removed/renamed):

| column | type | note |
|---|---|---|
| `type` | `TEXT NOT NULL DEFAULT 'bank'` | app-validated enum `cash \| bank \| card \| savings` |
| `is_manual` | `BOOL NOT NULL DEFAULT FALSE` | EB rows FALSE (from calibration); user rows TRUE |
| `currency` | `CHAR(3) NOT NULL DEFAULT 'EUR'` | account display currency |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | drives balance-history entry point |

Existing EB rows backfill entirely from the defaults (`is_manual=FALSE`, `type='bank'`,
`currency='EUR'`). `opening_balance`/`eb_balance`/`calibrated_at` keep their meaning;
`eb_balance`/`calibrated_at` stay NULL on manual rows.

**Manual account identity**: `account_uid = "manual:" + uuid4()`. The `manual:` prefix
namespaces it away from EB UIDs, matching the `tasker|` / `manual|` hash-namespacing
convention. `type` is validated in application code (like `taxonomy`), not a DB CHECK.

## Balance math

### `accounts.balances()` — LEFT JOIN

Switch from `INNER JOIN transactions` to **`FROM accounts a LEFT JOIN transactions t`**:
`balance = a.opening_balance + COALESCE(SUM(t.eur_amount), 0)`, grouped by account. A
freshly created cash account (opening only, no transactions) then appears with its
opening balance. The "only registered accounts" invariant is preserved and now driven by
the `accounts` table itself (manual accounts are registered; stale EB UIDs from consent
renewals are not — same net effect as the current INNER JOIN).

### Opening-balance semantics (manual)

The number entered at creation = **the account's balance as of now** (wallet-style);
future transactions move it. For an account with no prior transactions this equals the
EB convention `opening = current_balance − Σ(existing deltas)` with an empty sum.
Backdated transactions *before* `created_at` are an accepted edge case, deferred to SP-2
(CSV import must define opening semantics for imported history anyway).

### `balance_history()` — manual openings enter at `created_at`, not retroactively

Today `balance_history` sums **all** `opening_balance` into one flat baseline applied
across the whole series. That is correct for EB accounts (their opening is the balance at
t=−∞). It is wrong for a manual account whose opening is "balance now": it would add that
amount retroactively to every past net-worth point. Fix:

- `openings` (flat baseline) = `SUM(opening_balance)` **WHERE NOT is_manual**.
- Each manual account contributes its `opening_balance` as a synthetic net in
  `DATE_TRUNC('month', created_at)`, folded into the same `nets` map as transaction sums,
  so it enters `running` from its creation month forward (and 0 before).
- Transaction net sum is unchanged: `account_id IN (SELECT account_uid FROM accounts)`
  now naturally includes manual accounts' transactions.
- Update the docstring: manual accounts now have account_ids and **do** count; the
  `account_id IS NULL` remark is obsolete.

Reconciliation still holds: the final point (all creation months ≤ current) equals
`Σ non-manual openings + Σ manual openings + Σ all tx` = `accounts.balances` net worth.
A regression test must pin last-point == net worth with a mixed EB+manual set.

## API — `/v1/accounts` CRUD

Currently only `GET /v1/accounts`. Add (all under `router_v1`, JWT-guarded, `{data:...}`
envelope, `float()` at the boundary):

- `POST /v1/accounts` — create manual account `{display_name, type, currency?="EUR",
  opening_balance}`. Server generates `account_uid`, sets `is_manual=TRUE`. Returns the row.
- `PATCH /v1/accounts/{uid}` — **manual**: `display_name`, `type`, `opening_balance`.
  **EB**: `display_name`, `type` only (opening/currency stay calibration-managed; reject
  attempts to change them).
- `DELETE /v1/accounts/{uid}` — **manual only** and **only if no transaction references
  it** → else 409. EB accounts → 403 (system-managed; they reappear on calibration).

Validation: `type ∈ {cash, bank, card, savings}`; `opening_balance` Decimal;
unknown `uid` → 404.

## Manual-entry wiring

- `AddTransactionModal`: add an account `<select>` from `accountQueries.list()` (both
  manual and EB accounts selectable). Include `account_id` in the mutation payload
  (today omitted).
- Server: `ManualTransactionIn.account_id` already exists → add validation that it
  matches a registered account (422 if not). Selection default: preselect when a single
  account exists; otherwise require a choice.

## Frontend — account management

- AccountsPage gains **"+ Add account"** and a per-row edit affordance. Small modal in the
  `AddTransactionModal` visual idiom: create/edit `display_name`, `type`, and
  (manual only) `opening_balance`; EB rows expose rename + type only.
- Row shows a type-based icon + `display_name`; renaming EB accounts removes the raw-UID
  display. Update the "Balances synced from Enable Banking · 4×/day" note to reflect that
  manual accounts are user-maintained.

## Calibration safety (no code change, pin with a test)

`calibrate_balances.py` iterates only `settings.ENABLE_BANKING_ACCOUNT_IDS`, so it never
touches manual rows, and its `INSERT … ON CONFLICT DO UPDATE` sets only
`opening_balance/eb_balance/calibrated_at` — user-set `type`/`display_name`/`is_manual`/
`currency` are preserved. New columns take their defaults on the calibrate INSERT. A
regression test asserts a manual row and a user-typed EB row survive a calibrate run
unchanged (except EB opening/eb/calibrated).

## Testing

- **Unit**: CRUD rules (create sets is_manual + namespaced uid; PATCH EB rejects
  opening/currency; DELETE blocked with transactions and on EB); `balances()` LEFT JOIN
  surfaces a zero-transaction account; `ManualTransactionIn` rejects an unknown
  `account_id`; `balance_history` manual-opening-at-creation-month vs flat EB baseline.
- **Integration (real PG)**: create manual account → post manual tx → `balance =
  opening + tx`; delete blocked when a tx exists; calibrate leaves manual + typed-EB rows
  intact; `balance_history` last point == `accounts.balances` net worth for a mixed set.
- **Frontend**: picker sends `account_id`; account modal create/edit round-trips; row
  renders `display_name` (not the UID) after rename.

## Decisions (locked)

- Type enum `{cash, bank, card, savings}`, app-validated.
- Manual uid `manual:<uuid4>`, namespaced.
- Manual accounts single-currency EUR by default (multi-currency = YAGNI).
- Opening balance = balance as of creation (wallet-style).
- EB accounts editable: `display_name` + `type` only; not deletable.
- Delete manual account blocked if it has transactions (409).
- Manual opening enters balance-history from its `created_at` month, not retroactively.

## Forward note to SP-2 (CSV import)

CSV import will target a registered account (this registry), add `source="csv"` to the
`NormalizedTransaction.source` Literal with its own dedup hash, and must define opening
semantics for imported accounts that carry pre-`created_at` history (the edge case
deferred above).
