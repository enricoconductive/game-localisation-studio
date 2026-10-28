# Game Localisation Studio v0.3

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/enricoconductive/game-localisation-studio/blob/main/notebooks/Game_Localisation_Studio.ipynb)

Game Localisation Studio is a teaching environment for postgraduate translation students. Working in pairs in a Google Colab notebook, students direct a small team of AI agents, a **translator** and a **reviewer**, that localise scenes of an original Hong Kong mystery game, *The Lantern Mystery* (燈籠之謎), from Traditional Chinese into English. Students configure and compare prompts, judge every AI suggestion (some are wrong on purpose), direct a revision and approve the final text. They then play their translation in a browser game. No programming is needed: everything is done with buttons and text boxes. A free **Replay Mode** with prepared, clearly labelled outputs means the whole activity also works without an API key.

> **You are the localisation director. The agents are collaborators, not authorities.**

- **Notebook:** [Open in Colab](https://colab.research.google.com/github/enricoconductive/game-localisation-studio/blob/main/notebooks/Game_Localisation_Studio.ipynb)
- **Game:** <https://enricoconductive.github.io/game-localisation-studio/game/>

*Both links work once the repository is published on GitHub and GitHub Pages is enabled (see the instructor guide, section 3.1). Before that, use the offline bundle described below.*

## Quick start

**Students**

1. Click **Open in Colab** above, then **File → Save a copy in Drive**.
2. Run **Step 0** and follow Sections 1–6 in the notebook.
3. Read the [Student guide](docs/STUDENT_GUIDE.md) (four pages): keys and Colab Secrets, roles, prompting tips, judging findings, exporting, testing in the game, and what to do when something fails.

**Instructors**

1. Read the [Instructor guide](docs/INSTRUCTOR_GUIDE.md): setup, cost estimate, a 3-hour timing plan, mission-by-mission teaching notes, assessment rubric and troubleshooting.
2. The mission answer key (which prepared reviewer findings are wrong or debatable) and the string-by-string guide to the Chinese source are in the **private instructor pack**, which is not part of this repository. Ask the course leader.
3. The technical specification is in [CONTRACTS.md](docs/CONTRACTS.md).

## Providers

| Provider | Colab Secret | Status |
|---|---|---|
| Replay Mode | none | Prepared outputs; offline; the default |
| Claude (Anthropic): Claude Haiku 5.5 (default), Claude Sonnet 5.5 | `ANTHROPIC_API_KEY` | Verified |
| Hugging Face Inference Providers | `HF_TOKEN` | Not yet verified |
| HKBU GenAI | `HKBU_API_KEY` | **HKBU provider: configurable, not yet verified** (placeholders in `config/providers.json`; see the instructor guide, section 4) |

## Repository structure

```text
notebooks/Game_Localisation_Studio.ipynb   the student notebook (Step 0 + Sections 1–6 + help box)
src/                                       studio engine and notebook UI (Python)
  studio_ui.py      the notebook interface (ipywidgets)
  agents.py         translator / reviewer / reviser prompts, presets, runs
  providers.py      Claude, Hugging Face, HKBU, Replay connections; error messages; limits
  project_state.py  versions, findings, decisions, rules, approval, autosave
  exports.py        game_translation_en.json, agent_settings.json, workflow_report.html
  validation.py     placeholder / length / line-break checks
  importers.py      students' own .txt / .csv / .json material
  ui_compat.py      Colab and ipywidgets compatibility helpers
config/                                    providers.json (connections, limits), models.json (models, prices)
challenges/                                the four missions (intro, voice, pun, ui)
fixtures/                                  Replay outputs; catch-up checkpoints
game/                                      the browser game (static; served by GitHub Pages)
docs/                                      student guide, instructor guide, contracts
tools/                                     make_bundle.py, make_checkpoints.py
tests/                                     Python tests; tests/game/ for the game (Node)
```

## Offline bundle (before publication, or as a fallback)

```bash
python3 tools/make_bundle.py        # writes dist/studio_bundle.zip
```

If Step 0 cannot download the studio from GitHub, it installs `studio_bundle.zip` in one of two ways: upload it with the **Upload bundle** button that Step 0 shows, or drag it into Colab's Files panel (it becomes `/content/studio_bundle.zip`) and run Step 0 again ("Could not download from GitHub — using studio_bundle.zip from the Files panel."). See the instructor guide, section 16.

## Running the tests

Python (from the repository root; no test touches the network):

```bash
pip install -r requirements-dev.txt
pytest
```

Tests that check the answer key read the private instructor pack from `INSTRUCTOR_PACK` (default: `../instructor-pack` next to this repository). Without it they are skipped with the reason "instructor pack not found"; all other tests still run.

Game (Node 20 or later):

```bash
cd tests/game && npm install && npm test
```

`npm test` runs the unit tests and the Playwright end-to-end tests. If the Chromium build is not already installed, run `npx playwright install chromium` first. See [tests/game/README.md](tests/game/README.md) for details, and for how to play the game locally.

## Licences

- **Code:** MIT, see [LICENSE](LICENSE).
- **Content** (story, characters, dialogue, challenge materials, Replay fixtures, artwork and guides): CC BY 4.0, see [LICENSE-CONTENT](LICENSE-CONTENT).

© 2026 Enrico Bertelli
