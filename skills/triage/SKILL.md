---
name: triage
description: >
  This skill should be used after new concepts are added to the upskill wiki, or when the user asks "does this
  apply to my workflows", "which of my skills could use this", "what should I update", or "check my workflows
  against what I learned". Scores concepts against the registered workflow map and produces a short list of
  candidate updates, then asks the user which workflows to check.
metadata:
  version: "0.1.0"
---

# Triage: does this concept matter to anything I run?

Most new ideas do not apply to any given workflow. Triage exists so that evals and rewrites are spent only where
there is a plausible payoff. It is cheap by design: reading and reasoning, no edits.

## Procedure
1. **Load the inputs:** concept pages added or changed in this session (or all `active` ones if asked), and
   `workflow-map/*.md` plus `autonomy.json` for the registered workflows. If none are registered, stop and offer
   `wiki-setup` (register existing workflows) or creating a new workflow from the concept.
2. **Read each candidate workflow** (its SKILL.md and key references) enough to judge fit. Do not rely only on
   the map note - it can be stale.
3. **Score each (concept, workflow) pair:**
   - `applies` - the workflow currently does the thing the concept improves, and the concept's "when it applies"
     conditions hold;
   - `maybe` - plausible but depends on something untested;
   - `no` - skip (do not list these).
   For every `applies`/`maybe`, write: the specific change you would try (one sentence), the expected benefit,
   the risk, and whether the workflow has evals (Level from `autonomy.json`).
4. **Weigh confidence.** A `read-only` concept alone is not a reason to change a workflow: label such pairs
   "needs cross-check first" and add a backlog item instead of proposing the edit.
5. **Consider a new workflow.** If a solid concept matches no existing workflow but fits a recurring task the user
   has, suggest creating a new one (handled by `adapt`, new-workflow path). Suggest this sparingly.
6. **Write the map:** add each `applies` or `maybe` pair under "Concepts that may affect it". Do not record a `no`.
7. **Refuse a non-fit.** If every pair is `no`, or the user named a workflow that scores `no`, say it does not fit
   that workflow and stop. Do not shortlist it, do not ask them to pick it, and do not hand it to `adapt`.
   A direct "apply it anyway" does not override a `no`. The concept stays in the wiki for a workflow it actually fits.
8. **Ask the user** (one question, using tappable options if available): which listed workflows to check now.
   Show at most five, ranked by expected benefit. Mention which are at Level 0 (will only produce a proposal).
   Wait for the answer; do not start editing.

## Output shape (keep it short)
For each shortlisted workflow: name, autonomy level, the one-line proposed change, and why. If nothing applies,
say so plainly - that is a good outcome, and the concept stays in the wiki for later. Name the workflow that does
not fit and the one-sentence reason; do not invent a nearby edit to keep the loop moving.
