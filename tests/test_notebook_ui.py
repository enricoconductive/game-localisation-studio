"""Headless tests of the notebook UI (src/studio_ui.py).

The studio is built without a browser (ipywidgets works without a frontend) and driven
through its REAL buttons with ``.click()`` and by setting widget values, exactly as a
student would. No test touches the network.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

widgets = pytest.importorskip("ipywidgets")

from src import project_state as ps, providers, validation  # noqa: E402
from src import studio_ui, ui_compat  # noqa: E402
from src.studio_ui import Studio  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "tests" / "fixtures_synthetic"
REAL_FIXTURES = ROOT / "fixtures" / "replay_outputs.json"
FAKE_KEY = "sk-ant-api03-FAKEuiTESTkey1234567890abcdefXYZ"


def _real_fixtures():
    try:
        data = json.loads(REAL_FIXTURES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    intro = (data.get("challenges") or {}).get("intro") or {}
    return data if intro.get("translator_variants") or intro.get("translator") else None


needs_real = pytest.mark.skipif(_real_fixtures() is None,
                                reason="fixtures/replay_outputs.json (Replay team) not present yet")


def text_of(w) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(w.value)))


def make_studio(tmp_path, **kw) -> Studio:
    kw.setdefault("state_path", tmp_path / "studio_state.json")
    kw.setdefault("export_dir", tmp_path / "exports")
    kw.setdefault("colab", False)
    return Studio(**kw)


def valid_text(spec: dict, base: str) -> str:
    """A text that satisfies the string's placeholder and length constraints."""
    phs = " ".join(validation.normalise_placeholder(p) for p in spec.get("placeholders") or [])
    text = f"{base} {phs}".strip()
    max_len = spec.get("max_len")
    if max_len and len(text) > max_len:
        text = (base[: max(1, max_len - len(phs) - 1)].strip() + (" " + phs if phs else "")).strip()
    return text


def fix_critical_via_grid(studio: Studio) -> None:
    """Director fixes any remaining blocking problem by editing strings in the grid."""
    st = studio.state
    rep = ps.validate_current(st)
    bad = {i.string_id for i in rep.critical if i.string_id}
    if not bad:
        return
    spec = {s["id"]: s for s in st.strings}
    for sid in bad:
        studio._grid[sid].value = valid_text(spec[sid], "Fixed by director")
    studio.w["edit_comment"].value = "Fixed a technical problem"
    studio.w["btn_save_edits"].click()
    assert ps.validate_current(st).ok, studio.w["msg_director"].value


def all_html(studio: Studio) -> list[str]:
    return [w.value for w in studio.all_widgets() if isinstance(w, widgets.HTML)]


class MockLive(providers.Provider):
    """A 'live' provider: echoes the source (or a fixed text) as translations; scripted findings."""
    name = "anthropic"
    display_name = "Claude (Anthropic)"
    is_live = True

    def __init__(self, key=FAKE_KEY, fail=None, findings=None, text_fn=None):
        super().__init__(key, {})
        self.fail, self.findings, self.calls = fail, findings or [], []
        self.text_fn = text_fn or (lambda sid, user: f"EN {sid}")

    def complete(self, system, user, *, model, max_tokens=providers.DEFAULT_MAX_TOKENS, temperature=0.3,
                 replay_key=None):
        self.calls.append(replay_key)
        if self.usage_meter is not None:
            self.usage_meter.count_request()   # what a real provider does per HTTP attempt
        if self.fail is not None:
            raise self.fail
        key = replay_key or {}
        if key.get("stage") == "reviewer":
            body = {"findings": [f for f in self.findings if f["string_id"] in key["string_ids"]],
                    "overall_comment": "ok"}
        else:
            body = {"translations": [{"id": sid, "text": self.text_fn(sid, user), "note": ""}
                                     for sid in key.get("string_ids", [])]}
        return providers.ModelResponse(json.dumps(body), model, 100, 40, "live", False, "end_turn")

    def test_connection(self, model):
        return True, f"Connected with model '{model}'."


def connect_live(studio: Studio, prov) -> None:
    studio.use_provider(prov, "anthropic", "claude-haiku-5-5")


@pytest.fixture
def synthetic_root(tmp_path):
    """A tiny repo root built from tests/fixtures_synthetic (mission 'demo')."""
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "config", root / "config")
    (root / "game").mkdir(parents=True)
    shutil.copy(FX / "manifest.json", root / "game" / "strings_manifest.json")
    (root / "challenges").mkdir()
    shutil.copy(FX / "challenge.json", root / "challenges" / "demo.json")
    (root / "fixtures" / "checkpoints").mkdir(parents=True)
    return root


# =========================================================================== end to end


@needs_real
def test_intro_end_to_end_replay(tmp_path):
    s = make_studio(tmp_path)
    w = s.w
    # 1 connect Replay (the big button)
    w["btn_use_replay"].click()
    assert "Replay Mode is on" in text_of(w["msg_connect"])
    assert "REPLAY MODE" in w["status_html"].value
    # 2 choose intro
    w["mission"].value = "intro"
    w["locale"].value = "en-GB"
    w["team"].value = "Team Lantern"
    assert "開始調查" in w["source_table"].value
    w["btn_start"].click()
    assert s.state is not None and s.state.challenge_id == "intro", w["msg_mission"].value
    # 3 faithful preset
    w["preset_buttons"]["faithful"].click()
    assert s.state.agents["translator"]["preset"] == "faithful"
    assert w["t_settings"]["strategy"].value == 1
    # 4 baseline + translator (faithful) + translator (creative)
    w["btn_baseline"].click()
    w["btn_translator"].click()
    v_faithful = s.state.current_version()
    assert "Faithful" in v_faithful.label
    w["preset_buttons"]["creative"].click()
    w["btn_translator"].click()
    v_creative = s.state.current_version()
    assert "Creative" in v_creative.label and v_creative.version_id != v_faithful.version_id
    # compare the two runs
    w["cmp_a"].value, w["cmp_b"].value = v_faithful.version_id, v_creative.version_id
    w["btn_compare"].click()
    out = w["compare_out"].value
    differing = [sid for sid in s.state.string_ids()
                 if v_faithful.translations[sid] != v_creative.translations[sid]]
    assert differing
    assert f"{len(differing)} of 8 strings differ" in text_of(w["compare_out"])
    assert "changed" in out and "background:#fff8e1" in out
    assert 'class="diff"' in out and ('class="ins"' in out or 'class="del"' in out)  # prompt diff
    assert "What in the prompt caused these differences?" in text_of(w["compare_out"])
    assert html.escape(v_creative.translations[differing[0]]) in out
    # reviewer
    w["btn_reviewer"].click()
    findings = list(s.state.findings)
    assert len(findings) >= 4, w["msg_run"].value
    assert "Suggestion — you decide" in w["review_cards"].value
    s.section(5)
    spec = {x["id"]: x for x in s.state.strings}
    cards = s._finding_cards
    # accept one whose suggestion is technically valid, reject one, override one, edit one
    def ok_sugg(f):
        issues = validation.validate_string(f.string_id, f.suggestion,
                                            validation.StringSpec.from_dict(spec[f.string_id]))
        return all(i.severity != "CRITICAL" for i in issues)
    by_string: dict = {}
    for f in findings:
        by_string.setdefault(f.string_id, f)
    distinct = list(by_string.values())
    accept_f = next(f for f in distinct if ok_sugg(f))
    rest = [f for f in distinct if f is not accept_f]
    reject_f, override_f, edit_f = rest[0], rest[1], rest[2]
    override_text = valid_text(spec[override_f.string_id], "Director override wording")
    cards[accept_f.finding_id]["comment"].value = "Agree <b>fully</b>"
    cards[accept_f.finding_id]["btn_accept"].click()
    cards[reject_f.finding_id]["comment"].value = "This 'fix' breaks the voice"
    cards[reject_f.finding_id]["btn_reject"].click()
    cards[override_f.finding_id]["override"].value = override_text
    cards[override_f.finding_id]["comment"].value = "Neither version works; mine is closer"
    cards[override_f.finding_id]["btn_override"].click()
    cards[edit_f.finding_id]["edit"].value = valid_text(spec[edit_f.string_id], "Edited suggestion")
    cards[edit_f.finding_id]["btn_accept_edited"].click()
    dec = s.state.latest_decisions()
    assert dec[accept_f.finding_id].action == "accept" and dec[accept_f.finding_id].role == "AI Director"
    assert dec[reject_f.finding_id].action == "reject"
    assert dec[override_f.finding_id].action == "override" and not dec[override_f.finding_id].agrees_with_reviewer
    assert dec[edit_f.finding_id].action == "accept_edited"
    assert "Overrode" in text_of(w["decision_log"])
    # role switch is recorded
    w["role"].value = "Quality Evaluator"
    w["rule_kind"].value = "style"
    w["rule_text"].value = "Kit always calls Granny Wong 'Granny'."
    w["btn_rule"].click()
    assert s.state.memory_rules and s.state.memory_rules[0].role == "Quality Evaluator"
    # revision (only accepted strings are re-sent; human texts applied directly)
    w["role"].value = "AI Director"
    w["btn_revision"].click()
    rev = s.state.current_version()
    assert rev.kind == "revision", w["msg_director"].value
    assert rev.translations[override_f.string_id] == override_text
    assert rev.translations[accept_f.string_id] == accept_f.suggestion
    assert s.state.usage["requests"] == 0 and s.state.usage.get("simulated_requests", 0) > 0
    fix_critical_via_grid(s)
    # approve, then an edit revokes approval, then approve again
    w["btn_approve"].click()
    assert s.state.approval["approved"], w["msg_director"].value
    sid0 = s.state.string_ids()[2]
    s._grid[sid0].value = s._grid[sid0].value + " Indeed."
    w["btn_save_edits"].click()
    assert not s.state.approval["approved"]
    assert "Approval revoked" in text_of(w["msg_director"])
    w["btn_approve"].click()
    assert s.state.approval["approved"]
    # reflection + export all three
    reflection = "The agents <missed> the 'proverb' & we fixed it."
    w["reflection"].value = reflection
    w["btn_reflection"].click()
    w["btn_export_game"].click()
    w["btn_export_settings"].click()
    w["btn_export_report"].click()
    assert "saved to" in text_of(w["msg_export"]), w["msg_export"].value
    assert "Download progress" in text_of(w["msg_export"]) and "(1)" in text_of(w["msg_export"])
    exp = tmp_path / "exports"
    mission_dir = exp / "intro"                       # one folder per mission
    game, settings, report = (mission_dir / "game_translation_en.json",
                              mission_dir / "agent_settings.json", mission_dir / "workflow_report.html")
    assert game.exists() and settings.exists() and report.exists()
    manifest = validation.load_manifest()
    rep = validation.validate_game_file(game.read_text(encoding="utf-8"), manifest,
                                        require_all_for_mission="intro")
    assert rep.ok, rep.summary()
    gdata = json.loads(game.read_text(encoding="utf-8"))
    assert gdata["strings"][override_f.string_id] == override_text
    assert gdata["source"] == "replay"
    rtext = report.read_text(encoding="utf-8")
    assert html.escape(reflection) in rtext and "<missed>" not in rtext
    assert "Overrode reviewer" in rtext and "Agreed with reviewer" in rtext
    for p in (game, settings, report, tmp_path / "studio_state.json"):
        assert not providers.find_secrets(p.read_text(encoding="utf-8")), p
    assert all(s.progress_steps())
    # start the next mission keeps a copy of the finished project
    w["btn_next_mission"].click()
    assert s.state.challenge_id == "voice"
    assert list(exp.glob("finished_intro_*.json"))


def test_synthetic_end_to_end_with_plain_fixture(synthetic_root, tmp_path):
    """Old (pre-§15) fixture shape + synthetic manifest: whole flow through the buttons."""
    fx = json.loads((FX / "replay_outputs.json").read_text(encoding="utf-8"))
    s = make_studio(tmp_path, repo_root=synthetic_root, fixtures=fx)
    w = s.w
    w["btn_use_replay"].click()
    assert w["mission"].value == "demo"
    w["btn_start"].click()
    w["btn_baseline"].click()
    w["btn_translator"].click()
    w["btn_reviewer"].click()
    assert len(s.state.findings) == 3, w["msg_run"].value     # the unknown id is dropped
    f1, f2, f3 = s.state.findings
    s._finding_cards[f1.finding_id]["select"].value = True
    s._finding_cards[f2.finding_id]["select"].value = True
    w["bulk_comment"].value = "bulk ok"
    w["btn_bulk_accept"].click()
    s._finding_cards[f3.finding_id]["btn_reject"].click()
    w["btn_revision"].click()
    assert s.state.current_version().kind == "revision", w["msg_director"].value
    w["btn_review2"].click()
    fix_critical_via_grid(s)
    w["btn_approve"].click()
    assert s.state.approval["approved"], w["msg_director"].value
    w["btn_export_all"].click()
    game = tmp_path / "exports" / "demo" / "game_translation_en.json"
    assert game.exists(), w["msg_export"].value
    manifest = json.loads((FX / "manifest.json").read_text(encoding="utf-8"))
    assert validation.validate_game_file(game.read_text(encoding="utf-8"), manifest,
                                         require_all_for_mission="demo").ok


# =========================================================================== focused tests


@needs_real
def test_replay_edited_prompt_notice(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["preset_buttons"]["faithful"].click()
    assert "Prepared output" in text_of(s.w["replay_notice"])
    assert "cannot generate" not in text_of(s.w["replay_notice"])
    s.w["t_instructions"].value = s.w["t_instructions"].value + "\n- Make Granny sound grumpy."
    assert s.state.agents["translator"]["edited"] is True
    notice = text_of(s.w["replay_notice"])
    assert "Faithful" in notice and "Replay Mode cannot generate a new response" in notice
    s.w["btn_translator"].click()
    v = s.state.current_version()
    assert "Faithful" in v.label and "Replay Mode cannot generate" in text_of(s.w["msg_run"])
    # the edited instructions are what the prompt preview (and snapshot) contain
    s.w["preview_step"].value = "translator"
    s.w["btn_preview"].click()
    assert "Make Granny sound grumpy." in s.w["preview_user"].value
    assert "Temperature" in text_of(s.w["preview_info"])


@needs_real
def test_export_blocked_before_approval_keeps_work(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["btn_translator"].click()
    s.w["btn_export_game"].click()
    msg = text_of(s.w["msg_export"])
    assert "Export blocked" in msg and "not been approved" in msg and "How to fix" in msg
    assert not list((tmp_path / "exports").rglob("game_translation_en.json"))
    assert s.state.current_version() is not None
    assert s.w["btn_export_game"].disabled is False


@needs_real
def test_restore_and_history_compare(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["preset_buttons"]["faithful"].click()
    s.w["btn_translator"].click()
    first = s.state.current_version()
    s.w["preset_buttons"]["creative"].click()
    s.w["btn_translator"].click()
    s.w["hist_pick"].value = first.version_id
    s.w["btn_hist_compare"].click()
    assert "strings differ" in text_of(s.w["hist_compare_out"])
    s.w["btn_restore"].click()
    cur = s.state.current_version()
    assert cur.kind == "restored" and cur.translations == first.translations
    assert any(d.action == "restore_version" for d in s.state.decisions)


@needs_real
def test_resume_from_saved_state_and_file(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["preset_buttons"]["faithful"].click()
    s.w["btn_translator"].click()
    s.w["btn_reviewer"].click()
    f = s.state.findings[0]
    s._finding_cards[f.finding_id]["btn_reject"].click()
    s.w["role"].value = "Quality Evaluator"
    saved = tmp_path / "studio_state.json"
    assert saved.exists() and s.autosaved_at
    ids = [v.version_id for v in s.state.versions]
    # a new session finds the saved file and offers to resume
    s2 = make_studio(tmp_path)
    s2.connect_replay()
    s2.refresh()
    assert s2.w["resume_row"].layout.display != "none"
    s2.w["btn_resume"].click()
    assert [v.version_id for v in s2.state.versions] == ids, s2.w["msg_welcome"].value
    assert len(s2.state.decisions) == len(s.state.decisions)
    assert s2.role == "Quality Evaluator"
    assert s2._version_variant(s2.state.current_version()) == "faithful"
    assert s2.w["t_settings"]["strategy"].value == 1
    # resume from an uploaded progress file (ipywidgets 8 value shape)
    s.w["btn_status_download"].click()
    prog = next((tmp_path / "exports").glob("studio_progress_intro_*.json"))
    s3 = make_studio(tmp_path / "other")
    s3.connect_replay()
    s3.w["resume_upload"].value = ({"name": prog.name, "type": "application/json",
                                    "size": prog.stat().st_size, "content": memoryview(prog.read_bytes()),
                                    "last_modified": datetime.now(timezone.utc)},)
    s3.w["btn_resume_file"].click()
    assert [v.version_id for v in s3.state.versions] == ids, s3.w["msg_stuck"].value
    # a damaged file gives a friendly message and keeps the current work
    s3.w["resume_upload"].value = ({"name": "bad.json", "type": "application/json", "size": 3,
                                    "content": memoryview(b"{x"), "last_modified": datetime.now(timezone.utc)},)
    s3.w["btn_resume_file"].click()
    assert "damaged" in text_of(s3.w["msg_stuck"]) or "not a Game" in text_of(s3.w["msg_stuck"])
    assert [v.version_id for v in s3.state.versions] == ids


@needs_real
def test_catch_up_checkpoint_loads(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["btn_baseline"].click()
    s.w["btn_translator"].click()
    cp_dir = tmp_path / "checkpoints"
    cp_dir.mkdir()
    data = json.loads(s._state_text())
    data["ui_extras"]["checkpoint_label"] = "Intro · after the translator"
    (cp_dir / "intro_after_translator.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    s2 = make_studio(tmp_path / "late", checkpoints_dir=cp_dir)
    s2.connect_replay()
    labels = [lab for lab, _ in s2.w["checkpoint"].options]
    assert "Intro · after the translator" in labels
    s2.w["checkpoint"].value = str(cp_dir / "intro_after_translator.json")
    s2.w["btn_checkpoint"].click()
    assert s2.state and len(s2.state.versions) == 2, s2.w["msg_stuck"].value
    assert "Loaded the catch-up checkpoint" in text_of(s2.w["msg_stuck"])


def test_real_checkpoints_load_if_present(tmp_path):
    files = sorted((ROOT / "fixtures" / "checkpoints").glob("*.json"))
    if not files:
        pytest.skip("no fixtures/checkpoints/*.json yet (Replay team)")
    s = make_studio(tmp_path)
    assert [lab for lab, _ in s.w["checkpoint"].options] == [
        "Catch up: agents already run (Mission 1)", "Catch up: review done (Mission 1)",
        "Catch up: revision done (Mission 1)"]
    for p in files:
        s.w["checkpoint"].value = str(p)
        s.w["btn_checkpoint"].click()
        assert "Loaded the catch-up checkpoint" in text_of(s.w["msg_stuck"]), (p, s.w["msg_stuck"].value)
        s.section(4), s.section(5), s.section(6)


def test_custom_upload_html_is_escaped(tmp_path):
    evil = "<script>alert(1)</script>\n你好 <img src=x onerror=alert(2)>\n第三句\n"
    s = make_studio(tmp_path)
    prov = MockLive(text_fn=lambda sid, user: "<script>alert('model')</script> ok",
                    findings=[{"string_id": "custom.text.001", "category": "accuracy", "severity": "major",
                               "issue": "<img src=x onerror=alert(3)>", "reasoning": "<b>bold</b>",
                               "suggestion": "<script>steal()</script>"}])
    connect_live(s, prov)
    s.w["upload"].value = ({"name": "evil.txt", "type": "text/plain", "size": len(evil.encode()),
                            "content": memoryview(evil.encode("utf-8")),
                            "last_modified": datetime.now(timezone.utc)},)
    s.w["btn_use_upload"].click()
    assert s.w["mission"].value == "custom", s.w["msg_mission"].value
    assert "cannot be played in the game" in text_of(s.w["msg_mission"])
    s.w["btn_start"].click()
    s.w["btn_baseline"].click()
    s.w["btn_translator"].click()
    s.w["btn_reviewer"].click()
    assert s.state.findings, s.w["msg_run"].value
    s.section(5), s.section(6)
    values = all_html(s)
    joined = "\n".join(values).lower()
    assert "<script" not in joined and "<img" not in joined
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in "\n".join(values)
    # raw text goes into Textareas unchanged (it is never rendered as HTML there)
    assert any("<script>steal()</script>" == c["edit"].value for c in s._finding_cards.values())


def test_provider_error_is_friendly_and_buttons_recover(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    connect_live(s, MockLive(fail=providers._error("rate_limit", "Claude (Anthropic)")))
    s.w["btn_baseline"].click()
    msg = text_of(s.w["msg_run"])
    assert "many classmates" in msg and "Replay" in msg
    assert s.w["btn_baseline"].disabled is False
    assert s.state.versions == []
    assert s.state.usage["requests"] == 1 == s.meter.requests   # a failed attempt still counts
    # an unexpected exception: short message, work saved, key masked in the details
    connect_live(s, MockLive(fail=RuntimeError(f"boom {FAKE_KEY}")))
    s.w["btn_translator"].click()
    raw = s.w["msg_run"].value
    assert "Your work is saved" in raw and FAKE_KEY not in raw and "<details>" in raw
    assert s.w["btn_translator"].disabled is False


def test_request_counter_counts_only_live_calls(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["btn_baseline"].click()
    assert s.state.usage["requests"] == 0
    assert s.state.usage.get("simulated_requests", 0) >= 1 or not _real_fixtures()
    assert "Replay:" in s.w["est_translator"].value
    prov = MockLive()
    connect_live(s, prov)
    s.refresh()
    assert "This will make <b>1</b> request(s)" in s.w["est_translator"].value
    s.w["btn_translator"].click()
    assert s.state.usage["requests"] == 1 and len(prov.calls) == 1, s.w["msg_run"].value
    assert "1 / 40" in text_of(s.w["status_html"]) and "LIVE" in s.w["status_html"].value
    assert "Translator · Live · Balanced preset" in s.state.current_version().label


def test_live_key_never_stored_or_shown(tmp_path):
    class UD:
        def get(self, name):
            assert name == "ANTHROPIC_API_KEY"
            return FAKE_KEY

    made = {}

    def factory(name, key, cfg, meter):
        made["p"] = MockLive(key=key)
        return made["p"]

    s = make_studio(tmp_path, provider_factory=factory, userdata=UD())
    s.w["provider"].value = "anthropic"
    assert "ANTHROPIC_API_KEY" in s.w["key_help"].value
    s.w["btn_load_key"].click()
    assert "Key loaded" in text_of(s.w["msg_connect"]), s.w["msg_connect"].value
    s.w["btn_test"].click()
    assert "✅" in s.w["connect_state"].value
    s.w["btn_start"].click()
    s.w["btn_baseline"].click()
    s.w["btn_translator"].click()
    assert s.state.mode == "live" and s.state.usage["requests"] == 2
    s.w["btn_status_download"].click()
    for p in [tmp_path / "studio_state.json", *(tmp_path / "exports").glob("*.json")]:
        assert FAKE_KEY not in p.read_text(encoding="utf-8")
    assert all(FAKE_KEY not in v for v in all_html(s))
    assert FAKE_KEY not in json.dumps(s.extras) and not hasattr(s, "api_key")
    assert FAKE_KEY not in repr(s.provider)


def test_key_box_fallback_when_no_secret(tmp_path):
    class NoSecrets:
        def get(self, name):
            raise RuntimeError("SecretNotFoundError")

    made = []
    s = make_studio(tmp_path, userdata=NoSecrets(),
                    provider_factory=lambda n, k, c, m: made.append(MockLive(key=k)) or made[-1])
    s.w["provider"].value = "anthropic"
    s.w["btn_load_key"].click()
    assert "ANTHROPIC_API_KEY" in text_of(s.w["msg_connect"]) and s.provider is None
    assert s.w["key_box"].layout.display != "none"
    s.w["key_box"].value = FAKE_KEY
    s.w["btn_load_key"].click()
    assert s.provider is made[0] and s.w["key_box"].value == ""
    assert s.w["key_box"].layout.display == "none"
    assert all(FAKE_KEY not in v for v in all_html(s))


def test_hkbu_key_help_follows_the_verified_flag(tmp_path):
    s = make_studio(tmp_path)
    s.w["provider"].value = "hkbu"
    assert "configured by your instructor — not yet verified" in text_of(s.w["key_help"])
    s.provider_config["hkbu"]["verified"] = True
    s._refresh_key_help()
    assert "configured by your instructor" in text_of(s.w["key_help"])
    assert "not yet verified" not in text_of(s.w["key_help"])


@needs_real
def test_replay_locale_note_and_download_reminder(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["locale"].value = "en-US"
    s.w["btn_start"].click()
    note = studio_ui.REPLAY_LOCALE_NOTE
    assert note in text_of(s.w["msg_mission"]) and note in text_of(s.w["replay_notice"])
    s.w["btn_translator"].click()
    assert note in text_of(s.w["results_table"])
    fix_critical_via_grid(s)
    s.w["btn_approve"].click()
    assert s.state.approval["approved"] and "Download progress" in text_of(s.w["msg_director"])
    s2 = make_studio(tmp_path / "gb")
    s2.connect_replay()
    s2.w["btn_start"].click()
    s2.w["btn_translator"].click()
    assert note not in text_of(s2.w["results_table"]) + text_of(s2.w["replay_notice"])


def test_mission_titles_match_the_game(tmp_path):
    s = make_studio(tmp_path)
    labels = dict((v, lab) for lab, v in s.w["mission"].options)
    for n, m in enumerate(s.manifest["missions"], 1):
        assert labels[m["id"]].startswith(f"Mission {n} — {m['title_en']} ("), labels[m["id"]]


def test_hkbu_not_configured_is_friendly(tmp_path):
    s = make_studio(tmp_path)
    s.provider_config["hkbu"]["base_url"] = ""
    s.catalog["hkbu"]["models"] = []
    s.w["provider"].value = "hkbu"
    labels = [lab for lab, _ in s.w["model"].options]
    assert any("configured by your instructor — not yet verified" in lab for lab in labels)
    assert "not set up for this course yet" in text_of(s.w["msg_connect"])
    s.w["btn_load_key"].click()
    assert "not set up for this course yet" in text_of(s.w["msg_connect"])
    assert s.provider is None and s.w["btn_load_key"].disabled is False
    s.w["provider"].value = "huggingface"
    assert any("not yet verified" in lab for lab, _ in s.w["model"].options)


def test_hkbu_configured_lists_models(tmp_path):
    s = make_studio(tmp_path)
    s.w["provider"].value = "hkbu"
    assert s.w["model"].value == s.catalog["hkbu"]["default"]
    assert all("not yet verified" in lab for lab, _ in s.w["model"].options)
    assert "Load my key" in text_of(s.w["msg_connect"])


@needs_real
def test_start_mission_warns_before_overwriting(tmp_path):
    s = make_studio(tmp_path)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["btn_translator"].click()
    first = s.state
    s.w["btn_start"].click()
    assert s.state is first and "Are you sure" in text_of(s.w["msg_mission"])
    assert s.w["start_confirm"].layout.display != "none"
    s.w["btn_start_confirm"].click()
    assert s.state is not first and not s.state.versions
    assert list((tmp_path / "exports").glob("backup_intro_*.json"))
    # reset (with confirmation) also keeps a backup
    s.w["btn_translator"].click()
    s.w["btn_reset"].click()
    assert s.state.versions
    s.w["btn_reset_confirm"].click()
    assert not s.state.versions


def test_uploaded_files_both_ipywidgets_shapes():
    v7 = {"a.txt": {"content": b"hello", "metadata": {"name": "a.txt", "size": 5}}}
    v8 = ({"name": "b.csv", "content": memoryview(b"x,y"), "size": 3},)
    assert ui_compat.uploaded_files(v7) == [("a.txt", b"hello")]
    assert ui_compat.uploaded_files(v8) == [("b.csv", b"x,y")]
    assert ui_compat.uploaded_files(()) == [] and ui_compat.uploaded_files({}) == []


def test_sections_render_without_project(tmp_path):
    s = make_studio(tmp_path)
    for n in range(1, 7):
        box = s.section(n)
        assert isinstance(box, widgets.VBox) and box.children[0] is s.w["status_bar"]
    assert isinstance(s.stuck(), widgets.VBox)
    s.w["btn_baseline"].click()
    assert "Start a mission first" in text_of(s.w["msg_run"])
    with pytest.raises(ps.StudioError):
        s.section(9)
    assert studio_ui.GAME_URL.startswith("https://")
    assert "Approve in Section 5 first." in text_of(s.w["play_link"]) and "href" not in s.w["play_link"].value


# =========================================================================== session request cap


def test_session_meter_survives_key_reload_mission_change_and_load(tmp_path):
    """One request counter per session: reloading the key, switching provider or mission,
    resetting or loading a project never resets it; retries count; Replay never counts."""
    from conftest import FakeResponse, anthropic_body, error_body

    class UD:
        def get(self, name):
            return FAKE_KEY

    class Session:
        def __init__(self):
            self.n = 0

        def post(self, url, headers=None, json=None, params=None, timeout=None):
            self.n += 1
            if self.n == 1:   # the first attempt is rate-limited, then retried
                return FakeResponse(429, error_body("rate_limit_error", "slow down"))
            return FakeResponse(200, anthropic_body("OK"))

    session = Session()
    meters = []

    def factory(name, key, cfg, meter):
        meters.append(meter)
        return providers.make_provider(name, key, cfg, meter, session=session, sleep=lambda s: None)

    s = make_studio(tmp_path, provider_factory=factory, userdata=UD())
    s.w["provider"].value = "anthropic"
    s.w["btn_load_key"].click()
    s.w["btn_test"].click()
    assert "✅" in s.w["connect_state"].value, s.w["msg_connect"].value
    assert s.meter.requests == 2 == session.n                       # the retry was counted
    s.w["btn_load_key"].click()                                     # "Load my key" again
    assert meters[0] is meters[1] is s.meter and s.meter.requests == 2
    s.w["btn_start"].click()
    s.connect_replay()                                              # Replay never counts
    s.w["btn_baseline"].click()
    assert s.meter.requests == 2
    s.w["provider"].value = "anthropic"
    s.w["btn_load_key"].click()
    s.w["btn_test"].click()
    assert s.meter.requests == 3
    s.w["mission"].value = "voice"
    s.w["btn_start"].click()
    if s.w["start_confirm"].layout.display != "none":
        s.w["btn_start_confirm"].click()
    assert s.state.mission == "voice" and s.meter.requests == 3      # mission change
    s._reset_mission(confirmed=True)
    assert s.meter.requests == 3                                    # reset
    s.resume_from_bytes(json.dumps(s.state.to_dict()).encode())
    assert s.meter.requests == 3                                    # load a project
    assert "Live requests this session: 3 / 40" in text_of(s.w["status_html"])
    s.meter.requests = 40
    s.w["btn_translator"].click()
    assert "all 40 live requests" in text_of(s.w["msg_run"]) and session.n == 3


def test_review_messages_distinguish_dropped_skipped_and_clean(tmp_path):
    class Reviewer(MockLive):
        mode = "unknown_ids"

        def complete(self, system, user, *, model, max_tokens=providers.DEFAULT_MAX_TOKENS, temperature=0.3,
                     replay_key=None):
            key = replay_key or {}
            if key.get("stage") != "reviewer":
                return super().complete(system, user, model=model, replay_key=replay_key)
            ids = key["string_ids"]
            if self.mode == "unknown_ids":
                findings = [{"string_id": sid.upper(), "category": "accuracy", "severity": "major",
                             "issue": "Wrong"} for sid in ids]
            elif self.mode == "odd_category":
                findings = [{"string_id": ids[0], "category": "vibes", "severity": "huge",
                             "issue": "Flat", "suggestion": "Better"}]
            else:
                findings = []
            return providers.ModelResponse(json.dumps({"findings": findings}), model, 1, 1,
                                           "live", False, "end_turn")

    s = make_studio(tmp_path)
    prov = Reviewer()
    connect_live(s, prov)
    s.w["btn_start"].click()
    s.w["btn_translator"].click()
    s.w["btn_reviewer"].click()
    msg = text_of(s.w["msg_run"])
    assert "none could be used" in msg and "does NOT mean the translation is fine" in msg
    assert "dropped because they named an unknown string id" in msg
    prov.mode = "odd_category"
    s.w["btn_reviewer"].click()                    # the same strings are reviewed again
    msg = text_of(s.w["msg_run"])
    assert "made 1 suggestion" in msg and "unknown category or severity" in msg
    assert "category 'vibes' → accuracy" in msg
    s.w["btn_reviewer"].click()
    assert "Review skipped: no string has changed since the last review" in text_of(s.w["msg_run"])
    prov.mode = "clean"
    first = s.state.string_ids()[0]
    s._grid[first].value = "Investigate"
    s.w["btn_save_edits"].click()
    s.w["btn_reviewer"].click()
    assert "checked 1 string(s) and found no problems" in text_of(s.w["msg_run"])


# =========================================================================== Colab: downloads, theme, layout


def plain(w) -> str:
    """Text of an HTML widget with tags removed (no extra spaces around bold words)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(w.value)))


def fake_colab_files(monkeypatch, fail=False):
    """A stand-in for ``google.colab.files`` that records whether ``download`` ran inside an
    ``ipywidgets.Output`` context (in Colab a button callback has no other output context)."""
    import sys
    import types
    depth, calls = {"n": 0}, []
    enter, exit_ = widgets.Output.__enter__, widgets.Output.__exit__

    def counting_enter(self):
        depth["n"] += 1
        return enter(self)

    def counting_exit(self, *exc):
        depth["n"] -= 1
        return exit_(self, *exc)

    def download(path):
        calls.append((Path(path), depth["n"]))
        if fail:
            raise RuntimeError("no output context")

    monkeypatch.setattr(widgets.Output, "__enter__", counting_enter)
    monkeypatch.setattr(widgets.Output, "__exit__", counting_exit)
    colab = types.ModuleType("google.colab")
    colab.files = types.SimpleNamespace(download=download)
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    return calls


def test_colab_progress_download_runs_inside_an_output_widget(tmp_path, monkeypatch):
    calls = fake_colab_files(monkeypatch)
    s = make_studio(tmp_path, colab=True)
    s.connect_replay()
    s.w["btn_start"].click()
    # displayed exactly once (the welcome box), never in the status bar shown by every section
    assert s.w["download_out"] not in s.w["status_bar"].children
    assert s.w["download_out"] in s.welcome().children
    assert s.w["download_out_stuck"] in s.w["stuck_box"].children
    s.w["btn_status_download"].click()
    (path, depth), = calls
    assert depth >= 1 and path.name.startswith("studio_progress_intro_") and path.exists()
    msg = plain(s.w["msg_status"])
    assert "download started" in msg
    assert ("If nothing downloads: open the Files panel (📁 folder icon on the left) → exports → ⋮ "
            f"next to {path.name} → Download.") in msg
    s.w["btn_stuck_download"].click()
    assert len(calls) == 2 and calls[1][1] >= 1 and "download started" in text_of(s.w["msg_stuck"])
    joined = "\n".join(all_html(s))
    assert "data:" not in joined and "click here" not in joined


def test_colab_download_failure_never_claims_started(tmp_path, monkeypatch):
    calls = fake_colab_files(monkeypatch, fail=True)
    s = make_studio(tmp_path, colab=True)
    s.connect_replay()
    s.w["btn_start"].click()
    s.w["btn_status_download"].click()
    assert len(calls) == 1
    msg = plain(s.w["msg_status"])
    assert "download started" not in msg and "Traceback" not in msg
    assert "— use the Files panel to download it: open the Files panel (📁 folder icon on the left) → exports" in msg
    assert not s.w["download_out"].outputs          # the error was caught, not shown as a traceback
    # outside Colab nothing is downloaded and nothing is promised
    s2 = make_studio(tmp_path / "local")
    s2.connect_replay()
    s2.w["btn_start"].click()
    s2.w["btn_status_download"].click()
    local = plain(s2.w["msg_status"])
    assert len(calls) == 1 and "download started" not in local and "Files panel" not in local


def test_colab_exports_download_inside_the_export_output(synthetic_root, tmp_path, monkeypatch):
    calls = fake_colab_files(monkeypatch)
    fx = json.loads((FX / "replay_outputs.json").read_text(encoding="utf-8"))
    s = make_studio(tmp_path, repo_root=synthetic_root, fixtures=fx, colab=True)
    w = s.w
    w["btn_use_replay"].click()
    w["btn_start"].click()
    w["btn_translator"].click()
    fix_critical_via_grid(s)
    w["btn_approve"].click()
    assert s.state.approval["approved"], w["msg_director"].value
    # one Output per file, each shown once (a shared Output re-ran earlier downloads in Colab)
    outs = [w[f"download_out_{k}"] for k in ("game_translation", "agent_settings", "workflow_report")]
    assert all(o in s.w["sections"][6].children for o in outs) and len(set(map(id, outs))) == 3
    w["btn_export_all"].click()
    assert [p.name for p, _ in calls] == ["game_translation_en.json", "agent_settings.json",
                                          "workflow_report.html"], w["msg_export"].value
    assert all(d >= 1 for _, d in calls)
    msg = plain(w["msg_export"])
    assert msg.count("download started") == 3
    assert ("If nothing downloads: open the Files panel (📁 folder icon on the left) → exports → demo → ⋮ "
            "next to the file → Download.") in msg
    assert "data:" not in w["msg_export"].value


def test_sections_are_light_cards_and_style_is_in_every_output(tmp_path):
    s = make_studio(tmp_path)
    assert "<style>" in s.w["style"].value and ".studio-card" in s.w["style"].value
    assert s.w["style"] in s.w["status_bar"].children and s.w["style"] in s.welcome().children
    for root in [s.section(n) for n in range(1, 7)] + [s.stuck(), s.welcome()]:
        assert "studio-card" in root._dom_classes


def scroll_parents(studio) -> dict:
    """id(widget) → max_height of the bounded scroll box that holds it."""
    out = {}
    for w in studio.all_widgets():
        if "studio-scroll" in getattr(w, "_dom_classes", ()):
            for c in w.children:
                out[id(c)] = w.layout.max_height
    return out


def test_long_outputs_are_bounded_and_secondary_panels_collapsed(tmp_path):
    s = make_studio(tmp_path)
    bounded = scroll_parents(s)
    for key in ("source_table", "results_table", "compare_out", "review_cards", "validation_summary",
                "findings_box", "edit_grid", "decision_log", "history_table", "summary_table",
                "summary_findings", "prompt_evolution"):
        h = bounded.get(id(s.w[key]))
        assert h and int(h.rstrip("px")) <= 420, key
    assert s.w["preview_acc"].layout.display == "none"
    # no widgets.Tab / widgets.Accordion anywhere: Colab (ipywidgets 7.7.1) does not render them
    assert not [x for x in s.all_widgets() if isinstance(x, (widgets.Tab, widgets.Accordion))]
    assert s.w["context_acc"].selected_index is None and s.w["upload_acc"].selected_index is None
    sec4 = s.w["sections"][4].children
    assert sec4.index(s.w["msg_run"]) < sec4.index(s.w["run_tabs"])      # buttons → message → results
    sec5 = s.w["sections"][5].children
    assert sec5.index(s.w["director_tabs"]) + 1 == sec5.index(s.w["msg_director"])


def test_replay_button_and_role_selection_are_obvious(tmp_path):
    s = make_studio(tmp_path)
    b = s.w["btn_status_replay"]
    assert b.description == "Switch to Replay" and not b.disabled
    s.connect_replay()
    s.refresh()
    assert b.description == "✓ Replay Mode on" and b.disabled and b.button_style == ""
    b.click()                                      # nothing happens, and it stays disabled
    assert b.disabled
    connect_live(s, MockLive())
    s.refresh()
    assert b.description == "Switch to Replay" and not b.disabled and b.button_style == "warning"
    role = s.w["role"]
    assert [lab for lab, _ in role.options] == ["✓ AI Director", "Quality Evaluator"]
    role.value = "Quality Evaluator"
    assert s.role == "Quality Evaluator" and role.value == "Quality Evaluator"
    assert [lab for lab, _ in role.options] == ["AI Director", "✓ Quality Evaluator"]


# =========================================================================== v0.3 UX: play link, short text, tabs


def play_payload(studio: Studio):
    """The game file carried by the Section 6 play link (None when the link is hidden)."""
    import base64
    m = re.search(r'href="([^"]+)"', studio.w["play_link"].value)
    if m is None:
        return None
    url = html.unescape(m.group(1))
    assert url.startswith(studio_ui.GAME_URL + "#t=")
    payload = url.split("#t=", 1)[1]
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    return json.loads(raw.decode("utf-8"))


def test_play_link_only_for_the_approved_translation(synthetic_root, tmp_path):
    fx = json.loads((FX / "replay_outputs.json").read_text(encoding="utf-8"))
    s = make_studio(tmp_path, repo_root=synthetic_root, fixtures=fx)
    w = s.w
    w["btn_use_replay"].click()
    w["btn_start"].click()
    w["btn_translator"].click()
    fix_critical_via_grid(s)
    assert play_payload(s) is None and "Approve in Section 5 first." in text_of(w["play_link"])
    sec6 = list(w["sections"][6].children)
    assert sec6.index(w["play_link"]) < sec6.index(w["msg_export"])          # link above the exports
    w["btn_approve"].click()
    assert s.state.approval["approved"], w["msg_director"].value
    link = w["play_link"].value
    assert studio_ui.PLAY_TEXT in html.unescape(link)
    assert 'target="_blank"' in link and 'rel="noopener"' in link
    game = play_payload(s)
    expected, report = studio_ui.exports.build_game_translation(s.state, s.challenge, s.manifest)
    assert not report.critical and game["approved"] is True
    assert {k: v for k, v in game.items() if k != "generated_at"} == \
        {k: v for k, v in expected.items() if k != "generated_at"}
    w["btn_export_game"].click()
    exported = json.loads((tmp_path / "exports" / "demo" / "game_translation_en.json").read_text("utf-8"))
    assert game["strings"] == exported["strings"] and game["mission"] == exported["mission"] == "demo"
    # an edit revokes approval, and the link disappears with it
    sid = s.state.string_ids()[0]
    s._grid[sid].value = s._grid[sid].value + "!"
    w["btn_save_edits"].click()
    assert not s.state.approval["approved"]
    assert play_payload(s) is None and "Approve in Section 5 first." in text_of(w["play_link"])


def _notebook_markdown():
    nb = json.loads((ROOT / "notebooks" / "Game_Localisation_Studio.ipynb").read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown"]


def test_notebook_text_stays_short():
    cells = _notebook_markdown()
    assert len(cells[0].split()) <= 110, "intro cell is too long"
    sections = [c for c in cells if re.search(r"^## \d · ", c, re.M)]
    assert len(sections) == 6
    for c in sections:
        assert len(c.split()) <= 60, c[:60]


def test_section5_tabs_in_order_with_history_below(tmp_path):
    s = make_studio(tmp_path)
    tabs = s.w["director_tabs"]
    assert [lab for lab, _ in tabs._bar.options] == [
        "a · Decide", "b · Rules", "c · Revise", "d · Final edits", "e · Approve"]
    revise = tabs._bodies[2]
    assert s.w["btn_review2"] in list(studio_ui.iter_widgets(revise))
    assert s.w["btn_approve"] in list(studio_ui.iter_widgets(tabs._bodies[4]))
    hist = s.w["history_acc"]
    assert isinstance(hist, studio_ui._Accordion) and hist._titles == ["History — versions and decision log"]
    assert hist.selected_index is None                                   # collapsed by default
    inside = list(studio_ui.iter_widgets(hist))
    for key in ("hist_pick", "btn_hist_compare", "btn_restore", "history_table", "decision_log"):
        assert s.w[key] in inside, key
    sec5 = list(s.w["sections"][5].children)
    assert sec5.index(tabs) < sec5.index(s.w["msg_director"]) < sec5.index(hist)


def test_labelled_inputs_share_one_label_width(tmp_path):
    s = make_studio(tmp_path)
    kinds = (widgets.Dropdown, widgets.Text, widgets.Textarea, widgets.Password, widgets.ToggleButtons)
    labelled = [x for x in s.all_widgets() if isinstance(x, kinds) and x.description
                and not isinstance(getattr(x, "parent", None), studio_ui._Tabs)]
    assert len(labelled) >= 15
    for x in labelled:
        if x is s.w["director_tabs"]._bar or x is s.w["run_tabs"]._bar:
            continue
        assert x.style.description_width == studio_ui.LABEL_W, x.description
