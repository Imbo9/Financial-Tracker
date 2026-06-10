# Design Spec: `guidelines-review` Skill

**Date:** 2026-06-10  
**Status:** Approved

---

## Overview

A skill that reviews code against the project's coding guidelines (DataCamp + Full-Stack Best Practices) with contextual judgment — not mechanical rule-checking. Two modes: quick review of the current diff, deep review of a specific path.

---

## Architecture

**Approach:** Hybrid standalone + subagent delegation (Approach C)

- **Quick mode**: runs inline within the skill, no subagent
- **Deep mode**: delegates to `pr-review-toolkit:code-reviewer` subagent with guidelines injected as context

**Why this split:** Quick mode needs to be lightweight and fast (end-of-task check). Deep mode benefits from the subagent's existing confidence-based filtering infrastructure.

---

## Trigger

**Explicit invocation:**
- `/guidelines-review` — quick mode, reviews current git diff
- `/guidelines-review <path>` — deep mode, reviews file / folder / `.` for whole project

**Implicit trigger (skill trigger text):** activates when the user says things like "controlla il codice", "review prima del commit", "hai finito?", "check the code", "review this".

---

## Quick Mode

**Target:** `git diff HEAD` + staged changes  
**Runs:** inline, no subagent  
**When to use:** at the end of a task, before declaring work done

**Process:**
1. Run `git diff HEAD` to get current changes
2. Read `.claude/rules/coding-guidelines.md` (distilled principles)
3. For each potential violation, apply the reasoning gate (see below)
4. Output findings ordered by severity

**Output format:**
```
Guidelines review — N findings

🔴 path/file.py:LINE — short description
   Principio: <guideline name>
   Perché conta: <one sentence explaining concrete impact in this codebase>

🟡 ...

💡 ...
```

If no meaningful violations: `✓ Nessuna violazione significativa nel diff corrente`

---

## Deep Mode

**Target:** file, directory, or entire project (`.`)  
**Runs:** delegates to `pr-review-toolkit:code-reviewer` subagent  
**Context passed to subagent:** contents of both guideline files + reasoning gate instructions

**Process:**
1. Read `.claude/rules/coding-guidelines-datacamp.md` and `.claude/rules/coding-guidelines-fullstack.md`
2. Summarize key principles as review criteria
3. Invoke `pr-review-toolkit:code-reviewer` with:
   - Target path
   - Guidelines as additional review context
   - Instruction to apply the reasoning gate
4. Post-process output into three blocks

**Output format:**

**Block 1 — Summary** (one line per file/module):
```
src/server/app.py          ⚠ 2 issues
src/normalizer/normalize.py  ✓ clean
src/storage/db_insert.py   🔴 1 critical
```

**Block 2 — Findings** (same format as quick mode, ordered by severity)

**Block 3 — Recurring patterns** (if same principle violated in 3+ places, reported once as a pattern instead of N separate findings)

---

## The Reasoning Gate

Core differentiator. Applied to every potential finding before surfacing it.

For each candidate violation:
1. **Which principle?** Name the specific guideline
2. **Real impact?** Does this cause fragility, security risk, overengineering, or a future breakage — concretely, in this codebase?
3. **Context matters?** 3 similar lines in tests ≠ 3 similar lines in critical business logic. A long sequential function ≠ a god function.
4. **Decision:** only surface if impact is real and articulable in one sentence. Doubt goes to the code.

**Explicit rule in skill:** if you cannot explain in one sentence why this finding causes a real problem in this specific codebase, do not report it.

---

## Severity Scale

| Symbol | Level | Criteria |
|---|---|---|
| 🔴 | Critical | Security issue, data corruption, guaranteed crash, violation of project invariants (CLAUDE.md) |
| 🟡 | Warning | Measurable fragility, overengineering that will break on next change, pattern known to cause bugs |
| 💡 | Suggestion | Clear improvement with concrete benefit, not urgent |

---

## Guideline Sources

Located at (path-scoped rules, auto-injected for `src/**` and `frontend/src/**`):
- `.claude/rules/coding-guidelines.md` — distilled principles (always-on)
- `.claude/rules/coding-guidelines-datacamp.md` — full DataCamp guide
- `.claude/rules/coding-guidelines-fullstack.md` — full Full-Stack guide

---

## What This Skill Does NOT Do

- Does not fix code automatically (use `/code-review --fix` for that)
- Does not replace linters (ruff, ESLint already run via hooks)
- Does not flag style issues already caught by formatters
- Does not produce findings without reasoning — mechanical output is explicitly forbidden

---

## Relationship to Existing Infrastructure

| Tool | Role |
|---|---|
| Path-scoped rules | Inject guidelines passively while Claude writes code |
| `ruff_format.py` hook | Handles Python formatting automatically |
| `verify.py` hook | Lint gate on Stop |
| `pr-review-toolkit:code-reviewer` | Subagent used for deep mode |
| `guidelines-review` skill | Explicit, reasoned review with guidelines as primary lens |
