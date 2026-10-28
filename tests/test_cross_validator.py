"""Python validation.py and the game's validator.js must agree (CONTRACTS §5)."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src import validation as v

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "game" / "translations" / "example_student_export_intro.json"
MANIFEST = ROOT / "game" / "strings_manifest.json"
VALIDATOR_JS = ROOT / "game" / "validator.js"
GAME_FIXTURES = ROOT / "tests" / "game" / "fixtures"

needs_content = pytest.mark.skipif(not (SAMPLE.exists() and MANIFEST.exists()),
                                   reason="real game content not present")


@needs_content
def test_sample_translation_has_no_critical_issues():
    manifest = v.load_manifest(MANIFEST)
    rep = v.validate_game_file(SAMPLE.read_text(encoding="utf-8"), manifest)
    assert rep.critical == [], [i.to_dict() for i in rep.critical]


def _broken_variants(sample: dict) -> dict[str, str]:
    """Named broken (and valid) files derived from the sample, as JSON text."""
    def mutate(fn):
        d = copy.deepcopy(sample)
        fn(d)
        return json.dumps(d, ensure_ascii=False)

    strings = sample["strings"]
    ph_id = next(k for k, t in strings.items() if "{player_name}" in t)
    limited = next(k for k in strings if k.startswith(sample["mission"] + ".ui."))
    out = {
        "valid": json.dumps(sample, ensure_ascii=False),
        "invalid_json": json.dumps(sample)[:-5],
        "wrong_format": mutate(lambda d: d.update(format="something-else")),
        "wrong_schema": mutate(lambda d: d.update(schema_version="2.0")),
        "strings_list": mutate(lambda d: d.update(strings=["a"])),
        "value_number": mutate(lambda d: d["strings"].update({limited: 5})),
        "unknown_id": mutate(lambda d: d["strings"].update({"intro.ui.nonexistent": "x"})),
        "empty_text": mutate(lambda d: d["strings"].update({limited: "   "})),
        "missing_id": mutate(lambda d: d["strings"].pop(limited)),
        "ph_space": mutate(lambda d: d["strings"].update({ph_id: strings[ph_id].replace("{player_name}", "{player name}")})),
        "ph_unclosed": mutate(lambda d: d["strings"].update({ph_id: strings[ph_id].replace("{player_name}", "{player_name")})),
        "ph_translated": mutate(lambda d: d["strings"].update({ph_id: strings[ph_id].replace("{player_name}", "{玩家}")})),
        "ph_dropped": mutate(lambda d: d["strings"].update({ph_id: strings[ph_id].replace("{player_name}", "you")})),
        "ph_duplicated": mutate(lambda d: d["strings"].update({ph_id: strings[ph_id] + " {player_name}"})),
        "too_long": mutate(lambda d: d["strings"].update({limited: "Start investigating the mystery right now"})),
        "newline": mutate(lambda d: d["strings"].update({limited: "Go\nnow"})),
        "carriage_return": mutate(lambda d: d["strings"].update({limited: "Go\rnow"})),
        "control_char": mutate(lambda d: d["strings"].update({limited: "Go\tnow"})),
        "replacement_char": mutate(lambda d: d["strings"].update({limited: "Go �"})),
        "lone_surrogate": json.dumps(sample, ensure_ascii=False).replace(
            json.dumps(strings[limited], ensure_ascii=False), '"Go \\ud800"', 1),
        "char_unknown": mutate(lambda d: d.update(characters={"nobody": "Bob"})),
        "char_too_long": mutate(lambda d: d.update(characters={"kit": "K" * 21})),
        "char_not_object": mutate(lambda d: d.update(characters=["Kit"])),
        "warnings_only": mutate(lambda d: d["strings"].update({limited: " Go  <b>"})),
        "feff_trailing": mutate(lambda d: d["strings"].update({limited: "Go\ufeff"})),
        "feff_leading": mutate(lambda d: d["strings"].update({limited: "\ufeffGo"})),
        "nbsp_and_ideographic_space": mutate(lambda d: d["strings"].update({limited: "\u3000Go\u00a0"})),
        "only_feff": mutate(lambda d: d["strings"].update({limited: "\ufeff"})),
        "zero_width_space": mutate(lambda d: d["strings"].update({limited: "Go\u200b"})),
        "file_sep_char": mutate(lambda d: d["strings"].update({limited: "Go\x1c"})),
        "bad_source": mutate(lambda d: d.update(source="chatgpt")),
        "source_not_text": mutate(lambda d: d.update(source=["live"])),
        "no_source": mutate(lambda d: d.pop("source", None)),
        "reference_source": mutate(lambda d: d.update(source="reference")),
        "odd_locale": mutate(lambda d: d.update(locale="fr-FR")),
        "no_locale": mutate(lambda d: d.pop("locale", None)),
        "zh_locale": mutate(lambda d: d.update(locale="zh-Hant-HK")),
        "too_large": json.dumps(sample) + " " * (101 * 1024),
        "top_level_list": "[1, 2, 3]",
    }
    return out


def _js_codes(files: dict[str, str], manifest_path: Path, require: str | None = None) -> dict:
    script = r"""
const fs = require('fs');
const V = require(process.argv[1]);
const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const files = JSON.parse(fs.readFileSync(0, 'utf8'));
const opts = process.argv[3] ? {requireAllForMission: process.argv[3]} : {};
const out = {};
for (const [name, text] of Object.entries(files)) {
  const r = V.validateTranslationFile(text, manifest, opts);
  out[name] = {critical: [...new Set(r.critical.map(i => i.code))].sort(),
               warnings: [...new Set(r.warnings.map(i => i.code))].sort()};
}
process.stdout.write(JSON.stringify(out));
"""
    args = ["node", "-e", script, str(VALIDATOR_JS), str(manifest_path)] + ([require] if require else [])
    res = subprocess.run(args, input=json.dumps(files), capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _py_codes(files: dict[str, str], manifest: dict, require: str | None = None) -> dict:
    out = {}
    for name, text in files.items():
        rep = v.validate_game_file(text, manifest, require_all_for_mission=require)
        out[name] = {"critical": sorted(set(rep.codes("CRITICAL"))),
                     "warnings": sorted(set(rep.codes("WARNING")))}
    return out


needs_node = pytest.mark.skipif(shutil.which("node") is None or not VALIDATOR_JS.exists(),
                                reason="node or game/validator.js not available")


@needs_content
@needs_node
@pytest.mark.parametrize("require", [None, "intro"])
def test_python_and_js_agree_on_broken_files(require):
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    manifest = v.load_manifest(MANIFEST)
    files = _broken_variants(sample)
    js, py = _js_codes(files, MANIFEST, require), _py_codes(files, manifest, require)
    mismatches = {n: {"py": py[n], "js": js[n]} for n in files
                  if py[n]["critical"] != js[n]["critical"]}
    assert not mismatches, mismatches
    warn_mismatch = {n: {"py": py[n]["warnings"], "js": js[n]["warnings"]} for n in files
                     if py[n]["warnings"] != js[n]["warnings"]}
    assert not warn_mismatch, warn_mismatch
    assert py["valid"]["critical"] == [] and py["too_long"]["critical"] == ["too_long"]
    assert "whitespace" in py["feff_trailing"]["warnings"] and "whitespace" in py["feff_leading"]["warnings"]
    assert "whitespace" in py["nbsp_and_ideographic_space"]["warnings"]
    assert py["only_feff"]["critical"] == ["empty_text"]
    assert py["bad_source"]["critical"] == py["source_not_text"]["critical"] == ["bad_structure"]
    for name in ("no_source", "odd_locale", "no_locale"):
        assert py[name]["critical"] == [] and "bad_structure" in py[name]["warnings"], name
    for name in ("valid", "reference_source", "zh_locale"):
        assert "bad_structure" not in py[name]["warnings"], name


@needs_node
def test_python_and_js_agree_on_game_fixture_files():
    manifest_path = GAME_FIXTURES / "strings_manifest.json"
    tdir = GAME_FIXTURES / "translations"
    files = {f.name: f.read_text(encoding="utf-8") for f in sorted(tdir.glob("*.json"))
             if f.name != "zh-Hant.json"} if tdir.exists() else {}
    if not manifest_path.exists() or not files:
        pytest.skip("no translation fixtures in tests/game/fixtures")
    manifest = v.load_manifest(manifest_path)
    js, py = _js_codes(files, manifest_path), _py_codes(files, manifest)
    assert {n: py[n]["critical"] for n in files} == {n: js[n]["critical"] for n in files}


def test_duplicate_id_is_python_only(tmp_path):
    """JSON.parse cannot see duplicate keys; Python reports them (documented in CONTRACTS)."""
    manifest = json.loads((ROOT / "tests" / "fixtures_synthetic" / "manifest.json").read_text("utf-8"))
    text = ('{"format": "lantern-mystery-translation", "schema_version": "1.0", "locale": "en",'
            ' "strings": {"demo.ui.start": "Go", "demo.ui.start": "Run"}}')
    assert "duplicate_id" in v.validate_game_file(text, manifest).codes("CRITICAL")
