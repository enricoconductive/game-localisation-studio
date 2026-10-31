import json

import pytest

from src import agents as a, project_state as ps, providers as p
from conftest import ScriptedProvider, echo_translations



def live_state(challenge, **kw):
    return ps.new_project(challenge, "en-GB", "live", "anthropic", "claude-haiku-5-5", **kw)


# ----------------------------------------------------------------- settings


def test_default_configs_and_specs():
    for role, spec in (("translator", a.TRANSLATOR_SETTINGS_SPEC), ("reviewer", a.REVIEWER_SETTINGS_SPEC)):
        cfg = a.default_agent_config(role)
        assert cfg["instructions"] == cfg["default_instructions"]
        assert set(cfg["settings"]) == {s["key"] for s in spec}
        for s in spec:
            assert s["kind"] in ("slider", "dropdown", "checkbox") and s["label"] and s["help"]
    keys = {s["key"] for s in a.TRANSLATOR_SETTINGS_SPEC}
    assert keys == {"strategy", "cultural_adaptation", "register", "voice_strength", "glossary_strictness"}
    gl = next(s for s in a.TRANSLATOR_SETTINGS_SPEC if s["key"] == "glossary_strictness")
    assert gl["options"] == ["must_use", "prefer", "ignore"]
    assert a.default_settings("reviewer")["max_findings"] == 6


def test_settings_text_is_explicit_and_changes():
    s1 = a.settings_to_text("translator", {"strategy": 1, "glossary_strictness": "must_use"})
    s5 = a.settings_to_text("translator", {"strategy": 5, "cultural_adaptation": 5})
    assert "Translation strategy 1/5: very faithful" in s1 and "MUST use" in s1
    assert "Translation strategy 5/5: very creative" in s5 and "Cultural adaptation 5/5" in s5
    r = a.settings_to_text("reviewer", {"check_fluency": False, "strictness": 5, "max_findings": 3})
    assert "fluency" not in r.split("\n")[0] and "at most 3 findings" in r and "5/5" in r


def test_settings_validation():
    with pytest.raises(ps.StudioError):
        a.settings_to_text("reviewer", {f"check_{c}": False for c in a.CATEGORIES})
    with pytest.raises(ps.StudioError):
        a.normalise_settings("translator", {"register": "pirate"})
    assert a.normalise_settings("translator", {"strategy": 9})["strategy"] == 5


def test_temperature_mapping_visible(provider_config):
    assert [a.temperature_for("translator", {"strategy": n}) for n in range(1, 6)] == [0.1, 0.2, 0.4, 0.6, 0.8]
    assert a.temperature_for("reviewer") == a.REVIEWER_TEMPERATURE
    note = a.temperature_note("translator", {"strategy": 4}, "anthropic", provider_config)
    assert "0.6" in note and "reference only" in note
    assert "is sent" in a.temperature_note("translator", {}, "huggingface", provider_config)


# ----------------------------------------------------------------- prompts


def test_baseline_prompt_is_minimal(challenge):
    system, user = a.build_baseline_prompt(challenge, "en-GB")
    for s in challenge["strings"]:
        assert s["id"] in user and json.dumps(s["source"], ensure_ascii=False)[1:-1] in user
    for absent in ("paper-craft", challenge["scene_context"], "Granny Wong", "Maximum 12"):
        assert absent not in user + system


def test_translator_prompt_contents_and_role_separation(state, challenge):
    cfg = state.agents["translator"]
    cfg["instructions"] = "TEAM INSTRUCTION XYZ"
    rules = [{"rule_id": "M01", "kind": "glossary", "text": "Call him Kit", "source_term": "阿杰",
              "target_term": "Kit"}]
    system, user = a.build_translator_prompt(challenge, cfg, "en-GB", rules)
    for needed in ("TEAM INSTRUCTION XYZ", a.settings_to_text("translator", cfg["settings"]),
                   "紮作 → paper-craft", challenge["scene_context"], "Warm elderly shop owner",
                   "Maximum 12 characters", "{player_name} — copy exactly", "Max length: 12",
                   "British English", "Project memory (approved by the human director)",
                   "M01 [glossary] (阿杰 → Kit): Call him Kit", "demo.ui.coins"):
        assert needed in user, needed
    assert system == a.TRANSLATOR_ROLE
    whole = (system + user).lower()
    assert a.REVIEWER_ROLE.lower() not in whole and a.DEFAULT_REVIEWER_INSTRUCTIONS.lower() not in whole
    assert "findings" not in whole and "retrain" not in whole and "fine-tun" not in whole
    assert "SECRET_INSTRUCTOR_NOTE" not in user


def test_reviewer_prompt_contents(state, challenge):
    tr = {s["id"]: f"T:{s['id']}" for s in challenge["strings"]}
    system, user = a.build_reviewer_prompt(challenge, state.agents["reviewer"], "en-US", [], tr)
    assert system == a.REVIEWER_ROLE and "suggestions for a human localisation director" in system
    for s in challenge["strings"]:
        assert f'Translation under review: "T:{s["id"]}"' in user
        assert s["context"] in user
    for needed in ("紮作 → paper-craft", "American English", a.DEFAULT_REVIEWER_INSTRUCTIONS,
                   "Do not invent problems", "It is fine to report"):
        assert needed in user
    assert a.TRANSLATOR_ROLE not in user and "SECRET_INSTRUCTOR_NOTE" not in user


def test_locale_variants(state, challenge):
    users = {loc: a.build_translator_prompt(challenge, state.agents["translator"], loc, [])[1]
             for loc in ("en-GB", "en-US", "en")}
    assert "colour" in users["en-GB"] and "color," in users["en-US"]
    assert "International English" in users["en"]


def test_batches_limit_strings(state, challenge):
    ids = [s["id"] for s in challenge["strings"]][:3]
    _, user = a.build_translator_prompt(challenge, state.agents["translator"], "en", [], ids)
    assert "demo.ui.start" in user and "demo.ui.coins" not in user


# ----------------------------------------------------------------- parsing

GOOD = '{"translations": [{"id": "demo.ui.start", "text": "Investigate"}]}'


@pytest.mark.parametrize("text", [
    GOOD,
    f"```json\n{GOOD}\n```",
    f"Here is the translation you asked for:\n{GOOD}\nLet me know if you need more!",
    f"Sure! ```\n{GOOD}\n``` done",
])
def test_parse_translations_variants(text):
    out = a.parse_translations(text, ["demo.ui.start"])
    assert out == [{"id": "demo.ui.start", "text": "Investigate", "note": ""}]


def test_parse_translations_unknown_ids_dropped_and_garbage():
    text = json.dumps({"translations": [{"id": "x.y.z", "text": "?"},
                                        {"id": "demo.ui.start", "text": "Go", "note": "short"}]})
    assert a.parse_translations(text, ["demo.ui.start"]) == [
        {"id": "demo.ui.start", "text": "Go", "note": "short"}]
    for bad in ("I cannot do that.", "", '{"translations": "nope"}', '{"translations": []}', "{broken"):
        with pytest.raises(a.AgentOutputError):
            a.parse_translations(bad, ["demo.ui.start"])


def test_parse_findings_drops_unknown_and_normalises():
    text = "Review:\n" + json.dumps({"findings": [
        {"string_id": "demo.ui.start", "category": "Voice", "severity": "HUGE", "issue": "x",
         "reasoning": "y", "suggestion": "Go"},
        {"string_id": "nope.x.y", "category": "accuracy", "severity": "minor", "issue": "x"},
        {"string_id": "demo.ui.start", "category": "accuracy", "severity": "major", "issue": ""},
    ], "overall_comment": "ok"})
    findings, dropped = a.parse_findings(text, ["demo.ui.start"])
    assert dropped == 2
    assert findings == [{"string_id": "demo.ui.start", "category": "character_voice",
                         "severity": "minor", "issue": "x", "reasoning": "y", "suggestion": "Go",
                         "normalised": "category 'Voice' → character_voice; severity 'HUGE' → minor"}]
    assert a.parse_findings('{"findings": [], "overall_comment": "fine"}', ["a"]) == ([], 0)


# ----------------------------------------------------------------- runs (replay)


def test_replay_run_snapshots_and_stages(reviewed_state, challenge):
    st = reviewed_state
    assert st.baseline_version().kind == "baseline" and st.current_version().kind == "translator"
    assert st.baseline_version().translations["demo.ui.start"] == "Start the investigation"
    assert st.stage == "REVIEWED"
    assert {s.agent for s in st.prompt_snapshots} == {"baseline", "translator", "reviewer"}
    assert all(s.source == "replay" for s in st.prompt_snapshots)
    assert len([s for s in st.prompt_snapshots if s.agent == "translator"]) == 2   # 9 strings → 2 batches
    assert [f.finding_id for f in st.findings] == ["R1-01", "R1-02", "R1-03"]
    assert all(f.source == "replay" for f in st.findings)
    assert "1 finding(s) dropped" in st.history[-1]["detail"]                  # unknown id in fixture
    assert st.usage["requests"] == 0 and st.usage["simulated_requests"] == 6


def test_replay_revision_deterministic_and_round2(reviewed_state, replay, challenge):
    st = reviewed_state
    ps.decide_finding(st, "R1-01", "accept", "director")
    ps.decide_finding(st, "R1-02", "reject", "director", comment="Kit is calm on purpose")
    ps.decide_finding(st, "R1-03", "override", "director", human_text="The lantern master knows.")
    before = dict(st.current_version().translations)
    v = a.run_revision(st, replay, challenge)
    assert v.translations["demo.line.granny_greeting"] == "{player_name}, dear, there you are at last!"
    assert v.notes["demo.line.granny_greeting"] == "Warmer, more affectionate greeting (simulated)."
    assert v.translations["demo.line.granny_hint"] == "The lantern master knows."
    assert v.translations["demo.line.kit_reply"] == before["demo.line.kit_reply"]  # rejected
    assert v.source == "replay" and st.revision["cycles_done"] == 1 and st.stage == "REVISED"
    rev = [s for s in st.prompt_snapshots if s.agent == "reviser"]
    assert len(rev) == 1 and "Granny! The lanterns" not in rev[0].user      # rejected never sent
    assert "The lantern master knows." in rev[0].user                       # locked context
    assert a.estimate_requests(st, challenge, "reviewer") == 1
    f2 = a.run_reviewer(st, replay, challenge)
    assert [(f.finding_id, f.string_id) for f in f2] == [("R2-01", "demo.line.granny_greeting")]
    r2 = [s for s in st.prompt_snapshots if s.agent == "reviewer" and s.round == 2]
    assert "demo.line.granny_hint" in r2[0].user and "[demo.ui.start]" not in r2[0].user


def test_revision_limit(reviewed_state, replay, challenge):
    st = reviewed_state
    ps.decide_finding(st, "R1-01", "accept", "director")
    a.run_revision(st, replay, challenge)
    with pytest.raises(ps.StudioError) as e:
        a.run_revision(st, replay, challenge)
    assert "revision cycle" in e.value.user_message


def test_revision_zero_cycles_and_nothing_to_revise(challenge, replay):
    st = ps.new_project(challenge, "en-GB", "replay", "replay", "replay", max_cycles=0)
    a.run_translator(st, replay, challenge)
    a.run_reviewer(st, replay, challenge)
    with pytest.raises(ps.StudioError):
        a.run_revision(st, replay, challenge)
    st2 = ps.new_project(challenge, "en-GB", "replay", "replay", "replay", max_cycles=2)
    a.run_translator(st2, replay, challenge)
    a.run_reviewer(st2, replay, challenge)
    ps.bulk_decide(st2, ["R1-01", "R1-02"], "reject", "director")
    with pytest.raises(ps.StudioError) as e:
        a.run_revision(st2, replay, challenge)
    assert "rejected ones are never applied" in e.value.user_message
    assert st2.revision["cycles_done"] == 0
    with pytest.raises(ps.StudioError):
        ps.new_project(challenge, "en-GB", "replay", "replay", "replay", max_cycles=3)


def test_review_requires_translation(state, replay, challenge):
    with pytest.raises(ps.StudioError):
        a.run_reviewer(state, replay, challenge)


def test_replay_never_touches_network(no_network, challenge, replay_fixtures):
    prov = p.make_provider("replay", "", p.load_provider_config(), fixtures=replay_fixtures)
    st = ps.new_project(challenge, "en", "replay", "replay", "replay")
    a.run_baseline(st, prov, challenge)
    a.run_translator(st, prov, challenge)
    a.run_reviewer(st, prov, challenge)
    ps.decide_finding(st, "R1-01", "accept", "director")
    a.run_revision(st, prov, challenge)
    a.run_reviewer(st, prov, challenge)
    assert st.stage == "REVIEWED" and len(st.findings) == 4


# ----------------------------------------------------------------- runs (live, scripted)


def test_live_translator_batches_and_usage(challenge):
    st = live_state(challenge)
    prov = ScriptedProvider([echo_translations()])
    v = a.run_translator(st, prov, challenge)
    assert len(prov.calls) == 2 and all(len(c["replay_key"]["string_ids"]) <= 8 for c in prov.calls)
    assert v.translations["demo.ui.coins"] == "EN demo.ui.coins" and v.source == "live"
    assert st.usage["requests"] == 2 and st.usage["input_tokens"] == 20
    assert prov.calls[0]["temperature"] == 0.4 and prov.calls[0]["model"] == "claude-haiku-5-5"


def test_repair_then_success(challenge):
    st = live_state(challenge)
    prov = ScriptedProvider(["Sorry, here you go: not json", echo_translations(),
                             echo_translations()])
    a.run_translator(st, prov, challenge)
    assert len(prov.calls) == 3
    assert a.REPAIR_MARK in prov.calls[1]["user"] and a.REPAIR_MARK not in prov.calls[0]["user"]
    assert st.raw_failures == []


def test_garbage_twice_raises_and_keeps_raw(challenge):
    st = live_state(challenge)
    junk = "x" * 5000
    prov = ScriptedProvider([junk])
    with pytest.raises(a.AgentOutputError) as e:
        a.run_translator(st, prov, challenge)
    assert "repair" in e.value.user_message and len(prov.calls) == 2
    assert st.versions == [] and len(st.raw_failures) == 2
    assert len(st.raw_failures[0]["text"]) == 4000 and st.raw_failures[0]["agent"] == "translator"


def test_missing_ids_keep_previous_text(challenge):
    st = live_state(challenge)
    a.run_translator(st, ScriptedProvider([echo_translations("V1 ")]), challenge)

    def partial(system, user, key):
        ids = [i for i in key["string_ids"] if i != "demo.ui.start"]
        return json.dumps({"translations": [{"id": i, "text": "V2 " + i} for i in ids]})
    v2 = a.run_translator(st, ScriptedProvider([partial]), challenge)
    assert v2.translations["demo.ui.start"] == "V1 demo.ui.start"
    assert "kept the previous text" in v2.notes["demo.ui.start"]
    assert any(h["event"] == "warning" and "demo.ui.start" in h["detail"] for h in st.history)

    st2 = live_state(challenge)
    v = a.run_translator(st2, ScriptedProvider([partial]), challenge)
    assert "demo.ui.start" not in v.translations   # nothing fabricated


def test_cap_checked_before_calling(challenge):
    st = live_state(challenge, request_cap=40)
    st.usage["requests"] = 39
    prov = ScriptedProvider([echo_translations()])
    with pytest.raises(p.ProviderError) as e:
        a.run_translator(st, prov, challenge)
    assert e.value.kind == "cap_reached" and prov.calls == []
    assert a.estimate_requests(st, challenge, "translator") == 2


def findings_reply(findings):
    return json.dumps({"findings": findings, "overall_comment": "ok"})


def test_live_review_and_feedback_routing(challenge):
    st = live_state(challenge)
    a.run_translator(st, ScriptedProvider([echo_translations()]), challenge)
    fs = [{"string_id": "demo.ui.start", "category": "fluency", "severity": "minor",
           "issue": "Odd", "reasoning": "r", "suggestion": "ACCEPTED-SUGGESTION"},
          {"string_id": "demo.choice.ask", "category": "accuracy", "severity": "major",
           "issue": "Wrong", "reasoning": "r", "suggestion": "REJECTED-SUGGESTION"},
          {"string_id": "demo.choice.follow", "category": "accuracy", "severity": "critical",
           "issue": "Bad", "reasoning": "r", "suggestion": "REVIEWER-OVERRIDDEN"},
          {"string_id": "demo.line.kit_reply", "category": "fluency", "severity": "minor",
           "issue": "Meh", "reasoning": "r", "suggestion": "REVIEWER-EDITED"},
          {"string_id": "ghost.id.x", "category": "fluency", "severity": "minor", "issue": "?"}]

    def review(system, user, key):
        return findings_reply([f for f in fs if f["string_id"] in key["string_ids"]
                               or (f["string_id"] == "ghost.id.x" and "known_ids" in key)])
    found = a.run_reviewer(st, ScriptedProvider([review]), challenge)
    by_id = {f.string_id: f.finding_id for f in found}
    assert found[0].severity == "critical"   # sorted by severity
    ps.decide_finding(st, by_id["demo.ui.start"], "accept", "director", comment="good catch")
    ps.decide_finding(st, by_id["demo.choice.ask"], "reject", "director", comment="not wrong")
    ps.decide_finding(st, by_id["demo.choice.follow"], "override", "director", human_text="Go with Granny")
    ps.decide_finding(st, by_id["demo.line.kit_reply"], "accept_edited", "director",
                      human_text="Granny, they're gone!")
    assert a.estimate_requests(st, challenge, "revision") == 1
    reviser = ScriptedProvider([json.dumps({"translations": [{"id": "demo.ui.start", "text": "Look"}]})])
    v = a.run_revision(st, reviser, challenge)
    assert len(reviser.calls) == 1
    sent = reviser.calls[0]["user"]
    assert "ACCEPTED-SUGGESTION" in sent and "good catch" in sent
    assert "REJECTED-SUGGESTION" not in sent and "not wrong" not in sent
    assert "Go with Granny" in sent                       # locked context
    assert reviser.calls[0]["replay_key"]["string_ids"] == ["demo.ui.start"]
    assert v.translations["demo.ui.start"] == "Look"
    assert v.translations["demo.choice.follow"] == "Go with Granny"
    assert v.translations["demo.line.kit_reply"] == "Granny, they're gone!"
    assert v.translations["demo.choice.ask"] == "EN demo.choice.ask"


def test_override_only_needs_no_api_call(challenge):
    st = live_state(challenge)
    a.run_translator(st, ScriptedProvider([echo_translations()]), challenge)
    a.run_reviewer(st, ScriptedProvider([findings_reply([
        {"string_id": "demo.ui.start", "category": "technical", "severity": "major",
         "issue": "Too long?", "reasoning": "", "suggestion": "Go"}])]), challenge)
    ps.decide_finding(st, "R1-01", "override", "director", human_text="Begin")
    prov = ScriptedProvider(["should not be called"])
    v = a.run_revision(st, prov, challenge)
    assert prov.calls == [] and v.source == "human" and v.translations["demo.ui.start"] == "Begin"


def test_reviewer_respects_categories_and_max(challenge):
    st = live_state(challenge)
    a.run_translator(st, ScriptedProvider([echo_translations()]), challenge)
    st.agents["reviewer"]["settings"].update({"check_fluency": False, "max_findings": 1})
    many = [{"string_id": "demo.ui.start", "category": c, "severity": s, "issue": "i",
             "suggestion": "x"} for c, s in (("fluency", "critical"), ("accuracy", "minor"),
                                             ("accuracy", "major"))]
    found = a.run_reviewer(st, ScriptedProvider([findings_reply(many), findings_reply([])]), challenge)
    assert [(f.category, f.severity) for f in found] == [("accuracy", "major")]


def test_preview(reviewed_state, challenge, provider_config):
    pv = a.preview(reviewed_state, challenge, "translator", provider_config)
    assert pv["system"] == a.TRANSLATOR_ROLE and pv["requests"] == 2 and pv["temperature"] == 0.4
    assert "Replay" in pv["temperature_note"]


# ----------------------------------------------------------------- review fixes (v0.3.1)


class StopProvider(ScriptedProvider):
    """ScriptedProvider whose replies may be (text, stop_reason) pairs or exceptions."""

    def complete(self, system, user, *, model, max_tokens=1200, temperature=0.3, replay_key=None):
        self.calls.append({"user": user, "replay_key": replay_key})
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, BaseException):
            raise r
        text, stop = r if isinstance(r, tuple) else (r, "end_turn")
        text = text(system, user, replay_key) if callable(text) else text
        return p.ModelResponse(text, model, 10, 5, "live", False, stop)


def test_truncated_reply_asks_for_compact_output(challenge):
    st = live_state(challenge)
    prov = StopProvider([('{"translations": [{"id": "demo.ui.start", "text": "Inv', "max_tokens"),
                         echo_translations(), echo_translations()])
    a.run_translator(st, prov, challenge)
    repair = prov.calls[1]["user"]
    assert a.REPAIR_MARK in repair and "cut off because it was too long" in repair
    assert "leave every note empty" in repair
    assert any("cut off at the output limit" in h["detail"] for h in st.history)


def test_truncated_twice_says_the_reply_was_cut_off(challenge):
    st = live_state(challenge)
    prov = StopProvider([('{"translations": [', "length")])
    with pytest.raises(a.AgentOutputError) as e:
        a.run_translator(st, prov, challenge)
    msg = e.value.user_message
    assert "cut off because it was too long" in msg and "fewer strings or a shorter instruction" in msg
    assert st.versions == [] and len(prov.calls) == 2


def test_later_batch_failure_keeps_completed_batches(challenge):
    st = live_state(challenge)
    a.run_translator(st, ScriptedProvider([echo_translations("OLD ")]), challenge)
    busy = p._error("rate_limit", "Claude")
    prov = StopProvider([echo_translations("NEW "), busy])
    v = a.run_translator(st, prov, challenge)
    first, second = a._batches(st.string_ids())
    assert all(v.translations[sid] == f"NEW {sid}" for sid in first)
    assert all(v.translations[sid] == f"OLD {sid}" for sid in second)       # previous text kept
    assert all("a request failed" in v.notes[sid] for sid in second)
    partial = [h["detail"] for h in st.history if h["event"] == "partial_run"]
    assert len(partial) == 1 and "request 2 of 2 failed" in partial[0] and "many classmates" in partial[0]
    assert st.current_version_id == v.version_id


def test_first_batch_failure_changes_nothing(challenge):
    st = live_state(challenge)
    with pytest.raises(p.ProviderError):
        a.run_translator(st, StopProvider([p._error("rate_limit", "Claude")]), challenge)
    assert st.versions == [] and not any(h["event"] == "partial_run" for h in st.history)


def test_review_result_counts_and_all_dropped(challenge):
    st = live_state(challenge)
    a.run_translator(st, ScriptedProvider([echo_translations()]), challenge)
    ids = st.string_ids()
    junk = json.dumps({"findings": [{"string_id": "nope.x.y", "category": "accuracy",
                                     "severity": "major", "issue": "x"}]})
    res = a.run_reviewer(st, ScriptedProvider([junk]), challenge)
    assert res == [] and res.all_dropped and res.dropped == res.received == 2   # 2 batches
    assert st.revision.get("last_reviewed_version_id") is None                # still "not reviewed"
    assert "every finding was dropped" in st.history[-1]["detail"]
    odd = json.dumps({"findings": [{"string_id": ids[0], "category": "style", "severity": "HUGE",
                                    "issue": "x", "suggestion": "y"}]})
    res = a.run_reviewer(st, ScriptedProvider([odd]), challenge)
    assert len(res) == 1 and not res.all_dropped and res.normalised == [
        f"{res[0].finding_id}: category 'style' → fluency; severity 'HUGE' → minor"]
    assert (res[0].category, res[0].severity) == ("fluency", "minor")
    assert "unknown category or severity" in res.counts_text()
    skipped = a.run_reviewer(st, ScriptedProvider([odd]), challenge)
    assert skipped == [] and skipped.skipped and not skipped.all_dropped
    empty = a.run_reviewer(st, ScriptedProvider(['{"findings": []}']), challenge, string_ids=ids)
    assert empty == [] and not empty.skipped and not empty.all_dropped and empty.reviewed_ids == ids


def test_cap_uses_session_meter_and_counts_failed_attempts(challenge, provider_config):
    from conftest import FakeResponse, FakeSession, anthropic_body, error_body
    meter = p.UsageMeter(request_cap=4)
    meter.requests = 2                                     # used earlier in this session
    st = live_state(challenge)
    s = FakeSession(FakeResponse(429, error_body("rate_limit_error", "slow")),
                    FakeResponse(200, anthropic_body('{"translations": []}')))
    prov = p.make_provider("anthropic", "sk-ant-api03-METERtest0123456789abcdef", provider_config,
                           meter, session=s, sleep=lambda x: None)
    with pytest.raises(p.ProviderError) as e:
        a.run_translator(st, prov, challenge)               # needs 2 requests, 2 left: allowed
    assert e.value.kind == "cap_reached"                      # retry + repair used them up
    assert meter.requests == 4 and st.usage["requests"] == 2 and len(s.calls) == 2
    with pytest.raises(p.ProviderError) as e:
        a.run_translator(live_state(challenge), prov, challenge)   # a new project: still capped
    assert e.value.kind == "cap_reached" and "in this session" in e.value.user_message


# ----------------------------------------------------------------- structured outputs / max_tokens

def _validate(value, schema, path="$"):
    """A minimal JSON Schema checker for the subset used by structured outputs."""
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if t in types:
        assert isinstance(value, types[t]), f"{path}: expected {t}"
    elif t == "integer":
        assert isinstance(value, int) and not isinstance(value, bool), f"{path}: expected integer"
    elif t == "number":
        assert isinstance(value, (int, float)) and not isinstance(value, bool), f"{path}: number"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} not in enum"
    if t == "object":
        assert schema.get("additionalProperties") is False, f"{path}: additionalProperties"
        assert set(schema["required"]) <= set(value), f"{path}: missing {set(schema['required']) - set(value)}"
        assert set(value) <= set(schema["properties"]), f"{path}: extra {set(value) - set(schema['properties'])}"
        for k, v in value.items():
            _validate(v, schema["properties"][k], f"{path}.{k}")
    if t == "array":
        for i, v in enumerate(value):
            _validate(v, schema["items"], f"{path}[{i}]")


def test_schemas_accept_every_replay_fixture():
    import glob
    fx = p.load_replay_fixtures()
    ids = {}
    for f in glob.glob(str(p.repo_path("challenges")) + "/*.json"):
        with open(f, encoding="utf-8") as fh:
            ch = json.load(fh)
        ids[ch["id"]] = [s["id"] for s in ch["strings"]]
    checked = 0
    for cid, ch in fx["challenges"].items():
        tschema = a.translations_json_schema(ids[cid])
        fschema = a.findings_json_schema(ids[cid])
        for entry in ch["translator_variants"].values():
            _validate(entry, tschema)
            checked += 1
        for stage in ("reviewer", "reviewer_round2"):
            for entry in ch[stage].values():
                _validate(entry, fschema)
                checked += 1
        with pytest.raises(AssertionError):           # the checker really checks
            _validate({"translations": [{"id": "nope", "text": "x", "note": ""}]}, tschema)
    assert checked == 4 * 9


def test_schema_shapes():
    t = a.translations_json_schema(["x.a", "x.b", "x.a"])
    item = t["properties"]["translations"]["items"]
    assert item["required"] == ["id", "text", "note"] and item["properties"]["id"]["enum"] == ["x.a", "x.b"]
    f = a.findings_json_schema(["x.a"])
    fi = f["properties"]["findings"]["items"]
    assert f["required"] == ["findings", "overall_comment"]
    assert fi["properties"]["category"]["enum"] == list(a.CATEGORIES)
    assert fi["properties"]["severity"]["enum"] == list(a.SEVERITIES)
    assert set(fi["required"]) == {"string_id", "category", "severity", "issue", "reasoning", "suggestion"}


class SchemaEchoSession:
    """Answers each Claude request from its own json_schema (valid ids only); records bodies."""

    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, json=None, params=None, timeout=None):
        from conftest import FakeResponse, anthropic_body
        import json as _json
        self.calls.append({"json": json, "timeout": timeout})
        schema = json["output_config"]["format"]["schema"]
        if "translations" in schema["properties"]:
            ids = schema["properties"]["translations"]["items"]["properties"]["id"]["enum"]
            out = {"translations": [{"id": i, "text": f"EN {i}", "note": ""} for i in ids]}
        else:
            ids = schema["properties"]["findings"]["items"]["properties"]["string_id"]["enum"]
            out = {"findings": [{"string_id": ids[0], "category": "fluency", "severity": "minor",
                                 "issue": "stiff", "reasoning": "reads oddly", "suggestion": "Better"}],
                   "overall_comment": "ok"}
        return FakeResponse(200, anthropic_body(_json.dumps(out)))


def test_live_claude_run_sends_schema_and_max_tokens(challenge, provider_config):
    sess = SchemaEchoSession()
    prov = p.make_provider("anthropic", "sk-ant-api03-SCHEMAtest0123456789abcdef", provider_config,
                           p.UsageMeter(40), session=sess, sleep=lambda x: None)
    st = live_state(challenge)
    a.run_baseline(st, prov, challenge)
    a.run_translator(st, prov, challenge)
    found = a.run_reviewer(st, prov, challenge)
    assert found and found[0].category == "fluency"
    ids = [s["id"] for s in challenge["strings"]]
    batches = a._batches(ids)
    assert len(sess.calls) == 3 * len(batches)
    for c in sess.calls:
        body = c["json"]
        assert body["max_tokens"] == 4000 and c["timeout"] == 90
        assert body["thinking"] == {"type": "disabled"} and body["output_config"]["effort"] == "low"
        assert body["output_config"]["format"]["type"] == "json_schema"
    enums = [c["json"]["output_config"]["format"]["schema"]["properties"]["translations"]
             ["items"]["properties"]["id"]["enum"] for c in sess.calls[:len(batches)]]
    assert enums == batches
    assert st.current_version().translations[ids[0]] == f"EN {ids[0]}"


def test_max_tokens_from_limits_and_schema_only_when_accepted(challenge):
    seen = []

    class Recorder(p.Provider):          # accepts json_schema
        name, is_live = "anthropic", True

        def __init__(self):
            super().__init__("", {}, limits={"max_tokens": 2500})

        def complete(self, system, user, *, model, max_tokens=1, temperature=0.3, replay_key=None,
                     json_schema=None):
            seen.append((max_tokens, json_schema is not None))
            out = {"translations": [{"id": i, "text": "t", "note": ""} for i in replay_key["string_ids"]]}
            return p.ModelResponse(json.dumps(out), model, 1, 1, "live", False, "end_turn")

    a.run_translator(live_state(challenge), Recorder(), challenge)
    assert seen and all(s == (2500, True) for s in seen)

    class Wrapper:                       # pass-through wrapper (like the UI progress wrapper)
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def complete(self, *args, **kw):
            return self._inner.complete(*args, **kw)

    assert a._takes_json_schema(Wrapper(Recorder()))
    scripted = ScriptedProvider([echo_translations()])
    assert not a._takes_json_schema(scripted) and not a._takes_json_schema(Wrapper(scripted))
    a.run_translator(live_state(challenge), Wrapper(scripted), challenge)   # no TypeError


def test_provider_note_reaches_run_log(challenge, provider_config):
    from conftest import FakeResponse, error_body
    sess = SchemaEchoSession()
    first = [FakeResponse(400, error_body("invalid_request_error", "thinking is not supported"))]
    real_post = sess.post
    sess.post = lambda *a_, **k: (sess.calls.append({"json": k.get("json")}) or first.pop()) \
        if first else real_post(*a_, **k)
    prov = p.make_provider("anthropic", "sk-ant-api03-NOTEtest0123456789abcdef", provider_config,
                           p.UsageMeter(40), session=sess, sleep=lambda x: None)
    st = live_state(challenge)
    a.run_translator(st, prov, challenge)
    notes = [e for e in st.history if e["event"] == "provider_note"]
    assert len(notes) == 1 and "thinking" in notes[0]["detail"]
