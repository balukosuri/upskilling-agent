# Change report template

Keep it under 15 lines. Plain language first; details after.

**<Workflow>: <one-line title>** - <APPLIED automatically | APPLIED with your approval | NOT applied: <why> | PROPOSED>

- **Why:** <concept> (confidence: <level>, sources: <n>, model tag: <model>). <one sentence on the hypothesis>
- **What changed:** <plain description>; <N> lines in <files>.
- **Impact:** overall <before> -> <after> (<delta>); held-out <before> -> <after>; regressions: <none | list>;
  noise sd <x>. <Cases now passing that were failing, in words.>
- **Gate:** <decision>. Cautions: <none | list>.
- **Undo:** `<revert command>` (snapshot <change id>). Reverting lowers this workflow's autonomy one level.
- **Next:** <follow-up backlog items, or "none">
