"""Project state: versions, findings, human decisions and approval (CONTRACTS §9).

Decisions are append-only; the latest decision per finding wins. Any change after
approval revokes the approval automatically and records why.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from .providers import find_secrets, key_refusal
from .validation import StringSpec, validate_translations, ValidationReport

SCHEMA_VERSION = "1.0"
LOCALES = ("en-GB", "en-US", "en")
MODES = ("live", "replay")
STAGES = ("INPUT", "BASELINE", "TRANSLATED", "REVIEWED", "REVISED", "APPROVED", "EXPORTED")
FINDING_ACTIONS = ("accept", "reject", "accept_edited", "override")
ALL_ACTIONS = FINDING_ACTIONS + ("direct_edit", "add_rule", "send_revision", "restore_version",
                                 "approve_final", "revoke_approval")
MAX_TEAM_NAME = 80
MAX_COMMENT = 2000
MAX_HUMAN_TEXT = 1000
MAX_STATE_BYTES = 5 * 1024 * 1024   # a saved project is far smaller; refuse anything bigger


class StudioError(Exception):
    """A workflow problem explained to the student in ``user_message``."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_dict(cls, d: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (d or {}).items() if k in names})


@dataclass
class Rule:
    rule_id: str
    kind: str
    text: str
    source_term: str | None = None
    target_term: str | None = None
    from_finding: str | None = None
    role: str = ""
    created_at: str = field(default_factory=now_iso)


@dataclass
class Version:
    version_id: str
    label: str
    kind: str
    source: str
    round: int = 0
    parent_id: str | None = None
    translations: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    variant: str | None = None   # Replay prompt variant (CONTRACTS §15): faithful|balanced|creative


@dataclass
class Finding:
    finding_id: str
    round: int
    string_id: str
    category: str
    severity: str
    issue: str
    reasoning: str
    suggestion: str
    reviewed_version_id: str | None = None
    source: str = "live"


@dataclass
class Decision:
    decision_id: str
    action: str
    finding_id: str | None = None
    string_id: str | None = None
    role: str = ""
    reviewer_suggestion: str | None = None
    human_text: str | None = None
    agrees_with_reviewer: bool | None = None
    comment: str = ""
    created_at: str = field(default_factory=now_iso)


@dataclass
class PromptSnapshot:
    snapshot_id: str
    agent: str
    round: int
    system: str
    user: str
    model: str
    source: str
    created_at: str = field(default_factory=now_iso)


def _default_usage(cap: int = 40) -> dict:
    return {"requests": 0, "input_tokens": 0, "output_tokens": 0, "request_cap": cap,
            "est_cost_usd": None}


@dataclass
class ProjectState:
    challenge_id: str
    locale: str = "en-GB"
    mode: str = "replay"
    schema_version: str = SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    team_name: str = ""
    mission: str = ""
    strings: list = field(default_factory=list)          # StringSpec dicts (incl. source)
    provider: dict = field(default_factory=dict)
    agents: dict = field(default_factory=dict)
    memory_rules: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    current_version_id: str | None = None
    baseline_version_id: str | None = None
    findings: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    prompt_snapshots: list = field(default_factory=list)
    usage: dict = field(default_factory=_default_usage)
    revision: dict = field(default_factory=lambda: {"max_cycles": 1, "cycles_done": 0})
    stage: str = "INPUT"
    approval: dict = field(default_factory=lambda: {"approved": False, "version_id": None,
                                                    "role": None, "approved_at": None})
    reflection: str = ""
    raw_failures: list = field(default_factory=list)
    history: list = field(default_factory=list)

    # ------------------------------------------------------------- serialisation
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectState":
        d = dict(d)
        d["memory_rules"] = [_from_dict(Rule, r) for r in d.get("memory_rules", [])]
        d["versions"] = [_from_dict(Version, v) for v in d.get("versions", [])]
        d["findings"] = [_from_dict(Finding, f) for f in d.get("findings", [])]
        d["decisions"] = [_from_dict(Decision, x) for x in d.get("decisions", [])]
        d["prompt_snapshots"] = [_from_dict(PromptSnapshot, s)
                                 for s in d.get("prompt_snapshots", [])]
        return _from_dict(cls, d)

    # ------------------------------------------------------------- lookups
    def version(self, vid: str | None) -> Version | None:
        return next((v for v in self.versions if v.version_id == vid), None)

    def current_version(self) -> Version | None:
        return self.version(self.current_version_id)

    def baseline_version(self) -> Version | None:
        return self.version(self.baseline_version_id)

    def finding(self, fid: str) -> Finding | None:
        return next((f for f in self.findings if f.finding_id == fid), None)

    def latest_decisions(self) -> dict[str, Decision]:
        out: dict[str, Decision] = {}
        for d in self.decisions:
            if d.finding_id and d.action in FINDING_ACTIONS:
                out[d.finding_id] = d
        return out

    def open_findings(self, round: int | None = None) -> list[Finding]:
        decided = self.latest_decisions()
        return [f for f in self.findings if f.finding_id not in decided
                and (round is None or f.round == round)]

    def latest_review_round(self) -> int:
        rounds = [s.round for s in self.prompt_snapshots if s.agent == "reviewer"]
        rounds += [f.round for f in self.findings]
        return max(rounds, default=0)

    def spec(self) -> dict[str, StringSpec]:
        return {s["id"]: StringSpec.from_dict(s) for s in self.strings}

    def string_ids(self) -> list[str]:
        return [s["id"] for s in self.strings]

    def source_text(self, sid: str) -> str:
        return next((s.get("source", "") for s in self.strings if s["id"] == sid), "")

    # ------------------------------------------------------------- bookkeeping
    def log(self, event: str, detail: str = "") -> None:
        self.updated_at = now_iso()
        self.history.append({"created_at": self.updated_at, "event": event, "detail": detail})

    def _next(self, prefix: str, items: list, width: int) -> str:
        return f"{prefix}{len(items) + 1:0{width}d}"

    def next_version_id(self) -> str:
        return f"v{len(self.versions) + 1}"

    def add_version(self, label: str, kind: str, source: str, translations: dict, *,
                    round: int = 0, parent_id: str | None = None, notes: dict | None = None,
                    make_current: bool = True) -> Version:
        v = Version(self.next_version_id(), label, kind, source, round, parent_id,
                    dict(translations), dict(notes or {}))
        self.versions.append(v)
        if make_current:
            self.current_version_id = v.version_id
        self.log("version", f"{v.version_id} created ({label})")
        return v

    def add_decision(self, action: str, role: str, **kw) -> Decision:
        d = Decision(self._next("D", self.decisions, 3), action, role=role, **kw)
        self.decisions.append(d)
        self.updated_at = now_iso()
        return d

    def add_snapshot(self, agent: str, round: int, system: str, user: str, model: str,
                     source: str) -> PromptSnapshot:
        s = PromptSnapshot(self._next("S", self.prompt_snapshots, 3), agent, round, system,
                           user, model, source)
        self.prompt_snapshots.append(s)
        return s

    def working_stage(self) -> str:
        if self.revision.get("cycles_done", 0) and any(v.kind == "revision" for v in self.versions):
            return "REVISED"
        if self.findings or any(s.agent == "reviewer" for s in self.prompt_snapshots):
            return "REVIEWED"
        if self.current_version_id:
            return "TRANSLATED"
        if self.baseline_version_id:
            return "BASELINE"
        return "INPUT"

    def invalidate_approval(self, reason: str) -> None:
        """Called before any change; revokes an existing approval."""
        if self.approval.get("approved"):
            self.approval = {"approved": False, "version_id": None, "role": None, "approved_at": None}
            self.log("approval_revoked", f"Approval revoked automatically: {reason}")
        if self.stage in ("APPROVED", "EXPORTED"):
            self.stage = self.working_stage()


# --------------------------------------------------------------------------- API


def new_project(challenge: dict, locale: str, mode: str, provider_name: str,
                translator_model: str, reviewer_model: str | None = None, max_cycles: int = 1,
                team_name: str = "", request_cap: int = 40) -> ProjectState:
    from .agents import default_agent_config  # local import avoids a cycle

    if locale not in LOCALES:
        raise StudioError(f"Unknown English variant '{locale}'. Choose en-GB, en-US or en.")
    if mode not in MODES:
        raise StudioError("Mode must be 'live' or 'replay'.")
    if not isinstance(max_cycles, int) or not 0 <= max_cycles <= 2:
        raise StudioError("The number of revision cycles must be 0, 1 or 2.")
    team_name = (team_name or "").strip()[:MAX_TEAM_NAME]
    problem = key_refusal(team_name, "team name",
                          "The team name looks like it contains a key. Please use a plain name.")
    if problem:
        raise StudioError(problem)
    strings = []
    for s in challenge.get("strings", []):
        spec = StringSpec.from_dict(s).to_dict()
        strings.append(spec)
    state = ProjectState(
        challenge_id=challenge.get("id", "custom"), locale=locale, mode=mode,
        team_name=team_name, mission=challenge.get("mission", challenge.get("id", "custom")),
        strings=strings,
        provider={"name": provider_name, "translator_model": translator_model,
                  "reviewer_model": reviewer_model or translator_model},
        agents={"translator": default_agent_config("translator"),
                "reviewer": default_agent_config("reviewer")},
        usage=_default_usage(request_cap),
        revision={"max_cycles": max_cycles, "cycles_done": 0},
    )
    state.log("project_created", f"Challenge '{state.challenge_id}', {locale}, {mode} mode")
    return state


def _clean_text(text, limit, what) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) > limit:
        raise StudioError(f"The {what} is too long (limit {limit} characters).")
    problem = key_refusal(text, what)
    if problem:
        raise StudioError(problem)
    return text


def decide_finding(state: ProjectState, finding_id: str, action: str, role: str,
                   human_text: str | None = None, comment: str = "") -> Decision:
    """Record a human decision on a reviewer finding (append-only)."""
    f = state.finding(finding_id)
    if f is None:
        raise StudioError(f"There is no finding called '{finding_id}'.")
    if action not in FINDING_ACTIONS:
        raise StudioError(f"'{action}' is not a valid decision. Use accept, reject, "
                          "accept_edited or override.")
    comment = _clean_text(comment, MAX_COMMENT, "comment")
    human_text = _clean_text(human_text, MAX_HUMAN_TEXT, "replacement text") if human_text else None
    if action in ("accept_edited", "override") and not (human_text or "").strip():
        raise StudioError("Please type your own version of the string for this decision.")
    if action in ("accept", "reject"):
        human_text = None
    state.invalidate_approval(f"decision on {finding_id}")
    d = state.add_decision(action, role, finding_id=finding_id, string_id=f.string_id,
                           reviewer_suggestion=f.suggestion, human_text=human_text,
                           agrees_with_reviewer=action in ("accept", "accept_edited"),
                           comment=comment)
    state.log("decision", f"{d.decision_id}: {action} {finding_id} ({f.string_id}) by {role}")
    return d


def bulk_decide(state: ProjectState, finding_ids, action: str, role: str,
                comment: str = "") -> list[Decision]:
    if action not in ("accept", "reject"):
        raise StudioError("Bulk decisions can only accept or reject.")
    return [decide_finding(state, fid, action, role, comment=comment) for fid in finding_ids]


def add_rule(state: ProjectState, kind: str, text: str, role: str, source_term: str | None = None,
             target_term: str | None = None, from_finding: str | None = None) -> Rule:
    if kind not in ("glossary", "style"):
        raise StudioError("A memory rule is either 'glossary' or 'style'.")
    text = _clean_text(text, 500, "rule").strip()
    if not text:
        raise StudioError("Please write the rule text.")
    state.invalidate_approval("memory rule added")
    r = Rule(f"M{len(state.memory_rules) + 1:02d}", kind, text,
             _clean_text(source_term, 100, "source term") or None,
             _clean_text(target_term, 100, "target term") or None, from_finding, role)
    state.memory_rules.append(r)
    state.add_decision("add_rule", role, finding_id=from_finding, human_text=text,
                       comment=f"{r.rule_id} ({kind})")
    state.log("rule_added", f"{r.rule_id}: {text}")
    return r


def direct_edit(state: ProjectState, edits: dict, role: str, comment: str = "") -> Version:
    cur = state.current_version()
    if cur is None:
        raise StudioError("Run the translator first; there is no translation to edit yet.")
    known = set(state.string_ids()) or set(cur.translations)
    bad = [k for k in edits if k not in known]
    if bad:
        raise StudioError("These ids are not part of this challenge: " + ", ".join(bad))
    if not edits:
        raise StudioError("No edits were given.")
    comment = _clean_text(comment, MAX_COMMENT, "comment")
    clean = {k: _clean_text(v, MAX_HUMAN_TEXT, f"text for {k}") for k, v in edits.items()}
    state.invalidate_approval("direct edit")
    translations = {**cur.translations, **clean}
    notes = {k: "Edited directly by the human director" for k in clean}
    v = state.add_version("Human edit", "human_edit", "human", translations,
                          round=cur.round, parent_id=cur.version_id, notes=notes)
    for k, text in clean.items():
        state.add_decision("direct_edit", role, string_id=k, human_text=text, comment=comment)
    return v


def restore_version(state: ProjectState, version_id: str, role: str) -> Version:
    old = state.version(version_id)
    if old is None:
        raise StudioError(f"There is no version called '{version_id}'.")
    state.invalidate_approval(f"restored {version_id}")
    cur = state.current_version()
    v = state.add_version(f"Restored from {version_id}", "restored", "human", old.translations,
                          round=cur.round if cur else old.round,
                          parent_id=cur.version_id if cur else None, notes=old.notes)
    state.add_decision("restore_version", role, comment=f"Restored {version_id} as {v.version_id}")
    return v


def validate_current(state: ProjectState) -> ValidationReport:
    cur = state.current_version()
    return validate_translations(cur.translations if cur else {}, state.spec(), require_all=True)


def approve_final(state: ProjectState, role: str) -> None:
    cur = state.current_version()
    if cur is None:
        raise StudioError("There is no translation to approve yet.")
    report = validate_current(state)
    if not report.ok:
        first = report.critical[0].message
        raise StudioError(f"Approval blocked: {len(report.critical)} blocking problem(s). "
                          f"First: {first}")
    state.approval = {"approved": True, "version_id": cur.version_id, "role": role,
                      "approved_at": now_iso()}
    state.stage = "APPROVED"
    state.add_decision("approve_final", role, comment=f"Approved {cur.version_id}")
    state.log("approved", f"{cur.version_id} approved by {role}")


def revoke_approval(state: ProjectState, role: str) -> None:
    if not state.approval.get("approved"):
        return
    state.approval = {"approved": False, "version_id": None, "role": None, "approved_at": None}
    state.stage = state.working_stage()
    state.add_decision("revoke_approval", role)
    state.log("approval_revoked", f"Approval revoked by {role}")


def set_reflection(state: ProjectState, text: str) -> None:
    state.reflection = _clean_text(text, 5000, "reflection")
    state.log("reflection", "Reflection updated")


def can_export(state: ProjectState) -> tuple[bool, list[str]]:
    reasons = []
    ap = state.approval
    if not ap.get("approved"):
        reasons.append("The final translation has not been approved by the human director yet.")
    elif ap.get("version_id") != state.current_version_id:
        reasons.append("The approved version is not the current version. Approve it again.")
    report = validate_current(state)
    reasons += [f"Blocking problem: {i.message}" for i in report.critical]
    return (not reasons, reasons)


# --------------------------------------------------------------------------- persistence


def save_state(state: ProjectState, path) -> None:
    """Atomic JSON write; refuses to save anything that looks like a key."""
    text = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
    hits = find_secrets(text)
    if hits:
        raise StudioError("Not saved: the project contains something that looks like an API key ("
                          + ", ".join(hits[:3]) + "). Remove it and try again.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_state(path_or_text) -> ProjectState:
    """Load from a path or JSON text with friendly errors."""
    text = path_or_text
    too_big = StudioError(f"The project file is too large (over {MAX_STATE_BYTES // (1024 * 1024)} MB) "
                          "to be a Game Localisation Studio project. Use an earlier saved copy.")
    if isinstance(text, bytes):
        if len(text) > MAX_STATE_BYTES:
            raise too_big
        text = text.decode("utf-8-sig", errors="replace")
    elif isinstance(text, Path) or (isinstance(text, str) and not text.lstrip().startswith("{")):
        try:
            if Path(text).stat().st_size > MAX_STATE_BYTES:
                raise too_big
            text = Path(text).read_text(encoding="utf-8-sig")
        except OSError:
            raise StudioError("The project file could not be found or opened.") from None
    if len(text) > MAX_STATE_BYTES:
        raise too_big
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise StudioError("The project file is damaged (not valid JSON). "
                          "Use an earlier saved copy.") from None
    if not isinstance(data, dict) or "challenge_id" not in data or "schema_version" not in data:
        raise StudioError("This file is not a Game Localisation Studio project.")
    if str(data["schema_version"]).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise StudioError(f"This project was saved by a different version of the studio "
                          f"(schema {data['schema_version']}); it cannot be opened here.")
    try:
        return ProjectState.from_dict(data)
    except (TypeError, KeyError, AttributeError, RecursionError):
        raise StudioError("The project file is incomplete or damaged.") from None
