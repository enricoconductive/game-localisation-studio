import json

import pytest

from src import validation as v

T = {"demo.ui.start": "Investigate",
     "demo.narration.arrival": "Night on Cheung Chau.\nLanterns sway in the wind.",
     "demo.line.granny_greeting": "{player_name}, you're finally here!",
     "demo.line.kit_reply": "Granny, the lanterns are gone!",
     "demo.line.granny_hint": "The paper-craft master will know.",
     "demo.choice.follow": "Follow Granny", "demo.choice.ask": "Ask Kit",
     "demo.ending.a": "You found {lantern_count}/{lantern_total} lanterns.",
     "demo.ui.coins": "Coins: {coins}"}

CRITICAL_CODES = {"invalid_json", "wrong_format", "bad_structure", "unknown_id", "duplicate_id",
                  "missing_id", "empty_text", "placeholder_missing", "placeholder_extra",
                  "placeholder_broken", "too_long", "newline_not_allowed", "bad_encoding",
                  "file_too_large"}
WARNING_CODES = {"untranslated_cjk", "whitespace", "angle_brackets", "near_limit", "missing_id"}


def game_file(strings=None, **over):
    obj = {"format": "lantern-mystery-translation", "schema_version": "1.0", "locale": "en-GB",
           "mission": "demo", "source": "replay", "approved": True,
           "generated_by": "Game Localisation Studio v0.3", "generated_at": "2026-11-01T10:00:00Z",
           "characters": {"granny_wong": "Granny Wong", "kit": "Kit"},
           "strings": dict(T if strings is None else strings)}
    obj.update(over)
    return obj


def codes_for(sid, text, manifest):
    spec = v.spec_from_manifest(manifest, "demo")
    return {i.code for i in v.validate_string(sid, text, spec[sid])}


def test_valid_game_file(manifest):
    rep = v.validate_game_file(json.dumps(game_file(), ensure_ascii=False), manifest,
                               require_all_for_mission="demo")
    assert rep.ok, rep.to_dict()
    assert rep.critical == []
    assert "no blocking" in rep.summary().lower() or "passed" in rep.summary().lower()


def test_missing_id_required_only_for_export(manifest):
    strings = dict(T)
    del strings["demo.choice.ask"]
    rep = v.validate_game_file(game_file(strings), manifest, require_all_for_mission="demo")
    assert [i.string_id for i in rep.critical if i.code == "missing_id"] == ["demo.choice.ask"]
    rep = v.validate_game_file(game_file(strings), manifest)   # game import rule
    assert rep.ok and [(i.severity, i.string_id) for i in rep.issues if i.code == "missing_id"] \
        == [("WARNING", "demo.choice.ask")]


def test_missing_id_warning_uses_mission_field(manifest):
    rep = v.validate_game_file(game_file({}, mission="demo"), manifest)
    assert rep.ok and rep.codes("WARNING").count("missing_id") == len(T)
    assert v.validate_game_file(game_file({}, mission="nope"), manifest).codes() == []


def test_placeholders_listed_without_braces(manifest):
    manifest["strings"]["demo.ui.coins"]["placeholders"] = ["coins"]
    spec = v.spec_from_manifest(manifest, "demo")
    assert spec["demo.ui.coins"].placeholders == ["{coins}"]
    assert v.validate_string("demo.ui.coins", "Coins: {coins}", spec["demo.ui.coins"]) == []


def test_non_string_value_and_locale_not_checked(manifest):
    rep = v.validate_game_file(game_file({**T, "demo.ui.start": 5}, locale="fr-FR"), manifest)
    assert [(i.code, i.string_id) for i in rep.critical] == [("bad_structure", "demo.ui.start")]


@pytest.mark.parametrize("text,expected", [
    ("{player name}, hello", {"placeholder_broken", "placeholder_missing"}),
    ("{player_name, hello", {"placeholder_broken", "placeholder_missing"}),
    ("{玩家名字}, hello", {"placeholder_broken", "placeholder_missing"}),
    ("{Player_Name}, hello", {"placeholder_broken", "placeholder_missing"}),
    ("Hello there, detective!", {"placeholder_missing"}),
    ("{player_name}, {player_name}!", {"placeholder_extra"}),
    ("{player_name}, you have {coins}", {"placeholder_extra"}),
    ("player_name}, hi", {"placeholder_broken", "placeholder_missing"}),
])
def test_broken_placeholders(manifest, text, expected):
    assert expected <= codes_for("demo.line.granny_greeting", text, manifest)


def test_placeholder_order_may_change(manifest):
    assert codes_for("demo.ending.a", "{lantern_total} lanterns; you found {lantern_count}.",
                     manifest) == set()


def test_too_long_message_is_plain_english(manifest):
    spec = v.spec_from_manifest(manifest, "demo")
    issues = v.validate_string("demo.ui.start", "Start investigating", spec["demo.ui.start"])
    tl = [i for i in issues if i.code == "too_long"][0]
    assert tl.severity == "CRITICAL"
    assert "19 characters" in tl.message and "12" in tl.message
    assert tl.fix_hint


def test_near_limit_warning(manifest):
    issues = codes_for("demo.ui.start", "Investigate!", manifest)  # 12/12
    assert issues == {"near_limit"}


def test_newline_rule(manifest):
    assert "newline_not_allowed" in codes_for("demo.line.kit_reply", "Granny!\nGone!", manifest)
    assert codes_for("demo.narration.arrival", "Night.\nLanterns sway.", manifest) == set()
    assert {"newline_not_allowed", "bad_encoding"} <= codes_for("demo.line.kit_reply", "A\rB", manifest)


@pytest.mark.parametrize("text,ok", [
    ("Go 🔍 now", True),
    ("Café", True),                      # combining acute accent
    ("Naïve ñandú", True),
    ("Bad \ud800 text", False),          # lone surrogate
    ("Broken �", False),            # replacement character
    ("Bell \x07", False),                # control character
    ("Tab\there", False),
    ("C1 \x85", False),
])
def test_unicode_and_encoding(manifest, text, ok):
    codes = codes_for("demo.line.kit_reply", text, manifest)
    assert ("bad_encoding" not in codes) == ok


def test_code_points_counted_not_bytes(manifest):
    # 12 code points incl. an emoji and combining mark → fits exactly
    text = "Invéstigat🔍"
    assert len(text) == 12
    assert "too_long" not in codes_for("demo.ui.start", text, manifest)


def test_cjk_is_warning_only(manifest):
    codes = codes_for("demo.line.kit_reply", "婆婆, the lanterns!", manifest)
    assert codes == {"untranslated_cjk"}


def test_whitespace_and_angle_brackets(manifest):
    assert "whitespace" in codes_for("demo.line.kit_reply", " Granny!", manifest)
    assert "whitespace" in codes_for("demo.line.kit_reply", "Granny  gone", manifest)
    assert "angle_brackets" in codes_for("demo.line.kit_reply", "<b>Granny</b>", manifest)


def test_empty_text(manifest):
    assert codes_for("demo.line.kit_reply", "   ", manifest) == {"empty_text"}


def test_duplicate_keys_detected(manifest):
    text = json.dumps(game_file(), ensure_ascii=False)
    text = text.replace('"demo.choice.ask": "Ask Kit"',
                        '"demo.choice.ask": "Ask Kit", "demo.choice.ask": "Ask him"')
    rep = v.validate_game_file(text, manifest)
    assert [i.string_id for i in rep.critical if i.code == "duplicate_id"] == ["demo.choice.ask"]
    with pytest.raises(v.DuplicateKeyError):
        v.parse_json_strict('{"a": 1, "a": 2}')


@pytest.mark.parametrize("text,code", [
    ("{not json", "invalid_json"),
    (json.dumps(game_file(format="other")), "wrong_format"),
    (json.dumps(game_file(schema_version="2.0")), "wrong_format"),
    (json.dumps(game_file(strings=None) | {"strings": ["a"]}), "bad_structure"),
    (json.dumps(game_file({"demo.ui.start": 5})), "bad_structure"),
    (json.dumps(game_file({**T, "demo.ui.nope": "x"})), "unknown_id"),
    (json.dumps(game_file(characters={"granny_wong": "G" * 21})), "bad_structure"),
    (json.dumps(game_file(characters={"stranger": "Bob"})), "bad_structure"),
    (json.dumps(game_file(characters=["Granny"])), "bad_structure"),
])
def test_file_level_critical(manifest, text, code):
    rep = v.validate_game_file(text, manifest)
    assert code in rep.codes("CRITICAL")


def test_file_too_large_and_bad_bytes(manifest):
    big = json.dumps(game_file()) + " " * (101 * 1024)
    assert v.validate_game_file(big, manifest).codes() == ["file_too_large"]
    assert v.validate_game_file("é".encode("latin-1") * 10, manifest).codes() == ["bad_encoding"]
    bom = "﻿".encode() + json.dumps(game_file()).encode("utf-8")
    assert v.validate_game_file(bom, manifest).ok


def test_lone_surrogate_from_json_escape(manifest):
    text = json.dumps(game_file()).replace("Ask Kit", "Ask \\ud800 Kit")
    assert "bad_encoding" in v.validate_game_file(text, manifest).codes("CRITICAL")


def test_issue_shape_and_codes_match_contract(manifest):
    strings = {**T, "demo.ui.start": " Start investigating <now>\n{x"}
    rep = v.validate_game_file(game_file(strings), manifest, require_all_for_mission="demo")
    for i in rep.issues:
        d = i.to_dict()
        assert set(d) == {"severity", "code", "string_id", "message", "fix_hint"}
        assert d["message"] and d["fix_hint"]
        assert i.code in (CRITICAL_CODES if i.severity == "CRITICAL" else WARNING_CODES)


def test_extract_placeholders():
    assert v.extract_placeholders("{a} and {b_2} but not {C} or {x y}") == ["{a}", "{b_2}"]


def test_challenge_and_manifest_specs_agree(challenge, manifest):
    a, b = v.spec_from_challenge(challenge), v.spec_from_manifest(manifest, "demo")
    assert a.keys() == b.keys()
    for sid in a:
        for f in ("type", "speaker", "placeholders", "max_len", "allow_newlines"):
            assert getattr(a[sid], f) == getattr(b[sid], f)


def test_validate_translations_unknown_and_missing(challenge):
    spec = v.spec_from_challenge(challenge)
    rep = v.validate_translations({"demo.ui.start": "Go", "zzz.x.y": "?"}, spec)
    assert "unknown_id" in rep.codes() and rep.codes().count("missing_id") == len(spec) - 1


def test_unicode_whitespace_matches_javascript():
    """U+FEFF, no-break and ideographic spaces at the ends are a `whitespace` WARNING, as in
    validator.js (JavaScript's \\s); a zero-width space is not whitespace in either."""
    spec = v.StringSpec("a.b.c", max_len=40)
    for text in ("Hello﻿", "﻿Hello", "Hello ", "　Hello", "Hi "):
        assert "whitespace" in [i.code for i in v.validate_string("a.b.c", text, spec)], repr(text)
    assert "whitespace" not in [i.code for i in v.validate_string("a.b.c", "Hello​", spec)]
    assert [i.code for i in v.validate_string("a.b.c", "﻿", spec)] == ["empty_text"]
