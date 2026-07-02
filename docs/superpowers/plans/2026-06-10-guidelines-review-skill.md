# Guidelines Review Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `/guidelines-review` skill that reviews code against the project's two coding guideline docs with contextual judgment — not mechanical rule-checking.

**Architecture:** Single SKILL.md file with two modes: quick (inline diff review) and deep (path review via pr-review-toolkit:code-reviewer subagent). A reasoning gate ensures every finding is justified with concrete impact before being surfaced.

**Tech Stack:** Claude Code skill system (markdown), git diff, pr-review-toolkit:code-reviewer subagent

---

### Task 1: Write the skill file

**Files:**
- Create: `.claude/skills/guidelines-review/SKILL.md`

- [ ] **Step 1: Create the skill file**

Create `.claude/skills/guidelines-review/SKILL.md` with this exact content:

```markdown
---
name: guidelines-review
description: Reviews code against the project coding guidelines (DataCamp + Full-Stack Best Practices) with contextual judgment. Invoke when asked to review code, check before committing, or audit a file/folder/project for guideline compliance.
---

# Guidelines Review

Reviews code against the project's coding guidelines with contextual judgment — not mechanical rule-checking. Every finding must be justified with concrete impact.

## When to Use

Invoke this skill when:
- The user says "controlla il codice", "review", "check the code", "review before commit", "hai finito?"
- The user invokes `/guidelines-review` explicitly
- You are about to declare a task complete and want to do a final check

## Modes

Determine the mode from how the skill was invoked:

- **Quick mode** (no argument, or `--diff`): review the current git diff
- **Deep mode** (a path is provided): review a specific file, folder, or `.` for the whole project

---

## Quick Mode

Target: current git diff (`git diff HEAD` plus staged changes).

### Process

1. Run `git diff HEAD` to get the current changes. If the diff is empty, also check `git diff --cached`.
2. Read `.claude/rules/coding-guidelines.md` (distilled principles).
3. For each changed file and hunk, apply the **Reasoning Gate** to each potential violation.
4. Collect findings and output them ordered by severity (critical first).

### Reasoning Gate

Before surfacing any finding, answer these three questions:

1. **Which principle?** Name the specific guideline (e.g. "YAGNI", "Input Validation", "DRY").
2. **Real impact?** Does this concretely cause fragility, security risk, overengineering, or future breakage in THIS codebase — not in the abstract?
3. **Context?** Three similar lines in a test file ≠ three similar lines in core business logic. A long sequential pipeline function ≠ a god function.

**Rule:** If you cannot explain in one sentence why this finding causes a real problem in this specific codebase, do not report it. Doubt goes to the code.

### Output Format — Quick Mode

```
Guidelines review — N findings

🔴 path/file.py:LINE — short description
   Principio: <guideline name>
   Perché conta: <one sentence — concrete impact in this codebase>

🟡 path/file.py:LINE — short description
   Principio: <guideline name>
   Perché conta: <one sentence>

💡 path/file.py:LINE — short description
   Principio: <guideline name>
   Perché conta: <one sentence>
```

If no meaningful violations found:
```
✓ Nessuna violazione significativa nel diff corrente
```

### Severity Scale

| Symbol | Level    | Criteria |
|--------|----------|----------|
| 🔴 | Critical   | Security issue, data corruption, guaranteed crash, violation of CLAUDE.md invariants |
| 🟡 | Warning    | Measurable fragility, overengineering that will break on next change |
| 💡 | Suggestion | Clear improvement with concrete benefit, not urgent |

---

## Deep Mode

Target: a specific file, directory, or `.` for the whole project.

### Process

1. Read both full guideline files:
   - `.claude/rules/coding-guidelines-datacamp.md`
   - `.claude/rules/coding-guidelines-fullstack.md`
2. Summarize the key principles as review criteria (internal step, not shown to user).
3. Invoke the `pr-review-toolkit:code-reviewer` subagent with:
   - The target path to review
   - The guideline principles as additional review context
   - Explicit instruction to apply the Reasoning Gate (above) — only surface high-confidence findings with concrete impact
4. Post-process the subagent output into three blocks (see below).

### Output Format — Deep Mode

**Block 1 — Summary** (one line per file reviewed):
```
src/server/app.py              ⚠ 2 issues
src/normalizer/normalize.py    ✓ clean
src/storage/db_insert.py       🔴 1 critical
```

**Block 2 — Findings** (same format as quick mode, ordered by severity):
```
🔴 src/storage/db_insert.py:34 — ...
   Principio: ...
   Perché conta: ...

🟡 src/server/app.py:47 — ...
   ...
```

**Block 3 — Recurring Patterns** (only if the same principle is violated in 3+ separate places):
```
Pattern: DRY — logica di normalizzazione duplicata in 4 file
  src/normalizer/normalize.py:45, src/ingestion/tasker_parser.py:78,
  src/storage/reconcile.py:23, src/storage/db_insert.py:12
  Perché conta: ogni modifica al formato richiede 4 aggiornamenti sincronizzati
```

If no meaningful violations:
```
✓ Nessuna violazione significativa in <path>
```

---

## What This Skill Does NOT Do

- Does not fix code (use `/code-review --fix` for that)
- Does not replace ruff/ESLint (formatters/linters already run via hooks)
- Does not flag issues already caught by `verify.py` Stop hook
- Does not produce findings without reasoning — mechanical output is forbidden
```

- [ ] **Step 2: Verify the file was created correctly**

Check that the file exists and has valid frontmatter:
```
Get-Content .claude\skills\guidelines-review\SKILL.md | Select-Object -First 10
```

Expected: first line is `---`, second line starts with `name: guidelines-review`.

---

### Task 2: Test quick mode

- [ ] **Step 1: Ensure there is a diff to review**

If the working tree is clean, make a trivial edit to any `src/` file (e.g. add a blank line) or use the last real uncommitted change.

Run:
```
git diff HEAD --stat
```

Expected: at least one file listed.

- [ ] **Step 2: Invoke the skill in quick mode**

Run `/guidelines-review` (no argument).

Expected behavior:
- Claude runs `git diff HEAD`
- Reads `.claude/rules/coding-guidelines.md`
- Applies the reasoning gate
- Outputs either findings with 🔴/🟡/💡 + "Perché conta" lines, OR the `✓ Nessuna violazione` line
- Does NOT list findings without a "Perché conta" justification

- [ ] **Step 3: Verify reasoning gate is enforced**

Check that every finding in the output has:
1. A `Principio:` line naming a specific guideline
2. A `Perché conta:` line with a concrete, codebase-specific sentence (not generic)

If any finding is missing either line, the reasoning gate is not being applied — revise the skill's Gate instructions to be more explicit.

---

### Task 3: Test deep mode

- [ ] **Step 1: Invoke deep mode on a small path**

Run `/guidelines-review src/normalizer/`

Expected behavior:
- Claude reads both full guideline files
- Invokes `pr-review-toolkit:code-reviewer` subagent with guidelines as context
- Output contains Block 1 (summary per file), Block 2 (findings), and optionally Block 3 (patterns)
- All findings have Principio + Perché conta

- [ ] **Step 2: Verify subagent delegation**

Confirm that for deep mode Claude actually dispatches the `pr-review-toolkit:code-reviewer` subagent (you will see the agent spawn in the UI) rather than doing the review inline.

If Claude does it inline instead, strengthen the deep mode instruction: replace "Invoke the pr-review-toolkit:code-reviewer subagent" with "You MUST dispatch this as an Agent call to pr-review-toolkit:code-reviewer — do not perform the deep review inline."

---

### Task 4: Commit

- [ ] **Step 1: Stage and commit the skill**

```
git add .claude/skills/guidelines-review/SKILL.md
git commit -m "feat: add guidelines-review skill

Two-mode skill: quick diff review (inline) and deep path review
(via pr-review-toolkit:code-reviewer subagent). Reasoning gate
ensures every finding is justified with concrete codebase impact."
```

Expected: commit succeeds, ruff hook does not trigger (no .py file changed).
