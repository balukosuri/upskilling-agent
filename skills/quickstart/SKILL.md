---
name: quickstart
description: >
  This skill should be used the first time someone uses the Upskilling Agent, or when they say "get me started", "set
  me up", "how do I start", "find my skills and track them", "set everything up", "I'm new to this", or ask to learn
  something and apply it when no upskill wiki exists yet. Guides a newcomer from zero to a working loop in a few
  minutes: creates the wiki, finds their existing skills, registers the ones they pick, drafts starter test cases
  for them to approve, and then asks what they want to learn.
metadata:
  version: "0.1.0"
---

# Quickstart: from zero to a working loop

Audience: someone who has never used this plugin and may not know what a "wiki", "eval", or "autonomy level" is. Talk
plainly, keep each step short, and do the boring parts yourself. Never narrate file paths or script names. The aim is a
first real learn-and-apply cycle within one sitting, not a full setup ceremony. `$UP` is
`${CLAUDE_PLUGIN_ROOT}/scripts/upskilling-agent.py`.

## If they already gave you something to learn
Do step 1 silently, run the normal `upskilling-agent` flow on their material right away (learning is safe and needs no setup), and
do steps 2-4 at the moment triage asks "which workflows should I check?". Never make someone wait through setup before
the thing they asked for.

## Steps

**1. Notebook.** Run `python $UP where .`. If it finds a wiki, use it and skip creation. Otherwise create one with
`python $UP init ./upskill-wiki` (ask about location only if the folder is unclear). Say: "I've set up a notebook where
I'll keep what I learn and a log of every change I make."

**2. Find their skills.** Run `python $UP discover --wiki $WIKI`. Then:
- *Found some:* show at most 8 in plain words (name + what it does, from the description). List ones marked
  `writable: false` separately as "can't be edited here". Recommend starting with **one** skill they use often - a
  single tested skill teaches more than five half-set-up ones. Ask them to pick 1-3 (tappable options if available).
- *Found none:* ask where their skills live, or offer two alternatives: create a first skill from what they want to learn
  (`adapt`, new-workflow path), or learn-only mode for now.

**3. Register.** For each pick, run `register-workflow` using the skill's own description as the purpose. No questions.
Say: "I'll suggest changes to these but won't touch them until they have tests."

**4. Starter tests.** For each registered skill, run `eval-bootstrap` in **quick mode**. Set expectations first: "I'll
write 4 sample tests; you tell me which look right. About 5 minutes." If the user declines, leave that skill at propose-only
and move on; do not push.

**5. What to learn.** Ask: "What would you like me to learn? Send a link, video, document, or just a topic." Hand over to
`upskilling-agent` (Step 2 onward).

**6. Plain-language status.** When the first cycle finishes (or if they stop early), say where each skill stands:
- *Level 0 (no tests):* "I can suggest changes; you apply them."
- *Level 1 (starter tests):* "I'll draft and test changes, then ask you before applying anything."
- *Level 2 (full tests):* "I apply clear improvements myself and tell you after."
And how to move up: "Say 'expand my tests' whenever you want me to unlock more automation."

## Rules of thumb
- One question at a time; offer choices instead of open questions.
- Never register or edit a skill without the user's pick. Never edit skills marked not writable.
- If something fails (no web access, no Python, read-only folder), say what is missing and what still works: learning and
  proposals work without most of it.
- Do not explain the whole system up front. Introduce each concept only when it first matters.
