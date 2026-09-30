---
name: wiki-setup
description: >
  This skill should be used when the user wants to "set up the upskill wiki", "create my learning wiki",
  "register a workflow", "add this skill to the workflow map", "start tracking my skills", or when any other
  upskilling-agent skill finds no wiki. Creates the wiki from the template and registers workflows (skills, plugins)
  at autonomy Level 0.
metadata:
  version: "0.1.0"
---

# Wiki setup and workflow registration

## Create the wiki
0. If the user already has a wiki, `python ${CLAUDE_PLUGIN_ROOT}/scripts/upskilling-agent.py where .` finds it - use it instead of creating another.
1. Choose the location: default `./upskill-wiki` in the user's working folder. Ask only if the user has a
   different preference or the folder is ambiguous.
2. Run: `python ${CLAUDE_PLUGIN_ROOT}/scripts/upskilling-agent.py init <wiki-path> --scope personal`
   (existing files are never overwritten, so re-running is safe). v1 supports `personal` scope; `org` scope
   is accepted by the script but promotion between wikis is not built yet - say so if the user asks.
3. Suggest putting the wiki under git (`git init`) so wiki edits are versioned too. Do not run git unasked.
4. Read the created `schema.md` and tell the user in two sentences how the wiki works.

## Register workflows
A "workflow" is anything the user wants kept current and measurable: a skill folder, a plugin, or a single
SKILL.md. Registering is what lets triage know what exists.

For each workflow:
1. Get a short kebab-case name and the path (skill folder preferred over a single file, because the snapshot
   then covers references and scripts too).
2. Run: `python ${CLAUDE_PLUGIN_ROOT}/scripts/upskilling-agent.py register-workflow <wiki> --name <name> --path <path> --purpose "<one sentence>"`
3. Open the generated `workflow-map/<name>.md` and fill in inputs/outputs by reading the workflow. Good notes
   here make triage accurate.
4. State the outcome plainly: "`<name>` is at Level 0 (propose only). It moves up once it has test cases -
   want to build them now?" and hand off to `eval-bootstrap` if yes.

If the workflow path lives inside the `upskilling-agent` plugin, register it but warn that it will never be
auto-applied.

## Discover candidates (optional)
If asked "which of my skills should I track?", run `python ${CLAUDE_PLUGIN_ROOT}/scripts/upskilling-agent.py discover --wiki <wiki>`
(add `--root <folder>` for other locations) and suggest the ones used most often or that matter most. Skills marked
`writable: false` cannot be edited here. Do not register anything without confirmation.
