import json
import os

import pytest

from src import agents as a, project_state as ps


def test_new_project_fields(state, challenge):
    assert state.challenge_id == "demo" and state.stage == "INPUT" and state.mission == "demo"
    assert state.provider == {"name": "replay", "translator_model": "replay", "reviewer_model": "replay"}
    assert set(state.agents) == {"translator", "reviewer"}
    assert state.usage["request_cap"] == 40 and state.revision == {"max_cycles": 1, "cycles_done": 0}
    assert state.string_ids() == [s["id"] for s in challenge["strings"]]
    with pytest.raises(ps.StudioError):
        ps.new_project(challenge, "fr", "replay", "replay", "replay")
    with pytest.raises(ps.StudioError):
        ps.new_project(challenge, "en", "offline", "replay", "replay")


def test_decisions_append_only_latest_wins(reviewed_state):
    st = reviewed_state
    d1 = ps.decide_finding(st, "R1-01", "accept", "director")
    d2 = ps.decide_finding(st, "R1-01", "reject", "director", comment="changed my mind")
    assert [d.decision_id for d in st.decisions] == [d1.decision_id, d2.decision_id]
    assert st.latest_decisions()["R1-01"].action == "reject"
    assert d2.agrees_with_reviewer is False and d1.agrees_with_reviewer is True
    assert d1.reviewer_suggestion == st.finding("R1-01").suggestion
    assert [f.finding_id for f in st.open_findings()] == ["R1-02", "R1-03"]
    assert st.open_findings(round=2) == []


def test_decision_validation(reviewed_state):
    with pytest.raises(ps.StudioError):
        ps.decide_finding(reviewed_state, "R9-99", "accept", "director")
    with pytest.raises(ps.StudioError):
        ps.decide_finding(reviewed_state, "R1-01", "maybe", "director")
    with pytest.raises(ps.StudioError):
        ps.decide_finding(reviewed_state, "R1-01", "accept_edited", "director", human_text="  ")
    with pytest.raises(ps.StudioError):
        ps.bulk_decide(reviewed_state, ["R1-01"], "override", "director")
    assert len(ps.bulk_decide(reviewed_state, ["R1-01", "R1-02"], "accept", "director")) == 2


def test_approval_required_and_revoked_after_changes(reviewed_state, replay, challenge):
    st = reviewed_state
    ok, reasons = ps.can_export(st)
    assert not ok and "not been approved" in reasons[0]
    changes = [
        lambda: ps.decide_finding(st, "R1-01", "accept", "director"),
        lambda: ps.direct_edit(st, {"demo.ui.start": "Search"}, "director"),
        lambda: ps.add_rule(st, "style", "Use contractions in dialogue", "director"),
        lambda: ps.restore_version(st, st.versions[1].version_id, "director"),
        lambda: a.run_revision(st, replay, challenge),
    ]
    for change in changes:
        ps.approve_final(st, "director")
        assert st.stage == "APPROVED" and ps.can_export(st) == (True, [])
        change()
        assert not st.approval["approved"] and st.stage != "APPROVED"
        assert st.history[-1]["event"] != "approved"
        assert any(h["event"] == "approval_revoked" for h in st.history)
        assert not ps.can_export(st)[0]


def test_manual_revoke(reviewed_state):
    ps.approve_final(reviewed_state, "director")
    ps.revoke_approval(reviewed_state, "director")
    assert reviewed_state.stage == "REVIEWED" and reviewed_state.decisions[-1].action == "revoke_approval"


def test_approval_blocked_by_critical(reviewed_state):
    ps.direct_edit(reviewed_state, {"demo.line.granny_greeting": "{player name}, hi!"}, "director")
    with pytest.raises(ps.StudioError) as e:
        ps.approve_final(reviewed_state, "director")
    assert "blocked" in e.value.user_message
    reviewed_state.approval = {"approved": True, "version_id": reviewed_state.current_version_id,
                               "role": "x", "approved_at": "t"}
    ok, reasons = ps.can_export(reviewed_state)
    assert not ok and any("placeholder" in r for r in reasons)


def test_direct_edit_and_restore(reviewed_state):
    st = reviewed_state
    tv = st.current_version_id
    v = ps.direct_edit(st, {"demo.ui.start": "Search"}, "director", comment="shorter")
    assert v.kind == "human_edit" and v.source == "human" and v.parent_id == tv
    assert st.decisions[-1].action == "direct_edit" and st.decisions[-1].human_text == "Search"
    with pytest.raises(ps.StudioError):
        ps.direct_edit(st, {"nope.x.y": "?"}, "director")
    r = ps.restore_version(st, tv, "director")
    assert r.kind == "restored" and r.translations == st.version(tv).translations
    assert st.current_version_id == r.version_id


def test_save_load_round_trip(reviewed_state, tmp_path):
    st = reviewed_state
    ps.decide_finding(st, "R1-01", "accept_edited", "director", human_text="Hi {player_name}!", comment="é 😀")
    ps.add_rule(st, "glossary", "Use lantern-maker", "director", "紮作", "lantern-maker", "R1-03")
    ps.set_reflection(st, "The agent missed Granny's warmth.")
    path = tmp_path / "studio_state.json"
    ps.save_state(st, path)
    assert [f for f in os.listdir(tmp_path) if f.startswith(".tmp_")] == []
    loaded = ps.load_state(path)
    assert loaded.to_dict() == st.to_dict()
    assert ps.load_state(path.read_text(encoding="utf-8")).to_dict() == st.to_dict()
    assert loaded.latest_decisions()["R1-01"].human_text == "Hi {player_name}!"
    assert loaded.memory_rules[0].rule_id == "M01"


def test_save_refuses_secrets(reviewed_state, tmp_path):
    reviewed_state.reflection = "my key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123"
    with pytest.raises(ps.StudioError) as e:
        ps.save_state(reviewed_state, tmp_path / "s.json")
    assert "looks like an API key" in e.value.user_message
    assert "abcdefghijklmnop" not in e.value.user_message
    assert not (tmp_path / "s.json").exists()


@pytest.mark.parametrize("content,needle", [
    ("{not json", "damaged"),
    ('{"hello": 1}', "not a Game Localisation Studio project"),
    ('{"schema_version": "0.1", "challenge_id": "x"}', "different version"),
    ('{"schema_version": "2.0", "challenge_id": "x"}', "different version"),
    ('[1, 2]', "not a Game Localisation Studio project"),
])
def test_load_state_friendly_errors(tmp_path, content, needle):
    f = tmp_path / "bad.json"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(ps.StudioError) as e:
        ps.load_state(f)
    assert needle in e.value.user_message


def test_load_state_missing_file(tmp_path):
    with pytest.raises(ps.StudioError):
        ps.load_state(tmp_path / "nope.json")


def test_old_state_with_extra_fields_loads(reviewed_state):
    d = reviewed_state.to_dict()
    d["unknown_future_field"] = 1
    d["findings"][0]["extra"] = "x"
    assert ps.load_state(json.dumps(d)).findings[0].finding_id == "R1-01"


def test_rule_and_text_limits(reviewed_state):
    with pytest.raises(ps.StudioError):
        ps.add_rule(reviewed_state, "magic", "x", "director")
    with pytest.raises(ps.StudioError):
        ps.decide_finding(reviewed_state, "R1-01", "reject", "director", comment="x" * 3000)


def test_load_state_deep_nesting_and_size_limit(tmp_path):
    deep = '{"challenge_id": "x", "schema_version": "1.0", "a": ' + "[" * 100000 + "]" * 100000 + "}"
    with pytest.raises(ps.StudioError) as e:
        ps.load_state(deep)
    assert "damaged" in e.value.user_message
    big = '{"challenge_id": "x", "schema_version": "1.0", "pad": "' + "x" * ps.MAX_STATE_BYTES + '"}'
    for source in (big, big.encode()):
        with pytest.raises(ps.StudioError) as e:
            ps.load_state(source)
        assert "too large" in e.value.user_message and "5 MB" in e.value.user_message
    f = tmp_path / "big.json"
    f.write_text(big, encoding="utf-8")
    with pytest.raises(ps.StudioError) as e:
        ps.load_state(f)
    assert "too large" in e.value.user_message
