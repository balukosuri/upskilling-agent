#!/usr/bin/env python3
"""upskilling-agent.py - deterministic helpers for the Upskilling Agent (stdlib only).

Why this exists: the parts of the loop that protect the user (autonomy levels,
the eval gate, snapshots, revert, lint) must not depend on an LLM's judgment.
Skills call this script for those steps and use LLM judgment only for reading,
synthesizing, drafting, and rubric grading.

Commands
  init                create a wiki from the template
  register-workflow   add a workflow (skill/plugin path) to the workflow map at Level 0
  eligibility         which autonomy level does this workflow's eval suite support?
  autonomy            show or change a workflow's autonomy level
  grade               score saved outputs against eval cases -> results-<label>.json
  snapshot            copy a workflow to before/ and candidate/ and open a change id
  gate                compare baseline vs candidate results -> decision
  apply               copy candidate over the live workflow (gate-checked)
  record              write the changelog entry (+ journal line)
  revert              restore the pre-change snapshot and demote autonomy one level
  history             list changelog entries
  compare             per-case diff between two result sets (e.g. old-model vs new-model baseline)
  estimate            how many model calls an eval round will cost
  where               find the wiki from the current folder
  discover            find skills on disk that could be registered
  add-cases           validate drafted eval cases and add them (always unapproved)
  approve-cases       mark cases approved (only after the user says so)
  split-heldout       move some approved train cases into the held-out set
  rebuild-index       regenerate index.md from concept pages
  lint                health-check the wiki (stale, unverified, orphaned, inconsistent)
"""
import argparse
import difflib
import hashlib
import json
import os
import random
import re
import shutil
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = PLUGIN_ROOT / "wiki-template"
CONFIDENCE = ["read-only", "cross-checked", "tested-helped", "tested-no-help"]
STATUSES = ["draft", "active", "superseded", "retired"]
REQUIRED_CONCEPT = ["title", "slug", "scope", "status", "confidence",
                    "learned_on", "last_verified", "model_tags", "sources"]
DECISIONS = ["AUTO_APPLIED", "USER_APPLIED", "PROPOSED", "ASK_PENDING", "REJECTED"]


# ----------------------------------------------------------------- helpers
def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today():
    return date.today().isoformat()


def jload(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        die(f"invalid JSON in {p}: {e}")


def jsave(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def need_wiki(path):
    w = Path(path).expanduser().resolve()
    if not (w / "autonomy.json").exists():
        die(f"{w} is not an upskill wiki (run `init` first)")
    return w


def parse_frontmatter(text):
    """Tiny YAML-subset parser: `key: value` and inline lists `[a, b]`."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v[:1] not in ("'", '"'):
            v = re.sub(r"\s+#.*$", "", v).strip()   # drop trailing inline comment
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            fm[k] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
        else:
            fm[k] = v.strip("'\"")
    return fm, text[m.end():]


def as_list(v):
    if v in (None, ""):
        return []
    return v if isinstance(v, list) else [v]


def raw_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def sd(xs):
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def copy_tree(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git"), dirs_exist_ok=True)


def sync_dir(src, dst):
    """Make dst match src without deleting dst/.git."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    keep = {p.relative_to(src) for p in src.rglob("*") if p.is_file()}
    for p in list(dst.rglob("*")):
        if p.is_file() and ".git" not in p.parts and p.relative_to(dst) not in keep:
            p.unlink()
    for rel in keep:
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, t)


def restore(src_dir, live, kind):
    live = Path(live)
    if kind == "file":
        shutil.copy2(Path(src_dir) / live.name, live)
    else:
        sync_dir(src_dir, live)


def snap_dir(wiki, cid):
    d = wiki / "changelog" / "snapshots" / cid
    if not d.exists():
        die(f"unknown change id {cid}")
    return d


DET_KINDS = {"contains", "not_contains", "regex", "not_regex", "max_words", "min_words",
             "has_sections", "json_valid"}


def validate_cases(cases, existing_ids=()):
    """Return a list of human-readable problems with drafted/approved eval cases."""
    problems, seen = [], set(existing_ids)
    for i, c in enumerate(cases):
        cid = c.get("id")
        tag = f"case {cid or '#' + str(i)}"
        if not cid or not isinstance(cid, str):
            problems.append(f"{tag}: missing id")
        elif cid in seen:
            problems.append(f"{tag}: duplicate id")
        else:
            seen.add(cid)
        if not str(c.get("prompt", "")).strip():
            problems.append(f"{tag}: empty prompt")
        checks = c.get("checks") or []
        if not checks:
            problems.append(f"{tag}: needs at least one check")
        names = set()
        for ch in checks:
            n = ch.get("name")
            if not n:
                problems.append(f"{tag}: a check has no name")
                continue
            if n in names:
                problems.append(f"{tag}: duplicate check name '{n}'")
            names.add(n)
            typ = ch.get("type")
            if typ == "deterministic":
                k, v = ch.get("kind"), ch.get("value")
                if k not in DET_KINDS:
                    problems.append(f"{tag}/{n}: unknown kind '{k}' (allowed: {sorted(DET_KINDS)})")
                elif k != "json_valid" and v in (None, "", []):
                    problems.append(f"{tag}/{n}: '{k}' needs a value")
                elif k in ("regex", "not_regex"):
                    try:
                        re.compile(v)
                    except re.error as e:
                        problems.append(f"{tag}/{n}: invalid regex ({e})")
                elif k in ("max_words", "min_words"):
                    try:
                        int(v)
                    except (TypeError, ValueError):
                        problems.append(f"{tag}/{n}: value must be a number")
                elif k == "has_sections" and not isinstance(v, list):
                    problems.append(f"{tag}/{n}: has_sections value must be a list")
            elif typ == "rubric":
                if not str(ch.get("criterion", "")).strip():
                    problems.append(f"{tag}/{n}: rubric check needs a criterion (one yes/no question)")
            else:
                problems.append(f"{tag}/{n}: type must be 'deterministic' or 'rubric'")
    return problems


def load_cases(wiki, wf):
    d = wiki / "evals" / wf
    out = []
    for split in ("train", "heldout"):
        for c in jload(d / f"{split}.json", {"cases": []}).get("cases", []):
            c["_split"] = split
            out.append(c)
    return out


def run_scores(results):
    """{case_id: [score per run]} where score = fraction of checks passed."""
    by = {}
    for r in results.get("runs", []):
        chk = r["checks"]
        s = sum(1 for c in chk if c["passed"]) / len(chk) if chk else 0.0
        by.setdefault(r["case_id"], []).append(s)
    return by


def append_journal(wiki, line):
    with open(wiki / "journal.md", "a") as f:
        f.write(f"- {now()} - {line}\n")


# -------------------------------------------------------------------- init
def cmd_init(a):
    wiki = Path(a.wiki).expanduser().resolve()
    for d in ["sources", "concepts", "workflow-map", "evals", "changelog/snapshots"]:
        (wiki / d).mkdir(parents=True, exist_ok=True)
    created = []
    for f in sorted(TEMPLATE.rglob("*")):
        if f.is_file():
            rel = f.relative_to(TEMPLATE)
            dest = wiki / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            created.append(str(rel))
    cfg = jload(wiki / "config.json", {})
    cfg["scope"] = a.scope
    cfg.setdefault("created", today())
    jsave(wiki / "config.json", cfg)
    print(json.dumps({"wiki": str(wiki), "scope": a.scope, "created": created}, indent=2))


# ------------------------------------------------------- register / autonomy
def cmd_register(a):
    wiki = need_wiki(a.wiki)
    path = Path(a.path).expanduser().resolve()
    if not path.exists():
        die(f"workflow path does not exist: {path}")
    auto = jload(wiki / "autonomy.json", {"workflows": {}})
    wf = auto["workflows"].setdefault(a.name, {"level": 0, "history": []})
    wf["path"] = str(path)
    wf["registered"] = today()
    wf["history"].append({"date": now(), "event": "registered", "level": wf["level"]})
    jsave(wiki / "autonomy.json", auto)
    (wiki / "evals" / a.name).mkdir(parents=True, exist_ok=True)
    md = wiki / "workflow-map" / f"{a.name}.md"
    if not md.exists():
        md.write_text(
            f"---\nname: {a.name}\npath: {path}\nregistered: {today()}\n---\n\n"
            f"# {a.name}\n\n**Purpose:** {a.purpose or 'TODO: one sentence on what this workflow is for'}\n\n"
            "## Inputs / outputs\nTODO\n\n## Concepts that may affect it\n(triage fills this in)\n\n"
            "## Eval status\nNo eval suite yet - Level 0 (propose only).\n"
        )
    print(json.dumps({"registered": a.name, "path": str(path), "level": wf["level"]}, indent=2))


def compute_eligibility(wiki, wf, label="baseline", model=None):
    cases = [c for c in load_cases(wiki, wf) if c.get("approved") and c.get("checks")]
    n = len(cases)
    held = sum(1 for c in cases if c["_split"] == "heldout")
    neg = sum(1 for c in cases if c.get("negative"))
    res = jload(wiki / "evals" / wf / f"results-{label}.json")
    info = {"approved_cases": n, "heldout_cases": held, "negative_cases": neg,
            "baseline_present": res is not None,
            "baseline_model": (res or {}).get("model")}
    unmet1, unmet2 = [], []
    if n < 3:
        unmet1.append(f"need >=3 approved cases (have {n})")
    if res is None:
        unmet1.append(f"no baseline results (results-{label}.json)")
    if n < 8:
        unmet2.append(f"need >=8 approved cases (have {n})")
    if held < 2:
        unmet2.append(f"need >=2 held-out cases (have {held})")
    if neg < 1:
        unmet2.append("need >=1 negative case (should NOT trigger / must not do X)")
    if res is not None:
        by = run_scores(res)
        covered = all(c["id"] in by for c in cases)
        runs_min = min((len(v) for v in by.values()), default=0)
        noise = mean([sd(v) for v in by.values()]) if by else 1.0
        info.update({"min_runs_per_case": runs_min, "mean_run_to_run_sd": round(noise, 3),
                     "baseline_covers_all_cases": covered})
        if not covered:
            unmet2.append("baseline results do not cover all approved cases (re-grade)")
        if runs_min < 3:
            unmet2.append(f"need >=3 runs per case in baseline (have {runs_min})")
        if noise > 0.15:
            unmet2.append(f"baseline too noisy (mean run-to-run sd {noise:.2f} > 0.15): tighten vague checks")
        if model and res.get("model") != model:
            unmet2.append(f"baseline was run on {res.get('model') or 'an unrecorded model'}, current model is "
                          f"{model}: re-baseline (see model-upgrade)")
    level = 0
    if not unmet1:
        level = 1
        if not unmet2:
            level = 2
    return level, info, (unmet1 if level == 0 else unmet2 if level == 1 else [])


def cmd_eligibility(a):
    wiki = need_wiki(a.wiki)
    level, info, unmet = compute_eligibility(wiki, a.workflow, a.baseline, a.model)
    cur = jload(wiki / "autonomy.json", {"workflows": {}})["workflows"].get(a.workflow, {}).get("level")
    print(json.dumps({"workflow": a.workflow, "current_level": cur, "eligible_level": level,
                      "stats": info, "unmet_for_next_level": unmet}, indent=2))


def cmd_autonomy(a):
    wiki = need_wiki(a.wiki)
    auto = jload(wiki / "autonomy.json", {"workflows": {}})
    wf = auto["workflows"].get(a.workflow)
    if wf is None:
        die(f"workflow {a.workflow} not registered")
    if a.set is not None:
        if a.set > wf["level"]:
            level, _, unmet = compute_eligibility(wiki, a.workflow)
            if a.set > level:
                die(f"eval suite only supports Level {level}; unmet: {unmet}")
        wf["history"].append({"date": now(), "event": "level-change", "from": wf["level"],
                              "to": a.set, "reason": a.reason or ""})
        wf["level"] = a.set
        jsave(wiki / "autonomy.json", auto)
        append_journal(wiki, f"autonomy for `{a.workflow}` set to Level {a.set}. {a.reason or ''}")
    print(json.dumps({"workflow": a.workflow, "level": wf["level"], "path": wf["path"]}, indent=2))


# ------------------------------------------------------------------- grade
def run_det(check, text):
    k, v = check["kind"], check.get("value")
    ci = check.get("ci", True)
    lower = text.lower()
    if k == "contains":
        return (v.lower() in lower) if ci else (v in text)
    if k == "not_contains":
        return (v.lower() not in lower) if ci else (v not in text)
    if k == "regex":
        return re.search(v, text, re.I | re.M) is not None
    if k == "not_regex":
        return re.search(v, text, re.I | re.M) is None
    if k == "max_words":
        return len(text.split()) <= int(v)
    if k == "min_words":
        return len(text.split()) >= int(v)
    if k == "has_sections":
        return all(s.lower() in lower for s in v)
    if k == "json_valid":
        try:
            json.loads(text.strip())
            return True
        except ValueError:
            return False
    raise ValueError(f"unknown deterministic check kind: {k}")


def cmd_grade(a):
    wiki = need_wiki(a.wiki)
    cases = [c for c in load_cases(wiki, a.workflow) if c.get("approved") and c.get("checks")]
    if not cases:
        die("no approved cases with checks")
    problems = validate_cases(cases)
    if problems:
        die("eval suite has problems:\n  - " + "\n  - ".join(problems))
    ev = wiki / "evals" / a.workflow
    rubric = jload(ev / f"rubric-{a.label}.json", {})
    runs, pending = [], []
    for c in cases:
        for k in range(1, a.runs + 1):
            p = ev / "outputs" / a.label / c["id"] / f"run{k}.txt"
            if not p.exists():
                die(f"missing output file: {p}")
            text = p.read_text(errors="replace")
            checks = []
            for ch in c["checks"]:
                if ch["type"] == "deterministic":
                    checks.append({"name": ch["name"], "kind": "deterministic",
                                   "passed": bool(run_det(ch, text))})
                else:
                    v = rubric.get(c["id"], {}).get(str(k), {}).get(ch["name"])
                    if v is None:
                        pending.append({"case_id": c["id"], "run": k, "check": ch["name"],
                                        "criterion": ch.get("criterion", ""), "output_path": str(p),
                                        "prompt": c.get("prompt", "")})
                    else:
                        checks.append({"name": ch["name"], "kind": "rubric", "passed": bool(v)})
            runs.append({"case_id": c["id"], "run": k, "checks": checks})
    if pending and not a.allow_pending:
        jsave(ev / f"pending-{a.label}.json", pending)
        print(json.dumps({"status": "pending-rubric", "pending_checks": len(pending),
                          "file": str(ev / f"pending-{a.label}.json"),
                          "next": f"judge each item in a SEPARATE context, write rubric-{a.label}.json "
                                  "as {case_id: {run: {check_name: true|false}}}, then re-run grade"}, indent=2))
        sys.exit(2)
    res = {"workflow": a.workflow, "label": a.label, "model": a.model,
           "graded": datetime.now().isoformat(timespec="seconds"), "runs": runs}
    jsave(ev / f"results-{a.label}.json", res)
    by = run_scores(res)
    print(json.dumps({"status": "ok", "label": a.label, "model": a.model, "cases": len(by),
                      "overall": round(mean([mean(v) for v in by.values()]), 3),
                      "mean_run_to_run_sd": round(mean([sd(v) for v in by.values()]), 3)}, indent=2))


# ---------------------------------------------------------------- snapshot
def cmd_snapshot(a):
    wiki = need_wiki(a.wiki)
    wf = jload(wiki / "autonomy.json", {"workflows": {}})["workflows"].get(a.workflow)
    if wf is None:
        die(f"workflow {a.workflow} not registered")
    live = Path(wf["path"])
    if not live.exists():
        die(f"workflow path missing: {live}")
    stem = f"chg-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify(a.workflow)}"
    cid, n = stem, 1
    while (wiki / "changelog" / "snapshots" / cid).exists():
        n += 1
        cid = f"{stem}-{n}"
    base = wiki / "changelog" / "snapshots" / cid
    kind = "file" if live.is_file() else "dir"
    for name in ("before", "candidate"):
        d = base / name
        d.mkdir(parents=True)
        if kind == "file":
            shutil.copy2(live, d / live.name)
        else:
            copy_tree(live, d)
    jsave(base / "meta.json", {"change_id": cid, "workflow": a.workflow, "path": str(live),
                               "kind": kind, "created": now(), "status": "open"})
    target = base / "candidate" / (live.name if kind == "file" else "")
    print(json.dumps({"change_id": cid, "edit_here": str(target).rstrip("/"),
                      "before": str(base / "before")}, indent=2))


# -------------------------------------------------------------------- gate
def diff_stats(before, after):
    before, after = Path(before), Path(after)

    def files(root):
        return {str(p.relative_to(root)): p for p in root.rglob("*")
                if p.is_file() and ".git" not in p.parts}

    fb, fa = files(before), files(after)
    changed, touched, fm_changed = 0, [], False
    for name in sorted(set(fb) | set(fa)):
        try:
            x = fb[name].read_text().splitlines() if name in fb else []
            y = fa[name].read_text().splitlines() if name in fa else []
        except UnicodeDecodeError:
            same = name in fb and name in fa and fb[name].read_bytes() == fa[name].read_bytes()
            if not same:
                changed += 1
                touched.append(name)
            continue
        d = [l for l in difflib.unified_diff(x, y, lineterm="", n=0)
             if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        if d:
            changed += len(d)
            touched.append(name)
        if name.endswith("SKILL.md") and raw_frontmatter("\n".join(x)) != raw_frontmatter("\n".join(y)):
            fm_changed = True
    return {"changed_lines": changed, "files_touched": touched, "frontmatter_changed": fm_changed}


def cmd_gate(a):
    wiki = need_wiki(a.wiki)
    base = snap_dir(wiki, a.change_id)
    meta = jload(base / "meta.json")
    wf = meta["workflow"]
    level = jload(wiki / "autonomy.json")["workflows"][wf]["level"]
    ds = diff_stats(base / "before", base / "candidate")
    out = {"change_id": a.change_id, "workflow": wf, "level": level, "diff": ds,
           "candidate_hash": tree_hash(base / "candidate"), "hard_failures": [], "cautions": []}
    ev = wiki / "evals" / wf
    bres = jload(ev / f"results-{a.baseline}.json")
    cres = jload(ev / f"results-{a.candidate}.json")

    def finish(decision):
        out["decision"] = decision
        jsave(base / "gate.json", out)
        print(json.dumps(out, indent=2))

    if level == 0 or not bres or not cres:
        out["cautions"].append("Level 0 (no usable eval suite): propose only" if level == 0
                               else "baseline or candidate results missing")
        return finish("PROPOSE_ONLY")

    out["candidate_results_graded"] = cres.get("graded")
    bm, cm = bres.get("model"), cres.get("model")
    if not bm or not cm or bm != cm:
        out["hard_failures"].append(
            f"invalid comparison: baseline model={bm or 'unrecorded'}, candidate model={cm or 'unrecorded'}. "
            "Re-run both on the same model (grade --model <id>) and gate again.")
        return finish("RERUN")
    held_ids = {c["id"] for c in jload(ev / "heldout.json", {"cases": []}).get("cases", [])}
    bs, cs = run_scores(bres), run_scores(cres)
    if set(bs) != set(cs):
        out["hard_failures"].append("baseline and candidate scored different case sets")
        return finish("REJECT")
    regress = [c for c in sorted(bs) if mean(cs[c]) < mean(bs[c]) - a.tolerance]
    b_all, c_all = mean([mean(v) for v in bs.values()]), mean([mean(v) for v in cs.values()])
    held = [c for c in bs if c in held_ids]
    b_held = mean([mean(bs[c]) for c in held]) if held else None
    c_held = mean([mean(cs[c]) for c in held]) if held else None
    noise = mean([sd(v) for v in cs.values()])
    delta = c_all - b_all
    out["scores"] = {"baseline_overall": round(b_all, 3), "candidate_overall": round(c_all, 3),
                     "delta": round(delta, 3),
                     "baseline_heldout": None if b_held is None else round(b_held, 3),
                     "candidate_heldout": None if c_held is None else round(c_held, 3),
                     "regressed_cases": regress, "candidate_run_to_run_sd": round(noise, 3)}
    if regress:
        out["hard_failures"].append(f"cases regressed: {regress}")
    if held and c_held < b_held - a.tolerance:
        out["hard_failures"].append("held-out score dropped")
    if delta < -a.tolerance:
        out["hard_failures"].append("overall score dropped")
    base_noise = mean([sd(v) for v in bs.values()])
    bar = max(a.min_improvement, 0.5 * max(base_noise, noise))
    out["scores"]["required_improvement"] = round(bar, 3)
    if delta < bar:
        out["cautions"].append(f"improvement not clearly above noise (delta {delta:+.3f} < required {bar:.3f})")
    if not held:
        out["cautions"].append("no held-out cases were scored")
    if noise > a.max_noise:
        out["cautions"].append(f"unstable results (run-to-run sd {noise:.2f} > {a.max_noise})")
    if ds["changed_lines"] > a.max_changed_lines:
        out["cautions"].append(f"large change ({ds['changed_lines']} lines > {a.max_changed_lines})")
    if ds["frontmatter_changed"]:
        out["cautions"].append("SKILL.md frontmatter changed (affects triggering): human review required")
    if "upskilling-agent" in meta["path"]:
        out["cautions"].append("workflow is part of the upskilling-agent plugin itself: never auto-applied")
    if out["hard_failures"]:
        return finish("REJECT")
    return finish("AUTO_APPLY" if level >= 2 and not out["cautions"] else "ASK")


def cmd_apply(a):
    wiki = need_wiki(a.wiki)
    base = snap_dir(wiki, a.change_id)
    meta = jload(base / "meta.json")
    if not a.user_approved:
        g = jload(base / "gate.json")
        if not g:
            die("no gate result: run `gate` first, or pass --user-approved after the user approves")
        if g.get("decision") != "AUTO_APPLY":
            die(f"gate decision is {g.get('decision')}, not AUTO_APPLY; needs user approval")
        if g.get("candidate_hash") != tree_hash(base / "candidate"):
            die("candidate changed after it was gated; re-run evals and gate")
    restore(base / "candidate", meta["path"], meta["kind"])
    g = jload(base / "gate.json", {})
    ev = wiki / "evals" / meta["workflow"]
    cres_path, bres_path = ev / "results-candidate.json", ev / "results-baseline.json"
    cres = jload(cres_path)
    if (cres and g.get("scores") and g.get("candidate_results_graded") == cres.get("graded")
            and g.get("candidate_hash") == tree_hash(base / "candidate")):
        if bres_path.exists():
            arch = ev / f"results-baseline-before-{a.change_id}.json"
            shutil.copy2(bres_path, arch)
            meta["baseline_archive"] = arch.name
        meta["baseline_promoted"] = True
        cres["label"], cres["promoted_from"] = "baseline", a.change_id
        jsave(bres_path, cres)
    meta["status"] = "applied"
    meta["applied_by"] = "user" if a.user_approved else "gate"
    meta["applied_at"] = now()
    jsave(base / "meta.json", meta)
    print(json.dumps({"applied": a.change_id, "by": meta["applied_by"], "path": meta["path"]}, indent=2))


# ------------------------------------------------------------------ record
def cmd_record(a):
    wiki = need_wiki(a.wiki)
    base = snap_dir(wiki, a.change_id)
    meta = jload(base / "meta.json")
    gate = jload(base / "gate.json", {})
    if a.decision in ("AUTO_APPLIED", "USER_APPLIED"):
        after = base / "after"
        if after.exists():
            shutil.rmtree(after)
        after.mkdir()
        live = Path(meta["path"])
        if meta["kind"] == "file":
            shutil.copy2(live, after / live.name)
        else:
            copy_tree(live, after)
    concepts = [c for c in (a.concepts or "").split(",") if c]
    revert_cmd = f"python {Path(__file__).resolve()} revert {wiki} --change-id {a.change_id}"
    scores = gate.get("scores", {})
    lines = [
        "---", f"change_id: {a.change_id}", f"workflow: {meta['workflow']}", f"date: {now()}",
        f"decision: {a.decision}", f"concepts: [{', '.join(concepts)}]",
        f"autonomy_level: {gate.get('level', '')}", "---", "", f"# {a.title}", "",
        "## Why", a.summary or "(none given)", "",
        "## Impact (eval results)",
    ]
    if scores:
        lines += [f"- overall: {scores['baseline_overall']} -> {scores['candidate_overall']} (delta {scores['delta']:+})",
                  f"- held-out: {scores['baseline_heldout']} -> {scores['candidate_heldout']}",
                  f"- regressed cases: {scores['regressed_cases'] or 'none'}",
                  f"- run-to-run sd: {scores['candidate_run_to_run_sd']}"]
    else:
        lines.append("- no eval data (Level 0 or results missing): change is unmeasured")
    d = gate.get("diff", {})
    lines += ["", "## Diff", f"- lines changed: {d.get('changed_lines', '?')}",
              f"- files: {', '.join(d.get('files_touched', [])) or '-'}",
              f"- frontmatter changed: {d.get('frontmatter_changed', '?')}",
              f"- gate cautions: {'; '.join(gate.get('cautions', [])) or 'none'}", "",
              "## Revert", f"`{revert_cmd}`", "",
              f"Snapshots: `changelog/snapshots/{a.change_id}/` (before/, candidate/, after/)", ""]
    (wiki / "changelog" / f"{a.change_id}.md").write_text("\n".join(lines))
    row = {"event": "change", "change_id": a.change_id, "date": now(), "workflow": meta["workflow"],
           "title": a.title, "decision": a.decision, "concepts": concepts,
           "delta": scores.get("delta"), "level": gate.get("level")}
    with open(wiki / "changelog" / "index.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")
    append_journal(wiki, f"`{meta['workflow']}`: {a.title} [{a.decision}] ({a.change_id})")
    print(json.dumps({"recorded": a.change_id, "revert_command": revert_cmd}, indent=2))


def cmd_revert(a):
    wiki = need_wiki(a.wiki)
    base = snap_dir(wiki, a.change_id)
    meta = jload(base / "meta.json")
    if meta.get("status") == "reverted":
        die("already reverted")
    live = Path(meta["path"])
    if not (base / "after").exists() and meta.get("status") != "applied":
        die("this change was never applied; nothing to revert")
    restore(base / "before", live, meta["kind"])
    ev = wiki / "evals" / meta["workflow"]
    if meta.get("baseline_promoted"):
        arch = ev / meta.get("baseline_archive", "")
        if meta.get("baseline_archive") and arch.exists():
            shutil.copy2(arch, ev / "results-baseline.json")
        elif (ev / "results-baseline.json").exists():
            (ev / "results-baseline.json").unlink()
    meta["status"] = "reverted"
    meta["reverted_at"] = now()
    jsave(base / "meta.json", meta)
    auto = jload(wiki / "autonomy.json")
    wf = auto["workflows"][meta["workflow"]]
    old = wf["level"]
    wf["level"] = max(0, old - 1)
    wf["history"].append({"date": now(), "event": "demoted-after-revert", "from": old,
                          "to": wf["level"], "reason": a.change_id})
    jsave(wiki / "autonomy.json", auto)
    with open(wiki / "changelog" / f"{a.change_id}.md", "a") as f:
        f.write(f"\n## REVERTED {now()}\nRestored pre-change snapshot. Autonomy {old} -> {wf['level']} "
                "(a change that needed reverting means the evals missed something: add a case for it).\n")
    with open(wiki / "changelog" / "index.jsonl", "a") as f:
        f.write(json.dumps({"event": "revert", "change_id": a.change_id, "date": now(),
                            "workflow": meta["workflow"]}) + "\n")
    append_journal(wiki, f"REVERTED {a.change_id} on `{meta['workflow']}`; autonomy {old} -> {wf['level']}")
    print(json.dumps({"reverted": a.change_id, "autonomy": wf["level"]}, indent=2))


def cmd_history(a):
    wiki = need_wiki(a.wiki)
    rows = [json.loads(l) for l in (wiki / "changelog" / "index.jsonl").read_text().splitlines() if l.strip()] \
        if (wiki / "changelog" / "index.jsonl").exists() else []
    if a.workflow:
        rows = [r for r in rows if r.get("workflow") == a.workflow]
    print(json.dumps(rows[-a.limit:], indent=2))


def _suite_files(wiki, wf):
    d = wiki / "evals" / wf
    return d / "train.json", d / "heldout.json"


def cmd_add_cases(a):
    wiki = need_wiki(a.wiki)
    if a.workflow not in jload(wiki / "autonomy.json", {"workflows": {}})["workflows"]:
        die(f"workflow {a.workflow} not registered")
    raw = jload(a.file)
    drafts = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(drafts, list) or not drafts:
        die("drafts file must be a list of cases or {\"cases\": [...]}")
    existing = [c["id"] for c in load_cases(wiki, a.workflow)]
    problems = validate_cases(drafts, existing)
    if problems:
        die("draft cases rejected (nothing was added):\n  - " + "\n  - ".join(problems))
    for c in drafts:
        c["approved"] = False      # approval is a separate, explicit step after the user replies
    train_p, held_p = _suite_files(wiki, a.workflow)
    path = held_p if a.split == "heldout" else train_p
    data = jload(path, {"workflow": a.workflow, "cases": []})
    data.setdefault("cases", []).extend(drafts)
    jsave(path, data)
    print(json.dumps({"added": [c["id"] for c in drafts], "split": a.split, "approved": False,
                      "next": "show the cases to the user; run approve-cases only for what they accept"}, indent=2))


def cmd_approve_cases(a):
    wiki = need_wiki(a.wiki)
    train_p, held_p = _suite_files(wiki, a.workflow)
    files = {p: jload(p, {"workflow": a.workflow, "cases": []}) for p in (train_p, held_p)}
    all_ids = {c["id"] for d in files.values() for c in d["cases"]}
    want = all_ids if a.all else {i for i in (a.ids or "").split(",") if i}
    if not want:
        die("give --ids a,b,c or --all")
    if want - all_ids:
        die(f"unknown case ids: {sorted(want - all_ids)}")
    for d in files.values():
        for c in d["cases"]:
            if c["id"] in want:
                c["approved"] = True
    for p, d in files.items():
        if d["cases"]:
            jsave(p, d)
    level, info, unmet = compute_eligibility(wiki, a.workflow)
    print(json.dumps({"approved_now": sorted(want), "suite": info, "still_needed_for_next_level": unmet}, indent=2))


def cmd_split_heldout(a):
    wiki = need_wiki(a.wiki)
    train_p, held_p = _suite_files(wiki, a.workflow)
    train = jload(train_p, {"workflow": a.workflow, "cases": []})
    held = jload(held_p, {"workflow": a.workflow, "cases": []})
    approved = [c for c in train["cases"] if c.get("approved")]
    if len(approved) - a.count < 3:
        die(f"moving {a.count} would leave fewer than 3 approved train cases (have {len(approved)})")
    pool = [c for c in approved if not c.get("negative")] or approved
    moved = random.Random(a.seed).sample(pool, min(a.count, len(pool)))
    ids = {c["id"] for c in moved}
    train["cases"] = [c for c in train["cases"] if c["id"] not in ids]
    held["cases"].extend(moved)
    jsave(train_p, train)
    jsave(held_p, held)
    print(json.dumps({"moved_to_heldout": sorted(ids), "train_left": len(train["cases"]),
                      "heldout_total": len(held["cases"])}, indent=2))


SKIP_DIRS = {"node_modules", "__pycache__", "snapshots", "upskill-wiki", "outputs", "evals", "tests"}


def skill_description(text):
    m = re.search(r"^description:\s*(.*)$", raw_frontmatter(text), re.M)
    if not m:
        return ""
    first = m.group(1).strip()
    if first in (">", "|", ">-", "|-", ""):
        block = raw_frontmatter(text).split(m.group(0), 1)[1].splitlines()
        lines = []
        for ln in block:
            if ln.startswith((" ", "\t")):
                lines.append(ln.strip())
            elif ln.strip():
                break
        first = " ".join(lines)
    return re.sub(r"\s+", " ", first.strip("'\""))


def cmd_discover(a):
    roots = [Path(r).expanduser() for r in (a.root or [".", "~/.claude/skills", "/mnt/skills/user"])]
    reg = {}
    if a.wiki:
        reg = {w.get("path"): n for n, w in
               jload(Path(a.wiki).expanduser() / "autonomy.json", {"workflows": {}})["workflows"].items()}
    found = {}
    for root in roots:
        if not root.exists():
            continue
        root = root.resolve()
        for dirpath, dirs, files in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            dirs[:] = [] if depth >= 4 else [d for d in dirs if d not in SKIP_DIRS
                                             and (not d.startswith(".") or d == ".claude")]
            if "SKILL.md" not in files:
                continue
            d = Path(dirpath).resolve()
            if "upskilling-agent" in d.parts:
                continue
            text = (d / "SKILL.md").read_text(errors="replace")
            m = re.search(r"^name:\s*(\S+)", raw_frontmatter(text), re.M)
            found[str(d)] = {"name": m.group(1) if m else d.name, "path": str(d),
                             "description": skill_description(text)[:160],
                             "writable": os.access(d / "SKILL.md", os.W_OK),
                             "registered_as": reg.get(str(d))}
    items = sorted(found.values(), key=lambda x: (x["registered_as"] is not None, not x["writable"], x["name"]))
    print(json.dumps({"found": items, "count": len(items),
                      "note": "writable=false means the skill cannot be edited here (e.g. built-in); "
                              "the upskilling-agent plugin itself is excluded"}, indent=2))


def cmd_compare(a):
    wiki = need_wiki(a.wiki)
    ev = wiki / "evals" / a.workflow
    ra, rb = jload(ev / f"results-{a.a}.json"), jload(ev / f"results-{a.b}.json")
    if not ra or not rb:
        die("both results files must exist")
    sa, sb = run_scores(ra), run_scores(rb)
    common = sorted(set(sa) & set(sb))
    per = [{"case": c, a.a: round(mean(sa[c]), 3), a.b: round(mean(sb[c]), 3),
            "delta": round(mean(sb[c]) - mean(sa[c]), 3)} for c in common]
    print(json.dumps({
        "workflow": a.workflow, f"model_{a.a}": ra.get("model"), f"model_{a.b}": rb.get("model"),
        f"overall_{a.a}": round(mean([mean(sa[c]) for c in common]), 3),
        f"overall_{a.b}": round(mean([mean(sb[c]) for c in common]), 3),
        "regressions": [p for p in per if p["delta"] < 0],
        "improvements": [p for p in per if p["delta"] > 0],
        "unchanged": sum(1 for p in per if p["delta"] == 0),
        "cases_only_in_one": sorted(set(sa) ^ set(sb))}, indent=2))


def cmd_estimate(a):
    wiki = need_wiki(a.wiki)
    cases = [c for c in load_cases(wiki, a.workflow) if c.get("approved") and c.get("checks")]
    per_label_exec = len(cases) * a.runs
    per_label_judge = sum(sum(1 for ch in c["checks"] if ch["type"] == "rubric") for c in cases) * a.runs
    print(json.dumps({
        "approved_cases": len(cases), "runs_per_case": a.runs,
        "per_label": {"workflow_executions": per_label_exec, "rubric_judgements": per_label_judge},
        "baseline_round": per_label_exec + per_label_judge,
        "each_candidate_round": per_label_exec + per_label_judge,
        "note": "A change costs one baseline round (skipped if a current-model baseline exists) plus 1-3 candidate "
                "rounds (draft + up to 2 revisions). Rubric judgements run in separate contexts."}, indent=2))


def cmd_where(a):
    start = Path(a.start).expanduser().resolve()
    for d in [start, *start.parents]:
        for cand in (d, d / "upskill-wiki"):
            if (cand / "autonomy.json").exists() and (cand / "schema.md").exists():
                print(cand)
                return
    die("no upskill wiki found here or in a parent folder; run `init` (wiki-setup skill)")


def cmd_rebuild_index(a):
    wiki = need_wiki(a.wiki)
    groups = {"active": [], "draft": [], "superseded": [], "retired": []}
    for p in sorted((wiki / "concepts").glob("*.md")):
        fm, body = parse_frontmatter(p.read_text())
        m = re.search(r"\*\*Claim[^*]*\*\*\s*(.+)", body)
        summary = (m.group(1).strip() if m else fm.get("title", p.stem))[:110]
        groups.setdefault(fm.get("status", "draft"), []).append(
            f"- [[{p.stem}]] - {summary} - {fm.get('confidence', '?')}")
    lines = ["# Wiki index", "",
             "Generated by `rebuild-index` from concept pages - do not hand-edit (changes are overwritten).",
             "One line per page: `[[slug]] - summary - confidence`.", ""]
    total = 0
    for status, items in groups.items():
        if items:
            lines += [f"## {status.capitalize()} concepts", *items, ""]
            total += len(items)
    if not total:
        lines += ["## Concepts", "(none yet)", ""]
    lines += ["## Workflows", "See `workflow-map/`.", ""]
    (wiki / "index.md").write_text("\n".join(lines))
    print(json.dumps({"index": str(wiki / "index.md"), "concepts_listed": total}, indent=2))


# -------------------------------------------------------------------- lint
def cmd_lint(a):
    wiki = need_wiki(a.wiki)
    findings = []
    idx = (wiki / "index.md").read_text() if (wiki / "index.md").exists() else ""
    src_ids = {p.stem for p in (wiki / "sources").glob("*.md")}
    workflows = set(jload(wiki / "autonomy.json", {"workflows": {}})["workflows"])
    seen = {}
    for p in sorted((wiki / "concepts").glob("*.md")):
        fm, _ = parse_frontmatter(p.read_text())

        def add(sev, msg, p=p):
            findings.append({"severity": sev, "page": f"concepts/{p.name}", "message": msg})

        miss = [k for k in REQUIRED_CONCEPT if fm.get(k) in (None, "", [])]
        if miss:
            add("error", f"missing frontmatter: {', '.join(miss)}")
        if fm.get("confidence") not in CONFIDENCE:
            add("error", f"confidence must be one of {CONFIDENCE}")
        if fm.get("status") not in STATUSES:
            add("error", f"status must be one of {STATUSES}")
        slug = fm.get("slug", "")
        if slug and slug != p.stem:
            add("warn", f"slug '{slug}' does not match filename")
        if slug in seen:
            add("error", f"duplicate slug (also {seen[slug]})")
        seen[slug] = p.name
        active = fm.get("status") in ("active", "draft")
        try:
            lv = date.fromisoformat(fm.get("last_verified", ""))
            expires = int(fm.get("expires_after_days") or a.stale_days)
            age = (date.today() - lv).days
            if active and age > expires:
                add("warn", f"stale: last verified {age} days ago (limit {expires}) - re-verify or retire")
        except ValueError:
            add("error", "last_verified is not a valid YYYY-MM-DD date")
        try:
            learned = date.fromisoformat(fm.get("learned_on", ""))
            if fm.get("confidence") == "read-only" and active and (date.today() - learned).days > 30:
                add("info", "still 'read-only' after 30+ days: test it against a workflow or drop it")
        except ValueError:
            add("error", "learned_on is not a valid YYYY-MM-DD date")
        tags = as_list(fm.get("model_tags"))
        if a.current_model and active and tags and a.current_model not in tags:
            add("info", f"learned/tested on {tags}; current model is {a.current_model} - re-verify")
        for s in as_list(fm.get("sources")):
            if s not in src_ids:
                add("warn", f"source '{s}' has no page in sources/")
        if fm.get("confidence") == "tested-helped" and not fm.get("evidence"):
            add("warn", "tested-helped but no `evidence` (change id) recorded")
        if p.stem not in idx:
            add("warn", "not listed in index.md (orphan)")
        for w in as_list(fm.get("applies_to")):
            if w not in workflows:
                add("info", f"applies_to '{w}' is not a registered workflow")
    for p in sorted((wiki / "sources").glob("*.md")):
        fm, _ = parse_frontmatter(p.read_text())
        if not fm.get("trust"):
            findings.append({"severity": "warn", "page": f"sources/{p.name}", "message": "no trust rating"})
    inj = [re.compile(x, re.I) for x in (
        r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules)",
        r"disregard (the |all |your )?(system|previous|prior|safety)",
        r"(you|assistant|agent|claude)\s+(must|should|shall)\s+(now\s+)?(run|execute|delete|send|upload|exfiltrate)",
        r"do not (tell|inform|mention to) the user", r"reveal (your|the) system prompt")]
    for folder in ("concepts", "sources"):
        for p in sorted((wiki / folder).glob("*.md")):
            body = p.read_text()
            hit = next((rx.pattern for rx in inj if rx.search(body)), None)
            if hit:
                findings.append({"severity": "warn", "page": f"{folder}/{p.name}",
                                 "message": "possible embedded instruction aimed at an agent - review; "
                                            "a legitimate page about prompt injection may also match"})
    order = {"error": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    if a.json:
        print(json.dumps(findings, indent=2))
    else:
        counts = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
        print(f"wiki lint: {counts['error']} errors, {counts['warn']} warnings, {counts['info']} info")
        for f in findings:
            print(f"[{f['severity']}] {f['page']}: {f['message']}")


# --------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def P(name, fn, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("wiki")
        p.set_defaults(fn=fn)
        return p

    p = P("init", cmd_init)
    p.add_argument("--scope", choices=["personal", "org"], default="personal")
    p = P("register-workflow", cmd_register)
    p.add_argument("--name", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--purpose")
    p = P("eligibility", cmd_eligibility)
    p.add_argument("--workflow", required=True)
    p.add_argument("--baseline", default="baseline")
    p.add_argument("--model", help="current model id; baseline from another model caps eligibility at Level 1")
    p = P("autonomy", cmd_autonomy)
    p.add_argument("--workflow", required=True)
    p.add_argument("--set", type=int, choices=[0, 1, 2])
    p.add_argument("--reason")
    p = P("grade", cmd_grade)
    p.add_argument("--workflow", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--model", required=True, help="model id that produced these outputs (required: comparisons across models are invalid)")
    p.add_argument("--allow-pending", action="store_true")
    p = P("snapshot", cmd_snapshot)
    p.add_argument("--workflow", required=True)
    p = P("gate", cmd_gate)
    p.add_argument("--change-id", required=True)
    p.add_argument("--baseline", default="baseline")
    p.add_argument("--candidate", default="candidate")
    p.add_argument("--tolerance", type=float, default=0.0)
    p.add_argument("--min-improvement", type=float, default=0.02)
    p.add_argument("--max-noise", type=float, default=0.2)
    p.add_argument("--max-changed-lines", type=int, default=40)
    p = P("apply", cmd_apply)
    p.add_argument("--change-id", required=True)
    p.add_argument("--user-approved", action="store_true")
    p = P("record", cmd_record)
    p.add_argument("--change-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--decision", required=True, choices=DECISIONS)
    p.add_argument("--concepts")
    p.add_argument("--summary")
    p = P("revert", cmd_revert)
    p.add_argument("--change-id", required=True)
    p = P("history", cmd_history)
    p.add_argument("--workflow")
    p.add_argument("--limit", type=int, default=20)
    p = P("add-cases", cmd_add_cases)
    p.add_argument("--workflow", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--split", choices=["train", "heldout"], default="train")
    p = P("approve-cases", cmd_approve_cases)
    p.add_argument("--workflow", required=True)
    p.add_argument("--ids")
    p.add_argument("--all", action="store_true")
    p = P("split-heldout", cmd_split_heldout)
    p.add_argument("--workflow", required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--seed", type=int, default=1)
    p = sub.add_parser("discover")
    p.add_argument("--root", action="append")
    p.add_argument("--wiki")
    p.set_defaults(fn=cmd_discover)
    p = P("compare", cmd_compare)
    p.add_argument("--workflow", required=True)
    p.add_argument("--a", required=True, help="results label, e.g. baseline-old")
    p.add_argument("--b", required=True, help="results label, e.g. baseline")
    p = P("estimate", cmd_estimate)
    p.add_argument("--workflow", required=True)
    p.add_argument("--runs", type=int, default=3)
    p = sub.add_parser("where")
    p.add_argument("start", nargs="?", default=".")
    p.set_defaults(fn=cmd_where)
    p = P("rebuild-index", cmd_rebuild_index)
    p = P("lint", cmd_lint)
    p.add_argument("--current-model")
    p.add_argument("--stale-days", type=int, default=90)
    p.add_argument("--json", action="store_true")

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
