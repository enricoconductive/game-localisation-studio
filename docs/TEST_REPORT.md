# Test report — Game Localisation Studio v0.3

Date: 28 October 2026. Everything below was actually run. Nothing is reported as passing unless it was executed.

## 1. Automated tests

| Suite | Command | Result |
|---|---|---|
| Python, with the private instructor pack present | `python3 -m pytest -q tests` | **448 passed** |
| Python, public repo only (no instructor pack) | `INSTRUCTOR_PACK=/nonexistent python3 -m pytest -q tests` | **389 passed, 59 skipped** (the skipped tests need the answer key) |
| Game validator and security (Node) | `cd tests/game && npm run test:unit` | **33 / 33 passed** |
| Game end-to-end, test fixtures (Playwright, Chromium) | `npm run test:e2e` | **17 / 17 passed** |
| Game end-to-end, real content | `LANTERN_CONTENT_DIR=game npm run test:e2e` | **17 / 17 passed** |

What the suites cover, mapped to spec §11:

- **Translation data.** Valid game JSON. Missing, unknown and duplicate ids. Placeholders dropped, extra, broken (`{player name}`, `{player_name`) or translated. Character limits. Newline rules. Non-Latin text, emoji and combining characters. Lone surrogates and control characters. U+FEFF and other Unicode whitespace. `source` and `locale` fields. File size. Generic TXT, CSV and JSON imports, including oversize files, too many rows, bad encoding and HTML-looking text.
- **Validator agreement.** The Python and JavaScript validators produce identical CRITICAL and WARNING codes over 26+ deliberately broken files. The only exception is `duplicate_id`, which only Python can detect.
- **Agent orchestration.**
  - Baseline generation.
  - Translator and reviewer role separation.
  - Reviewer findings: unknown ids dropped, and the dropped count is shown.
  - Decisions: accept, reject, accept with edit and override. Rejected feedback never reaches the revision prompt, and overrides are applied without an API call.
  - Partial re-runs: only strings with accepted findings are re-sent.
  - Revision cap of 0–2 cycles.
  - Approval gate. Any later change revokes the approval.
  - State save, restore and resume.
  - Malformed, prose-wrapped, fenced and truncated model replies: one repair request, then a plain-English error.
  - Later-batch failure keeps the batches that completed.
- **Providers (mocked HTTP).**
  - Success, 401, 429 then success, 429 exhausted, timeout, no credit, invalid model.
  - Retry-After honoured, backoff jitter, error-type precedence.
  - Bad provider address returns `not_configured`. HKBU with an empty config returns `not_configured`. HKBU with a configured mock server sends the expected request shape.
  - Provider switching.
  - A session-level request cap that counts every HTTP attempt and survives key reloads and mission changes.
  - Claude request body: thinking disabled for Haiku, `between_tools` for Sonnet, JSON-schema structured output, `max_tokens` 4000. A 400 mentioning thinking is retried once without the thinking setting.
  - Replay Mode with the network disabled.
- **Replay fixtures.** All 4 missions × 3 presets validate against the output schemas. Accepting the good findings produces a valid translation. The Interface Trap variants trigger the expected CRITICAL codes. No fixture string copies the reference English. Checkpoints load and replay forward to export.
- **Exports.**
  - The game-compatible JSON validates, and `agent_settings.json` is valid JSON.
  - The HTML report escapes `<script>` and `<img onerror>` everywhere and contains no `<script>`.
  - Rejected feedback is shown as rejected and not applied, and approved and human-edited text is preserved.
  - Planted fake keys are caught in every export path. A loaded key of unknown format (32 hex characters) can never reach prompts, state or exports.
- **Reference isolation.** No reference-English string of 4 or more words appears in any baseline, translator, reviewer or revision prompt, for any challenge. `src/` never reads `en.reference.json`.
- **Notebook UI.**
  - A full intro mission driven through the real ipywidgets buttons (`Button.click()`): Replay, Faithful preset, translator, Creative preset, translator, compare runs, reviewer, all four decision types, rule, revision, approve, approval revoked by an edit, approve again, reflection, export of all three files.
  - Resume from the autosave and from an uploaded file. Catch-up checkpoints.
  - Friendly provider errors that re-enable the buttons.
  - Colab download behaviour: downloads run inside an Output, each Output is displayed once, there is one Output per export file, and no `data:` links are used.
  - Setup-cell bundle paths: upload widget, bundle dropped in the Files panel, damaged bundle.
  - The notebook executes top to bottom with nbclient with no cell errors.
- **Browser game (Playwright).**
  - Original Traditional Chinese loads.
  - Interface switch between English and 繁體中文, including validation errors.
  - Dialogue selector (Original / Reference / Student): all four missions with both endings, in Chinese and in reference English.
  - A valid student import is applied and labelled. An invalid file is rejected, with the Chinese left unchanged.
  - Placeholders render. The toast's line break renders.
  - Injected HTML shows as plain text.
  - Language settings persist across a reload. Reset keeps the interface language.

## 2. Manual tests in real Google Colab (Chrome, dark theme)

Run in the instructor's own Colab account, using the bundle fallback because the repo was not yet public.

| Check | Result |
|---|---|
| Upload the notebook. Step 0 with the repo unavailable, and `studio_bundle.zip` dragged into the Files panel | ✅ "Could not download from GitHub — using studio_bundle.zip from the Files panel." Then "The studio is ready". |
| Runtime → Run all; widgets render (status bar, role toggle, progress, sliders, dropdowns, tabs) | ✅ After the fixes, readable in the dark theme on a light card. |
| Button callbacks in Colab (Start mission, Baseline, Translator) | ✅ Sections 3–6 update without re-running cells. |
| Colab Secrets: `ANTHROPIC_API_KEY` loaded with **Load my key** | ✅ "Key loaded … (it stays hidden)". |
| **Test connection** with live Claude | ✅ "Connected to Claude (Anthropic) with model 'claude-haiku-5-5'". |
| Live intro mission: baseline → translator → reviewer → 2 accepted, 2 rejected → revision | ✅ 4 requests, 12,386 input and 3,192 output tokens, **US$0.0028**, no unreadable replies, 4 reviewer findings. |
| Technical validation caught a live model error | ✅ Approval blocked: "Begin investigation" is 19 characters against a 12-character limit. A human edit to "Investigate" fixed it, then approval succeeded (recorded as AI Director). |
| Exported live `game_translation_en.json` | ✅ Validates with no CRITICAL issues (1 near-limit warning), `source: live`, `approved: true`, en-GB. No key in any of the three exports. |
| The live export played in the game | ✅ Imported, "Student's imported English" shown, both choices displayed, Ending A reached. |
| Downloads from buttons (progress file and the three exports) | ✅ Each file arrives exactly once, after two fixes found in this test (see §3). A click by the instructor confirmed it. |
| Restart session → Step 0 → **Resume my saved session** | ✅ "Loaded your saved session: Mission 1 … 2 version(s), 2 decision(s), current version v2". |

Earlier problems found in Colab and fixed: downloads duplicated (7 copies, then 5); low contrast in the dark theme; long outputs jumping; "Switch to Replay" shown while already in Replay; an unclear selected role; Live Claude replies cut off by Haiku 5.5's default thinking.

## 3. Issues found and fixed during testing

1. **Live reviewer reply cut off.** Claude Haiku 5.5's default thinking used up the 1,200-token cap. Fix: thinking is now disabled per model through `config/models.json` `request_options`, JSON-schema structured output is used, and the cap is 4,000 tokens. Verified live.
2. **Duplicate downloads in Colab.** A shared Output widget re-ran its download scripts in every view. Fix: one Output per download, each displayed exactly once. Verified live.
3. **Dark-theme readability, page jumps and ambiguous controls.** Fixed with a light card, bounded tabs and accordions, and clear labels.
4. **Independent security review.** It found 11 problems (1 high, 3 medium, 7 low), all fixed with regression tests:
   - a key of unknown format could leak into exports;
   - the request cap could be bypassed;
   - completed batches were lost when a later one failed;
   - dropped findings were reported as "no findings";
   - errors were classified in the wrong order;
   - unescaped error text appeared in the setup cell;
   - deeply nested state files were not handled;
   - Python and JavaScript treated U+FEFF differently;
   - `source` and `locale` were not validated;
   - truncated replies were not explained;
   - `.gitignore` had gaps.

## 4. Not tested, or only partly tested

- **The real HKBU API.** No specification was available. The adapter is configurable through `config/providers.json` and is tested only against a mock server. It is marked *not yet verified* until your colleague tests it.
- **Hugging Face live calls.** The endpoint was checked against the documentation; there have been no live calls.
- **Opening from the GitHub "Open in Colab" badge, the `git clone` path, and the GitHub Pages game URL.** These can only be tested after publication. The bundle fallback was used instead.
- **Resume from an uploaded progress file in Colab, and the "Upload bundle" button.** Both use Colab's file picker inside an output frame, which could not be automated. The same code is tested headlessly with both ipywidgets 7 and 8 upload formats.
- **19 pairs at once.** Rate limits under real classroom load were not tested. Retries with backoff, jitter and Retry-After, plus a session cap of 40 requests, are in place, and Replay Mode is the fallback.
- **Safari, Firefox and Edge.** The game e2e tests use Chromium, and the Colab tests used Chrome.
- **Native-speaker proofreading of the Chinese source text** is still to be done by a Chinese-reading colleague. A checklist is in the private instructor pack.

## 5. Known limitations

- Chrome asks before a site downloads several files at once (**Export all three files**). If a student clicks **Block**, every later download from Colab fails silently. The Student Guide and the notebook point to the Files panel fallback and explain how to re-allow downloads.
- The Colab autosave lives in the runtime. It survives a reconnect but not a recycled runtime, so the notebook reminds students to **Download progress**.
- Replay outputs are written in British English, and a note says so for en-US and international projects.
- Replay Mode cannot respond to hand-edited prompts. Only the three presets have prepared outputs, and this is labelled clearly.
- A stale "Start a mission first" message can stay visible in the status bar after the mission starts. This is cosmetic.
