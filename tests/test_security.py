"""Secrets never leave the provider; exports refuse anything key-like; Replay is offline."""
import json
from pathlib import Path

import pytest

from src import agents as a, exports as ex, project_state as ps, providers as p
from conftest import FAKE_ANTHROPIC_KEY, FAKE_HF_TOKEN, FakeResponse, FakeSession, anthropic_body

ROOT = Path(__file__).resolve().parent.parent
PLANTS = [FAKE_ANTHROPIC_KEY, FAKE_HF_TOKEN, "Bearer abcDEF1234567890ghiJKL",
          '"api_key": "a1b2c3d4e5f6a7b8c9d0e1f2"', "sk-proj-ABCDEFGHIJ1234567890klmnop"]


@pytest.mark.parametrize("planted", PLANTS)
def test_scan_detects_planted_keys(planted):
    hits = ex.scan_for_secrets(f"some text {planted} more")
    assert hits and all(planted not in h for h in hits)


def test_scan_no_false_positives_on_clean_files():
    for rel in ("config/providers.json", "config/models.json", "docs/CONTRACTS.md"):
        assert ex.scan_for_secrets((ROOT / rel).read_text(encoding="utf-8")) == [], rel
    assert ex.scan_for_secrets('"input_tokens": 1234, "secret_name": "ANTHROPIC_API_KEY"') == []
    assert ex.scan_for_secrets("plain words", extra_secrets=["mysecretvalue"]) == []
    assert ex.scan_for_secrets("x mysecretvalue y", extra_secrets=["mysecretvalue"])


@pytest.fixture
def approved(reviewed_state):
    ps.approve_final(reviewed_state, "director")
    return reviewed_state


def test_key_in_translation_blocks_game_export(approved, challenge, manifest, tmp_path):
    approved.current_version().translations["demo.line.kit_reply"] = FAKE_ANTHROPIC_KEY
    r = ex.export_game_translation(approved, challenge, manifest, tmp_path)
    assert not r.ok and "API key" in r.message and FAKE_ANTHROPIC_KEY not in r.message
    assert list(tmp_path.iterdir()) == []


def test_key_in_reflection_blocks_report(approved, challenge, manifest, tmp_path):
    approved.reflection = f"oops {FAKE_HF_TOKEN}"
    res = ex.export_all(approved, challenge, manifest, tmp_path)
    assert not res["workflow_report"].ok and not (tmp_path / "workflow_report.html").exists()
    assert FAKE_HF_TOKEN not in res["workflow_report"].message


def test_key_in_instructions_blocks_settings(approved, challenge, manifest, tmp_path):
    approved.agents["translator"]["instructions"] += f"\nkey: {FAKE_ANTHROPIC_KEY}"
    res = ex.export_all(approved, challenge, manifest, tmp_path)
    assert not res["agent_settings"].ok and not (tmp_path / "agent_settings.json").exists()


def test_key_in_comment_finding_or_state_is_refused(reviewed_state, challenge, tmp_path):
    with pytest.raises(ps.StudioError):
        ps.decide_finding(reviewed_state, "R1-01", "reject", "d", comment=FAKE_ANTHROPIC_KEY)
    with pytest.raises(ps.StudioError):
        ps.direct_edit(reviewed_state, {"demo.ui.start": FAKE_HF_TOKEN}, "d")
    with pytest.raises(ps.StudioError):
        ps.new_project(challenge, "en", "replay", "replay", "replay", team_name=FAKE_ANTHROPIC_KEY)
    reviewed_state.findings[0].suggestion = FAKE_ANTHROPIC_KEY
    with pytest.raises(ps.StudioError):
        ps.save_state(reviewed_state, tmp_path / "s.json")


def test_live_key_never_reaches_any_output(challenge, manifest, provider_config, tmp_path):
    st = ps.new_project(challenge, "en-GB", "live", "anthropic", "claude-haiku-5-5")

    def tr(batch):
        return FakeResponse(200, anthropic_body(json.dumps(
            {"translations": [{"id": i, "text": t} for i, t in batch]})))
    good = {"demo.ui.start": "Investigate", "demo.narration.arrival": "Night falls.",
            "demo.line.granny_greeting": "{player_name}, at last!", "demo.line.kit_reply": "They're gone!",
            "demo.line.granny_hint": "Ask the master.", "demo.choice.follow": "Follow Granny",
            "demo.choice.ask": "Ask Kit", "demo.ending.a": "{lantern_count} of {lantern_total} found.",
            "demo.ui.coins": "Coins: {coins}"}
    items = list(good.items())
    session = FakeSession(tr(items[:8]), tr(items[8:]))
    prov = p.make_provider("anthropic", FAKE_ANTHROPIC_KEY, provider_config, session=session)
    a.run_translator(st, prov, challenge)
    assert session.calls[0]["headers"]["x-api-key"] == FAKE_ANTHROPIC_KEY   # sent only as header
    ps.approve_final(st, "director")
    ps.save_state(st, tmp_path / "state.json")
    res = ex.export_all(st, challenge, manifest, tmp_path)
    assert all(r.ok for r in res.values()), {k: r.message for k, r in res.items()}
    for f in tmp_path.iterdir():
        text = f.read_text(encoding="utf-8")
        assert FAKE_ANTHROPIC_KEY not in text and ex.scan_for_secrets(text) == [], f.name
    assert FAKE_ANTHROPIC_KEY not in repr(prov) and FAKE_ANTHROPIC_KEY not in json.dumps(st.to_dict())


def test_replay_is_offline_end_to_end(no_network, challenge, manifest, replay_fixtures, tmp_path):
    prov = p.make_provider("replay", "", p.load_provider_config(), fixtures=replay_fixtures)
    with pytest.raises(RuntimeError):
        prov.session   # Replay has no HTTP session at all
    st = ps.new_project(challenge, "en-GB", "replay", "replay", "replay")
    a.run_baseline(st, prov, challenge)
    a.run_translator(st, prov, challenge)
    a.run_reviewer(st, prov, challenge)
    ps.decide_finding(st, "R1-01", "accept", "director")
    a.run_revision(st, prov, challenge)
    ps.approve_final(st, "director")
    res = ex.export_all(st, challenge, manifest, tmp_path)
    assert all(r.ok for r in res.values())
    html = (tmp_path / "workflow_report.html").read_text(encoding="utf-8")
    assert "<script" not in html.lower() and ex.CSP in html and "http://" not in html.split("<svg")[0]


def test_report_has_no_external_resources(reviewed_state, challenge, manifest):
    html = ex.render_workflow_report(reviewed_state, challenge, manifest)
    assert "<script" not in html.lower() and "<link" not in html.lower() and "src=" not in html.lower()
    assert ' href="' not in html.lower()


# ----------------------------------------------------------------- loaded keys without a prefix

HEX_KEY = "3f9a1c0e7b2d4a6f8e1c3b5d7f9a0c2e"     # a 32-hex gateway key: no pattern matches it


def _valid(spec: dict) -> str:
    phs = " ".join("{" + x.strip("{}") + "}" for x in spec.get("placeholders") or [])
    text = f"Go {phs}".strip()
    return text[: spec["max_len"]] if spec.get("max_len") else text


class _EchoSession:
    """Answers every translator request with valid text for the ids named in the prompt."""

    def __init__(self, specs):
        self.specs, self.calls = specs, []

    def post(self, url, headers=None, json=None, params=None, timeout=None):
        import json as _json
        self.calls.append(_json.dumps(json))
        user = json["messages"][0]["content"]
        items = [{"id": sid, "text": _valid(sp)} for sid, sp in self.specs.items() if sid in user]
        return FakeResponse(200, anthropic_body(_json.dumps({"translations": items})))


@pytest.fixture
def hex_studio(tmp_path, provider_config):
    pytest.importorskip("ipywidgets")
    from src.studio_ui import Studio
    challenge = json.loads((ROOT / "challenges" / "introductory.json").read_text(encoding="utf-8"))
    session = _EchoSession({s["id"]: s for s in challenge["strings"]})

    class UD:
        def get(self, name):
            return HEX_KEY

    def factory(name, key, cfg, meter):
        return p.make_provider("anthropic", key, cfg, meter, session=session, sleep=lambda s: None)

    s = Studio(state_path=tmp_path / "studio_state.json", export_dir=tmp_path / "exports",
               colab=False, provider_factory=factory, userdata=UD())
    s.w["provider"].value = "anthropic"
    s.w["btn_load_key"].click()
    assert s.provider is not None and HEX_KEY in p.loaded_secrets()
    s._session = session
    return s


def _all_files_text(*dirs) -> str:
    return "\n".join(f.read_text(encoding="utf-8", errors="ignore")
                     for d in dirs if d.exists() for f in d.rglob("*") if f.is_file())


def test_loaded_hex_key_cannot_reach_prompts_exports_or_state(hex_studio, tmp_path):
    s = hex_studio
    assert p.find_secrets(f"our key is {HEX_KEY}")                 # the loaded key is known
    s.w["team"].value = f"Team {HEX_KEY}"
    s.w["btn_start"].click()
    assert s.state is None and "contains your API key" in s.w["msg_mission"].value
    s.w["team"].value = "Team Lantern"
    s.w["btn_start"].click()
    st = s.state
    clean = st.agents["translator"]["instructions"]
    # student-typed text holding the key is refused with a plain message
    s.w["t_instructions"].value = clean + f"\nInternal note: {HEX_KEY}"
    assert "This text contains your API key — remove it" in s.w["msg_config"].value
    assert HEX_KEY not in json.dumps(st.agents)
    s.w["btn_translator"].click()                                  # nothing is sent
    assert "contains your API key" in s.w["msg_run"].value
    assert st.prompt_snapshots == [] and s._session.calls == []
    s.w["t_instructions"].value = clean
    s.w["btn_translator"].click()
    assert st.current_version() is not None, s.w["msg_run"].value
    for fn in (lambda: ps.set_reflection(st, f"we used {HEX_KEY}"),
               lambda: ps.add_rule(st, "style", f"use {HEX_KEY}", "d"),
               lambda: ps.direct_edit(st, {"intro.ui.start": HEX_KEY}, "d"),
               lambda: s.import_material("x.txt", f"line {HEX_KEY}\n".encode())):
        with pytest.raises(ps.StudioError) as e:
            fn()
        assert "contains your API key" in e.value.user_message and HEX_KEY not in e.value.user_message
    s.w["reflection"].value = f"We used key {HEX_KEY} for this"
    s.w["btn_reflection"].click()
    assert "contains your API key" in s.w["msg_export"].value and HEX_KEY not in st.reflection
    s.w["btn_approve"].click()
    s.w["btn_export_all"].click()                                  # export saves the reflection first
    assert "contains your API key" in s.w["msg_export"].value
    assert not (tmp_path / "exports").exists() or not any((tmp_path / "exports").iterdir()), \
        (s.w["msg_export"].value, s.w["msg_director"].value, list((tmp_path / "exports").iterdir()))
    # even if the key got into the project some other way, it is never sent, saved or exported
    st.memory_rules.append(ps.Rule("M99", "style", f"secret {HEX_KEY}"))
    n_calls, n_snaps = len(s._session.calls), len(st.prompt_snapshots)
    s.w["btn_translator"].click()
    assert len(s._session.calls) == n_calls and len(st.prompt_snapshots) == n_snaps
    with pytest.raises(ps.StudioError):
        ps.save_state(st, tmp_path / "planted.json")
    assert not s._try_autosave() and "looks like an API key" in s.autosave_problem
    st.memory_rules.pop()
    s.w["reflection"].value = ""
    st.reflection = f"planted {HEX_KEY}"
    res = ex.export_all(st, s.challenge, s.manifest, tmp_path / "exports")
    assert not res["workflow_report"].ok and HEX_KEY not in res["workflow_report"].message
    st.reflection = ""
    s._try_autosave()
    assert all(HEX_KEY not in c for c in s._session.calls)
    assert HEX_KEY not in _all_files_text(tmp_path)
    assert HEX_KEY not in json.dumps(st.to_dict()) and HEX_KEY not in json.dumps(s.extras)


def test_autosave_failure_shows_the_reason(tmp_path):
    pytest.importorskip("ipywidgets")
    from src.studio_ui import Studio
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x")
    s = Studio(state_path=blocker / "studio_state.json", export_dir=tmp_path / "exports", colab=False)
    s.connect_replay()
    s.w["btn_start"].click()
    msg = s.w["msg_mission"].value
    assert "Autosave did not work this time: the project file could not be written" in msg
    assert "Autosave failed" in s.w["status_html"].value


@pytest.mark.parametrize("text", [
    "The Lantern Bearer Extraordinaire arrives at the market.",
    "Bearer of good news, 2 lanterns found",
    "the key to the attic is under the mat",
    "Secret passage behind the stall: number 12",
    "Token of thanks for {player_name}",
    '"secret_name": "HKBU_API_KEY"',
])
def test_generic_patterns_allow_game_text(text):
    assert p.find_secrets(text) == [], text


@pytest.mark.parametrize("text", [
    FAKE_ANTHROPIC_KEY, FAKE_HF_TOKEN, "Authorization: Bearer abcDEF1234567890ghiJKL",
    f"our key is {HEX_KEY}", f"HKBU_API_KEY={HEX_KEY}", "token 0d3c9b6e-1f2a-4b3c-9d8e-7f6a5b4c3d2e",
    "api_key: 'Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5'",
])
def test_generic_patterns_still_catch_real_looking_tokens(text):
    assert p.find_secrets(text), text
