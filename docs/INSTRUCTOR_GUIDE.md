# Instructor guide: Game Localisation Studio v0.3

This guide is for the instructor running the session, and for the HKBU colleague who will configure the HKBU GenAI connection. It assumes no programming and **no knowledge of Chinese or Cantonese**. For the student-facing instructions, see [`STUDENT_GUIDE.md`](STUDENT_GUIDE.md).

> **The mission answer key is in the private instructor pack — ask the course leader.** The pack is kept out of this public repository on purpose. It holds `ANSWER_KEY.md` (which prepared reviewer findings are wrong or debatable, and how to spot an accepted wrong one), `INSTRUCTOR_REVIEW.md` (a string-by-string reading of the source text with the reference English, and the native-speaker proofreading checklist), the per-finding teaching notes and the per-mission instructor notes. Nothing in the notebook, Replay Mode or the game needs it.

**Contents**

1. [Overview and learning outcomes](#1-overview-and-learning-outcomes)
2. [What is in the repository](#2-what-is-in-the-repository)
3. [Before class: setup and configuration](#3-before-class-setup-and-configuration)
4. [HKBU GenAI setup (for the colleague configuring it)](#4-hkbu-genai-setup-for-the-colleague-configuring-it)
5. [Claude and Hugging Face: models and cost](#5-claude-and-hugging-face-models-and-cost)
6. [Replay Mode](#6-replay-mode)
7. [Classroom preparation checklist](#7-classroom-preparation-checklist)
8. [Suggested timing for a 3-hour session](#8-suggested-timing-for-a-3-hour-session)
9. [Running the session remotely](#9-running-the-session-remotely)
10. [Using the game without reading Chinese](#10-using-the-game-without-reading-chinese)
11. [Mission-by-mission teaching notes](#11-mission-by-mission-teaching-notes)
12. [Assessing the workflow report](#12-assessing-the-workflow-report)
13. [Common student errors](#13-common-student-errors)
14. [Troubleshooting](#14-troubleshooting)
15. [Security and privacy](#15-security-and-privacy)
16. [Pre-publication testing with `studio_bundle.zip`](#16-pre-publication-testing-with-studio_bundlezip)
17. [Extending the activity](#17-extending-the-activity)

---

## 1. Overview and learning outcomes

Students work in pairs in a Google Colab notebook, the **studio**. They configure a **translator agent** and a **reviewer agent**, run them on short scenes from an original Hong Kong mystery game (*The Lantern Mystery*, 燈籠之謎), and compare a context-free baseline with their configured agents. They then change the prompt and compare again, judge every reviewer suggestion, direct a revision and approve a final translation. Last, they export it and play it in a browser game. The pedagogical core is a single sentence that appears throughout the notebook:

> **You are the localisation director. The agents are collaborators, not authorities.**

The reviewer's prepared findings (Replay Mode) **include wrong and debatable suggestions on purpose**. Rejecting them, with reasons, is the main evidence of learning. Which ones they are is in the private instructor pack.

### The four missions

| Studio mission (dropdown in Section 2) | Same scene in the game | id | Strings | Estimated time (challenge file) |
|---|---|---|---|---|
| Mission 1 — The Lantern Mystery (Introductory) | Mission 1 · The Lantern Mystery | `intro` | 8 | 80 min, including setup |
| Mission 2 — An Evening at the Lantern Shop (Challenge A: Character Voice) | Mission 2 · An Evening at the Lantern Shop | `voice` | 8 | 40 min (≈ 35–40, skip Section 1) |
| Mission 3 — The Riddle King (Challenge B: The Pun Boss) | Mission 3 · The Riddle King | `pun` | 6 | 40 min (≈ 35–40, skip Section 1) |
| Mission 4 — The Detective's Toolbar (Challenge C: The Interface Trap) | Mission 4 · The Detective's Toolbar | `ui` | 7 | 40 min (≈ 35–40, skip Section 1) |

The studio's mission titles are built from the game's mission titles, so students see the same name in both.

### Learning outcomes

By the end of the session, students can:

| # | Outcome | Teaching objectives it draws on (from `challenges/*.json`) |
|---|---|---|
| LO1 | **Configure and brief AI agents** for a localisation task, and explain how a prompt change alters the output. | Intro: set up translator and reviewer agents and compare with a context-free baseline. A: write instructions that keep two distinct voices. B: brief an AI translator to prioritise effect over literal meaning and compare several creative solutions. |
| LO2 | **Evaluate AI suggestions critically**: accept, edit, reject or override them, and justify each decision. | Intro: act as the human director, accept/edit/reject AI suggestions and justify the decision. A: use the reviewer to spot "flattened" lines. |
| LO3 | **Preserve character voice and cultural effect** across languages. | Intro: two distinct English voices; make culture-bound expressions (歇後語, 茶餐廳, the moon rabbit) work. A: register, terms of address and code-mixing build a character; idiom vs paraphrase for 成語. B: translatable vs recreated puns; linked strings; lantern riddles for international players. |
| LO4 | **Deliver technically valid game text**: placeholders, character limits and line breaks. | Intro: keep `{player_name}` and button limits. C: keep placeholders exactly, respect limits (tokens count literally), know when a line break is allowed, fix CRITICAL validator issues before export. |
| LO5 | **Reflect** on a human–AI workflow, using evidence from their own process. | The reflection question in Section 6 and the workflow report. |

## 2. What is in the repository

| Path | What it is |
|---|---|
| `notebooks/Game_Localisation_Studio.ipynb` | The student notebook: Step 0 (setup), Sections 1–6 and the help box. |
| `src/` | The studio engine and user interface (Python). Students never open it. |
| `config/providers.json` | Provider connection settings (Claude, HKBU GenAI, Hugging Face, Replay) and the class limits. |
| `config/models.json` | The models offered in the **Model:** dropdown, with prices and "verified" flags. |
| `challenges/*.json` | The four missions: strings, context, character profiles, glossary, teaching objectives. |
| `fixtures/replay_outputs.json` | The prepared Replay outputs (three presets per mission). |
| `fixtures/checkpoints/` | Three catch-up states for Mission 1. |
| `game/` | The browser game (static HTML/JavaScript), served by GitHub Pages. `game/translations/en.reference.json` is the reference English. `example_student_export_intro.json` is a demo export. |
| `docs/` | This guide, the student guide and `CONTRACTS.md` (technical specification). |
| `tools/` | `make_bundle.py` (offline zip) and `make_checkpoints.py` (regenerates catch-up states). |
| `tests/` | Automated tests (Python with `pytest`; game tests with Node/Playwright). See the README. Tests that need the answer key read the instructor pack and are skipped without it. |
| *Instructor pack* (private, **not** in this repository) | `ANSWER_KEY.md`, `INSTRUCTOR_REVIEW.md`, `teaching_notes.json`, `instructor_notes/`, and the content generator `tools/gen_content.py`. Ask the course leader. |

## 3. Before class: setup and configuration

### 3.1 Publish the repository and the game

1. The repository must be **public** on GitHub as `enricoconductive/game-localisation-studio` so that Colab can clone it and the badge works.
2. **GitHub Pages:** in the repository, go to **Settings → Pages**, choose *Deploy from a branch*, branch `main`, folder `/ (root)`, and save. After a minute or two the game is at <https://enricoconductive.github.io/game-localisation-studio/game/>.
3. **Colab link** (also the README badge): <https://colab.research.google.com/github/enricoconductive/game-localisation-studio/blob/main/notebooks/Game_Localisation_Studio.ipynb>

Step 0 of the notebook clones the `main` branch at the moment a student runs it. **Push any configuration change before class.** When a student runs Step 0 again in the same runtime, it tries `git pull --ff-only` (20-second limit) so your fixes reach them; if that fails it says "Using the copy already downloaded" and carries on with the older copy (see Troubleshooting). A studio installed from `studio_bundle.zip` cannot update itself.

### 3.2 Choose how students connect

| Option | Good for | Trade-offs |
|---|---|---|
| **Replay Mode for everyone** | Guaranteed to work; free; no keys to distribute. | Outputs do not respond to prompt edits (only to presets). Good enough for every learning outcome except "see a live model react to *your* wording". |
| **One Claude key per pair** (19 keys) | Each pair has its own rate limit; you can revoke one key without affecting others; usage per pair is visible in the Console. | 19 keys to create and hand out securely; more admin. |
| **One shared Claude key** | Simplest to distribute. | All 19 pairs share one rate limit, so expect "service is busy" messages when everyone clicks at once. One leaked key affects the whole class. |
| **HKBU GenAI** | University-provided; no external billing. | **Untested until confirmed** by the colleague who configures it (section 4). |

A practical compromise: one key per pair, or a shared key plus Replay as the default for half the class.

### 3.3 Protect your budget

- In the **Anthropic Console**, create a separate workspace for the course, create the class key(s) in it, and **set a monthly spend limit** on that workspace. Check the rate limits that apply to your organisation in the Console before class.
- **Delete or rotate the keys after the session.**
- `config/providers.json` → `limits` holds the studio's own safety limits:

  | Field | Current value | Meaning |
  |---|---|---|
  | `request_cap` | `40` | Maximum live requests per notebook session (all missions together). The status bar shows **Live requests this session: n / 40**. |
  | `timeout_seconds` | `45` | How long the studio waits for a reply. |
  | `max_retries` | `2` | Automatic retries on "busy", server errors, timeouts and network errors (never on a wrong key or no credit). |
  | `backoff_seconds` | `[1, 3]` | The waits between those retries. |

  **Note:** the request cap counts per session. The count survives **Load my key**, provider and model changes, starting or resetting a mission and loading a project or checkpoint; it starts again from 0 only when Step 0 is run again or the runtime restarts. Every live attempt counts (retries, repair requests and **Test connection** included); Replay never counts. The cap stops runaway clicking; it is not a budget. The Console spend limit is your real budget control.

### 3.4 Distribute keys safely

Send each pair's key through a private channel (for example an LMS private message), never on a shared screen or in the class chat. Students store it in **Colab Secrets** under the exact name the studio shows (`ANTHROPIC_API_KEY`, `HKBU_API_KEY` or `HF_TOKEN`) and switch on **Notebook access**. See the student guide, section 2.

## 4. HKBU GenAI setup (for the colleague configuring it)

> **Status: configurable, not yet verified.** No public specification of the HKBU GenAI API was available when the studio was built. The values below are **placeholders**. The studio has been tested only against simulated HKBU replies (OpenAI-style and Anthropic-style) in `tests/test_providers.py`, never against the real service. Treat the HKBU connection as **untested until you confirm it** with the steps below.

### 4.1 What you need from the HKBU GenAI documentation

- the base URL and the full path of the chat endpoint;
- how the key is sent (header name and any prefix such as `Bearer `);
- whether the model or deployment name goes in the URL or in the request body;
- any required version parameter or extra headers;
- whether the request/response format is OpenAI-style "chat completions" or Anthropic-style "messages";
- where the reply text and the token counts are found in the response;
- the exact model (or deployment) names you want to offer.

### 4.2 Fill in `config/providers.json` → `"hkbu"`

| Field | What it means | Current value |
|---|---|---|
| `display_name` | Name shown in messages. | `"HKBU GenAI"` |
| `base_url` | Start of the endpoint URL, without a trailing slash. **While this is empty, students see "HKBU GenAI is not set up for this course yet."** | `""` |
| `path_template` | Full request URL. May contain `{base_url}`, `{model}` and `{api_version}`. | `"{base_url}/chat/completions"` |
| `api_version` | Value substituted for `{api_version}`, if the service needs one. | `""` |
| `auth_header_name` | The header that carries the key. | `"Authorization"` |
| `auth_prefix` | Text placed before the key in that header (note the space in `"Bearer "`). Use `""` for none. | `"Bearer "` |
| `extra_headers` | Any additional fixed headers, as `{"Name": "value"}`. Never put the key here. | `{}` |
| `query_params` | URL query parameters, as `{"name": "value"}`; values may use `{model}` or `{api_version}`. | `{}` |
| `request_style` | `"openai_chat"` (reply text read from `choices.0.message.content`) or `"anthropic_messages"` (reply text read from `content.0.text`). | `"openai_chat"` |
| `model_in_body` | `true` if the model name goes in the JSON body (OpenAI style), `false` if it is only in the URL. | `true` |
| `response_text_path` | Override for where the reply text is, as a dot path such as `choices.0.message.content`. Leave `""` to use the default for the style. | `""` |
| `usage_input_path` / `usage_output_path` | Dot paths to the token counts, if they differ from the defaults (`usage.prompt_tokens` / `usage.completion_tokens`, or `usage.input_tokens` / `usage.output_tokens`). | `""` |
| `send_temperature` | `true` to send the temperature derived from the "strategy" slider; `false` if the service rejects it. | `true` |
| `model_params` | Extra body fields per model, for example `{"<model-name>": {"<field>": "<value>"}}`. | `{}` |
| `secret_name` | The Colab Secret students create. | `"HKBU_API_KEY"` |
| `models` | Fallback list of model names (plain strings), used only if `config/models.json` lists none. Prefer `models.json`. | `[]` |
| `verified` | Set to `true` once you have confirmed the connection (see 4.4). | `false` |

Two common gateway shapes, given **only as illustrations of how the fields combine** (they are *not* HKBU's values):

- *OpenAI-compatible gateway:* `path_template` `"{base_url}/chat/completions"`, `auth_header_name` `"Authorization"`, `auth_prefix` `"Bearer "`, `model_in_body` `true`.
- *Gateway with the deployment name and a version in the URL:* `path_template` `"{base_url}/deployments/{model}/chat/completions"`, `query_params` `{"api-version": "{api_version}"}`, `auth_header_name` set to whatever header the documentation names, `auth_prefix` `""`, `model_in_body` `false`.

### 4.3 Add the models to `config/models.json` → `"hkbu"`

```json
"hkbu": {
  "default": "<model name to preselect>",
  "note": "Confirmed with HKBU GenAI on <date> by <name>.",
  "models": [
    {"id": "<exact model or deployment name>", "label": "<friendly label>", "verified": false}
  ]
}
```

- `id` must be exactly what the service expects. It is what replaces `{model}` and goes in the body.
- While `verified` is `false`, the dropdown shows the label followed by *(set up by your instructor, unverified)*.
- Optional: add `"pricing": {"input_per_mtok": <number>, "output_per_mtok": <number>, "currency": "USD"}` to get a cost estimate in the status bar.
- **Never put a key in either configuration file.**

### 4.4 Test it

1. Push the changes to GitHub (or build a bundle, section 16), then open the notebook in a **fresh** Colab runtime.
2. Add your own key in Colab Secrets as `HKBU_API_KEY` with **Notebook access** on.
3. In Section 1 choose **HKBU GenAI**, pick the model, click **Load my key**, then **Test connection**. This sends one small request ("Reply with the single word OK"). You should see **Connected to HKBU GenAI with model '…'.**
4. Then run Mission 1 end to end in Live Mode: **1 · Baseline (one-shot)**, **2 · Run translator**, **3 · Run reviewer**, **Send accepted feedback**. Check that the status bar's **Live requests this session** and **Tokens** counters move. If the token counters stay at zero, fix the `usage_*_path` fields.
5. Only when all of this works, set `"verified": true` for the model in `models.json` and for `hkbu` in `providers.json`, and update the notes with the date.

| Message in Section 1 | Likely cause |
|---|---|
| "…not set up for this course yet." | `base_url` is empty, or `request_style` is not one of the two allowed values. |
| "…key was not accepted." | Wrong header name or prefix, or a wrong key. |
| "The model '…' is not available…" | The `id` does not match the service's model or deployment name, or the path is wrong. |
| "…sent back a reply the studio could not use. (no text in the reply)" | Wrong `request_style` or `response_text_path`. |
| "Could not reach HKBU GenAI…" | Wrong `base_url`, or the service is reachable only from the campus network or VPN. A Colab machine is not on the campus network. |

The key-help box in Section 1 reads `"verified"` under `hkbu` in `providers.json`: while it is `false` it says HKBU GenAI is *set up by your instructor, unverified*; once it is `true` it says only *set up by your instructor*. Each model label follows its own `verified` flag in `models.json`.

## 5. Claude and Hugging Face: models and cost

### 5.1 Claude (Anthropic): verified

- Secret name: `ANTHROPIC_API_KEY`.
- Models (`config/models.json`): **Claude Haiku 5.5** (`claude-haiku-5-5`, the default and recommended) and **Claude Sonnet 5.5** (`claude-sonnet-5-5`, stronger, about 20 times the price). Both are marked `verified: true`, with pricing checked on 2026-10-28.
- On the configured API version, Claude does not accept a temperature setting, so the studio does not send one (`send_temperature: false`). The preview tells students that their settings work "through the prompt lines". Every slider still changes the prompt text.
- **Advanced: use a different model for the reviewer** (Section 1) lets a pair use, say, Haiku for the translator and Sonnet for the reviewer.

### 5.2 Worked cost estimate for 19 pairs (Claude Haiku 5.5)

Prices from `config/models.json`: **$0.10 per million input tokens** and **$0.50 per million output tokens** (prompts of 100K tokens or fewer, which covers every prompt here).

**Assumptions**

- Each mission has at most 8 strings, so every step is **one request** (batches hold 8 strings).
- Measured prompt sizes for Mission 1: the translator prompt is about 8,100 characters and the reviewer prompt about 9,600 characters, which is roughly 2,400–2,900 tokens. **We round up to 3,000 input tokens per request.**
- Output is capped at 4,000 tokens per request (`limits.max_tokens` in `config/providers.json`). Claude's thinking is switched off (`request_options` in `config/models.json`), so the cap only holds the JSON reply. **A realistic reply is about 1,000 output tokens**; the worst case assumes every reply hits the 4,000 cap.
- Requests per pair in the planned session:

  | Activity | Requests |
  |---|---|
  | Test connection | 1 |
  | Mission 1: baseline 1, translator 3 runs (the compare activity), reviewer 1, revision 1, round-2 review 1 | 7 |
  | One advanced mission: baseline 1, translator 2 runs, reviewer 1, revision 1 | 5 |
  | Allowance for repair requests (when a reply cannot be read) and re-runs | 2 |
  | **Total per pair** | **15** |

**Arithmetic**

- Typical cost per request = 3,000 × $0.10 / 1,000,000 + 1,000 × $0.50 / 1,000,000 = $0.0003 + $0.0005 = **$0.0008**
- Worst case per request (reply hits the 4,000 cap) = $0.0003 + 4,000 × $0.50 / 1,000,000 = $0.0003 + $0.002 = **$0.0023**
- Planned session: 19 pairs × 15 requests = 285 requests; 285 × $0.0008 ≈ **US$0.23 for the whole class** (≤ US$0.66 if every reply hit the cap).
- Worst case (every pair uses the full 40-request session cap): 19 × 40 = 760 requests; 760 × $0.0008 ≈ **US$0.61** (≤ US$1.75 if every reply hit the cap). Each time a pair reruns Step 0 they get a new count, so allow, say, double that.
- Reality check: a real live test run of 5 requests cost **US$0.004**.
- With Claude Sonnet 5.5 ($2.00 / $10.00 per million): $0.006 + $0.010 = $0.016 per request typical ($0.046 at the cap), so 285 × $0.016 ≈ **US$4.56** for the planned session (≤ US$13.11).

The status bar shows each pair's running **Est. cost** in Live Mode. Even the worst case is small. A Console spend limit of a few dollars is a sensible safety net.

### 5.3 Hugging Face: not verified

- Secret name: `HF_TOKEN` (a fine-grained token with permission to make calls to Inference Providers).
- Default model: `openai/gpt-oss-120b`. You can append `:cheapest`, `:fastest` or `:<provider>` to choose a routing policy (`openai/gpt-oss-120b:cheapest` is listed).
- Both models are `verified: false`. The request shape follows the Inference Providers documentation but **has not been tested live**, and the dropdown labels say *(unverified)*.
- Prices depend on the provider the router chooses and are not listed, so no cost estimate is shown.

To offer another model, add an entry to the provider's `models` list in `config/models.json`, and mark it `verified: true` only after you have run Mission 1 with it.

## 6. Replay Mode

**What it is.** Replay serves outputs written in advance by the course team from `fixtures/replay_outputs.json`. It needs no key and no internet, costs nothing, and never counts against the request cap. Every screen, the status bar, the comparisons, the exports and the game label it: **REPLAY MODE — simulated outputs, not live AI** In the game, the badge reads "Showing: Student's imported English · simulated (Replay Mode)".

**Presets and variants.** For each mission there is one prepared baseline and **one prepared translator output per preset** (Faithful, Balanced, Creative), each with its own reviewer findings and round-2 findings. This means the key activity (change the prompt, run again, compare) still works in Replay, as long as students switch **presets**. If students edit the sliders or instructions themselves, Replay serves the output of the preset they started from and says so ("Your own edits are saved in your prompt and report, but Replay Mode cannot generate a new response — switch to Live Mode to test them."). All prepared English is British English, whatever English variant the project uses. When a project is set to en-US or en, the studio says so: "Replay examples are written in British English; live agents will follow your choice."

**Deliberate errors.** The prepared findings include wrong and debatable suggestions on purpose. Which ones, and why, is documented in the private instructor pack (`ANSWER_KEY.md`, `teaching_notes.json`). This makes Replay the most reliable mode for *teaching critical evaluation*.

**When to use it**

- as the starting mode (the studio boots in Replay);
- for your own demonstration on a shared screen;
- for pairs whose key fails, or when the class hits rate limits;
- **as the fallback for the whole class**: if the live service fails, say "everyone click **Switch to Replay**". Nothing is lost, and every learning outcome remains reachable.

## 7. Classroom preparation checklist

**One to two weeks before**

- [ ] Get the **private instructor pack** from the course leader (answer key, `INSTRUCTOR_REVIEW.md`). Keep it off shared screens and out of the student area.
- [ ] Ask a **Chinese-reading colleague** to proofread the source text, using the *Native-speaker proofreading checklist* at the end of `INSTRUCTOR_REVIEW.md` (in the pack). You cannot check the Chinese yourself; this step matters.
- [ ] Decide on the connection option (section 3.2) and, if live, create the workspace, spend limit and keys.
- [ ] If you want HKBU GenAI, give the colleague section 4 and agree a date for the test.
- [ ] Publish the repository and enable GitHub Pages (section 3.1).

**Two or three days before**

- [ ] **Test run in Replay:** open the Colab link in a fresh runtime, do Mission 1 end to end (all six sections), export, and import `game_translation_en.json` into the game.
- [ ] **Test live with one key:** **Load my key** → **Test connection** → one full Mission 1 run. Note the cost in the status bar.
- [ ] Open the **game link** on a second device. Check **English** / **繁體中文**, **Reference English**, and import `game/translations/example_student_export_intro.json`.
- [ ] Try the **Checkpoint:** dropdown (**Load checkpoint**) and **Download progress** → **Resume from file** once.
- [ ] Build `studio_bundle.zip` (`python3 tools/make_bundle.py`) and keep it ready to share (section 16).
- [ ] Prepare a breakout-room list of 19 pairs and decide which advanced mission each pair does.
- [ ] Prepare an LMS assignment for `workflow_report.html` (and, optionally, the other two files).

**Backup plan**

- [ ] Live service fails → everyone clicks **Switch to Replay**.
- [ ] GitHub or Colab clone fails → share `studio_bundle.zip`; Step 0 asks for it.
- [ ] GitHub Pages fails → students can still open the game locally with `python3 -m http.server` in the repository folder and visit `http://localhost:8000/game/` (instructor demo only; most students will not do this).
- [ ] A pair falls badly behind → catch-up checkpoints (section 8.3).

## 8. Suggested timing for a 3-hour session

The section times printed in the notebook add up to about 83 minutes for Mission 1, including setup (Setup 3, Connect 5, Mission 5, Configure 15, Run 20, Human Director 25, Export 10). That leaves room for a break, one advanced mission (≈ 35–40 minutes; students are already connected, so they skip Section 1), a debrief and a buffer.

| Clock | Duration | Activity | Roles |
|---|---|---|---|
| 0:00 | 10 min | Welcome, aims, the director principle; quick demo of the game in **Original Chinese** and **Reference English**; explain the two roles. | — |
| 0:10 | 8 min | Breakout rooms. Open the notebook, **File → Save a copy in Drive**, Step 0 (≈3 min), Section 1 (≈5 min: Replay, or **Load my key** → **Test connection**). | Pair decides who starts as AI Director. |
| 0:18 | 5 min | Section 2: start Mission 1. | **🔁 Swap 1** after Section 2. |
| 0:23 | 15 min | Section 3: presets, instructions, **Show full prompt**. | |
| 0:38 | 20 min | Section 4: baseline, translator, **change the prompt → run again → Compare A and B**, reviewer. ⭐ Key activity. | **🔁 Swap 2** after Section 4. |
| 0:58 | 25 min | Section 5: decide on every finding, add a rule, send feedback, approve. | |
| 1:23 | 10 min | Section 6: export, play in the game. | |
| 1:33 | 10 min | **Break.** Ask every pair to click **Download progress** first. | |
| 1:43 | 5 min | Five-minute plenary: "Which finding did you reject, and why?" Assign advanced missions. | **🔁 Swap 3** (**Next mission**). |
| 1:48 | 40 min | One advanced mission (A, B or C), Sections 2–6 (skip Section 1). | Swap again at the orange boxes if time allows. |
| 2:28 | 25 min | Debrief and reflection: each pair writes the reflection and exports again; compare decisions across pairs; collect `workflow_report.html`. | — |
| 2:53 | 7 min | Buffer for overruns, technical problems and catch-up. | — |

**Assigning advanced missions.** Either give every pair the same one (easier to debrief), or split the class into three groups, about 6 pairs each on A, B and C, and have each group report back. **Next mission** in Section 6 always moves to the next mission in the order intro → voice → pun → ui. For B or C, students pick the mission in Section 2 instead.

### 8.1 Role-swap points

The notebook marks three swaps with orange **🔁 Swap roles now** boxes: after Section 2, after Section 4, and after Section 6. Remind students to change **Who is deciding:** in the status bar each time, because every decision in the log is recorded with the role that made it.

### 8.2 Where to put your attention

Section 5 is "the most important part". Spend your breakout-room visits there and ask: *"Show me a finding you rejected. Why?"*

### 8.3 If the class is behind: catch-up checkpoints

The help box (**🆘 If you get stuck**) offers three Mission 1 checkpoints in the **Checkpoint:** dropdown. They are Replay Mode, Balanced preset, en-GB:

| Checkpoint (label in the dropdown) | Contains | Use it if, at about… |
|---|---|---|
| Catch up: agents already run (Mission 1) | baseline + translator run | 0:55, a pair has no translator run yet |
| Catch up: review done (Mission 1) | + reviewer findings, no decisions | 1:00, a pair has not run the reviewer |
| Catch up: revision done (Mission 1) | + sample decisions, one project rule, one revision | 1:20, a pair has not revised (they can still approve and export) |

**Load checkpoint** saves the pair's previous work as a backup first.

Other ways to save time:

- set **Revision cycles allowed:** to `0 (no revision)` and go straight to editing and approval;
- skip **Review again (optional)**;
- move everyone to Replay (no waiting for replies);
- turn the advanced mission into a whole-class demonstration on your screen.

## 9. Running the session remotely

- **One notebook per pair.** The project lives in one Colab runtime: the autosave is `/content/studio_state.json`, which is lost when Colab recycles the runtime. In each breakout room one student shares their Colab tab and clicks. The other directs, and **Who is deciding:** records who decided. To hand the keyboard over, the driver clicks **Download progress** and sends the file in the room chat. The partner opens their own copy, runs Step 0, and uses **Choose file** → **Resume from file**. The studio reminds students to download progress after **Approve final translation** and after every export.
- **Breakout rooms:** one per pair (19 rooms). Visit Section 5 first. Bring everyone back at the break and for the debrief.
- **Your screen share:** share a single browser tab, not your whole desktop. Zoom the browser to 125–150% so the widgets are readable. Demonstrate in **Replay Mode**, so no key is involved. **Never open the Colab Secrets panel while sharing.**
- **Collecting work:** each pair uploads `workflow_report.html` to an LMS assignment, renamed with the team name and mission. In Colab each mission's files go into their own folder (`exports/intro/`, `exports/voice/`, …), but the file names are the same for every mission, so a browser may save a second download as `workflow_report (1).html`. `game_translation_en.json` and `agent_settings.json` are optional extras. The report is a single self-contained HTML file: open it in any browser.
- **Live help:** ask students to paste the **error message text** (not screenshots of their Secrets) in the room chat. The text never contains the key, because the studio masks it.

## 10. Using the game without reading Chinese

- **Interface** (top right) switches menus, buttons and messages between **English** (the default) and **繁體中文**. It does not change the dialogue.
- **Dialogue language** has three options:
  - **Original Chinese (原文)**: the source;
  - **Reference English (參考譯文)**: the course team's translation, so you know what happens in every scene. The badge reads "Showing: Reference English (course team) — one possible solution";
  - **Student's imported English (學生譯文)**: available after **Import student JSON** or **Paste JSON** → **Check and apply**. The game switches to it automatically when a file is applied.
- **Comparing student and reference.** Play a scene in **Student's imported English**, then switch to **Reference English** on the same screen. Do not mark differences as errors. The reference is **one possible solution**. Judge the student's text against the *Intended meaning* and *What to look for* items in `INSTRUCTOR_REVIEW.md`, and against the answer key (both in the private instructor pack).
- **"N strings in this mission are still in Chinese."** The imported file does not cover every string of that mission. Usually the students imported a different mission's file.
- **Several files:** you can import several students' files one after another. Later imports override earlier ones. **Reset to 中文** clears all imports. Reloading the page also clears them.
- **Demo file:** `game/translations/example_student_export_intro.json` is a plausible Replay export of Mission 1 for showing the import before students have their own.

## 11. Mission-by-mission teaching notes

The mission answer key is in the private instructor pack — ask the course leader. It lists, for each mission and preset, what the prepared Replay outputs get wrong, which reviewer findings are wrong or debatable, and how to spot a wrong finding that a pair accepted. Below are the objectives, what to watch for (also useful in Live Mode) and discussion questions.

### Mission 1 — The Lantern Mystery (Introductory, `intro`)

**Objectives:** set up the two agents and compare them with the baseline; keep `{player_name}` and the 12-character button limit; two distinct voices (proud, proverb-loving Granny Wong vs slangy teenager Kit); make culture-bound expressions work; act as director.

**What to watch for:** `intro.ui.start` over 12 characters ("Start Investigation" is 19); `{player_name}` dropped, translated or turned into "Detective {player_name}" (shows "Detective Detective" with the default name); the rabbit saying (歇後語) rendered word for word; Kit flattened into polite English; "tea restaurant" for 茶餐廳; "Osmanthus Street" instead of the **required** "Kwai Heung Street"; Chinese quotation marks 「」 or "……" left in the English.

**Discussion questions**

- How do you translate a saying whose humour depends on a rabbit, in a story about a rabbit lantern: keep the image, replace it, or explain it?
- 茶餐廳: "cha chaan teng", "café" / "diner", or a gloss? What does each do for an international player?
- British, American or neutral "internet" slang for Kit? Does the English variant matter here?
- What happens to "Detective {player_name}" when the default name is "Detective"?

### Mission 2 — An Evening at the Lantern Shop (Challenge A: Character Voice, `voice`)

**Objectives:** register, terms of address and code-mixing build a character; instructions that keep two distinct voices; use the reviewer to spot "flattened" lines; idiom vs paraphrase for 成語.

**What to watch for:** "Grandma" for 婆婆 (it wrongly makes them family; the required term is "Granny"); "Ah Kit" or "Kit Boy"; Kit and Granny speaking the same polite English; "clock in" for 打卡 (here it means a social-media check-in); English words already in the source ("old school", "feel") copied unnaturally ("it has feel"); two speakers in `voice.ending.b` normalised into one register.

**Discussion questions**

- Read only Granny's lines aloud, then only Kit's. Could you tell who is speaking without the name tag?
- Is the affection in a term of address like 阿杰仔, or in the sentence around it?
- The source already contains English words. Is code-mixing still visible in an English translation? How could you show it?
- What happens if a pair mixes British and American slang for Kit?

### Mission 3 — The Riddle King (Challenge B: The Pun Boss, `pun`)

**Objectives:** tell a translatable pun from one that must be recreated; handle linked strings (riddle, answer and reaction change together); brief the translator to prioritise effect over literal meaning; handle lantern riddles (猜燈謎) for international players.

**What to watch for:** the character riddle translated literally, which makes it unsolvable in English ("Guess one character!", answer "免" left in Chinese); a pun *explained* instead of made; **linked strings that no longer agree** (`pun.line.king_riddle`, `pun.choice.answer`, `pun.ending.a`). The validator cannot catch this; only a human can. Also: the 50-character limit on answer buttons, "two eggs" not understood as "zero", and 『』 brackets left in.

**Discussion questions**

- Which puns can be translated, which must be replaced, and which could be dropped if the scene still works?
- For the character riddle, what must stay (a rabbit losing its tail, a solvable answer) and what may change (the answer word)?
- How do you make the agents translate the three linked strings consistently? (A project rule? One instruction?)
- en-GB "duck" vs en-US "goose egg": how does the English variant change the roast in Ending B?

### Mission 4 — The Detective's Toolbar (Challenge C: The Interface Trap, `ui`)

**Objectives:** keep placeholders such as `{lantern_count}` exactly as written; respect character limits (placeholder tokens count literally); know when a line break is allowed; read the validator's report and fix CRITICAL issues before export.

**What to watch for:** dropped, translated (`{物品名稱}`) or broken (`{coins`) placeholders; overlong buttons ("Use the item" is 12, limit 10); a line break in the status bar (only the toast, `ui.hud.toast`, may have one); leftover Chinese; **the counter in the wrong order** ("Lanterns: {lantern_total}/{lantern_count}" shows "5/2" but passes validation); "You raise {item_name}" without an article (displays as "You raise torch").

**Discussion questions**

- Why must `{lantern_count}` stay exactly as it is, even though it "looks like" English?
- What would a player think if the status bar said "Lanterns: 5/2"?
- Placeholders count towards the limit as written. How much room is really left?
- Which problems did the validator catch, and which needed a human (word order, tone, articles)?

## 12. Assessing the workflow report

Each `workflow_report.html` contains: project details and mode (with a Replay notice if applicable); source, baseline, agent-reviewed and final translations side by side; every finding with the human decision, the human text, the comment and *Agreed / overrode*; the project rules; the validation results; the version history; the prompt evolution (default → current instructions, first → latest prompt sent); the usage counters; and the reflection.

A simple rubric (adapt the weights to your course):

| Criterion (weight) | Strong | Adequate | Weak | Where to look in the report |
|---|---|---|---|---|
| **Agent configuration** (20%) | Instructions rewritten in the pair's own words, targeted at this mission's challenge; at least one deliberate prompt change compared and explained. | Preset adjusted with minor edits; one comparison made. | Preset left unchanged; no comparison. | Prompt evolution; version history |
| **Critical evaluation of findings** (30%) | Every finding decided; the wrong findings (see the answer key in the instructor pack) rejected or overridden; debatable ones argued either way. | Most findings decided; some wrong findings accepted, or comments missing. | Everything accepted; no comments. | Findings and decisions table; *Agreed / overrode* column |
| **Justified interventions** (20%) | Comments give reasons (meaning, voice, constraint, glossary, linked strings); useful project rules; direct edits where the reviewer missed something. | Some reasons; generic rules. | Interventions without reasons. | Comments; rules; human-edit versions |
| **Technical validity** (15%) | Approved; no CRITICAL issues; warnings checked; placeholders and limits respected; the game plays correctly. | Approved with warnings left unexplained. | Not approved / export blocked, or obvious placeholder errors. | Validation section; final translation column |
| **Reflection** (15%) | Specific: names strings, quotes before and after, links outcomes to prompt changes and decisions, admits what did not work. | General but accurate. | Vague or missing. | Reflection |

A pair working in Replay Mode is not disadvantaged. Assess their judgement, not the model's output.

## 13. Common student errors

- **Accepting everything.** Clicking **Accept** on every finding without reading them.
- **Not counting characters** in a suggested button label, or forgetting that a `{placeholder}` token counts towards the limit.
- **Treating the reviewer, or the Reference English, as the answer key.**
- **Changing several things at once**, then being unable to say what caused a difference.
- **Editing the preview box** under **Show full prompt** (it changes nothing), instead of the instructions box.
- **Expecting Replay to respond to their own wording**, when only preset changes produce different prepared outputs.
- **Forgetting to change "Who is deciding:"** after a swap, so the log attributes decisions to the wrong role.
- **Typing in the edit grid and then running another step** without **Save edits as new version**.
- **Changing something after approval** and not noticing the "Approval revoked" message, then wondering why export is blocked.
- **Accepting only one of a set of linked strings** (the pun riddle, its answer and Ending A; the café choice and Ending B).
- **Translating or reformatting placeholders**, for example `{player name}` or `{玩家名稱}`.
- **Importing the wrong file into the game** (`agent_settings.json` instead of `game_translation_en.json`), or a file from another mission.
- **Writing personal data** (names, student numbers) in the team name, comments or rules.

## 14. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Colab warns "This notebook was not authored by Google". | Normal for notebooks opened from GitHub. | Click **Run anyway**. |
| A section cell prints "⏳ The studio is not set up yet…". | The section cell ran before Step 0 finished, or Step 0 failed. | Run Step 0 again, wait for **The studio is ready**, then rerun the section cell. |
| Widgets do not appear (no buttons, or text such as `VBox(...)`). | The widget display did not load in the browser, often because of a blocked third-party cookie or an extension. | Rerun Step 0, then the section cell. Try **Runtime → Restart session** and run again. Use an up-to-date Chrome or Edge, and allow cookies for colab.research.google.com. |
| "No Claude (Anthropic) key was provided. (Add it in Colab under the key icon (Secrets) as ANTHROPIC_API_KEY and allow notebook access.)" | The secret name is misspelt (it is case-sensitive), the secret was added to a different notebook copy, or **Notebook access** is off. | Check the exact name, switch on **Notebook access**, click **Load my key** again. Colab may ask once to grant access; accept. As a last resort, use the hidden password box that appears under the buttons. |
| "…key was not accepted." | Wrong or revoked key, or part of the key was pasted. | Paste the whole key again into the secret's value, or issue a new key. |
| "…account has no credit left…" | Billing limit reached in the Console. | Raise the spend limit, or move the class to Replay. |
| "…service is busy — many classmates are using the service at once." | Rate limit: likely with 19 pairs on one shared key, all clicking at the same moment. | Wait 30 seconds and retry (the studio already retries twice). Stagger the groups ("odd rooms run now, even rooms in one minute"), move some pairs to Replay, or use one key per pair. |
| "…did not answer within 45 seconds." | Slow service or network. | Try again; otherwise **Switch to Replay**. |
| "You have used all 40 live requests allowed for this exercise." | The session request cap (status bar: **Live requests this session: 40 / 40**). | **Switch to Replay**, or raise `limits.request_cap` in `config/providers.json` before class. Running Step 0 again starts a new count. |
| "The translator reply could not be read, even after one repair request." | The model returned something that is not the required JSON, often after very long or contradictory instructions. | Try again; simplify the instructions; or switch to Replay. The raw reply is kept in the project. |
| "The translator reply was cut off because it was too long, even after asking for a shorter reply…" | The reply hit the output limit (`limits.max_tokens`, 4000 by default), usually because the instructions ask for long notes. | Ask for short notes, use fewer strings, or switch to Replay. Nothing was changed. |
| "⚠️ Only part of this step worked. …" | A later batch failed (busy service, cap, unreadable reply) after earlier batches succeeded. Only possible with more than 8 strings, i.e. custom uploads. | The finished strings are kept; the others keep their previous text. Run the step again to retry them. |
| "The reviewer checked N string(s) and found no problems." | The reviewer really had nothing to say about those strings. | Normal. Encourage the pair to look for what the reviewer missed. |
| "Review skipped: no string has changed since the last review…" | No string changed since the last review, so no request was sent. | Edit strings or run a revision first, then review again. |
| "⚠️ The reviewer replied with N finding(s), but none could be used…" | Every finding in the reply named a string id that does not exist or had no issue text, so all were dropped (the message lists the counts). This does **not** mean the translation is fine. | Run the reviewer again, or switch to Replay. |
| "This text contains your API key — remove it from the …" | A student pasted their key into instructions, a comment, a rule, the reflection or an uploaded file. | Remove it. The key belongs only in Colab Secrets. If it was shown on screen, rotate it. |
| "Autosave failed: … Fix it, or click “Download progress”." (also in the status bar, with the reason) | The project could not be written (for example it contains something that looks like a key, or the disk is full). | Fix the reason shown, then click **Download progress**. |
| Nothing downloads after **Download progress** or an export. | The browser blocked an automatic (or a second) download, or Colab could not start it. Chrome asks before a site downloads several files at once ("Export all three files"); once a student clicks **Block**, *every* later download from Colab silently fails, including single files (observed in testing). The message only says **download started** when Colab accepted the download; otherwise it says "use the Files panel to download it". | The file is always saved: open the Files panel (📁 folder icon on the left) → `exports` (progress files) or `exports` → the mission's folder, e.g. `intro` (exports) → **⋮** next to the file → **Download**. Click the download icon at the right of Chrome's address bar → **Always allow … to download multiple files** → Done (or chrome://settings/content/automaticDownloads → allow colab.research.google.com). A repeated download may be saved as `game_translation_en (1).json`; that is the same file. |
| Colab disconnected, same runtime. | Idle timeout or network drop. | Run Step 0 again → **Resume my saved session** (the autosave is still in `/content`). |
| **Resume my saved session** says no saved session was found. | The runtime was deleted or recycled, and the autosave (`/content/studio_state.json`) went with it. | **Resume from file** with a progress file. This is why students should **Download progress** before every break. Otherwise load a **Checkpoint:**. |
| A configuration change you pushed is not visible to a student. | Their runtime holds the copy cloned earlier and the update in Step 0 failed ("Using the copy already downloaded"), or the studio was installed from the bundle. | Ask them to run Step 0 again. If that still fails: **Download progress**, then **Runtime → Disconnect and delete runtime**, run Step 0 again, **Resume from file**. |
| The game still shows Chinese after import. | **Dialogue language** was switched back to **Original Chinese** (the game selects **Student's imported English** by itself after a successful import); the page was reloaded (imports are not kept); or the file belongs to another mission ("N strings in this mission are still in Chinese."). | Choose **Student's imported English** again; import again after a reload; check the mission. |
| The game says **This file was not applied**. | The file has a **Must fix** problem (broken placeholder, too long, invalid JSON), is the wrong file, was edited by hand, or is over 100 KB. | Fix the strings in the notebook, approve, export again and reimport. Nothing in the game changes until a file passes. |
| The game or the studio lists a check such as "The file does not say where the translation came from (no 'source')." or "The 'locale' should be one of en-GB, en-US, en, zh-Hant-HK…". | The file was edited or assembled by hand. These are warnings; a wrong `source` value is a **Must fix** problem. | Use the file exported by the studio; it sets `source` and `locale` itself. |
| A **CHECK** item says a string "has a space (or an invisible space-like character) at the start or end, or a double space." | Extra spaces, often invisible ones pasted from a word processor (non-breaking or full-width spaces). | Retype the start and end of the string in the edit grid. |
| The game shows "The game files could not be loaded". | It was opened from a downloaded file (`file://`), or Pages is not yet live. | Use the GitHub Pages link, or run `python3 -m http.server` in the repository folder and open `http://localhost:8000/game/`. |
| Choosing **HKBU GenAI** shows "HKBU GenAI is not set up for this course yet…". | `base_url` in `config/providers.json` is empty. | Configure it (section 4), or use Claude or Replay. |
| Export is blocked ("Export blocked — nothing was written…"). | Not approved, the approved version is not the current one, or there are MUST FIX issues. | Fix in the edit grid (Section 5, d.), **Approve final translation** (g.), export again. |
| Step 0 shows "The studio could not be downloaded automatically". | The repository is private, unpublished, or GitHub is unreachable. | Upload `studio_bundle.zip` with **Upload bundle**, or drag it into the Files panel and run Step 0 again (section 16). |

## 15. Security and privacy

- **Keys.** Students keep keys in Colab Secrets, which belong to their Google account. The studio reads the key once, keeps it only inside the connection object in memory, and never stores it in the project, the autosave, the progress file, messages or exports. Error messages mask it. If anything that looks like a key appears in instructions, comments, rules or translations, the studio refuses to save or export it. These behaviours are covered by `tests/test_security.py`, `tests/test_providers.py` and `tests/test_notebook_ui.py`.
- **Configuration files never contain keys**, only the *name* of the secret.
- **What is sent to a live provider:** the system and user prompts shown by **Show full prompt**. That is the game's source text, context, character profiles and glossary; the pair's instructions and settings; their project rules; for the reviewer, the translation under review; for a revision, the accepted findings and the director's comments. **No personal data is needed.** Tell students not to write names, student numbers or other personal details in instructions, comments or rules. The team name is not sent to the model, but it appears in the exports.
- **Replay Mode** makes no network requests at all (tested in `tests/test_security.py`).
- **Exports contain no keys.** `agent_settings.json` records models, prompts, settings, glossary and rules. `workflow_report.html` is a self-contained page with no scripts and no external resources (tested). The game renders imported text as plain text only (tested in `tests/game/security.test.js` and the end-to-end suite).
- **The reference English never reaches the agents.** It lives only in `game/translations/en.reference.json` and in the private instructor pack; `tests/test_reference_isolation.py` checks this.
- **The answer key is not in this repository.** Teaching notes, instructor notes, `INSTRUCTOR_REVIEW.md` and the content generator live in the private instructor pack; `tests/test_content.py` checks that none of them is in the public files.
- **After the session,** delete or rotate the class keys.

## 16. Pre-publication testing with `studio_bundle.zip`

Use this before the repository is public, or as a fallback on the day.

1. On your computer, in the repository folder, run:

   ```bash
   python3 tools/make_bundle.py
   ```

   This writes `dist/studio_bundle.zip` (code, configuration, missions, fixtures, game and notebook; no tests, no saved student files, no instructor pack material). `dist/` is not committed to Git.
2. In Colab, open the notebook with **File → Upload notebook** (choose `notebooks/Game_Localisation_Studio.ipynb`), or use the GitHub link if the repository is public.
3. Run Step 0. It prints "Downloading the studio…". If the repository cannot be cloned, there are two routes:
   - **Upload button:** Step 0 shows **The studio could not be downloaded automatically** and an **Upload bundle** button. Upload `studio_bundle.zip`, and wait for "✅ Done. The studio is installed."
   - **Files panel:** drag `studio_bundle.zip` into Colab's Files panel (📁 folder icon on the left; it lands in `/content/studio_bundle.zip`), then run Step 0 again. It prints "Could not download from GitHub — using studio_bundle.zip from the Files panel." and installs it. The Files panel route is useful when the upload widget does not appear.
4. Continue with Section 1 as normal.

The setup cell checks the zip before unpacking it (no unsafe paths, size limits). This is tested in `tests/test_notebook_exec.py`. Share the zip with students only through the LMS.

## 17. Extending the activity

- **New missions.** All game and challenge content is generated from one data source by `tools/gen_content.py`, which is in the private instructor pack because it also holds the instructor notes. Add a mission there, then run `python3 tools/gen_content.py <path to this repository>` from the pack. It rewrites the manifest, story, translations and challenge files in the repository, and the instructor notes and `INSTRUCTOR_REVIEW.md` in the pack. For Replay Mode, add prepared outputs for the new mission to `fixtures/replay_outputs.json` (one per preset). For **Next mission**, add its id to `MISSION_ORDER` in `src/studio_ui.py`. Then run the tests, which check consistency between the content files, and have the new source text proofread.
- **New providers or models.** A new model for an existing provider is a single entry in `config/models.json`. An OpenAI-compatible service can often be connected through the configurable HKBU fields (section 4). A provider with a different protocol needs code in `src/providers.py`.
- **Students' own material.** In Section 2, students can upload a `.txt` (one string per line), a `.csv` with a `source` column (optional: id, context, max_len, speaker) or a `.json` file. The limits are UTF-8, 200 KB, 200 strings and 500 characters per string. Custom material goes through the whole workflow and exports `custom_translation_en.json` and the report, but **cannot be played in the game** and has no Replay outputs (use Live Mode).
- **More revision cycles.** **Revision cycles allowed:** in Section 5 offers 0, 1 (default) or 2, with an optional round-2 review. Use 2 with stronger groups to discuss diminishing returns.
- **Other variations:** run the same mission with Haiku and Sonnet in different rooms and compare; give one group the reviewer at **Review strictness** 5 and another at 1; ask pairs to write a project rule that fixes the linked-strings problem in Challenge B.
