---
name: eval-bootstrap
description: >
  This skill should be used when a workflow has no test cases yet or too few, and the user wants to "build
  evals for my skill", "create test cases", "measure this workflow", "make this workflow safe to auto-update",
  "expand my tests", "raise its autonomy level", or when quickstart/adapt finds a workflow at Level 0. Drafts test
  cases for the user to approve (quick mode: 4 starter cases; expand mode: grow to a full suite with held-out and
  negative cases), records a noise-checked baseline, and reports which autonomy level the suite supports.
metadata:
  version: "0.1.0"
---

# Eval bootstrap: from zero test cases to a trustworthy baseline

Why this matters: the whole loop is only as safe as its evals. A weak suite lets bad changes through and rejects good
ones. Deciding what "good" means is the one step that cannot be delegated to the model - a model grading its own taste
is circular - so this skill minimizes the user's effort rather than skipping it: the agent drafts, the user approves.

`$WIKI` and `$UP` come from the `upskilling-agent` skill. File formats and check types: `references/case-format.md`. Running and
grading: `eval-run`. Pick the mode:

| Mode | When | Result |
|---|---|---|
| **Quick** | first time, or the user wants speed | 4 approved cases, baseline -> **Level 1** (drafts + asks you) |
| **Expand** | user says "expand my tests", or wants auto-apply | 8+ cases incl. held-out + negative -> **Level 2** possible |

## Quick mode (about 5 minutes of the user's time)
1. **Understand the skill.** Read its SKILL.md and references: purpose, typical inputs, what a good output looks like,
   likely failure modes.
2. **Draft exactly 4 cases:** three typical inputs (prefer real examples found in the skill, the conversation, or ones
   the user pastes; otherwise realistic invented ones) and **one negative case** (an input where the skill should
   decline, stay in scope, or not invent facts).
3. **Write 2-3 checks per case, mostly deterministic** (contains, has_sections, max_words, regex, json_valid): they are
   cheap and repeatable. At most one rubric check per case, phrased as a single yes/no question a stranger could answer.
4. **Validate and store.** Write the drafts to a temp JSON file and run
   `python $UP add-cases $WIKI --workflow NAME --file drafts.json`. The script rejects malformed drafts whole (fix and
   retry) and always stores cases as **unapproved**.
5. **Show the cases compactly** - each as "input -> what I'll check for" in plain words - and ask once: approve all,
   edit some, or drop some. Apply edits, re-run `add-cases` for changed/new ones if needed.
6. **Approve only what they accept:** `python $UP approve-cases $WIKI --workflow NAME --ids a,b,c` (or `--all` only if
   they said "all"). Never approve on your own.
7. **Baseline:** state the cost (`python $UP estimate ...`), run 3 runs of each approved case on the *current* workflow
   with label `baseline` (see `eval-run`; grade with `--model <current model ID>`), then
   `python $UP eligibility $WIKI --workflow NAME --model <current model ID>`.
8. **Set the level** with the user's OK: `python $UP autonomy $WIKI --workflow NAME --set 1 --reason "quick suite"`.
   Tell them plainly what Level 1 means and that "expand my tests" unlocks more.

Quick mode has no held-out cases, so it cannot reach Level 2 - say so; do not pretend otherwise.

## Expand mode
1. Read the current suite and the workflow's change history (`python $UP history $WIKI --workflow NAME`). Look for
   gaps: input types not covered, failures the user mentioned, reverted changes (each revert should become a case).
2. Draft cases until there are **at least 8 approved**, including **at least 1 negative**; ask the user for any real
   inputs that ever went wrong. Same flow as quick mode steps 3-6.
3. **Hold some out:** once 8+ are approved, `python $UP split-heldout $WIKI --workflow NAME --count 2` (about a quarter
   of the suite; the adapt step never reads these). Tell the user why: they catch changes that only "learn the test".
4. **Re-baseline** the whole suite (3 runs, current model) so every case has baseline results, then run eligibility.
5. **Noise check.** If `mean_run_to_run_sd` is above 0.15, find the vague checks (the flaky cases) and tighten them;
   do not relax the threshold. A perfect baseline means the suite is too easy: add harder cases.
6. Offer Level 2 if eligible, with the user's OK: `python $UP autonomy ... --set 2 --reason "full suite"`.

## Guardrails
- Approval is explicit. `add-cases` forces `approved: false`; only `approve-cases` after the user's actual reply flips it.
- Do not write checks that merely repeat the skill's own wording - they test that it follows itself, not that it works.
- Record the suite's intent in `workflow-map/<name>.md` under "Eval status".
