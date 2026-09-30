---
name: changelog
description: >
  This skill should be used to review, explain, or undo workflow changes made by the Upskilling Agent: "what changed
  in my skills", "show the changelog", "what was the impact of that update", "undo the last change", "revert
  that", "why did you change X", "roll back my skill". Reads the changelog, shows impact, and reverts from
  snapshots with the revert script.
metadata:
  version: "0.1.0"
---

# Changelog: review impact and reverse changes

`$WIKI` and `$UP` come from the `upskilling-agent` skill. Entries live in `$WIKI/changelog/<change_id>.md`, with an index in
`index.jsonl`, and full before/candidate/after copies in `changelog/snapshots/<change_id>/`.

## Review
1. List: `python $UP history $WIKI [--workflow NAME] [--limit N]`.
2. For a specific change, read its entry and summarize in plain language: what changed, the concept and sources
   behind it, eval before/after, gate decision, and current status (applied, reverted, proposed).
3. For "what has helped so far", aggregate: count changes by decision, list the largest positive deltas, and list
   reverted or rejected experiments (these are as valuable as the successes; they prevent repeated dead ends).

## Revert
1. Identify the change id (default: the most recent applied change for the workflow the user means). If several
   are plausible, show them and ask.
2. Confirm once, briefly, unless the user has already clearly asked to undo it. Note what will be restored.
3. Run `python $UP revert $WIKI --change-id ID`. The script restores the pre-change snapshot, marks the entry as
   reverted, appends to the changelog and journal, and **demotes the workflow one autonomy level**.
4. Explain the demotion: a change that needed reverting means the evals missed something. Ask what went wrong and
   offer to add a case that would have caught it (`eval-bootstrap`), then re-baseline.
5. Update the linked concept's confidence if the revert shows it does not hold (`tested-no-help`), and note why in
   the journal.

## Notes
- Reverting restores the workflow to its state *at snapshot time*. If the user made manual edits after the change,
  warn them those will be overwritten; the `after/` snapshot preserves the changed version if they want to compare.
- A revert of a revert is not supported; to reapply, copy from `snapshots/<id>/after/` by hand or re-run adapt.
