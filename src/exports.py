"""Exports: game translation file, agent settings and the HTML workflow report (CONTRACTS §12).

Every dynamic value in the report is passed through ``html.escape``; the report has a
strict Content-Security-Policy and contains no script. Nothing is written when the
project is not approved, has CRITICAL issues, or contains something that looks like a key.
"""
from __future__ import annotations

import difflib
import html
import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import agents
from .project_state import ProjectState, can_export, now_iso, validate_current
from .providers import find_secrets
from .validation import (FORMAT_NAME, ValidationReport, spec_from_challenge, validate_game_file,
                         validate_translations, MAX_CHARACTER_NAME)

GENERATED_BY = "Game Localisation Studio v0.3"
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
WORKFLOW_STEPS = ["INPUT", "BASELINE", "TRANSLATOR", "REVIEWER", "HUMAN DECISION", "REVISION",
                  "VALIDATION", "HUMAN APPROVAL", "EXPORT"]
ACTION_LABELS = {"accept": "Accepted", "reject": "Rejected — not applied",
                 "accept_edited": "Accepted with edits", "override": "Overridden by human text"}


@dataclass
class ExportResult:
    ok: bool
    path: str | None
    message: str
    issues: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def __getitem__(self, key):  # dict-style access, as written in CONTRACTS
        return getattr(self, key)


def scan_for_secrets(text: str, extra_secrets=()) -> list[str]:
    """Masked descriptions of key-like strings found in ``text`` (empty list = clean).

    Besides the patterns, this always checks every API key loaded in this session
    (``providers.loaded_secrets``), so keys without a known prefix are caught too."""
    return find_secrets(text, extra_secrets)


def _e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------- game file


def _is_game_mission(challenge: dict, manifest: dict | None) -> bool:
    if not manifest:
        return False
    return challenge.get("mission") in {m.get("id") for m in manifest.get("missions", [])}


def output_source(state: ProjectState) -> str:
    """``live | replay | mixed`` from the versions behind the current translation."""
    srcs, seen, v = set(), set(), state.current_version()
    while v is not None and v.version_id not in seen:
        seen.add(v.version_id)
        if v.source in ("live", "replay"):
            srcs.add(v.source)
        v = state.version(v.parent_id)
    if srcs == {"live", "replay"}:
        return "mixed"
    if srcs:
        return srcs.pop()
    return "replay" if state.mode == "replay" else "live"


def uses_simulated_output(state: ProjectState) -> bool:
    return (state.mode == "replay" or any(v.source == "replay" for v in state.versions)
            or any(f.source == "replay" for f in state.findings))


def build_game_translation(state: ProjectState, challenge: dict,
                           manifest: dict | None) -> tuple[dict, ValidationReport]:
    cur = state.current_version()
    translations = dict(cur.translations) if cur else {}
    order = [sid for sid in state.string_ids() if sid in translations]
    order += [sid for sid in translations if sid not in order]
    mission = challenge.get("mission") or state.mission
    game = _is_game_mission(challenge, manifest)
    obj = {"format": FORMAT_NAME, "schema_version": "1.0", "locale": state.locale,
           "mission": mission if game else "custom", "source": output_source(state),
           "approved": bool(state.approval.get("approved")), "generated_by": GENERATED_BY,
           "generated_at": now_iso()}
    if game:
        known = manifest.get("characters") or {}
        chars = {c["id"]: c["name_en_suggestion"] for c in challenge.get("characters", [])
                 if isinstance(c, dict) and c.get("id") in known
                 and isinstance(c.get("name_en_suggestion"), str)
                 and 0 < len(c["name_en_suggestion"].strip()) <= MAX_CHARACTER_NAME}
        if chars:
            obj["characters"] = chars
    obj["strings"] = {sid: translations[sid] for sid in order}
    if game:
        report = validate_game_file(json.dumps(obj, ensure_ascii=False, indent=2), manifest,
                                    require_all_for_mission=mission)
    else:
        report = validate_translations(translations, spec_from_challenge(challenge), True)
    return obj, report


def _blocked(message: str, issues=()) -> ExportResult:
    return ExportResult(False, None, message, [i.to_dict() if hasattr(i, "to_dict") else i
                                               for i in issues])


def export_game_translation(state: ProjectState, challenge: dict, manifest: dict | None,
                            out_dir) -> ExportResult:
    ok, reasons = can_export(state)
    if not ok:
        return _blocked("Export blocked: " + " ".join(reasons[:3]), validate_current(state).critical)
    obj, report = build_game_translation(state, challenge, manifest)
    if not report.ok:
        return _blocked(f"Export blocked: {report.summary()} First: {report.critical[0].message}",
                        report.critical)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if scan_for_secrets(text):
        return _blocked("Export blocked: the translation contains something that looks like an "
                        "API key. Remove it and approve again.")
    name = "game_translation_en.json" if obj["mission"] != "custom" else "custom_translation_en.json"
    path = Path(out_dir) / name
    _write_atomic(path, text)
    state.stage = "EXPORTED"
    state.log("exported", f"{name} written")
    return ExportResult(True, str(path), f"Saved {name}. Import it into the game to play your "
                        "translation.", [w.to_dict() for w in report.warnings])


# --------------------------------------------------------------------------- settings


def _prompt_pair(state: ProjectState, agent: str) -> dict:
    snaps = [s for s in state.prompt_snapshots
             if s.agent == agent and agents.REPAIR_MARK not in s.user]
    if not snaps:
        return {"initial": None, "final": None}
    pick = lambda s: {"system": s.system, "user": s.user, "model": s.model,  # noqa: E731
                      "round": s.round, "source": s.source, "created_at": s.created_at}
    return {"initial": pick(snaps[0]), "final": pick(snaps[-1])}


def build_agent_settings(state: ProjectState, challenge: dict) -> dict:
    """Models, prompts (initial + final), settings, glossary, rules, limits. Never a key."""
    out_agents = {}
    for role in ("translator", "reviewer"):
        cfg = state.agents.get(role, {})
        out_agents[role] = {
            "settings": cfg.get("settings", {}),
            "settings_text": agents.settings_to_text(role, cfg.get("settings", {})),
            "instructions": cfg.get("instructions", ""),
            "default_instructions": cfg.get("default_instructions", ""),
            "instructions_changed": cfg.get("instructions") != cfg.get("default_instructions"),
            "temperature": agents.temperature_for(role, cfg.get("settings")),
        }
        if "preset" in cfg:  # translator only (CONTRACTS §15)
            out_agents[role]["preset"] = cfg["preset"]
            out_agents[role]["edited_after_preset"] = bool(cfg.get("edited"))
    return {
        "format": "game-localisation-studio-agent-settings", "schema_version": "1.0",
        "generated_by": GENERATED_BY, "generated_at": now_iso(),
        "challenge_id": state.challenge_id, "team_name": state.team_name,
        "locale": state.locale, "mode": state.mode,
        "provider": {k: state.provider.get(k) for k in ("name", "translator_model", "reviewer_model")},
        "agents": out_agents,
        "prompts": {a: _prompt_pair(state, a) for a in ("baseline", "translator", "reviewer", "reviser")},
        "glossary": challenge.get("glossary", []),
        "memory_rules": [r.__dict__ for r in state.memory_rules],
        "revision": {"max_cycles": state.revision.get("max_cycles"),
                     "cycles_done": state.revision.get("cycles_done")},
        "limits": {"batch_size": agents.BATCH_SIZE, "max_tokens": agents.MAX_TOKENS,
                   "request_cap": state.usage.get("request_cap")},
        "usage": dict(state.usage),
        "simulated": uses_simulated_output(state),
    }


# --------------------------------------------------------------------------- HTML


def prompt_diff_html(old: str, new: str, context: int = 3) -> str:
    """Escaped side-by-side line diff as an HTML table (no script, no links)."""
    a, b = (old or "").splitlines(), (new or "").splitlines()
    rows = []

    def row(l, r, cls_l="", cls_r=""):
        rows.append(f'<tr><td class="{cls_l}">{_e(l)}</td><td class="{cls_r}">{_e(r)}</td></tr>')

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            n = i2 - i1
            if n > 2 * context + 1:
                for k in range(context):
                    row(a[i1 + k], b[j1 + k])
                rows.append(f'<tr><td colspan="2" class="skip">… {n - 2 * context} unchanged '
                            'line(s) …</td></tr>')
                for k in range(n - context, n):
                    row(a[i1 + k], b[j1 + k])
            else:
                for k in range(n):
                    row(a[i1 + k], b[j1 + k])
        else:
            left, right = a[i1:i2], b[j1:j2]
            for k in range(max(len(left), len(right))):
                l = left[k] if k < len(left) else ""
                r = right[k] if k < len(right) else ""
                row(l, r, "del" if k < len(left) else "", "ins" if k < len(right) else "")
    if not rows:
        return '<p class="muted">No difference.</p>'
    return ('<table class="diff"><thead><tr><th>Before</th><th>After</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>")


_CSS = """
:root{--ink:#1f2933;--muted:#616e7c;--line:#d9e2ec;--bg:#f5f7fa;--card:#fff;--accent:#c0392b;
--blue:#2471a3;--green:#1e8449;--amber:#b9770e}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,
sans-serif;color:var(--ink);background:var(--bg)}main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:0 0 12px;border-bottom:2px solid var(--line);
padding-bottom:6px}section{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:18px 20px;margin:16px 0}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;
white-space:pre-wrap;word-break:break-word}th{background:#eef2f7}tbody tr:nth-child(even) td{background:#fafbfc}
.muted{color:var(--muted)}.banner{background:#fff4e5;border:2px solid var(--amber);border-radius:10px;
padding:12px 16px;font-weight:600}.badge{display:inline-block;padding:1px 8px;border-radius:10px;
font-size:12px;font-weight:600;background:#e4e7eb}.critical,.CRITICAL{background:#fde2e1;color:#a61b1b}
.major,.WARNING{background:#fff1d6;color:#8a5a00}.minor{background:#e3f2fd;color:#1c4f80}
.agree{color:var(--green);font-weight:600}.disagree{color:var(--accent);font-weight:600}
.diff td{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;width:50%}
.diff td.del{background:#fde2e1}.diff td.ins{background:#e3f9e5}.diff td.skip{text-align:center;
color:var(--muted);background:#f0f4f8}dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0}
dt{font-weight:600}dd{margin:0}svg{width:100%;height:auto}.quote{border-left:4px solid var(--blue);
padding:8px 14px;background:#f0f6fb;white-space:pre-wrap}
"""


def _workflow_svg(state: ProjectState) -> str:
    reached = {
        "INPUT": True,
        "BASELINE": state.baseline_version_id is not None,
        "TRANSLATOR": any(v.kind == "translator" for v in state.versions),
        "REVIEWER": bool(state.findings) or any(s.agent == "reviewer" for s in state.prompt_snapshots),
        "HUMAN DECISION": bool(state.latest_decisions()) or any(
            d.action == "direct_edit" for d in state.decisions),
        "REVISION": any(v.kind == "revision" for v in state.versions),
        "VALIDATION": state.current_version() is not None,
        "HUMAN APPROVAL": bool(state.approval.get("approved")),
        "EXPORT": state.stage == "EXPORTED",
    }
    w, h, gap, y = 100, 54, 12, 20
    parts = ['<svg viewBox="0 0 1016 100" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Workflow diagram"><defs><marker id="arr" markerWidth="8" markerHeight="8" '
             'refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#616e7c"/></marker></defs>']
    for i, step in enumerate(WORKFLOW_STEPS):
        x = 4 + i * (w + gap)
        human = step.startswith("HUMAN")
        fill = ("#fdecea" if human else "#e8f1fb") if reached[step] else "#f5f7fa"
        stroke = ("#c0392b" if human else "#2471a3") if reached[step] else "#bcccdc"
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
                     f'stroke="{stroke}" stroke-width="2"/>')
        words = step.split(" ")
        for k, word in enumerate(words):
            ty = y + h / 2 + (k - (len(words) - 1) / 2) * 14 + 4
            parts.append(f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-size="11" '
                         f'font-weight="600" fill="#1f2933">{_e(word)}</text>')
        if reached[step]:
            parts.append(f'<text x="{x + w / 2}" y="{y + h + 16}" text-anchor="middle" '
                         'font-size="10" fill="#1e8449">done</text>')
        if i < len(WORKFLOW_STEPS) - 1:
            parts.append(f'<line x1="{x + w}" y1="{y + h / 2}" x2="{x + w + gap - 1}" '
                         f'y2="{y + h / 2}" stroke="#616e7c" stroke-width="2" marker-end="url(#arr)"/>')
    parts.append("</svg>")
    return "".join(parts)


def _table(headers, rows) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _first_version(state, kind):
    return next((v for v in state.versions if v.kind == kind), None)


def render_workflow_report(state: ProjectState, challenge: dict, manifest: dict | None) -> str:
    """Self-contained HTML report (escaped, CSP-locked, no script)."""
    cur, base = state.current_version(), state.baseline_version()
    agent_v = _first_version(state, "translator")
    title = challenge.get("title") or state.challenge_id
    S = []  # sections

    if uses_simulated_output(state):
        S.append('<p class="banner">Replay notice: some or all AI outputs in this project are '
                 'SIMULATED — prepared in advance by the course team, not generated live.</p>')

    p = state.provider
    S.append("<section><h2>Project</h2><dl>" + "".join(
        f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in [
            ("Challenge", title), ("Team", state.team_name or "—"), ("English variant", state.locale),
            ("Mode", state.mode), ("Provider", p.get("name")),
            ("Translator model", p.get("translator_model")), ("Reviewer model", p.get("reviewer_model")),
            ("Stage", state.stage), ("Created", state.created_at), ("Last updated", state.updated_at),
            ("Approved", "yes, by " + str(state.approval.get("role")) + " at "
             + str(state.approval.get("approved_at")) if state.approval.get("approved") else "no")])
        + "</dl></section>")

    S.append("<section><h2>Workflow</h2>" + _workflow_svg(state)
             + '<p class="muted">Red boxes are human steps; blue boxes are automated steps.</p></section>')

    rows = []
    for sid in state.string_ids():
        rows.append([f"<code>{_e(sid)}</code>", _e(state.source_text(sid)),
                     _e(base.translations.get(sid, "—") if base else "—"),
                     _e(agent_v.translations.get(sid, "—") if agent_v else "—"),
                     _e(cur.translations.get(sid, "—") if cur else "—")])
    S.append("<section><h2>Translations side by side</h2>"
             + _table(["String id", "Source", "Baseline", "Translator agent", "Final"], rows)
             + "</section>")

    decisions = state.latest_decisions()
    frows = []
    for f in state.findings:
        d = decisions.get(f.finding_id)
        if d is None:
            decision, agree, human = "No decision", "—", ""
        else:
            decision = ACTION_LABELS.get(d.action, d.action)
            agree = ('<span class="agree">Agreed with reviewer</span>' if d.agrees_with_reviewer
                     else '<span class="disagree">Overrode reviewer</span>')
            human = d.human_text or ""
        frows.append([_e(f.finding_id), f"<code>{_e(f.string_id)}</code>",
                      f'<span class="badge">{_e(f.category)}</span> '
                      f'<span class="badge {_e(f.severity)}">{_e(f.severity)}</span>',
                      _e(f.issue) + ("<br><span class='muted'>" + _e(f.reasoning) + "</span>"
                                     if f.reasoning else ""),
                      _e(f.suggestion), _e(decision), agree if d else _e(agree), _e(human),
                      _e(d.comment if d else "")])
    S.append("<section><h2>Reviewer findings and human decisions</h2>"
             + (_table(["Finding", "String", "Type", "Issue and reasoning", "Reviewer suggestion",
                        "Human decision", "Agreed / overrode", "Human text", "Comment"], frows)
                if frows else '<p class="muted">The reviewer reported no findings.</p>')
             + "</section>")

    rrows = [[_e(r.rule_id), _e(r.kind), _e(r.source_term or ""), _e(r.target_term or ""),
              _e(r.text), _e(r.from_finding or ""), _e(r.role)] for r in state.memory_rules]
    S.append("<section><h2>Project memory rules</h2>"
             + (_table(["Rule", "Kind", "Source term", "Target term", "Rule", "From finding", "Added by"],
                       rrows) if rrows else '<p class="muted">No rules were added.</p>')
             + "</section>")

    report = validate_current(state)
    vrows = [[f'<span class="badge {_e(i.severity)}">{_e(i.severity)}</span>', _e(i.code),
              _e(i.string_id or ""), _e(i.message), _e(i.fix_hint)] for i in report.issues]
    S.append("<section><h2>Validation</h2><p>" + _e(report.summary()) + "</p>"
             + (_table(["Severity", "Code", "String", "Problem", "How to fix"], vrows) if vrows else "")
             + "</section>")

    verrows = [[_e(v.version_id), _e(v.label), _e(v.kind), _e(v.source), _e(v.round),
                _e(v.parent_id or ""), _e(v.created_at)] for v in state.versions]
    hrows = [[_e(h.get("created_at")), _e(h.get("event")), _e(h.get("detail"))] for h in state.history]
    S.append("<section><h2>Versions and revision history</h2><p>Revision cycles used: "
             f"{_e(state.revision.get('cycles_done'))} of {_e(state.revision.get('max_cycles'))}.</p>"
             + _table(["Version", "Label", "Kind", "Source", "Round", "Based on", "Created"], verrows)
             + "<h3>Timeline</h3>" + _table(["Time", "Event", "Detail"], hrows) + "</section>")

    diffs = []
    for role in ("translator", "reviewer"):
        cfg = state.agents.get(role, {})
        diffs.append(f"<h3>{_e(role.title())}: instructions (default → final)</h3>"
                     + prompt_diff_html(cfg.get("default_instructions", ""), cfg.get("instructions", "")))
        pair = _prompt_pair(state, role)
        if pair["initial"] and pair["final"]:
            diffs.append(f"<h3>{_e(role.title())}: first prompt sent → last prompt sent</h3>"
                         + prompt_diff_html(pair["initial"]["user"], pair["final"]["user"]))
    S.append("<section><h2>Prompt evolution</h2>" + "".join(diffs) + "</section>")

    u = state.usage
    S.append("<section><h2>Usage</h2><dl>" + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in [
        ("Live requests", f"{u.get('requests', 0)} of {u.get('request_cap')}"),
        ("Simulated (Replay) requests", u.get("simulated_requests", 0)),
        ("Input tokens", u.get("input_tokens", 0)), ("Output tokens", u.get("output_tokens", 0)),
        ("Estimated cost (USD)", "not available" if u.get("est_cost_usd") is None
         else f"{u['est_cost_usd']:.4f}")]) + "</dl></section>")

    S.append("<section><h2>Reflection</h2><p class='muted'>What did your agents get wrong, what did "
             "you change, and why was the final result better?</p><div class='quote'>"
             + (_e(state.reflection) or "<span class='muted'>Not answered yet.</span>")
             + "</div></section>")

    return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>Workflow report — {_e(title)}</title><style>{_CSS}</style></head><body><main>"
            f"<h1>Localisation workflow report</h1><p class='muted'>{_e(title)} · generated "
            f"{_e(now_iso())} by {_e(GENERATED_BY)}</p>" + "".join(S) + "</main></body></html>\n")


# --------------------------------------------------------------------------- all


def _write_checked(path: Path, text: str, what: str) -> ExportResult:
    hits = scan_for_secrets(text)
    if hits:
        return _blocked(f"{what} not saved: it contains something that looks like an API key "
                        f"({', '.join(hits[:2])}).")
    _write_atomic(path, text)
    return ExportResult(True, str(path), f"Saved {path.name}.")


def export_all(state: ProjectState, challenge: dict, manifest: dict | None,
               out_dir) -> dict[str, ExportResult]:
    game = export_game_translation(state, challenge, manifest, out_dir)
    if not game.ok:
        blocked = _blocked(game.message, game.issues)
        return {"game_translation": game, "agent_settings": blocked, "workflow_report": blocked}
    out = Path(out_dir)
    settings_text = json.dumps(build_agent_settings(state, challenge), ensure_ascii=False, indent=2) + "\n"
    return {
        "game_translation": game,
        "agent_settings": _write_checked(out / "agent_settings.json", settings_text, "Agent settings"),
        "workflow_report": _write_checked(out / "workflow_report.html",
                                          render_workflow_report(state, challenge, manifest),
                                          "Workflow report"),
    }
