---
name: adapt
description: >
  This skill should be used to change a workflow (skill, plugin, prompt set) based on something learned: "update
  my skill with this", "apply this concept to my workflow", "rewrite this workflow using what we learned", "try
  this technique on X", "create a new skill from what you learned", or when triage selected a workflow to check.
  Snapshots the workflow, drafts a minimal candidate, measures it against evals, applies the script-enforced gate,
  then applies, asks, or proposes according to the workflow's autonomy level, and logs impact and revert steps.
metadata:
  version: "0.1.0"
---

# Adapt: change a workflow safely and measurably

Principle: a change is a hypothesis ("concept X will improve workflow Y"). The eval gate is the experiment, the
snapshot is the undo button, the changelog is the lab notebook. `$WIKI` and `$UP` come from the `upskilling-agent` skill.
Read `references/report-template.md` for the report format.

## A. Improve an existing workflow

0. **Confirm the fit.** Score the concept against this workflow using the `triage` scale. A `no` means stop
   before any snapshot: tell the user it does not fit and why, in one or two sentences. Do not draft a change
   that forces the idea in. Asking to apply it does not turn a `no` into a `maybe`.
1. **Check level and suite.** `python $UP eligibility $WIKI --workflow NAME` and read `autonomy.json`.
   Below Level 1 there is nothing to measure: you may still draft (steps 2-3) but the outcome is a proposal.
2. **Snapshot.** `python $UP snapshot $WIKI --workflow NAME` -> returns `change_id` and `edit_here`.
   Never edit the live workflow. All edits go in the candidate folder.
3. **Draft the candidate.** Rules that keep changes honest:
   - one concept per change, so impact is attributable;
   - the smallest edit that tests the idea; keep instructions lean and explain the *why* rather than adding rigid
     rules;
   - leave the SKILL.md frontmatter (name, description) alone unless the concept is specifically about
     triggering - changed frontmatter always needs human review;
   - use only `train.json` for examples. **Do not open `heldout.json` or held-out outputs.** They exist to catch
     overfitting; peeking defeats them;
   - link the change to its concept page and sources in your notes.
4. **Measure** (skip if Level 0 / no suite). With `eval-run`: a baseline on the *current model* must exist
   (after an applied change it is promoted automatically from that change's candidate results; re-run `baseline`
   against `before/` only if the suite or the model changed - see `model-upgrade`). Grade with `--model <model ID>`; run the candidate as label
   `candidate`, same runs. Then
   `python $UP gate $WIKI --change-id CHANGE_ID --baseline baseline --candidate candidate`.
   The gate requires the gain to exceed the measured noise, so tiny gains on a noisy suite come back as `ASK`.
   You may revise the candidate up to **two** times based on train-case failures; each revision re-runs the
   candidate and gate. More rounds mean tuning to the test, not improving the workflow. Keep the gate's aggregate
   numbers as your only held-out signal.
5. **Act on the gate's decision** (it is computed by the script, not by you):
   | Decision | Do |
   |---|---|
   | `AUTO_APPLY` (Level 2, clean) | `python $UP apply $WIKI --change-id ID`, then record + report |
   | `ASK` | show the report and the diff; wait for the user; on yes `apply ... --user-approved`; record as `USER_APPLIED`, or `ASK_PENDING` if they defer |
   | `REJECT` | do not apply; record as `REJECTED`; keep the concept as `tested-no-help` with `evidence` |
   | `RERUN` | baseline and candidate were run on different (or unrecorded) models: the comparison is invalid. Re-run whichever is off on the current model with `grade --model`, then gate again. Do not record this as a rejection |
   | `PROPOSE_ONLY` | show the proposed diff and why; the user applies it (or asks you to: then `--user-approved`, and say plainly it is unmeasured) |
6. **Record** (use `PROPOSED` for `PROPOSE_ONLY` outcomes). `python $UP record $WIKI --change-id ID --title "..." --decision <D> --concepts slug1,slug2 --summary "why"`.
   Then update: concept `confidence` (+ `evidence: ID`), `workflow-map/NAME.md` eval status, `journal.md` (record does
   the journal line), and add follow-ups to `backlog.md`.
7. **Report** with the template: what changed, why, before/after, gate decision and cautions, revert command.
   Auto-applied changes must be reported immediately - that is the notification the user asked for.

## B. Create a new workflow from what was learned
Use this when a solid concept fits a recurring task but no workflow exists (triage suggests it sparingly).
1. Confirm the idea with the user in a sentence.
2. Draft the skill folder in the user's chosen location, following the skill-creator guidance if available
   (lean SKILL.md, explain the why, references for detail).
3. Register it at Level 0 (`wiki-setup`), then offer `eval-bootstrap`. There is no baseline to beat for a brand-new
   workflow, so nothing is auto-applied: it earns autonomy through evals like any other.
4. Log it in the changelog via a snapshot-less journal line and link the concept.

## Hard rules
- Never call `apply` without a gate result or an explicit `--user-approved` from the user's actual reply.
- Never auto-apply to anything inside the `upskilling-agent` plugin; the gate refuses, and you should not work around it.
- If `apply` refuses because the candidate changed after gating, re-run evals and the gate; do not bypass.
- If anything looks wrong after an apply, revert first, investigate second (`changelog` skill).
