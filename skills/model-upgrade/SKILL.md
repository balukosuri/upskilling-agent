---
name: model-upgrade
description: >
  This skill should be used when a new model has been released or the user switches models, or they ask "new model
  dropped - what should I re-check", "re-baseline my workflows", "did my skills get worse on the new model",
  "what can I simplify now", "quarterly workflow review", or "are my old tips still valid". Re-runs workflow
  baselines on the current model, compares against the old model's scores, flags regressions, finds scaffolding that
  may no longer be needed, and re-verifies wiki concepts tied to the old model.
metadata:
  version: "0.1.0"
---

# Model upgrade: what does a new model change for my workflows?

Every workflow and every learned tip was tuned under some model. A new model can break a workflow silently, make a
workaround unnecessary, or make an old tip wrong. Scores from different models must never be compared as if they were
one experiment - the gate refuses to (`RERUN`). This skill is the routine that keeps baselines honest.
`$WIKI` and `$UP` come from the `upskilling-agent` skill. Let `NEW` be the model ID powering this session.

## Procedure
1. **Learn what changed.** Use `ingest` on the release notes/announcement and reputable early write-ups (primary
   sources first). Record concepts such as "behaves differently on X" with `model_tags: [NEW]`.
2. **Find affected workflows.** For each registered workflow run
   `python $UP eligibility $WIKI --workflow NAME --model NEW`. If `baseline_model` differs from `NEW`, or no baseline
   exists, the workflow needs a re-baseline. Workflows without a suite: say they cannot be checked and offer
   `eval-bootstrap`.
3. **Estimate cost first.** `python $UP estimate $WIKI --workflow NAME` for each; state the total and confirm before
   running a large batch.
4. **Re-baseline on the new model.** Keep the old scores: copy
   `evals/NAME/results-baseline.json` to `results-baseline-<oldmodel>.json`. Then follow `eval-run` with label
   `baseline` and `--model NEW` against the *unchanged live workflow* (no edits during this step).
5. **Compare.** `python $UP compare $WIKI --workflow NAME --a baseline-<oldmodel> --b baseline`.
   - **Regressions** (cases scoring lower): highest priority. Treat the release notes and any related concepts as the
     starting hypothesis and go through `adapt` to fix them. These are ordinary changes: snapshot, gate, log.
   - **No change / improvements:** the workflow is fine. Note it in the journal.
6. **Look for simplification.** Read each workflow for instructions that compensate for old-model weaknesses
   (heavy step-by-step scaffolding, repeated reminders, rigid formats, workarounds the release notes say are fixed).
   Propose removing them one piece at a time through `adapt`. A simplification usually shows no score gain, so the gate
   returns `ASK` - which is right: a leaner workflow is only worth it if you agree, and cost/latency may improve.
7. **Re-verify the wiki.** Run `wiki-lint` with `--current-model NEW`: concepts tagged only with older models become
   re-verification candidates. Prioritize ones that drove workflow changes.
8. **Report** as a small table: workflow | old score | new score | status (fine / regressed / needs suite) | next step.
   Then the concept re-verification count and the top 1-3 recommendations.

## Notes
- Autonomy is not silently lowered by a model change, but the gate will not auto-apply against a baseline from another
  model, and eligibility caps at Level 1 until re-baselined. That is by design.
- Do not re-baseline in the same run as an edit: you would not know whether a score change came from the model or the
  edit.
