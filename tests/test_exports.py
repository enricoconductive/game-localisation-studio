import json
import re

import pytest

from src import agents as a, exports as ex, project_state as ps, providers as p, validation as v
from conftest import FAKE_ANTHROPIC_KEY, FakeResponse, FakeSession, anthropic_body

XSS = ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>"]


@pytest.fixture
def approved(reviewed_state, replay, challenge):
    st = reviewed_state
    ps.decide_finding(st, "R1-01", "accept", "director", comment="warmer")
    ps.decide_finding(st, "R1-02", "reject", "director", comment="Kit stays calm")
    ps.decide_finding(st, "R1-03", "override", "director", human_text="The lantern master knows.")
    a.run_revision(st, replay, challenge)
    ps.set_reflection(st, "The baseline broke {player_name}; we fixed voices.")
    ps.approve_final(st, "director")
    return st


def test_export_blocked_without_approval(reviewed_state, challenge, manifest, tmp_path):
    before = reviewed_state.to_dict()
    res = ex.export_all(reviewed_state, challenge, manifest, tmp_path)
    assert all(not r.ok for r in res.values())
    assert "not been approved" in res["game_translation"].message
    assert list(tmp_path.iterdir()) == []
    assert reviewed_state.to_dict() == before


def test_export_blocked_with_critical(approved, challenge, manifest, tmp_path):
    cur = approved.current_version()
    cur.translations["demo.ui.start"] = "Start investigating now"   # bypass revoke on purpose
    r = ex.export_game_translation(approved, challenge, manifest, tmp_path)
    assert not r.ok and r["ok"] is False and r.path is None
    assert any(i["code"] == "too_long" for i in r.issues)
    assert not (tmp_path / "game_translation_en.json").exists()


def test_game_file_is_valid_and_preserves_approved_text(approved, challenge, manifest, tmp_path):
    res = ex.export_all(approved, challenge, manifest, tmp_path)
    assert all(r.ok for r in res.values()), {k: r.message for k, r in res.items()}
    text = (tmp_path / "game_translation_en.json").read_text(encoding="utf-8")
    obj = json.loads(text)
    assert v.validate_game_file(text, manifest, require_all_for_mission="demo").ok
    assert obj["strings"] == approved.current_version().translations
    assert obj["approved"] is True and obj["source"] == "replay" and obj["locale"] == "en-GB"
    assert obj["mission"] == "demo" and obj["characters"] == {"granny_wong": "Granny Wong", "kit": "Kit"}
    assert obj["generated_by"] == "Game Localisation Studio v0.3"
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", obj["generated_at"])
    assert approved.stage == "EXPORTED"


def test_agent_settings(approved, challenge, manifest, tmp_path):
    ex.export_all(approved, challenge, manifest, tmp_path)
    s = json.loads((tmp_path / "agent_settings.json").read_text(encoding="utf-8"))
    assert s["provider"]["translator_model"] == "replay"
    for role in ("translator", "reviewer"):
        assert s["agents"][role]["settings_text"] and s["agents"][role]["default_instructions"]
        assert s["prompts"][role]["initial"]["user"] and s["prompts"][role]["final"]["user"]
    assert s["prompts"]["reviewer"]["initial"]["round"] == 1
    assert s["revision"] == {"max_cycles": 1, "cycles_done": 1}
    assert s["glossary"][0]["target"] == "paper-craft" and s["simulated"] is True
    assert "instructor_notes" not in json.dumps(s) and "SECRET_INSTRUCTOR_NOTE" not in json.dumps(s)


def test_report_content(approved, challenge, manifest):
    html = ex.render_workflow_report(approved, challenge, manifest)
    assert ex.CSP in html and "<script" not in html.lower()
    assert "Replay notice" in html and "SIMULATED" in html
    assert "<svg" in html and all(step in html for step in ("BASELINE", "TRANSLATOR", "APPROVAL"))
    assert "Rejected — not applied" in html and "Overridden by human text" in html
    assert "Overrode reviewer" in html and "Agreed with reviewer" in html
    assert "Kit stays calm" in html and "The baseline broke {player_name}" in html
    rejected = approved.finding("R1-02").suggestion
    assert rejected not in approved.current_version().translations.values()
    assert "Prompt evolution" in html and "Live requests" in html


def test_report_escapes_xss(approved, challenge, manifest, tmp_path):
    st = approved
    ps.direct_edit(st, {"demo.line.kit_reply": XSS[0], "demo.line.granny_hint": XSS[1]}, "director",
                   comment=XSS[1])
    ps.decide_finding(st, "R1-02", "reject", "director", comment=XSS[0])
    ps.set_reflection(st, XSS[0] + XSS[1])
    st.team_name = XSS[1]
    st.agents["translator"]["instructions"] += "\n" + XSS[0]
    challenge = {**challenge, "title": XSS[0]}
    html = ex.render_workflow_report(st, challenge, manifest)
    low = html.lower()
    assert "<script" not in low and "<img" not in low and "onerror=alert(1)>" not in low
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_prompt_diff_html_escapes():
    out = ex.prompt_diff_html("a\n<b>old</b>\nc", "a\n<script>new</script>\nc")
    assert "<script" not in out and "&lt;script&gt;new&lt;/script&gt;" in out
    assert 'class="del"' in out and 'class="ins"' in out
    long_a = "\n".join(f"line {i}" for i in range(40))
    assert "unchanged" in ex.prompt_diff_html(long_a, long_a + "\nextra")


def test_live_only_project_has_no_replay_banner(challenge, manifest, provider_config):
    st = ps.new_project(challenge, "en-US", "live", "anthropic", "claude-haiku-5-5")

    def reply(batch):
        return FakeResponse(200, anthropic_body(json.dumps(
            {"translations": [{"id": i, "text": "Ok"} for i in batch]})))
    ids = st.string_ids()
    prov = p.make_provider("anthropic", FAKE_ANTHROPIC_KEY, provider_config,
                           session=FakeSession(reply(ids[:8]), reply(ids[8:])))
    a.run_translator(st, prov, challenge)
    html = ex.render_workflow_report(st, challenge, manifest)
    assert "Replay notice" not in html and ex.output_source(st) == "live"
    assert FAKE_ANTHROPIC_KEY not in html


def test_mixed_source(reviewed_state, challenge):
    prov = ScriptedLive()
    ps.decide_finding(reviewed_state, "R1-01", "accept", "director")
    a.run_revision(reviewed_state, prov, challenge)
    assert ex.output_source(reviewed_state) == "mixed"


class ScriptedLive(p.Provider):
    is_live = True

    def complete(self, system, user, *, model, max_tokens=1200, temperature=0.3, replay_key=None):
        return p.ModelResponse(json.dumps({"translations": [{"id": i, "text": "Live " + i}
                                                            for i in replay_key["string_ids"]]}),
                               model, 1, 1)


def test_custom_challenge_export(tmp_path):
    from src.importers import import_upload
    ch = import_upload("lines.txt", "你好\n再見 {player_name}\n".encode())
    st = ps.new_project(ch, "en", "live", "anthropic", "m")
    a.run_translator(st, ScriptedLive(), ch)
    ps.direct_edit(st, {"custom.text.002": "Bye {player_name}"}, "director")
    ps.approve_final(st, "director")
    r = ex.export_game_translation(st, ch, None, tmp_path)
    assert r.ok and r.path.endswith("custom_translation_en.json")
    obj = json.loads((tmp_path / "custom_translation_en.json").read_text(encoding="utf-8"))
    assert obj["mission"] == "custom" and obj["format"] == "lantern-mystery-translation"
