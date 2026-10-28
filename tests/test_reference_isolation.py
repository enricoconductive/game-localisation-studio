"""The course team's reference English must never reach the students' agents.

Agents see only what src/agents.py puts into prompts (source, context, constraints,
glossary, scene context, character profiles). This test builds every kind of prompt for
every challenge and checks that no reference sentence leaks into it, and that no module
in src/ reads en.reference.json.
"""
import json
import re
from pathlib import Path

import pytest

from src import agents

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / "game" / "translations" / "en.reference.json").read_text(encoding="utf-8"))["strings"]
CHALLENGES = ["introductory", "character_voice", "pun_boss", "interface_trap"]
LOCALE = "en-GB"


def norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def ngrams(text, n=8):
    w = re.findall(r"[a-z0-9'{}_]+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def all_prompts(challenge):
    ids = [s["id"] for s in challenge["strings"]]
    dummy = {sid: f"DUMMY TRANSLATION {i}" for i, sid in enumerate(ids)}
    feedback = [{"string_id": ids[0], "finding_id": "R1-01", "category": "accuracy", "severity": "minor",
                 "issue": "dummy issue", "suggestion": "dummy suggestion", "comment": ""}]
    tr, rv = agents.default_agent_config("translator"), agents.default_agent_config("reviewer")
    prompts = [
        agents.build_baseline_prompt(challenge, LOCALE),
        agents.build_translator_prompt(challenge, tr, LOCALE, []),
        agents.build_reviewer_prompt(challenge, rv, LOCALE, [], dummy),
        agents.build_revision_prompt(challenge, tr, LOCALE, [], dummy, feedback, ids[:1],
                                     locked={ids[-1]: dummy[ids[-1]]}),
    ]
    return [norm(p) for pair in prompts for p in pair]


@pytest.mark.parametrize("name", CHALLENGES)
def test_no_reference_sentence_in_any_prompt(name):
    challenge = json.loads((ROOT / "challenges" / f"{name}.json").read_text(encoding="utf-8"))
    prompts = all_prompts(challenge)
    assert len(prompts) == 8
    for sid, ref in REFERENCE.items():
        if len(ref.split()) < 4:
            continue
        for p in prompts:
            assert norm(ref) not in p, f"reference for {sid} leaks into a {name} prompt"
            leaked = ngrams(ref) & ngrams(p)
            assert not leaked, f"reference for {sid} leaks into a {name} prompt: {sorted(leaked)[:3]}"


def test_challenge_files_do_not_contain_reference_fields():
    for name in CHALLENGES:
        challenge = json.loads((ROOT / "challenges" / f"{name}.json").read_text(encoding="utf-8"))
        for s in challenge["strings"]:
            assert "reference" not in s, (name, s["id"])


def test_src_never_reads_the_reference_file():
    offenders = [p.name for p in (ROOT / "src").glob("*.py")
                 if "en.reference" in p.read_text(encoding="utf-8")]
    assert offenders == [], f"src modules must not read en.reference.json: {offenders}"
