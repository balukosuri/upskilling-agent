# Eval case format

Files: `$WIKI/evals/<workflow>/train.json` and `heldout.json`. Same schema.

```json
{
  "workflow": "meeting-notes",
  "cases": [
    {
      "id": "train-01",
      "prompt": "The exact user message to run the workflow with.",
      "files": [],
      "negative": false,
      "approved": true,
      "checks": [
        {"name": "has action items section", "type": "deterministic", "kind": "has_sections", "value": ["Action items"]},
        {"name": "under 300 words", "type": "deterministic", "kind": "max_words", "value": 300},
        {"name": "owners named", "type": "rubric", "criterion": "Every action item names a person responsible."}
      ]
    }
  ]
}
```
- `id`: unique across train + heldout (use `train-NN` / `heldout-NN`).
- `files`: paths to input files the case needs (copy them next to the suite, e.g. `evals/<wf>/fixtures/`).
- `negative: true`: the case tests restraint (should not trigger, should decline, should not fabricate).

## Deterministic check kinds
| kind | value | passes when |
|---|---|---|
| contains | string | text contains it (case-insensitive unless `"ci": false`) |
| not_contains | string | text does not contain it |
| regex | pattern | pattern found (case-insensitive, multiline) |
| not_regex | pattern | pattern not found |
| max_words / min_words | number | word count within limit |
| has_sections | list of strings | every heading/label appears |
| json_valid | - | whole output parses as JSON |

## Rubric checks
`{"name": "...", "type": "rubric", "criterion": "one yes/no question"}`. Judged by a separate context (see
`eval-run`), never by the agent that drafted the change.

Good criteria: "Does the summary mention the deadline given in the input?" / "Does the reply avoid promising a
refund?" Bad criteria: "Is the writing good?" / "Is it helpful?"

## Numbers to aim for
- Level 1: >= 3 approved cases and one baseline run.
- Level 2: >= 8 approved cases, >= 2 held-out, >= 1 negative, >= 3 baseline runs per case, mean run-to-run sd <= 0.15.
