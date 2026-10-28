"""Replay prompt variants, translator presets, prepared outputs and checkpoints (CONTRACTS §8, §15).

Everything here runs offline: the full-workflow tests use the ``no_network`` fixture.
The verdicts for the prepared findings (``teaching_notes``) live in the private instructor
pack; tests that need them are skipped when it is absent (``conftest.instructor_pack_dir``).
"""
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from src import agents as a, exports as ex, project_state as ps, providers as p, validation as v
from conftest import PACK_SKIP, load_fx, load_teaching_notes

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "fixtures" / "replay_outputs.json"
CHECKPOINTS = ROOT / "fixtures" / "checkpoints"
LABEL = "SIMULATED OUTPUT — prepared in advance by the course team. Not generated live."
MISSIONS = {"intro": ("introductory", 8), "voice": ("character_voice", 8),
            "pun": ("pun_boss", 6), "ui": ("interface_trap", 7)}
VARIANTS = a.PRESET_ORDER
VERDICTS = {"good", "debatable", "wrong"}
SEV_ORDER = {"critical": 0, "major": 1, "minor": 2}

# CRITICAL validation codes each prepared translator variant is meant to produce (§15).
EXPECTED_CRITICAL = {
    ("intro", "faithful"): {("intro.ui.start", "too_long")},
    ("ui", "faithful"): {("ui.choice.use", "too_long")},
    ("ui", "balanced"): {("ui.hud.inventory", "too_long")},
    ("ui", "creative"): {("ui.hud.status", "newline_not_allowed"),
                         ("ui.hud.toast", "placeholder_broken"),
                         ("ui.hud.toast", "placeholder_missing"),
                         ("ui.ending.b", "placeholder_missing")},
}
CASES = [(m, var) for m in MISSIONS for var in VARIANTS]


@pytest.fixture(scope="module")
def fixtures():
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def challenges():
    return {m: json.loads((ROOT / "challenges" / f"{f}.json").read_text(encoding="utf-8"))
            for m, (f, _) in MISSIONS.items()}


@pytest.fixture(scope="module")
def manifest():
    return v.load_manifest()


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for x in obj.values():
            yield from _walk_strings(x)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk_strings(x)


def _crit(translations, challenge):
    rep = v.validate_translations(translations, v.spec_from_challenge(challenge), require_all=True)
    return {(i.string_id, i.code) for i in rep.critical}


# ----------------------------------------------------------------- presets


def test_presets_shape_and_balanced_is_default():
    assert a.PRESET_ORDER == ("faithful", "balanced", "creative")
    assert set(a.TRANSLATOR_PRESETS) == set(a.PRESET_ORDER)
    for name, pr in a.TRANSLATOR_PRESETS.items():
        assert pr["label"] and pr["description"] and len(pr["instructions"]) > 200
        assert a.normalise_settings("translator", pr["settings"]) == pr["settings"], name
        assert "placeholder" in pr["instructions"].lower()
    bal = a.TRANSLATOR_PRESETS["balanced"]
    assert bal["settings"] == a.default_settings("translator")
    assert bal["instructions"] == a.DEFAULT_TRANSLATOR_INSTRUCTIONS
    f, c = a.TRANSLATOR_PRESETS["faithful"]["settings"], a.TRANSLATOR_PRESETS["creative"]["settings"]
    assert f["strategy"] < 3 < c["strategy"] and f["voice_strength"] < c["voice_strength"]
    assert f["glossary_strictness"] == "must_use"
    cfg = a.default_agent_config("translator")
    assert cfg["preset"] == "balanced" and cfg["edited"] is False
    assert "preset" not in a.default_agent_config("reviewer")     # the reviewer has no presets


def test_apply_preset_mark_edited_and_note(challenge):
    cfg = a.default_agent_config("translator")
    assert a.apply_preset(cfg, "faithful") is cfg
    assert cfg["settings"] == a.TRANSLATOR_PRESETS["faithful"]["settings"]
    assert cfg["instructions"] == a.FAITHFUL_TRANSLATOR_INSTRUCTIONS
    assert cfg["preset"] == "faithful" and cfg["edited"] is False
    assert cfg["default_instructions"] == a.DEFAULT_TRANSLATOR_INSTRUCTIONS
    assert a.mark_edited(cfg)["edited"] is False
    note = a.replay_variant_note(cfg)
    assert "‘Faithful’ preset" in note and "Live Mode" not in note
    cfg["settings"]["voice_strength"] = 4
    assert a.mark_edited(cfg)["edited"] is True
    assert a.replay_variant_note(cfg) == (
        "Prepared output for the ‘Faithful’ preset. Your own edits are saved in your prompt and "
        "report, but Replay Mode cannot generate a new response — switch to Live Mode to test them.")
    a.apply_preset(cfg, "faithful")
    cfg["instructions"] += "\n- Use British slang for Kit."
    assert a.mark_edited(cfg)["edited"] is True
    with pytest.raises(ps.StudioError):
        a.apply_preset(cfg, "wild")
    # the preset's text really reaches the prompt
    a.apply_preset(cfg, "creative")
    _, user = a.build_translator_prompt(challenge, cfg, "en-GB", [])
    assert a.CREATIVE_TRANSLATOR_INSTRUCTIONS in user and "Translation strategy 5/5" in user


def test_preset_instructions_do_not_leak_the_reference():
    reference = json.loads((ROOT / "game" / "translations" / "en.reference.json")
                           .read_text(encoding="utf-8"))["strings"]
    def grams(t, n=6):
        w = re.findall(r"[a-z0-9'{}_]+", t.lower())
        return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}
    for pr in a.TRANSLATOR_PRESETS.values():
        for ref in reference.values():
            assert not grams(ref) & grams(pr["instructions"])


def test_old_configs_without_preset_fields_still_work(state):
    cfg = state.agents["translator"]
    del cfg["preset"], cfg["edited"]
    assert a._preset_name(cfg) == "balanced"
    assert "‘Balanced’" in a.replay_variant_note(cfg)
    assert a.mark_edited(cfg)["edited"] is False and cfg["preset"] == "balanced"


def test_version_variant_and_agent_config_round_trip(state, replay, challenge, tmp_path):
    a.apply_preset(state.agents["translator"], "creative")
    vers = a.run_translator(state, replay, challenge)
    assert vers.variant == "creative"
    path = tmp_path / "s.json"
    ps.save_state(state, path)
    back = ps.load_state(path)
    assert back.current_version().variant == "creative"
    assert back.agents["translator"]["preset"] == "creative"
    assert back.agents["translator"]["edited"] is False
    assert back.to_dict() == state.to_dict()
    old = state.to_dict()
    for x in old["versions"]:
        x.pop("variant")
    assert ps.ProjectState.from_dict(old).current_version().variant is None


# ----------------------------------------------------------------- fixture structure


def test_fixture_top_level(fixtures):
    assert fixtures["label"] == LABEL
    assert fixtures["schema_version"] == "1.0"
    assert set(fixtures["challenges"]) == set(MISSIONS)
    assert "teaching_notes" not in fixtures, "the answer key belongs in the private instructor pack"
    for m, entry in fixtures["challenges"].items():
        assert set(entry) == {"baseline", "translator_variants", "reviewer", "reviewer_round2",
                              "revision_notes"}, m
        for stage in ("translator_variants", "reviewer", "reviewer_round2"):
            assert set(entry[stage]) == set(VARIANTS), (m, stage)


@pytest.mark.parametrize("mission", MISSIONS)
def test_fixture_translations_parse_and_cover_every_id(fixtures, challenges, mission):
    ch = challenges[mission]
    ids = [s["id"] for s in ch["strings"]]
    assert len(ids) == MISSIONS[mission][1]
    entry = fixtures["challenges"][mission]
    outputs = [entry["baseline"]] + [entry["translator_variants"][x] for x in VARIANTS]
    for out in outputs:
        items = a.parse_translations(json.dumps(out, ensure_ascii=False), ids)
        assert [i["id"] for i in items] == ids
        assert all(i["text"].strip() for i in items)
    assert set(entry["revision_notes"]) == set(ids)
    texts = {x: {t["id"]: t["text"] for t in entry["translator_variants"][x]["translations"]}
             for x in VARIANTS}
    for sid in ids:   # the variants are really different from each other
        assert len({texts[x][sid] for x in VARIANTS}) >= 2, sid
    assert sum(len({texts[x][sid] for x in VARIANTS}) == 3 for sid in ids) >= len(ids) - 2


@pytest.mark.parametrize("mission,variant", CASES)
def test_fixture_findings_parse(fixtures, challenges, mission, variant):
    ch = challenges[mission]
    ids = [s["id"] for s in ch["strings"]]
    spec = v.spec_from_challenge(ch)
    entry = fixtures["challenges"][mission]
    for stage in ("reviewer", "reviewer_round2"):
        raw = entry[stage][variant]
        assert raw["overall_comment"].strip()
        for f in raw["findings"]:
            assert f["category"] in a.CATEGORIES and f["severity"] in a.SEVERITIES
            assert f["string_id"] in ids and f["issue"] and f["reasoning"] and f["suggestion"]
        found, dropped = a.parse_findings(json.dumps(raw, ensure_ascii=False), ids)
        assert dropped == 0 and len(found) == len(raw["findings"])
    r1 = entry["reviewer"][variant]["findings"]
    assert 3 <= len(r1) <= 6
    sev = [SEV_ORDER[f["severity"]] for f in r1]
    assert sev == sorted(sev), "ordered by severity so the engine's R1-xx ids match the notes"
    assert 1 <= len(entry["reviewer_round2"][variant]["findings"]) <= 3
    for r2 in entry["reviewer_round2"][variant]["findings"]:
        assert not v.validate_translations({r2["string_id"]: r2["suggestion"]}, spec,
                                           require_all=False).critical


@pytest.mark.parametrize("mission,variant", CASES)
def test_teaching_notes_match_fixture_findings(fixtures, teaching_notes, challenges, mission, variant):
    ch = challenges[mission]
    spec = v.spec_from_challenge(ch)
    entry = fixtures["challenges"][mission]
    notes = teaching_notes[mission]["variants"][variant]
    r1 = entry["reviewer"][variant]["findings"]
    tn = notes["findings"]
    assert len(tn) == len(r1)
    for n, (f, note) in enumerate(zip(r1, tn), 1):
        assert note["finding_id"] == f"R1-{n:02d}" and note["fixture_index"] == n - 1
        assert note["string_id"] == f["string_id"] and note["verdict"] in VERDICTS
        assert note["recommended_action"] in ("accept", "reject", "override") and note["why"]
        if note["verdict"] == "good":
            assert note["recommended_action"] == "accept"
        if note["verdict"] in ("good", "debatable"):
            assert not _crit({f["string_id"]: f["suggestion"]},
                             {"strings": [s for s in ch["strings"] if s["id"] == f["string_id"]]})
        if note["recommended_action"] == "override":
            assert note["override_text"] and not v.validate_translations(
                {f["string_id"]: note["override_text"]}, spec, require_all=False).critical
    verdicts = Counter(x["verdict"] for x in tn)
    assert verdicts["good"] >= 2 and verdicts["wrong"] >= 1, verdicts
    good_ids = [x["string_id"] for x in tn if x["verdict"] == "good"]
    assert len(good_ids) == len(set(good_ids)), "at most one good finding per string"
    assert set(teaching_notes) == set(MISSIONS)
    assert len(notes["round2"]) == len(entry["reviewer_round2"][variant]["findings"])


@pytest.mark.parametrize("mission,variant", CASES)
def test_translator_variant_critical_codes(fixtures, challenges, mission, variant):
    tr = {t["id"]: t["text"] for t in
          fixtures["challenges"][mission]["translator_variants"][variant]["translations"]}
    expected = EXPECTED_CRITICAL.get((mission, variant), set())
    assert _crit(tr, challenges[mission]) == expected


@pytest.mark.parametrize("mission,variant", CASES)
def test_teaching_notes_expected_critical(teaching_notes, mission, variant):
    noted = {(x["string_id"], x["code"]) for x in
             teaching_notes[mission]["variants"][variant]["expected_critical"]}
    assert noted == EXPECTED_CRITICAL.get((mission, variant), set())


def test_ui_variants_trigger_the_interface_trap(fixtures, challenges):
    codes = {var: {c for _, c in _crit(
        {t["id"]: t["text"] for t in fixtures["challenges"]["ui"]["translator_variants"][var]["translations"]},
        challenges["ui"])} for var in VARIANTS}
    assert codes["faithful"] == {"too_long"}                       # overlong button
    assert {"placeholder_broken", "newline_not_allowed", "placeholder_missing"} <= codes["creative"]
    creative = {t["id"]: t["text"] for t in fixtures["challenges"]["ui"]["translator_variants"]["creative"]["translations"]}
    assert "{player name}" in creative["ui.hud.toast"] and "\n" in creative["ui.hud.status"]


def test_placeholders_preserved_outside_the_ui_traps(fixtures, challenges):
    for m, ch in challenges.items():
        spec = v.spec_from_challenge(ch)
        for var in VARIANTS:
            for t in fixtures["challenges"][m]["translator_variants"][var]["translations"]:
                if (t["id"], "placeholder_missing") in EXPECTED_CRITICAL.get((m, var), set()):
                    continue
                assert Counter(v.extract_placeholders(t["text"])) == Counter(spec[t["id"]].placeholders), t["id"]


def test_baseline_shows_typical_machine_translation_errors(fixtures):
    base = " ".join(t["text"] for m in MISSIONS for t in fixtures["challenges"][m]["baseline"]["translations"])
    for err in ("tea restaurant", "Sister Chang'e", "rabbit's tail — cannot be long", "Osmanthus Street",
                "Grandma", "clock in", "Guess one character", "{玩家名稱}"):
        assert err in base, err


def test_no_fixture_string_equals_a_reference_string(fixtures):
    reference = json.loads((ROOT / "game" / "translations" / "en.reference.json")
                           .read_text(encoding="utf-8"))["strings"]
    norm = lambda s: re.sub(r"\s+", " ", s).strip().casefold()  # noqa: E731
    refs = {norm(s) for s in reference.values()}
    hits = [s for s in _walk_strings(fixtures) if norm(s) in refs]
    assert hits == []


def test_fixture_english_is_british(fixtures):
    text = " ".join(_walk_strings(fixtures["challenges"]))
    for us in ("color", "favorite", "realize", "neighbor", "center "):
        assert us not in text.lower(), us


# ----------------------------------------------------------------- ReplayProvider variants


def test_replay_provider_selects_variant_by_key(fixtures):
    r = p.ReplayProvider(fixtures)
    ok, msg = r.test_connection()
    assert ok and "4 prepared" in msg
    for var in VARIANTS:
        resp = r.complete("S", "U", replay_key={"challenge": "intro", "stage": "translator",
                                                "variant": var})
        expected = fixtures["challenges"]["intro"]["translator_variants"][var]["translations"]
        assert json.loads(resp.text)["translations"] == expected and resp.simulated
        rv = r.complete("S", "U", replay_key={"challenge": "intro", "stage": "reviewer", "round": 1,
                                              "variant": var})
        assert json.loads(rv.text) == fixtures["challenges"]["intro"]["reviewer"][var]
        r2 = r.complete("S", "U", replay_key={"challenge": "intro", "stage": "reviewer", "round": 2,
                                              "variant": var})
        assert json.loads(r2.text) == fixtures["challenges"]["intro"]["reviewer_round2"][var]
    default = r.complete("S", "U", replay_key={"challenge": "intro", "stage": "translator"})
    odd = r.complete("S", "U", replay_key={"challenge": "intro", "stage": "translator", "variant": "wild"})
    bal = fixtures["challenges"]["intro"]["translator_variants"]["balanced"]["translations"]
    assert json.loads(default.text)["translations"] == bal == json.loads(odd.text)["translations"]
    for stage in ("teaching_notes", "translator_variants", "revision_notes"):
        with pytest.raises(p.ProviderError):
            r.complete("S", "U", replay_key={"challenge": "intro", "stage": stage})
    assert "teaching" not in default.text and "verdict" not in default.text


def test_replay_provider_backward_compatible_with_single_entries(replay_fixtures):
    r = p.ReplayProvider(replay_fixtures)            # tests/fixtures_synthetic: old shape
    for var in (None, "faithful", "creative"):
        key = {"challenge": "demo", "stage": "translator"}
        if var:
            key["variant"] = var
        out = json.loads(r.complete("S", "U", replay_key=key).text)
        assert out == replay_fixtures["challenges"]["demo"]["translator"]
        rv = json.loads(r.complete("S", "U", replay_key={"challenge": "demo", "stage": "reviewer",
                                                          "round": 1, "variant": var}).text)
        assert rv == replay_fixtures["challenges"]["demo"]["reviewer"]


def test_old_fixture_runs_with_any_preset(challenge, replay_fixtures):
    st = ps.new_project(challenge, "en-GB", "replay", "replay", "replay")
    a.apply_preset(st.agents["translator"], "faithful")
    prov = p.ReplayProvider(replay_fixtures)
    vers = a.run_translator(st, prov, challenge)
    assert vers.variant == "faithful" and vers.label == "Translator · Replay · Faithful preset"
    assert vers.translations["demo.ui.start"] == "Investigate"
    assert a.run_reviewer(st, prov, challenge)


def test_edited_preset_serves_the_preset_variant_with_label(no_network, fixtures, challenges):
    ch = challenges["intro"]
    st = ps.new_project(ch, "en-GB", "replay", "replay", "replay")
    cfg = st.agents["translator"]
    a.apply_preset(cfg, "creative")
    cfg["instructions"] += "\n- Keep Chang'e in every line that mentions the moon."
    a.mark_edited(cfg)
    assert cfg["edited"] is True
    prov = p.make_provider("replay", "", p.load_provider_config(), fixtures=fixtures)
    vers = a.run_translator(st, prov, ch)
    want = {t["id"]: t["text"] for t in fixtures["challenges"]["intro"]["translator_variants"]["creative"]["translations"]}
    assert vers.translations == want and vers.variant == "creative"
    assert vers.label.startswith("Translator · Replay · Creative preset") and "edits" in vers.label
    assert any(h["event"] == "replay_variant" and h["detail"] == a.replay_variant_note(cfg)
               for h in st.history)
    snap = [s for s in st.prompt_snapshots if s.agent == "translator"][-1]
    assert "Keep Chang'e in every line" in snap.user and snap.source == "replay"   # edits are saved
    # the reviewer follows the variant of the version under review, even after a human edit
    ps.direct_edit(st, {"intro.ui.start": "Let's go"}, "director")
    a.apply_preset(cfg, "faithful")                     # changing the preset later does not matter
    found = a.run_reviewer(st, prov, ch)
    want_issues = [f["issue"] for f in fixtures["challenges"]["intro"]["reviewer"]["creative"]["findings"]]
    assert [f.issue for f in found] == want_issues


def test_unedited_label_for_each_preset(fixtures, challenges):
    prov = p.ReplayProvider(fixtures)
    for var in VARIANTS:
        st = ps.new_project(challenges["voice"], "en-GB", "replay", "replay", "replay")
        a.apply_preset(st.agents["translator"], var)
        vers = a.run_translator(st, prov, challenges["voice"])
        assert vers.label == f"Translator · Replay · {a.TRANSLATOR_PRESETS[var]['label']} preset"


# ----------------------------------------------------------------- full workflow


def _run_to_review(ch, fixtures, variant):
    prov = p.make_provider("replay", "", p.load_provider_config(), fixtures=fixtures)
    st = ps.new_project(ch, "en-GB", "replay", "replay", "replay")
    a.apply_preset(st.agents["translator"], variant)
    a.run_baseline(st, prov, ch)
    a.run_translator(st, prov, ch)
    found = a.run_reviewer(st, prov, ch)
    return st, prov, found


def _apply_notes(st, notes, debatable="recommended"):
    for n in notes["findings"]:
        fid, act = n["finding_id"], n["recommended_action"]
        if n["verdict"] == "debatable" and debatable != "recommended":
            act = debatable
        if act == "override":
            ps.decide_finding(st, fid, "override", "director", human_text=n["override_text"],
                              comment="Reviewer's fix is wrong; using our own text.")
        else:
            ps.decide_finding(st, fid, act, "director", comment=n["why"][:200])


@pytest.mark.parametrize("debatable", ["recommended", "accept"])
@pytest.mark.parametrize("mission,variant", CASES)
def test_full_replay_workflow(no_network, fixtures, teaching_notes, challenges, manifest, tmp_path,
                              mission, variant, debatable):
    ch = challenges[mission]
    st, prov, found = _run_to_review(ch, fixtures, variant)
    raw = fixtures["challenges"][mission]["reviewer"][variant]["findings"]
    notes = teaching_notes[mission]["variants"][variant]
    # engine ids match the teaching notes
    assert [(f.finding_id, f.string_id, f.suggestion) for f in found] == \
        [(n["finding_id"], n["string_id"], r["suggestion"]) for n, r in zip(notes["findings"], raw)]
    assert st.current_version().variant == variant
    assert _crit(st.current_version().translations, ch) == EXPECTED_CRITICAL.get((mission, variant), set())
    _apply_notes(st, notes, debatable)
    rev = a.run_revision(st, prov, ch)
    assert rev.variant == variant and rev.source == "replay"
    assert ps.validate_current(st).ok, ps.validate_current(st).summary()
    decided = {d.string_id for d in st.latest_decisions().values() if d.action != "reject"}
    for n in notes["findings"]:                          # rejected suggestions were never applied
        if n["recommended_action"] == "reject" and n["string_id"] not in decided:
            assert rev.translations[n["string_id"]] == st.version(rev.parent_id).translations[n["string_id"]]
    round2 = a.run_reviewer(st, prov, ch)                # only strings that changed are reviewed
    changed = {sid for sid, t in rev.translations.items()
               if t != st.version(rev.parent_id).translations[sid]}
    assert all(f.string_id in changed and f.finding_id.startswith("R2-") for f in round2)
    ps.approve_final(st, "director")
    ok, reasons = ps.can_export(st)
    assert ok, reasons
    res = ex.export_all(st, ch, manifest, tmp_path)
    assert all(r.ok for r in res.values())
    game = json.loads(Path(res["game_translation"].path).read_text(encoding="utf-8"))
    assert game["source"] == "replay" and v.validate_game_file(game, manifest, mission).ok


@pytest.mark.parametrize("mission,variant", CASES)
def test_accepting_wrong_findings_is_caught_later(no_network, fixtures, challenges, mission, variant):
    """Accept everything: broken suggestions fail validation and round 2 flags them."""
    ch = challenges[mission]
    st, prov, found = _run_to_review(ch, fixtures, variant)
    ps.bulk_decide(st, [f.finding_id for f in found], "accept", "director")
    a.run_revision(st, prov, ch)
    crit = _crit(st.current_version().translations, ch)
    raw = fixtures["challenges"][mission]["reviewer"][variant]["findings"]
    last = {}
    for f in raw:
        last[f["string_id"]] = f["suggestion"]           # the last accepted suggestion wins
    for sid, sugg in last.items():
        assert st.current_version().translations[sid] == sugg
        broken = _crit({sid: sugg}, {"strings": [s for s in ch["strings"] if s["id"] == sid]})
        assert broken <= crit
    round2 = {f.string_id for f in a.run_reviewer(st, prov, ch)}
    notes = load_teaching_notes()                         # optional: only in the instructor pack
    for r in (notes[mission]["variants"][variant]["round2"] if notes else ()):
        if r["appears"].startswith("only if"):
            assert r["string_id"] in round2, r


# ----------------------------------------------------------------- checkpoints


def _load_tool():
    spec = importlib.util.spec_from_file_location("make_checkpoints", ROOT / "tools" / "make_checkpoints.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strip_times(obj):
    if isinstance(obj, dict):
        return {k: _strip_times(x) for k, x in obj.items() if not k.endswith("_at")}
    if isinstance(obj, list):
        return [_strip_times(x) for x in obj]
    return obj


CHECKPOINT_NAMES = ("intro_after_agents", "intro_after_review", "intro_after_revision")


@pytest.mark.parametrize("name", CHECKPOINT_NAMES)
def test_checkpoint_loads_and_is_safe(name):
    path = CHECKPOINTS / f"{name}.json"
    text = path.read_text(encoding="utf-8")
    assert p.find_secrets(text) == []
    st = ps.load_state(path)
    assert st.mode == "replay" and st.provider["name"] == "replay" and st.challenge_id == "intro"
    assert st.locale == "en-GB" and not st.approval["approved"]
    assert st.baseline_version().kind == "baseline"
    assert st.current_version().variant == "balanced"
    assert st.agents["translator"]["preset"] == "balanced"
    assert st.usage["requests"] == 0
    expected = {"intro_after_agents": ("TRANSLATED", 0, 0),
                "intro_after_review": ("REVIEWED", 6, 0),
                "intro_after_revision": ("REVISED", 6, 6)}[name]
    assert (st.stage, len(st.findings), len(st.latest_decisions())) == expected


def test_revision_checkpoint_has_sample_decisions():
    st = ps.load_state(CHECKPOINTS / "intro_after_revision.json")
    actions = Counter(d.action for d in st.latest_decisions().values())
    assert actions["accept"] >= 2 and actions["reject"] == 1 and actions["override"] == 1
    ov = next(d for d in st.decisions if d.action == "override")
    assert ov.comment and ov.human_text
    assert len(st.memory_rules) == 1 and st.memory_rules[0].from_finding
    assert st.revision["cycles_done"] == 1 and st.current_version().kind == "revision"
    assert ps.validate_current(st).ok


def test_checkpoints_are_up_to_date(fixtures):
    """The committed files equal a fresh run of tools/make_checkpoints.py (timestamps aside)."""
    states = _load_tool().build_states(fixtures)
    assert tuple(states) == CHECKPOINT_NAMES
    labels = _load_tool().LABELS
    for name, st in states.items():
        saved = json.loads((CHECKPOINTS / f"{name}.json").read_text(encoding="utf-8"))
        assert saved.pop("checkpoint_label") == labels[name]
        assert _strip_times(saved) == _strip_times(st.to_dict()), name


@pytest.mark.parametrize("name", CHECKPOINT_NAMES)
def test_checkpoint_replays_forward_to_export(no_network, fixtures, challenges, manifest, tmp_path, name):
    ch = challenges["intro"]
    st = ps.load_state(CHECKPOINTS / f"{name}.json")
    prov = p.make_provider("replay", "", p.load_provider_config(), fixtures=fixtures)
    if name == "intro_after_agents":
        a.run_reviewer(st, prov, ch)
    if name != "intro_after_revision":
        notes = load_teaching_notes()
        if notes is None:
            pytest.skip(PACK_SKIP)
        _apply_notes(st, notes["intro"]["variants"]["balanced"])
        a.run_revision(st, prov, ch)
    ps.set_reflection(st, "Kit kept his slang; the saying now works in English.")
    ps.approve_final(st, "director")
    res = ex.export_all(st, ch, manifest, tmp_path)
    assert all(r.ok for r in res.values()), {k: r.message for k, r in res.items()}
    assert (tmp_path / "game_translation_en.json").exists()
