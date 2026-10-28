# Contracts — Game Localisation Studio v0.3

This file is the shared interface between the game, the challenge content, the Python engine and the notebook UI. If you change a contract, update this file in the same change.

Repository root = `game-localisation-studio/`. Python code is imported as the package `src` (the repo root is put on `sys.path`). All JSON files are UTF-8, 2-space indented, with `ensure_ascii=False`.

---

## 1. Ownership (who writes what)

| Area | Owner | Notes |
|---|---|---|
| `game/strings_manifest.json`, `game/story.json`, `game/translations/zh-Hant.json`, `challenges/*.json` | Content | the single source of truth for ids and constraints |
| `game/index.html`, `game/game.js`, `game/validator.js`, `game/style.css`, `game/assets/*`, `tests/game/*` | Game | must NOT edit the content files |
| `src/providers.py`, `agents.py`, `validation.py`, `project_state.py`, `exports.py`, `importers.py`, `config/*.json`, `tests/test_*.py` | Engine | |
| `src/studio_ui.py`, `src/ui_compat.py`, `notebooks/*.ipynb`, `tests/test_notebook*.py` | UI (wave 2) | |
| `fixtures/replay_outputs.json`, `fixtures/checkpoints/*` | Replay (wave 2) | |
| *private instructor pack* (`../instructor-pack/`, **not** in this repository): `teaching_notes.json`, `instructor_notes/<challenge>.json`, `ANSWER_KEY.md`, `INSTRUCTOR_REVIEW.md`, `tools/gen_content.py` | Content / Replay | the answer key. Tests read it from `INSTRUCTOR_PACK` (default `../instructor-pack` relative to the repo root) and skip with a clear reason if it is absent. `tools/gen_content.py <repo> [<pack>]` writes the public content files into the repo and the instructor notes and `INSTRUCTOR_REVIEW.md` into the pack. |

---

## 2. Missions and string ids

There are four missions. Each is a short scene that can be **played on its own**.

| mission id | challenge file | strings | focus |
|---|---|---|---|
| `intro` | `challenges/introductory.json` | exactly 8 | everything a little; both endings reachable |
| `voice` | `challenges/character_voice.json` | 6–8 | character voice, register, relationships |
| `pun` | `challenges/pun_boss.json` | 5–7 | wordplay, humour, cultural references |
| `ui` | `challenges/interface_trap.json` | 6–8 | char limits, placeholders, ids, formatting |

String id format: `<mission>.<kind>.<name>`, matching the regex `^[a-z]+\.[a-z_]+\.[a-z0-9_]+$`, for example `intro.ui.start`, `intro.line.granny_greeting`, `intro.choice.follow`, `intro.ending.a`.

Placeholders are written `{snake_case}` (regex `\{[a-z_][a-z0-9_]*\}`). The game supplies these runtime values:

| placeholder | value in game |
|---|---|
| `{player_name}` | name typed by the player (default `偵探` / `Detective`) |
| `{lantern_count}` | integer, lanterns found |
| `{lantern_total}` | integer, total lanterns |
| `{coins}` | integer |
| `{item_name}` | an inventory item name (fixed bilingual pair inside the game, not translatable) |

Content may use only these placeholders.

---

## 3. `game/strings_manifest.json`

```json
{
  "schema_version": "1.0",
  "game": "lantern-mystery",
  "source_locale": "zh-Hant-HK",
  "characters": {
    "granny_wong": {"name_zh": "黃婆婆", "name_en_default": "Granny Wong", "colour": "#c0392b"},
    "kit":         {"name_zh": "阿杰",   "name_en_default": "Kit",         "colour": "#2471a3"}
  },
  "missions": [
    {"id": "intro", "title_zh": "…", "title_en": "…", "challenge_file": "challenges/introductory.json",
     "string_ids": ["intro.ui.start", "…"]}
  ],
  "strings": {
    "intro.ui.start": {
      "mission": "intro",
      "type": "ui",
      "speaker": null,
      "placeholders": [],
      "max_len": 12,
      "allow_newlines": false
    }
  }
}
```

Rules:
- `type` ∈ `ui | narration | dialogue | choice | ending`.
- `speaker` is a key of `characters`, or `null` for narration/UI.
- `placeholders` lists every placeholder in the zh-Hant source, each occurring exactly once. The translation must contain **the same multiset**.
- `max_len` (int or null) counts Unicode code points of the translated string **as written**, with placeholder tokens counted literally.
- `allow_newlines` defaults to `false`. `\n` is permitted only when it is `true`.
- Every `string_ids` list must match the ids in that mission's challenge file.

Mission titles and the game's own chrome (Import / Reset / mission selector / name box) are **fixed bilingual** text inside the game and are not translated by students.

## 4. `game/story.json` (scene graph)

```json
{
  "schema_version": "1.0",
  "missions": {
    "intro": {
      "start": "n1",
      "nodes": {
        "n1": {"kind": "title",  "text": "intro.ui.start", "next": "n2"},
        "n2": {"kind": "line",   "text": "intro.narration.arrival", "next": "n3"},
        "n3": {"kind": "line",   "text": "intro.line.granny_greeting", "next": "n4"},
        "n4": {"kind": "choice", "options": [
                 {"text": "intro.choice.follow", "next": "endA"},
                 {"text": "intro.choice.ask",    "next": "endB"}]},
        "endA": {"kind": "ending", "text": "intro.ending.a", "ending": "A"},
        "endB": {"kind": "ending", "text": "intro.ending.b", "ending": "B"}
      }
    }
  }
}
```

- `kind` ∈ `title | line | choice | ending | hud`. In a `title` node the string is the start button label.
- A `line` node takes its speaker from the manifest entry of its `text` string.
- `hud` (used by the `ui` mission) is `{"kind": "hud", "texts": ["ui.hud.lanterns", …], "next": "…"}`: several UI strings shown at once (status bar, buttons, inventory, toast).
- Each mission must have exactly two endings, `A` and `B`, both reachable through one `choice` node that has exactly two options. (A mission may have a second choice before that.)
- Every string id of the mission appears somewhere in its graph.

## 5. `game/translations/zh-Hant.json` and the game translation file (Export A)

Source file:
```json
{"format": "lantern-mystery-translation", "schema_version": "1.0", "locale": "zh-Hant-HK",
 "source": "original", "strings": {"intro.ui.start": "開始調查", "…": "…"}}
```

Exported English file, `game_translation_en.json`:
```json
{
  "format": "lantern-mystery-translation",
  "schema_version": "1.0",
  "locale": "en-GB",
  "mission": "intro",
  "source": "replay",
  "approved": true,
  "generated_by": "Game Localisation Studio v0.3",
  "generated_at": "2026-11-01T10:00:00Z",
  "characters": {"granny_wong": "Granny Wong", "kit": "Kit"},
  "strings": {"intro.ui.start": "Investigate", "…": "…"}
}
```

- `locale` ∈ `en-GB | en-US | en` (international English).
- `source` ∈ `live | replay | mixed | original | reference` (`reference` = `game/translations/en.reference.json`, the course team's reference English, which may carry an extra `note` field; it is never sent to agents). The game shows a "simulated (Replay Mode)" badge when it is `replay` or `mixed`.
- `characters` is optional. Each value is a non-empty string of at most 20 code points with no newline.
- `mission` is optional, informational only.
- File size is at most 100 KB.
- **Game import via URL fragment.** Besides file/paste import, the game accepts the same file in the
  link `<game url>#t=<base64url(UTF-8 compact JSON)>` (§12 `game_play_url`). `validator.js`
  `decodeSharedTranslation(fragment)` accepts `#t=…` or `t=…` (padding optional) and returns
  `{ok: true, text}` or `{ok: false, code, message, message_zh, fix_hint, fix_hint_zh, issue}` with
  `code` ∈ `invalid_link` (no `t` parameter, empty, not base64url, not UTF-8) | `file_too_large`
  (decoded payload over 100 KB). On success the text goes through the normal import (same validation,
  CRITICAL panel, Student option and badges; source label "link from Colab" / 「來自 Colab 的連結」);
  on failure the error panel is shown and the dialogue stays Chinese. Either way the game removes the
  fragment (`history.replaceState`), so a reload does not import it again and nothing is stored.
  `invalid_link` is a game-only code (not in the Python/JS file-validation parity set).

### Validation rules (Python `validation.py` and JS `validator.js` MUST agree)

**CRITICAL** issues block the import or export:

| code | rule |
|---|---|
| `invalid_json` | the text does not parse as JSON |
| `wrong_format` | `format` ≠ `lantern-mystery-translation`, or the major part of `schema_version` ≠ 1 |
| `bad_structure` | `strings` is not an object of string → string, `characters` is malformed, or `source` is present but not one of the allowed values |
| `unknown_id` | the id is not in the manifest |
| `duplicate_id` | the same key appears twice (Python only — JS `JSON.parse` cannot detect this; documented) |
| `missing_id` | an id required by the mission is absent or empty. The **Python export** requires every id of the mission. The **game import** treats missing ids as a WARNING and falls back to Chinese. |
| `empty_text` | the value is empty or whitespace-only |
| `placeholder_missing` / `placeholder_extra` / `placeholder_broken` | the placeholder multiset differs from the manifest, or a stray `{` or `}` / malformed token appears (e.g. `{player name}`, `{player_name`) |
| `too_long` | longer than `max_len` |
| `newline_not_allowed` | contains `\n` or `\r` when `allow_newlines` is false |
| `bad_encoding` | contains lone surrogates, control chars (other than `\n`), or U+FFFD |
| `file_too_large` | over 100 KB |

**WARNING** issues are shown but do not block:

| code | rule |
|---|---|
| `untranslated_cjk` | contains CJK ideographs (U+3400–U+9FFF) |
| `whitespace` | leading/trailing whitespace (JavaScript's `\s` set, so U+FEFF, U+00A0, U+3000 … count; U+200B does not), or a double space |
| `angle_brackets` | contains `<` or `>` (they will display literally) |
| `near_limit` | ≥ 90% of `max_len` |
| `missing_id` | (game import only, see above) |
| `bad_structure` | `source` is missing, or `locale` is missing / not a string / not one of `en-GB`, `en-US`, `en`, `zh-Hant-HK` |

Each issue is `{severity, code, string_id|null, message, fix_hint}`. `message` and `fix_hint` are written in plain English for a non-programmer, e.g. *"The button text 'Start investigating' is 19 characters, but the limit is 12."* / *"Shorten it — try a single verb such as 'Investigate'."*

**Resolutions agreed between `validation.py` and `validator.js`** (both implement these; `tests/test_cross_validator.py` runs both over the same broken files):
- (a) Manifest `placeholders` may be written `"{x}"` or `"x"`; both mean `{x}`.
- (b) "Control chars" = U+0000–U+001F except `\n`, plus U+007F–U+009F. So `\r` and `\t` are always `bad_encoding`; `\r` is *also* `newline_not_allowed` when newlines are disallowed.
- (c) A present but empty/whitespace-only value gives only `empty_text` (never `missing_id` too). `missing_id` means the key is absent.
- (d) Game-file validation: missing ids are WARNING by default, for every mission the file touches plus its `mission` field. With `require_all_for_mission` (Python) / `requireAllForMission` (JS) they are CRITICAL — the Python export always uses this.
- (e) A `characters` key that is not in the manifest is CRITICAL `bad_structure`. A name that is empty, longer than 20 code points or contains a newline is `bad_structure`; one with control/broken characters is `bad_encoding`; Chinese in a name is a `untranslated_cjk` WARNING.
- (f) `source` ∈ `live | replay | mixed | original | reference`: a present but different value is CRITICAL `bad_structure`; a missing `source` is a WARNING `bad_structure`. `locale` must be a string in `en-GB | en-US | en | zh-Hant-HK`, else WARNING `bad_structure`. `approved` and `generated_*` are informational.
- (g) "Whitespace" (for `empty_text` and `whitespace`) is JavaScript's `\s` set in both validators (Python uses `validation.JS_WHITESPACE`, not `str.strip()`).
- A top-level value that is not an object is `wrong_format`. A wrong `format` and a wrong `schema_version` are reported separately, and string checks still run. A non-string value is `bad_structure` for that id. Broken-placeholder messages may list one or several fragments; the code set is what must agree.

## 6. Challenge files `challenges/*.json`

```json
{
  "schema_version": "1.0",
  "id": "intro",
  "mission": "intro",
  "title": "Mission 1 — The Lantern Mystery (Introductory)",
  "title_zh": "…",
  "estimated_minutes": 80,
  "brief": "2–4 sentences for students",
  "teaching_objectives": ["…"],
  "scene_context": "what happens in this scene, where, why",
  "characters": [
    {"id": "granny_wong", "name_zh": "黃婆婆", "name_en_suggestion": "Granny Wong",
     "profile": "…", "voice": "…", "relationships": "…"}
  ],
  "glossary": [
    {"source": "紮作", "target": "paper-craft lantern making", "strictness": "preferred", "note": "…"}
  ],
  "strings": [
    {"id": "intro.ui.start", "source": "開始調查", "type": "ui", "speaker": null,
     "context": "start button on title screen", "intended_meaning": "…",
     "constraints": ["Maximum 12 characters", "Imperative verb"],
     "placeholders": [], "max_len": 12, "allow_newlines": false,
     "focus": ["ui_constraint"]}
  ]
}
```

- `title` is `"Mission <n> — <manifest title_en> (<label>)"`, where `<n>` is the mission's position in the manifest and `<label>` is `Introductory` or `Challenge A: Character Voice` / `Challenge B: The Pun Boss` / `Challenge C: The Interface Trap`, so the studio and the game use the same mission names (tested). `estimated_minutes` is 80 for the intro (including setup) and 40 for each advanced mission (students skip Section 1).
- **Instructor notes are not in the challenge files.** They live in the private instructor pack, one file per challenge, `instructor_notes/<challenge file name>.json`:
  ```json
  {"schema_version": "1.0", "mission": "intro", "challenge_file": "challenges/introductory.json",
   "instructor_notes": {"discussion_points": ["…"], "defensible_solutions": {"intro.line.x": ["…", "…"]},
                        "deliberate_traps": ["…"], "common_ai_errors": ["…"]}}
  ```

- `focus` tags are taken from: `character_voice, cultural, humour, wordplay, ambiguity, variable, ui_constraint, choice, formatting, terminology`.
- `strings[*].placeholders`, `max_len`, `allow_newlines`, `type` and `speaker` MUST equal the manifest entries (a test cross-checks this).
- Should a challenge dict ever carry `instructor_notes` (e.g. an uploaded full challenge file), they are never sent to a model, never shown in the notebook and never exported.
- **Custom uploads** (`importers.py`) produce the same shape with `id: "custom"`, `mission: "custom"`, ids `custom.text.001`, … They are not game-compatible. Export A is then written as `custom_translation_en.json`, with the same envelope and `mission: "custom"`, validated against the challenge's own constraints.

## 7. Agent output schemas (what models must return)

The translator, baseline and reviser all return:
```json
{"translations": [{"id": "intro.ui.start", "text": "Investigate", "note": "short rationale (optional)"}]}
```

The reviewer returns:
```json
{"findings": [
   {"string_id": "intro.line.granny_greeting",
    "category": "character_voice",
    "severity": "major",
    "issue": "what is wrong",
    "reasoning": "why it matters",
    "suggestion": "the full replacement English string"}],
 "overall_comment": "one or two sentences"}
```
- `category` ∈ `accuracy | fluency | terminology | cultural | character_voice | technical`.
- `severity` ∈ `minor | major | critical`.
- The code assigns `finding_id = f"R{round}-{n:02d}"`. Findings whose `string_id` is unknown are dropped and the number dropped is reported.
- An unknown `category`/`severity` is mapped to the nearest allowed value (aliases, else `accuracy` / `minor`); `parse_findings` marks such findings with `normalised` (e.g. `"category 'style' → fluency"`) and the run message shows it.

Parsing accepts a bare JSON object, a JSON object inside a ```json fence, or a JSON object surrounded by prose. On failure the engine makes **one** repair request. If that also fails, it raises `AgentOutputError` with a plain-English message and keeps the raw text in state for inspection. Nothing is fabricated.

## 8. Replay fixtures `fixtures/replay_outputs.json`

```json
{
  "label": "SIMULATED OUTPUT — prepared in advance by the course team. Not generated live.",
  "schema_version": "1.0",
  "challenges": {
    "intro": {
      "baseline":   {"translations": […]},
      "translator": {"translations": […]},
      "reviewer":   {"findings": […], "overall_comment": "…"},
      "reviewer_round2": {"findings": […], "overall_comment": "…"},
      "revision_notes": {"<string_id>": "note the simulated translator gives when applying feedback"}
    }
  }
}
```
These are stored in exactly the shape a model would return. `ReplayProvider` serves them as JSON **text**, so the same parsing path is exercised. `reviewer_round2` findings are filtered down to the strings that were actually revised. The file may also carry `locale_note`. It carries **no** answer key: the verdicts for these findings (`teaching_notes`) live in the private instructor pack as `teaching_notes.json` (`{schema_version, teaching_notes_readme, teaching_notes}`; shape in §15). `ReplayProvider` works without them.

**Replay revision is deterministic** and does not use a fixture translation. For each string with an `accept` decision, the new text is the reviewer's `suggestion`. For `accept_edited` and `override` decisions it is the human text. Every other string is unchanged. The note comes from `revision_notes`, or else "Applied accepted reviewer suggestion (simulated)."

## 9. `ProjectState` (`src/project_state.py`) — JSON-serialisable dataclasses

```text
ProjectState
  schema_version: "1.0"
  created_at, updated_at: ISO-8601 UTC strings
  team_name: str                      # optional free text; no other personal data stored
  challenge_id: str                   # "intro" | "voice" | "pun" | "ui" | "custom"
  locale: "en-GB" | "en-US" | "en"
  mode: "live" | "replay"
  provider: {name, translator_model, reviewer_model}        # NEVER a key
  agents: {"translator": AgentConfig, "reviewer": AgentConfig}
      AgentConfig = {settings: dict, instructions: str, default_instructions: str}
  memory_rules: [Rule]
      Rule = {rule_id "M01", kind "glossary"|"style", text, source_term|None, target_term|None,
              from_finding|None, role, created_at}
  versions: [Version]
      Version = {version_id "v1", label, kind "baseline"|"translator"|"revision"|"human_edit"|"restored",
                 source "live"|"replay"|"human", round int, parent_id|None,
                 translations {id: text}, notes {id: text}, created_at}
  current_version_id: str|None        # the working version (not baseline)
  baseline_version_id: str|None
  findings: [Finding]
      Finding = {finding_id, round, string_id, category, severity, issue, reasoning, suggestion,
                 reviewed_version_id, source "live"|"replay"}
  decisions: [Decision]                # APPEND-ONLY; the latest per finding_id wins
      Decision = {decision_id "D001", action, finding_id|None, string_id|None, role,
                  reviewer_suggestion|None, human_text|None, agrees_with_reviewer bool|None,
                  comment str, created_at}
      action ∈ accept | reject | accept_edited | override | direct_edit | add_rule |
               send_revision | restore_version | approve_final | revoke_approval
  prompt_snapshots: [PromptSnapshot]
      {snapshot_id, agent "baseline"|"translator"|"reviewer"|"reviser", round, system, user,
       model, source, created_at}
  usage: {requests, input_tokens, output_tokens, request_cap, est_cost_usd|None}
  revision: {max_cycles 0..2 (default 1), cycles_done}
  stage: "INPUT"|"BASELINE"|"TRANSLATED"|"REVIEWED"|"REVISED"|"APPROVED"|"EXPORTED"
  approval: {approved bool, version_id|None, role|None, approved_at|None}
  reflection: str
  raw_failures: [{agent, round, text (truncated 4000 chars), created_at}]
  history: [{created_at, event, detail}]    # human-readable timeline for the report
```

Public functions (Engine implements; UI calls):
```python
new_project(challenge: dict, locale: str, mode: str, provider_name: str, translator_model: str,
            reviewer_model: str | None = None, max_cycles: int = 1, team_name: str = "") -> ProjectState
save_state(state, path) -> None                 # atomic write; raises if a secret pattern or a loaded key is found
load_state(path_or_text) -> ProjectState        # validates schema_version; friendly error; refuses > 5 MB (MAX_STATE_BYTES) and absurd nesting
state.version(vid) / state.current_version() / state.baseline_version()
state.latest_decisions() -> dict[finding_id, Decision]
state.open_findings(round=None) -> list[Finding]   # findings without a decision
decide_finding(state, finding_id, action, role, human_text=None, comment="") -> Decision
bulk_decide(state, finding_ids, action, role, comment="") -> list[Decision]
add_rule(state, kind, text, role, source_term=None, target_term=None, from_finding=None) -> Rule
direct_edit(state, edits: dict[id, text], role, comment="") -> Version   # new human_edit version
restore_version(state, version_id, role) -> Version                     # new "restored" version
approve_final(state, role) -> None      # raises if validation has CRITICAL issues
revoke_approval(state, role) -> None
can_export(state) -> tuple[bool, list[str]]   # needs approval + no CRITICAL issues
```
Any change after approval (edit, decision, restore, revision) automatically revokes the approval and logs it.

Engine additions (additive; UI may rely on them):
- `ProjectState` also stores `mission` and `strings` (a snapshot of each string's spec incl. `source`, `context`), so validation, approval and `can_export` need no challenge argument. `usage` also has `simulated_requests`; `revision` also has `last_reviewed_version_id`.
- `new_project(..., request_cap=40)`; `set_reflection(state, text)`; `validate_current(state) -> ValidationReport`.
- All workflow errors raise `StudioError(user_message)` (in `project_state`); `AgentOutputError` is a subclass. Comments, human texts, rules, the reflection, the team name, agent instructions and uploaded files are refused if they look like an API key or contain a loaded key (`providers.key_refusal`: "This text contains your API key — remove it from the …").
- `usage` is **per project** (for the report): `requests` counts every live HTTP attempt this project made (retries and failed attempts included, read from the session meter). The cap itself is enforced by the session meter (§10).
- Version rounds: baseline/translator versions have round 0; review round N creates findings `RN-xx`; the revision applying round N has round N. Later reviewer rounds default to the strings whose text changed since the last review.

## 10. Providers (`src/providers.py`)

```python
class ProviderError(Exception):
    kind: str   # auth | rate_limit | no_credit | invalid_model | timeout | network | server |
                # cap_reached | bad_response | not_configured | no_key
    user_message: str   # plain English, secret-masked, always ends with the Replay hint
    retryable: bool

@dataclass
class ModelResponse:
    text: str; model: str; input_tokens: int | None; output_tokens: int | None
    source: str        # "live" | "replay"
    simulated: bool

class Provider:
    name: str; display_name: str; is_live: bool; verified: bool
    def complete(self, system: str, user: str, *, model: str, max_tokens: int = 4000,
                 temperature: float = 0.3, replay_key: dict | None = None,
                 json_schema: dict | None = None) -> ModelResponse
    def test_connection(self, model: str) -> tuple[bool, str]

AnthropicProvider(api_key, config)      # POST https://api.anthropic.com/v1/messages
HuggingFaceProvider(api_key, config)    # OpenAI-compatible router chat/completions
HKBUProvider(api_key, config)           # every HTTP detail from config/providers.json["hkbu"]
ReplayProvider(fixtures: dict)          # replay_key = {"challenge", "stage", "round"}

make_provider(name, api_key, provider_config, usage_meter) -> Provider
load_api_key(provider_name, provider_config) -> str     # Colab Secrets, else getpass; never printed
mask_secrets(text, secrets) -> str
UsageMeter(request_cap=40, pricing=None): .check() raises cap_reached; .record(resp); .snapshot()
load_model_catalog(path="config/models.json") -> dict
load_provider_config(path="config/providers.json") -> dict
```
- Timeout is 45 s (`limits.timeout_seconds`); Claude uses its own `timeout_seconds` 90 from `providers.json["anthropic"]`, and the timeout message names the value used. There are at most 2 retries, with exponential backoff (1 s, 3 s), only on 429/5xx/timeout/network errors. 401/403/402/400-invalid-model are never retried.
- Plain-English messages are given for: wrong key, rate limit ("many classmates are using the service at once — wait 30 seconds or switch to Replay"), no credit, unknown model, timeout.
- The key is held only in the provider instance and is never placed in exceptions, `repr`, logs or state. Providers holding a key register themselves in a `weakref.WeakSet`; `loaded_secrets()` reads their keys, and `find_secrets` / `mask_secrets` / `scan_for_secrets` always check them, so a key without a known prefix (e.g. a 32-hex gateway key) is still caught in student text, prompts, state and exports. `Provider.complete` refuses (without any HTTP request) a prompt that contains its own key; `agents` refuses before snapshotting a prompt in which `find_secrets` finds anything.
- Generic patterns need a real-looking token: `Bearer` + ≥ 20 chars of `[A-Za-z0-9._-]` containing a digit; `key|token|secret|…` followed by `:`/`=` and ≥ 16 chars, or by a space (optionally "is"/"was") and ≥ 20 chars, of `[A-Za-z0-9._+/=-]` with letters and digits.
- **Usage meter**: the studio owns one `UsageMeter` per session (`Studio.meter`), passed to every provider it builds (and attached by `use_provider` to a live provider without one). It survives "Load my key", provider switches, mission start/reset and project loads. `UsageMeter.count_request()` runs before **every** live HTTP attempt (retries, repair requests, test connection; `post_json(..., on_attempt=...)`); `record(resp)` adds tokens/cost only. Replay never counts. The status bar shows "Live requests this session: n / cap"; `agents._check_cap` uses the provider's meter when it has one.
- **Retries**: the wait is `backoff[i] + uniform(0, 0.5 × backoff[i])` (jitter); for 429/529 a numeric `Retry-After` header is honoured; any wait is capped at `MAX_RETRY_AFTER` = 20 s.
- **Error classification** (`classify_http_error(status, detail, provider, model, secrets=(), error_type="")`): 429 is always `rate_limit`. Otherwise a known provider error `type`/`code` wins (`authentication_error`/`permission_error`/`invalid_api_key` → `auth`; `billing_error`/`insufficient_quota` → `no_credit`; `not_found_error`/`model_not_found` → `invalid_model`; `rate_limit_error` → `rate_limit`; `overloaded_error`/`api_error` → `server`), then: 402 or a 4xx mentioning credit balance/billing/quota → `no_credit`; 401/403 → `auth`; 404, or 400/422 whose text is about the model **id** ("unknown model", "model: x", "model … does not exist") → `invalid_model` (a 400 such as "max_tokens > the maximum for this model" stays `bad_response`); 5xx/529 → `server`. `requests` `InvalidURL`/`MissingSchema`/`InvalidSchema`/`InvalidHeader`/`URLRequired` → `not_configured` ("the provider address is not set up correctly — ask your instructor"), never retried.
- **Truncation**: `ModelResponse.truncated` is true when `stop_reason` is `max_tokens` (Anthropic) or `length` (OpenAI-style `finish_reason`; HKBU reads `stop_reason_path`, default `stop_reason` / `choices.0.finish_reason`).
- Claude: `anthropic-version: 2026-10-21` (configurable). On that API version `temperature`/`top_p`/`top_k` are rejected, so `providers.json` has `"send_temperature": false` for Claude: the temperature mapping is shown to students but not sent. Per-model `request_options` come from `config/models.json` (`make_provider(..., model_catalog=None)` loads it): `thinking` is sent as a top-level field and `effort` goes into `output_config.effort` — Haiku 5.5 `{"thinking": {"type": "disabled"}, "effort": "low"}`, Sonnet 5.5 `{"thinking": {"type": "between_tools"}, "effort": "low"}` (thinking tokens count toward `max_tokens`, so thinking is turned off). If Claude answers 400 with an error mentioning `thinking`, the request is sent again **once** without `thinking`, that model is remembered for the session, and a plain note goes to `Provider.notes` (agents log it as a `provider_note` event). A `json_schema` passed to `complete` becomes `output_config.format = {"type": "json_schema", "schema": …}` (structured outputs). `model_params` can still add extra body fields per model (empty for Claude). Text is read from `content[*]` blocks of type `text`; `stop_reason: "refusal"` → `bad_response`. Status mapping: 401/403 → `auth`; 402, or any 4xx whose message mentions credit balance/billing → `no_credit`; 404, or 400/422 mentioning the model → `invalid_model`; 429 → `rate_limit`; 529/5xx → `server` (retried).
- Hugging Face: `POST https://router.huggingface.co/v1/chat/completions`, `Authorization: Bearer <HF_TOKEN>` (from the Inference Providers docs; not tested live, `verified: false`). `json_schema` is ignored (body unchanged); Replay ignores it too.
- HKBU: `config/providers.json["hkbu"]` keys `base_url, path_template ({base_url} {model} {api_version}), api_version, auth_header_name, auth_prefix, extra_headers, query_params, request_style (openai_chat | anthropic_messages), model_in_body, response_text_path, usage_input_path, usage_output_path, send_temperature, model_params, supports_json_schema, secret_name, models, verified, notes`. Empty `base_url` → `not_configured`. `json_schema` is sent only when `supports_json_schema` is true (`openai_chat` → `response_format: {"type": "json_schema", "json_schema": {"name", "strict": true, "schema"}}`; `anthropic_messages` → `output_config.format`).
- Additions: `ModelResponse.stop_reason`; `make_provider(..., *, session=None, sleep=None, fixtures=None)` (injectable for tests); `load_api_key(..., *, getpass_fn=None, userdata=None)`; `load_replay_fixtures(path)`; `find_secrets(text, extra)` (used by `exports.scan_for_secrets` and `save_state`). Replay keys may also carry `string_ids` (the batch; outputs are filtered to it), `known_ids` (findings for unknown ids pass through once so the parser can drop and count them) and `deterministic_output` (the replay revision of §8, served as JSON text).

## 11. Agents (`src/agents.py`)

```python
TRANSLATOR_SETTINGS_SPEC / REVIEWER_SETTINGS_SPEC   # list of {key, label, kind slider|dropdown|checkbox, options/range, default, help}
default_agent_config(role) -> dict                  # {"settings", "instructions", "default_instructions"}
settings_to_text(role, settings) -> str             # the exact lines added to the prompt (shown to students)
build_baseline_prompt(challenge, locale) -> (system, user)
build_translator_prompt(challenge, agent_cfg, locale, memory_rules, string_ids=None) -> (system, user)
build_reviewer_prompt(challenge, agent_cfg, locale, memory_rules, translations, string_ids=None) -> (system, user)
build_revision_prompt(challenge, agent_cfg, locale, memory_rules, translations, feedback, string_ids) -> (system, user)
parse_translations(text, expected_ids) -> list[dict]
parse_findings(text, valid_ids) -> tuple[list[dict], int]          # (findings, dropped_count)
estimate_requests(state, challenge, step) -> int    # shown before each run
run_baseline(state, provider, challenge) -> Version
run_translator(state, provider, challenge) -> Version
run_reviewer(state, provider, challenge, string_ids=None) -> list[Finding]
run_revision(state, provider, challenge) -> Version      # bounded by revision.max_cycles
class AgentOutputError(Exception): user_message
```
- The **baseline** is deliberately minimal ("Translate into English. Return JSON."), with no context or glossary, so students can see what the configured agents add.
- **Translator** prompt = system role text + editable instructions + `settings_to_text` + glossary + approved memory rules + scene context + character profiles + strings (id, source, type, speaker, constraints, placeholders, max_len) + output schema.
- **Reviewer** prompt = role + editable instructions + settings + **source, context, glossary, rules, the translation under review** + schema. It is told that its findings are suggestions for a human director.
- **Revision** prompt = translator prompt + the accepted feedback only (finding issue, suggestion, human comment) + "do not change other strings". It is sent only for the strings with `accept` decisions. `accept_edited`/`override`/`direct_edit` texts are applied directly, with no API call, and are passed as locked context.
- Batches hold at most 8 strings. `max_tokens` is 4000 (`MAX_TOKENS`; `providers.json` `limits.max_tokens` overrides it, read from `provider.limits`) for baseline, translator, reviser, reviewer and the repair request alike. The temperature comes from the translator's strategy (shown in the preview).
- Every run stores a `PromptSnapshot` (in Replay too, marked `source: "replay"`).
- **Structured outputs**: `translations_json_schema(ids)` (`{translations: [{id ∈ batch ids, text, note}]}`, `note` required, may be empty) and `findings_json_schema(valid_ids)` (`{findings: [{string_id ∈ batch ids, category ∈ CATEGORIES, severity ∈ SEVERITIES, issue, reasoning, suggestion}], overall_comment}`) are strict (every field required, `additionalProperties: false` on every object). `_ask` passes the batch's schema as `json_schema` only to providers whose `complete` accepts it (`Provider.accepts_json_schema` and the signature, following pass-through wrappers' `_inner`); the tolerant parser and the one repair request remain the safety net for every provider.
- Additions: `build_revision_prompt(..., locked: dict | None = None)` (human-decided texts passed as context only); `run_revision(state, provider, challenge, role="director")`; `normalise_settings(role, settings)`; `temperature_for(role, settings)` and `temperature_note(role, settings, provider_name, provider_config)` (strategy 1–5 → 0.1/0.2/0.4/0.6/0.8; reviewer 0.1; baseline 0.3); `preview(state, challenge, step, provider_config=None) -> {system, user, temperature, temperature_note, requests}` for the "show prompt before running" panel; `extract_json_object(text)`; `REPAIR_MARK` (the repair request is also snapshotted; exports skip it when picking initial/final prompts).
- Translator settings keys: `strategy, cultural_adaptation, voice_strength` (sliders 1–5), `register` (`match_source|neutral|casual|formal|playful|dramatic`), `glossary_strictness` (`must_use|prefer|ignore`). Reviewer: `check_<category>` checkboxes, `strictness` 1–5, `max_findings` 1–10 (default 6). Findings outside the ticked categories or over the maximum are ignored and logged.
- `estimate_requests` counts calls regardless of mode (Replay calls are free and not counted against the cap).
- **Truncated replies**: if an unreadable reply was cut off (`resp.truncated`), the repair request asks for compact output (empty notes, no explanations); if that fails too, the `AgentOutputError` says the reply was cut off and suggests fewer strings or a shorter instruction.
- **Batch failures** (baseline / translator): if the first batch fails, the error is raised and nothing changes. If a later batch fails (provider error, cap, unreadable reply), no further batches are sent; the version is still created with the completed batches, the failed/unsent ids keep the previous version's text (note "Not translated this time (a request failed) …"), and a `partial_run` history event explains which ids and why. Running the step again retries everything. Revision batches stay all-or-nothing (a revision round can be applied once).
- `run_reviewer` returns `ReviewResult` (a `list[Finding]` with `skipped`, `reviewed_ids`, `received`, `dropped`, `off_topic`, `over_limit`, `normalised`, `all_dropped`, `counts_text()`). `skipped` = nothing changed since the last review (no request sent). If every finding in the replies was dropped (`all_dropped`), the version is **not** marked as reviewed and the UI shows it as a problem, not as "no findings".

## 12. Exports (`src/exports.py`)

```python
build_game_translation(state, challenge, manifest) -> tuple[dict, ValidationReport]
export_game_translation(state, challenge, manifest, out_dir) -> ExportResult   # blocked if CRITICAL or not approved
build_agent_settings(state, challenge) -> dict     # models, prompts (initial + final), settings, glossary, rules, revision limits; NO keys
render_workflow_report(state, challenge, manifest) -> str   # self-contained HTML; html.escape everything; CSP meta, no <script>
export_all(state, challenge, manifest, out_dir) -> dict[str, ExportResult]
scan_for_secrets(text, extra_secrets=()) -> list[str]   # patterns: sk-ant-…, hf_…, Bearer …, api-key values, long hex/base64 tokens next to "key"
prompt_diff_html(old, new) -> str       # escaped side-by-side diff
game_play_url(game_obj: dict, base: str) -> str   # "<base>#t=<payload>"; ValueError if > 100 KB or a key is found
PLAY_PARAM = "t"
```
`game_play_url`: payload = `base64.urlsafe_b64encode(json.dumps(game_obj, ensure_ascii=False,
separators=(",", ":")).encode("utf-8"))` with the `=` padding stripped; result is
`base.rstrip("#") + "#t=" + payload`. The translation travels in the URL **fragment**, which browsers
never send to a server (GitHub Pages never sees it). It raises `ValueError` with a plain-English message
if the compact JSON is over 100 KB (the game's cap) or if `scan_for_secrets` finds anything. Pass the
object from `build_game_translation` (only after approval, like Export A). The game side is in §5.
`ExportResult = {ok: bool, path: str|None, message: str, issues: [Issue]}`
The studio writes each mission's files into their own folder, `<export_dir>/<mission>/` (in Colab `/content/exports/intro/` …; custom uploads use `custom/`), keeping the file names above. Progress files and backups stay in `<export_dir>/`.
(a dataclass with `.to_dict()`; `result["ok"]` also works). `export_all` returns keys `game_translation`, `agent_settings`, `workflow_report`; if the game export is blocked, all three are blocked and nothing is written. `output_source(state)` gives the file's `source`.

The report contains:
- project details, mode/provider/model, and a Replay notice if applicable
- a workflow diagram (inline SVG)
- source / baseline / agent / final translations side by side
- findings, each with the human decision and whether the human agreed or overrode
- rules added
- validation results
- revision history and versions
- the prompt evolution diffs
- usage counters
- the reflection answer to *"What did your agents get wrong, what did you change, and why was the final result better?"*

## 13. Validation API (`src/validation.py`)

```python
load_manifest(path="game/strings_manifest.json") -> dict
spec_from_manifest(manifest, mission) -> dict[id, StringSpec]
spec_from_challenge(challenge) -> dict[id, StringSpec]
validate_translations(translations: dict, spec, require_all=True) -> ValidationReport
validate_game_file(text_or_obj, manifest, require_all_for_mission=None) -> ValidationReport
parse_json_strict(text) -> object        # raises with duplicate-key detection
extract_placeholders(text) -> list[str]
ValidationReport: issues, critical (list), warnings (list), ok (bool), summary() -> str
```

## 14. Imports (`src/importers.py`)

```python
import_upload(filename: str, data: bytes) -> dict    # returns a challenge dict (custom) or raises ImportRejected(user_message)
```
- Limits: UTF-8 only (BOM tolerated), ≤ 200 KB, ≤ 200 strings, each ≤ 500 characters.
- Extensions: `.txt` (one string per non-empty line), `.csv` (header must contain `source`; optional `id, context, max_len, speaker`), `.json` (a challenge file, or a list of `{id?, source, context?, max_len?}`).
- Anything that looks like HTML/script is kept as plain text, never executed or rendered as HTML.
- The returned challenge also has `source_language` and `import_warnings` (e.g. "Entry 3 looks like HTML…"). An uploaded `id` is kept in `context` as "(original id: …)"; the engine id is always `custom.text.NNN`. A full challenge file keeps its `title`, `brief`, `scene_context` and `glossary`; `instructor_notes` are dropped.

---

## 15. Translator presets and Replay prompt variants (wave 2 addition)

The point of the exercise is that **changing the translator's prompt changes the translation**. In Live Mode that happens for real. In Replay Mode, students pick between three **prepared prompt variants**, so they can still see the effect offline. Each variant is clearly labelled as prepared output.

### Presets (`src/agents.py`)
```python
TRANSLATOR_PRESETS = {
  "faithful": {"label": "Faithful", "description": "Stay close to the source wording and structure.",
               "settings": {...}, "instructions": "<full instruction text>"},
  "balanced": {...},   # == current defaults
  "creative": {...},
}
PRESET_ORDER = ("faithful", "balanced", "creative")
apply_preset(agent_cfg: dict, name: str) -> dict   # sets settings + instructions, cfg["preset"] = name, cfg["edited"] = False
mark_edited(agent_cfg: dict) -> dict               # cfg["edited"] = True if settings/instructions differ from the preset
replay_variant_note(agent_cfg) -> str              # plain-English label for the UI and the version
```
- `AgentConfig` gains `preset` (default `"balanced"`) and `edited` (bool). The reviewer has no presets.
- Presets are just starting points. Students can then edit sliders and instructions freely. The preset's full instruction text is shown to them, and nothing is hidden.

### Replay fixture shape (replaces the single `translator` / `reviewer` / `reviewer_round2` entries)
```json
"intro": {
  "baseline": {"translations": [...]},
  "translator_variants": {"faithful": {"translations": [...]}, "balanced": {...}, "creative": {...}},
  "reviewer":        {"faithful": {"findings": [...], "overall_comment": "..."}, "balanced": {...}, "creative": {...}},
  "reviewer_round2": {"faithful": {...}, "balanced": {...}, "creative": {...}},
  "revision_notes":  {"<string_id>": "..."}
}
```
- `replay_key` gains `"variant"`, which is the translator config's `preset`. The reviewer stages use the variant of the version under review, stored as `Version.variant`, a new optional field.
- Backward compatibility: a plain `translator` / `reviewer` entry is treated as `balanced`.
- If the student has edited a preset (`edited: True`), Replay still serves that preset's variant. The version label and the UI then say: *"Prepared output for the ‘Faithful’ preset. Your own edits are saved in your prompt and report, but Replay Mode cannot generate a new response — switch to Live Mode to test them."*
- Version labels in Replay: `"Translator · Replay · Faithful preset"`.

### What the variants must show
- **faithful**: accurate but stiff. Literal idioms, flat character voice. Placeholders and limits are fine, except that one string is over-literal and near or over its limit.
- **balanced**: generally good, with 2–3 genuine issues.
- **creative**: lively, strong voice and good puns. One or two over-adaptations, such as an added plot detail, a lost cultural reference, or one technical slip: a too-long button, a dropped placeholder, or `{player name}`. These are mainly in the `ui` mission.
- The reviewer findings for each variant include **at least one wrong or debatable finding, on purpose**, such as a "fix" that breaks the voice or a "correction" that changes the meaning. Students must then practise rejecting and overriding.
- Every fixture translation must be distinct from `game/translations/en.reference.json` (no whole-string copies). This is tested.

### Implementation notes (wave 2, Replay)
- `apply_preset` changes the config in place and returns it; it leaves `default_instructions` as the studio default, so the report's prompt diff shows the preset as a change. `mark_edited` compares normalised settings and stripped instructions with the preset. Configs saved without `preset`/`edited` count as `balanced`, not edited.
- `run_translator` sends `replay_key["variant"] = cfg["preset"]` and sets `Version.variant`. In Replay the label is `"Translator · Replay · <Label> preset"`, with `" (your edits not applied)"` appended when `edited`; the full `replay_variant_note` sentence is logged in `history` (event `replay_variant`). The reviewer and the reviser use `version_variant(state, version)`, which is the version's own variant or the nearest parent's (so human edits, restores and revisions keep it), defaulting to `balanced`. Revisions record it too.
- `ReplayProvider` chooses `translator_variants[variant]`, or the per-variant entry of `reviewer` / `reviewer_round2`. An unknown or missing variant falls back to `balanced`. A plain `translator`, or a `reviewer` that has a `findings` key, is served whatever the variant.
- The private instructor pack's `teaching_notes.json` has `teaching_notes` (`{mission: {summary, baseline, compare_side_by_side, variants: {preset: {expected_critical, findings: [{finding_id, fixture_index, string_id, verdict good|debatable|wrong, recommended_action, why, override_text?}], round2: [...], missed_by_reviewer}}}}`) and `teaching_notes_readme`. They are for instructors only: they are not in this repository, never sent to a model and never served. `fixtures/replay_outputs.json` keeps only `locale_note`. Reviewer findings are stored in severity order, so with the default reviewer settings the engine ids `R1-xx` match `finding_id`. Round-2 findings marked "only if …" appear only when the student accepted the matching wrong finding.
- Catch-up checkpoints `fixtures/checkpoints/intro_after_{agents,review,revision}.json` are generated by `python3 tools/make_checkpoints.py`. Each run produces them with the real engine in Replay Mode, using the Balanced preset. Each file also has a top-level `checkpoint_label` ("Catch up: agents already run (Mission 1)", "Catch up: review done (Mission 1)", "Catch up: revision done (Mission 1)"), shown in the studio's **Checkpoint:** dropdown and ignored by `load_state`. `tests/test_replay.py` checks that they are up to date.
