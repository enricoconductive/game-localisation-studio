"""Consistency tests for the game content (manifest, story graph, zh-Hant source, challenge files).

Standard library + pytest only. Does not import src/* on purpose.
Instructor notes live in the private instructor pack; the tests that need them are skipped
when the pack is not available (see ``conftest.instructor_pack_dir``).
"""
import json
import re
from collections import Counter, deque
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "game" / "strings_manifest.json"
STORY_PATH = ROOT / "game" / "story.json"
ZH_PATH = ROOT / "game" / "translations" / "zh-Hant.json"

ID_RE = re.compile(r"^[a-z]+\.[a-z_]+\.[a-z0-9_]+$")
PLACEHOLDER_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")
CJK_RE = re.compile(r"[㐀-鿿]")
ALLOWED_PLACEHOLDERS = {"{player_name}", "{lantern_count}", "{lantern_total}", "{coins}", "{item_name}"}
STRING_TYPES = {"ui", "narration", "dialogue", "choice", "ending"}
NODE_KINDS = {"title", "line", "choice", "ending", "hud"}
FOCUS_TAGS = {"character_voice", "cultural", "humour", "wordplay", "ambiguity", "variable",
              "ui_constraint", "choice", "formatting", "terminology"}

MISSION_SIZES = {"intro": (8, 8), "voice": (6, 8), "pun": (5, 7), "ui": (6, 8)}
CHALLENGE_FILES = {
    "intro": "challenges/introductory.json",
    "voice": "challenges/character_voice.json",
    "pun": "challenges/pun_boss.json",
    "ui": "challenges/interface_trap.json",
}
# Each entry is a set of alternatives: at least one tag of each set must appear in the mission.
REQUIRED_FOCUS = {
    "intro": [{"character_voice"}, {"cultural"}, {"humour", "ambiguity"}, {"variable"},
              {"ui_constraint"}, {"choice"}],
    "voice": [{"character_voice"}, {"choice"}],
    "pun": [{"wordplay"}, {"humour"}, {"cultural"}, {"choice"}],
    "ui": [{"ui_constraint"}, {"variable"}, {"formatting"}, {"choice"}],
}
CHALLENGE_KEYS = {"schema_version", "id", "mission", "title", "title_zh", "estimated_minutes", "brief",
                  "teaching_objectives", "scene_context", "characters", "glossary", "strings"}
CHALLENGE_STRING_KEYS = {"id", "source", "type", "speaker", "context", "intended_meaning", "constraints",
                         "placeholders", "max_len", "allow_newlines", "focus"}
NOTES_KEYS = {"discussion_points", "defensible_solutions", "deliberate_traps", "common_ai_errors"}
CHARACTER_KEYS = {"id", "name_zh", "name_en_suggestion", "profile", "voice", "relationships"}
GLOSSARY_KEYS = {"source", "target", "strictness"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest():
    return load(MANIFEST_PATH)


@pytest.fixture(scope="module")
def story():
    return load(STORY_PATH)


@pytest.fixture(scope="module")
def zh():
    return load(ZH_PATH)


@pytest.fixture(scope="module")
def challenges():
    return {m: load(ROOT / f) for m, f in CHALLENGE_FILES.items()}


def mission_ids(manifest, mission):
    return next(m["string_ids"] for m in manifest["missions"] if m["id"] == mission)


# --------------------------------------------------------------------------- parsing

@pytest.mark.parametrize("path", [MANIFEST_PATH, STORY_PATH, ZH_PATH] + [ROOT / f for f in CHALLENGE_FILES.values()])
def test_file_parses_as_utf8_json_without_duplicate_keys(path):
    def no_dupes(pairs):
        keys = [k for k, _ in pairs]
        dupes = [k for k, n in Counter(keys).items() if n > 1]
        assert not dupes, f"duplicate keys {dupes} in {path.name}"
        return dict(pairs)

    json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dupes)


# --------------------------------------------------------------------------- manifest

def test_manifest_header(manifest):
    assert manifest["schema_version"] == "1.0"
    assert manifest["game"] == "lantern-mystery"
    assert manifest["source_locale"] == "zh-Hant-HK"
    assert {"granny_wong", "kit", "riddle_king"} <= set(manifest["characters"])
    for key, c in manifest["characters"].items():
        assert c["name_zh"] and c["name_en_default"], key
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", c["colour"]), key


def test_manifest_missions(manifest):
    assert [m["id"] for m in manifest["missions"]] == list(CHALLENGE_FILES)
    for m in manifest["missions"]:
        assert m["challenge_file"] == CHALLENGE_FILES[m["id"]]
        assert m["title_zh"] and m["title_en"]
        lo, hi = MISSION_SIZES[m["id"]]
        assert lo <= len(m["string_ids"]) <= hi, m["id"]
        assert len(set(m["string_ids"])) == len(m["string_ids"])


def test_intro_has_exactly_eight_strings(manifest):
    assert len(mission_ids(manifest, "intro")) == 8


def test_manifest_string_ids_and_fields(manifest):
    all_listed = [sid for m in manifest["missions"] for sid in m["string_ids"]]
    assert sorted(all_listed) == sorted(manifest["strings"]), "mission string_ids must cover all manifest strings"
    for sid, spec in manifest["strings"].items():
        assert ID_RE.match(sid), sid
        assert sid.split(".")[0] == spec["mission"], sid
        assert sid in mission_ids(manifest, spec["mission"])
        assert spec["type"] in STRING_TYPES, sid
        assert spec["speaker"] is None or spec["speaker"] in manifest["characters"], sid
        if spec["type"] == "dialogue":
            assert spec["speaker"] is not None, f"{sid}: dialogue needs a speaker"
        else:
            assert spec["speaker"] is None, f"{sid}: only dialogue has a speaker"
        assert spec["max_len"] is None or (isinstance(spec["max_len"], int) and spec["max_len"] > 0), sid
        if spec["type"] in ("ui", "choice"):
            assert spec["max_len"], f"{sid}: UI and choice strings need max_len"
        assert isinstance(spec["allow_newlines"], bool), sid
        assert isinstance(spec["placeholders"], list), sid


# --------------------------------------------------------------------------- zh-Hant source

def test_zh_envelope(zh):
    assert zh["format"] == "lantern-mystery-translation"
    assert zh["schema_version"].split(".")[0] == "1"
    assert zh["locale"] == "zh-Hant-HK"
    assert zh["source"] == "original"


def test_zh_has_every_id_with_chinese_text(manifest, zh):
    assert set(zh["strings"]) == set(manifest["strings"])
    for sid, text in zh["strings"].items():
        assert isinstance(text, str) and text.strip(), sid
        assert CJK_RE.search(text), f"{sid}: source has no CJK"
        assert text == text.strip(), f"{sid}: leading/trailing whitespace"
        if not manifest["strings"][sid]["allow_newlines"]:
            assert "\n" not in text and "\r" not in text, f"{sid}: newline in single-line string"


def test_placeholders_match_manifest(manifest, zh):
    for sid, text in zh["strings"].items():
        found = PLACEHOLDER_RE.findall(text)
        assert Counter(found) == Counter(manifest["strings"][sid]["placeholders"]), sid
        assert all(n == 1 for n in Counter(found).values()), f"{sid}: placeholder repeated"
        assert set(found) <= ALLOWED_PLACEHOLDERS, sid
        stripped = PLACEHOLDER_RE.sub("", text)
        assert "{" not in stripped and "}" not in stripped, f"{sid}: stray brace"


# --------------------------------------------------------------------------- challenges

@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_challenge_structure(mission, challenges, manifest):
    ch = challenges[mission]
    assert CHALLENGE_KEYS <= set(ch), CHALLENGE_KEYS - set(ch)
    assert ch["schema_version"] == "1.0"
    assert ch["id"] == mission and ch["mission"] == mission
    assert isinstance(ch["estimated_minutes"], int) and ch["estimated_minutes"] > 0
    assert ch["brief"].strip() and ch["scene_context"].strip()
    assert 3 <= len(ch["teaching_objectives"]) <= 5
    assert 3 <= len(ch["glossary"]) <= 6
    for g in ch["glossary"]:
        assert GLOSSARY_KEYS <= set(g), g
    assert ch["characters"]
    for c in ch["characters"]:
        assert CHARACTER_KEYS <= set(c), c
        assert c["id"] in manifest["characters"]
        assert c["name_zh"] == manifest["characters"][c["id"]]["name_zh"]
    assert "instructor_notes" not in ch, "instructor notes belong in the private instructor pack"


def test_challenge_titles_follow_the_game(challenges, manifest):
    """Studio titles are built from the game's mission titles: 'Mission N — <game title> (…)'."""
    for n, m in enumerate(manifest["missions"], 1):
        title = challenges[m["id"]]["title"]
        assert title.startswith(f"Mission {n} — {m['title_en']} (") and title.endswith(")"), title
        assert challenges[m["id"]]["title_zh"] == m["title_zh"]


def test_answer_key_is_not_in_the_public_repo():
    replay = load(ROOT / "fixtures" / "replay_outputs.json")
    assert not {"teaching_notes", "teaching_notes_readme"} & set(replay)
    assert '"verdict"' not in (ROOT / "fixtures" / "replay_outputs.json").read_text(encoding="utf-8")
    for f in CHALLENGE_FILES.values():
        assert "instructor_notes" not in load(ROOT / f), f
    assert not (ROOT / "docs" / "INSTRUCTOR_REVIEW.md").exists()
    assert not (ROOT / "tools" / "gen_content.py").exists()


@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_instructor_notes_structure(mission, instructor_notes, manifest):
    notes = instructor_notes[mission]
    assert NOTES_KEYS <= set(notes)
    for key in ("discussion_points", "deliberate_traps", "common_ai_errors"):
        assert notes[key], f"{mission}: {key} empty"
    assert set(notes["defensible_solutions"]) <= set(mission_ids(manifest, mission))


@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_challenge_strings_match_manifest_and_source(mission, challenges, manifest, zh):
    ch = challenges[mission]
    ids = [s["id"] for s in ch["strings"]]
    assert ids == mission_ids(manifest, mission)
    for s in ch["strings"]:
        assert CHALLENGE_STRING_KEYS <= set(s), (s["id"], CHALLENGE_STRING_KEYS - set(s))
        spec = manifest["strings"][s["id"]]
        for field in ("type", "speaker", "placeholders", "max_len", "allow_newlines"):
            assert s[field] == spec[field], f"{s['id']}.{field}"
        assert s["source"] == zh["strings"][s["id"]], s["id"]
        assert s["context"].strip() and s["intended_meaning"].strip(), s["id"]
        assert isinstance(s["constraints"], list) and s["constraints"], s["id"]
        assert s["focus"] and set(s["focus"]) <= FOCUS_TAGS, s["id"]
        if s["speaker"]:
            assert s["speaker"] in {c["id"] for c in ch["characters"]}, f"{s['id']}: speaker not profiled"


@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_challenge_covers_required_focus(mission, challenges):
    tags = {t for s in challenges[mission]["strings"] for t in s["focus"]}
    for alternatives in REQUIRED_FOCUS[mission]:
        assert tags & alternatives, f"{mission} lacks focus {alternatives}"


@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_defensible_solutions_pass_technical_rules(mission, instructor_notes, manifest):
    """The sample English solutions must themselves obey the string constraints."""
    for sid, options in instructor_notes[mission]["defensible_solutions"].items():
        spec = manifest["strings"][sid]
        assert 1 <= len(options) <= 4, sid
        for text in options:
            assert Counter(PLACEHOLDER_RE.findall(text)) == Counter(spec["placeholders"]), (sid, text)
            if spec["max_len"]:
                assert len(text) <= spec["max_len"], (sid, text, len(text))
            if not spec["allow_newlines"]:
                assert "\n" not in text, (sid, text)
            assert not CJK_RE.search(text), (sid, text)


def test_pun_strings_have_several_solutions(challenges, instructor_notes):
    sols = instructor_notes["pun"]["defensible_solutions"]
    for s in challenges["pun"]["strings"]:
        assert 2 <= len(sols.get(s["id"], [])) <= 4, s["id"]


# --------------------------------------------------------------------------- story graph

def node_texts(node):
    if node["kind"] in ("title", "line", "ending"):
        return [node["text"]]
    if node["kind"] == "hud":
        return list(node["texts"])
    if node["kind"] == "choice":
        return [o["text"] for o in node["options"]]
    return []


def successors(node):
    if node["kind"] == "choice":
        return [o["next"] for o in node["options"]]
    if node["kind"] == "ending":
        return []
    return [node["next"]]


@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_story_graph(mission, story, manifest, challenges):
    assert story["schema_version"] == "1.0"
    g = story["missions"][mission]
    nodes = g["nodes"]
    assert g["start"] in nodes
    referenced = []
    for nid, node in nodes.items():
        assert node["kind"] in NODE_KINDS, nid
        referenced += node_texts(node)
        for nxt in successors(node):
            assert nxt in nodes, f"{mission}.{nid} -> missing node {nxt}"
        if node["kind"] == "line":
            assert manifest["strings"][node["text"]]["type"] in ("narration", "dialogue"), nid
        if node["kind"] == "title":
            assert manifest["strings"][node["text"]]["type"] == "ui", nid
        if node["kind"] == "hud":
            assert all(manifest["strings"][t]["type"] == "ui" for t in node["texts"]), nid
        if node["kind"] == "ending":
            assert manifest["strings"][node["text"]]["type"] == "ending", nid
        if node["kind"] == "choice":
            assert len(node["options"]) == 2, nid
            assert all(manifest["strings"][o["text"]]["type"] == "choice" for o in node["options"]), nid
    assert sorted(referenced) == sorted(mission_ids(manifest, mission)), "each mission string used exactly once"
    assert sorted(referenced) == sorted(s["id"] for s in challenges[mission]["strings"])

    endings = {nid: n["ending"] for nid, n in nodes.items() if n["kind"] == "ending"}
    assert sorted(endings.values()) == ["A", "B"]

    # one choice node whose two options lead to ending A and ending B
    def reaches(start):
        seen, queue, found = {start}, deque([start]), set()
        while queue:
            nid = queue.popleft()
            if nid in endings:
                found.add(endings[nid])
            for nxt in successors(nodes[nid]):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return found, seen

    final_choices = [n for n in nodes.values() if n["kind"] == "choice"
                     and sorted(reaches(o["next"])[0] == {e} for o, e in zip(n["options"], "AB")) == [True, True]]
    assert final_choices, f"{mission}: no choice node splitting into endings A and B"

    found, seen = reaches(g["start"])
    assert found == {"A", "B"}, f"{mission}: endings reachable from start: {found}"
    assert seen == set(nodes), f"{mission}: unreachable nodes {set(nodes) - seen}"


# --------------------------------------------------------------------------- line breaks

def test_only_the_toast_allows_a_line_break(manifest, zh):
    toast = "ui.hud.toast"
    assert manifest["strings"][toast]["allow_newlines"] is True
    assert zh["strings"][toast].count("\n") == 1
    others = [sid for sid, spec in manifest["strings"].items() if spec["allow_newlines"] and sid != toast]
    assert others == [], f"only {toast} may allow newlines: {others}"


# --------------------------------------------------------------------------- glossary

@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_street_name_is_required_glossary_term(mission, challenges):
    entries = [g for g in challenges[mission]["glossary"] if "桂香街" in g["source"]]
    assert entries, f"{mission}: 桂香街 missing from glossary"
    assert entries[0]["target"] == "Kwai Heung Street"
    assert entries[0]["strictness"] == "required"


# --------------------------------------------------------------------------- reference + example export

REFERENCE_PATH = ROOT / "game" / "translations" / "en.reference.json"
STUDENT_PATH = ROOT / "game" / "translations" / "example_student_export_intro.json"


def _words(text):
    return re.findall(r"[A-Za-z0-9'{}_]+", text.lower())


def _ngrams(text, n=8):
    w = _words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def test_reference_file_envelope(manifest):
    ref = load(REFERENCE_PATH)
    assert ref["format"] == "lantern-mystery-translation"
    assert ref["schema_version"] == "1.0"
    assert ref["locale"] == "en-GB"
    assert ref["source"] == "reference"
    assert ref["note"].startswith("Reference translation by the course team")
    assert set(ref["characters"]) == set(manifest["characters"])
    assert set(ref["strings"]) == set(manifest["strings"])


@pytest.mark.parametrize("mission", list(CHALLENGE_FILES))
def test_reference_passes_validation_cleanly(mission, manifest):
    from src.validation import validate_game_file
    rep = validate_game_file(REFERENCE_PATH.read_text(encoding="utf-8"), manifest,
                             require_all_for_mission=mission)
    assert rep.critical == [], [i.to_dict() for i in rep.critical]
    assert rep.warnings == [], [i.to_dict() for i in rep.warnings]


def test_reference_is_not_the_intended_meaning_gloss(challenges):
    ref = load(REFERENCE_PATH)["strings"]
    for ch in challenges.values():
        for s in ch["strings"]:
            r = ref[s["id"]]
            assert r not in s["intended_meaning"], s["id"]
            shared = _ngrams(r) & _ngrams(s["intended_meaning"])
            assert not shared, (s["id"], shared)


def test_example_student_export_is_valid_and_differs_from_reference(manifest):
    from src.validation import validate_game_file
    stu = load(STUDENT_PATH)
    assert stu["format"] == "lantern-mystery-translation"
    assert stu["mission"] == "intro" and stu["source"] == "replay" and stu["approved"] is True
    assert stu["locale"] in ("en-GB", "en-US", "en")
    assert list(stu["strings"]) == mission_ids(manifest, "intro")
    rep = validate_game_file(STUDENT_PATH.read_text(encoding="utf-8"), manifest,
                             require_all_for_mission="intro")
    assert rep.critical == [], [i.to_dict() for i in rep.critical]
    ref = load(REFERENCE_PATH)["strings"]
    different = [sid for sid, t in stu["strings"].items() if t != ref[sid]]
    assert len(different) >= 5, "the demo needs visibly different wording"
