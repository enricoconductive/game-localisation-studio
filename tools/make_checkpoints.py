"""Generate the catch-up checkpoints for the intro mission (CONTRACTS §15).

The checkpoints are produced by running the real engine in Replay Mode on the prepared
outputs in ``fixtures/replay_outputs.json``, so they are always consistent with the
engine and the fixtures. Re-run this script whenever either changes:

    python3 tools/make_checkpoints.py            # writes fixtures/checkpoints/*.json

Files written (all Replay Mode, Balanced preset, en-GB, no keys, not approved):
- intro_after_agents.json    baseline + translator done
- intro_after_review.json    + reviewer findings (round 1), no decisions yet
- intro_after_revision.json  + sample human decisions, one memory rule, one revision run

Each file also carries a top-level ``checkpoint_label``, shown in the studio's
"Checkpoint:" dropdown (ignored when the project is loaded).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import agents, project_state as ps, providers  # noqa: E402

OUT_DIR = ROOT / "fixtures" / "checkpoints"
CHALLENGE_FILE = ROOT / "challenges" / "introductory.json"
ROLE = "director"
NAMES = ("intro_after_agents", "intro_after_review", "intro_after_revision")
LABELS = {"intro_after_agents": "Catch up: agents already run (Mission 1)",
          "intro_after_review": "Catch up: review done (Mission 1)",
          "intro_after_revision": "Catch up: revision done (Mission 1)"}

# Sample decisions on the Balanced reviewer findings, so the last checkpoint has a revision.
DECISIONS = [
    ("R1-01", "accept", None, "The saying now works in English and keeps the rabbit."),
    ("R1-02", "accept", None, "Follow the glossary and match Ending B."),
    ("R1-03", "accept", None, ""),
    ("R1-04", "reject", None, "Kit's slang is his voice; standard English would make him sound like Granny."),
    ("R1-05", "override",
     "It is the eve of the Mid-Autumn Festival and Kwai Heung Street is strung with lanterns. "
     "{player_name} has only just reached the corner when the news arrives: the fair's prize "
     "treasure, the giant rabbit lantern, has flown the nest.",
     "Keep a light flying image for 不翼而飛, but as a natural English idiom."),
    ("R1-06", "accept_edited", "Open case",
     "Agree a friendlier label helps, but 'Start the case' breaks the 12-character limit."),
]
RULE = {"kind": "glossary", "text": "Always write 茶餐廳 as 'cha chaan teng', never 'tea restaurant'.",
        "source_term": "茶餐廳", "target_term": "cha chaan teng", "from_finding": "R1-02"}


def load_challenge() -> dict:
    return json.loads(CHALLENGE_FILE.read_text(encoding="utf-8"))


def build_states(fixtures: dict | None = None) -> dict[str, ps.ProjectState]:
    """Run the intro mission in Replay Mode and return the three checkpoint states."""
    challenge = load_challenge()
    provider = providers.ReplayProvider(fixtures if fixtures is not None
                                        else providers.load_replay_fixtures())
    st = ps.new_project(challenge, "en-GB", "replay", "replay", "replay", "replay",
                        max_cycles=1, team_name="Catch-up checkpoint")
    agents.apply_preset(st.agents["translator"], "balanced")
    states = {}

    agents.run_baseline(st, provider, challenge)
    agents.run_translator(st, provider, challenge)
    st.log("checkpoint", "Catch-up checkpoint prepared by the course team: baseline and "
                         "translator done (Replay Mode, Balanced preset).")
    states["intro_after_agents"] = ps.ProjectState.from_dict(st.to_dict())

    agents.run_reviewer(st, provider, challenge)
    st.log("checkpoint", "Catch-up checkpoint prepared by the course team: reviewer findings "
                         "ready, no human decisions yet.")
    states["intro_after_review"] = ps.ProjectState.from_dict(st.to_dict())

    for fid, action, text, comment in DECISIONS:
        ps.decide_finding(st, fid, action, ROLE, human_text=text, comment=comment)
    ps.add_rule(st, RULE["kind"], RULE["text"], ROLE, source_term=RULE["source_term"],
                target_term=RULE["target_term"], from_finding=RULE["from_finding"])
    agents.run_revision(st, provider, challenge, role=ROLE)
    st.log("checkpoint", "Catch-up checkpoint prepared by the course team: sample decisions "
                         "and one revision applied; not approved yet.")
    states["intro_after_revision"] = ps.ProjectState.from_dict(st.to_dict())
    return states


def write_checkpoints(out_dir: Path | str = OUT_DIR, fixtures: dict | None = None) -> dict[str, Path]:
    out_dir = Path(out_dir)
    paths = {}
    for name, state in build_states(fixtures).items():
        path = out_dir / f"{name}.json"
        data = {"checkpoint_label": LABELS[name], **state.to_dict()}
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if providers.find_secrets(text):   # never write anything that looks like a key
            raise ps.StudioError(f"Not written: {name} contains something that looks like a key.")
        ps.load_state(text)                # still a valid project file
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths[name] = path
    return paths


def main() -> None:
    for name, path in write_checkpoints().items():
        st = ps.load_state(path)
        print(f"{path.relative_to(ROOT)}: stage {st.stage}, {len(st.versions)} version(s), "
              f"{len(st.findings)} finding(s), {len(st.decisions)} decision(s)")


if __name__ == "__main__":
    main()
