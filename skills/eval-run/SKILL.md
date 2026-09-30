---
name: eval-run
description: >
  This skill should be used to execute and score a workflow's eval cases: "run the evals", "score this
  candidate", "compare before and after", "run the baseline", or as a stage inside eval-bootstrap and adapt.
  Runs each case several times in fresh contexts, saves outputs, grades deterministic checks with the script,
  judges rubric checks blind in a separate context, and produces results files the gate consumes.
metadata:
  version: "0.1.0"
---

# Eval run: execute, grade, and compare

`$WIKI` and `$UP` come from the `upskilling-agent` skill. Suite location: `$WIKI/evals/<workflow>/`.

## Labels
- `baseline` - the workflow as it is now (or the snapshot's `before/` when a change is in flight).
- `candidate` - the drafted version under test (the snapshot's `candidate/` folder).
Both must be run on the same model and with the same number of runs. `--model` is required when grading and is stored
in the results; the gate refuses (`RERUN`) if baseline and candidate models differ or are unrecorded.

## 0. Estimate and confirm
`python $UP estimate $WIKI --workflow NAME` shows how many executions and rubric judgements a round costs. State it
(especially for baselines or many workflows) and confirm before large batches. A change costs one baseline (skipped if
a current-model baseline exists) plus 1-3 candidate rounds.

## 1. Execute
For each approved case (train and held-out) and each run k in 1..3:
1. Start from a **fresh context** - a subagent if available, otherwise a clean, separate pass. Reusing context
   leaks earlier outputs and hides run-to-run variance, which is exactly what the noise check needs.
2. Give it the workflow under test (baseline: `before/` or live; candidate: the candidate path) and the case
   `prompt` (plus any `files`). It behaves as if a user had typed that prompt.
3. Save only the final user-facing output as text to
   `$WIKI/evals/<workflow>/outputs/<label>/<case_id>/run<k>.txt`.
   If the workflow produces a file, save a text rendering of it (or extracted text) so checks can read it, and
   note the limitation.
Use the same case order for both labels. Run baseline and candidate close in time to avoid drift.

## 2. Grade deterministic checks (script)
`python $UP grade $WIKI --workflow NAME --label LABEL --runs 3 --model <model ID powering the runs>`
- Exit 0: no rubric checks pending; `results-LABEL.json` written.
- Exit 2 and `pending-LABEL.json`: rubric checks need judging; go to step 3.

## 3. Judge rubric checks (blind, separate context)
For each item in `pending-LABEL.json`, spawn a **separate judge context** that sees only the case prompt, the
output text, and the single criterion - not the workflow, the diff, or which label it is. If judging baseline
and candidate outputs together, shuffle them and hide labels. Ask for `true`/`false` and a one-line reason.
Why blind and separate: the model that wrote the change is biased toward believing it worked.
Write `$WIKI/evals/<workflow>/rubric-LABEL.json`:
`{"case_id": {"1": {"check name": true, "...": false}, "2": {...}}}`
then re-run `grade` (now exit 0).

## 4. Compare
- For a baseline suite: report overall score and run-to-run noise; noise above 0.15 means fix the vague checks
  (see `eval-bootstrap`).
- For a candidate: run `python $UP gate ...` (done by `adapt`) - do not judge pass/fail by eye. The gate applies
  the rules for regressions, held-out, noise, and change size.

## Practical notes
- Cost: cases x runs x 2 labels. If the suite is large, keep 3 runs but say the cost up front and confirm.
- A flaky case (passes 1 of 3) is a bad case or bad check, not evidence about the workflow. Fix the check.
- Never edit an outputs file after it is saved. Never grade from memory: always from the saved file.
