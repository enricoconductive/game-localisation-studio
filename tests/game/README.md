# The Lantern Mystery — game tests

Two suites, both run from this folder (`tests/game/`). Node 20+ (tested on Node 26).

## 1. Unit tests (no install needed)

```bash
cd tests/game
npm run test:unit        # = node --test validator.test.js security.test.js
```

- `validator.test.js` — every CONTRACTS §5 rule in `game/validator.js` (fixture manifest); every issue
  code is produced with English `message`/`fix_hint` **and** zh-Hant `message_zh`/`fix_hint_zh`; code titles
  in both languages. Also validates the fixture `en.reference.json` / `example_student_export_intro.json`
  and, when present, the real `game/translations/zh-Hant.json`, `en.reference.json` (every mission) and
  `example_student_export_intro.json` against `game/strings_manifest.json` (skipped if absent).
- `security.test.js` — static checks: no `innerHTML`/`eval`-style sinks, CSP meta tag, no inline or
  external scripts, inert SVG assets.

## 2. End-to-end tests (Playwright, Chromium)

```bash
cd tests/game
npm install                      # playwright 1.62.0 (Chromium build 1234)
npx playwright install chromium  # only if that browser build is not already cached
npm run test:e2e                 # against the fixtures in tests/game/fixtures/
LANTERN_CONTENT_DIR=game npm run test:e2e   # against the real content in game/
```

`server.js` serves the game code from `game/` and overlays the content files (`strings_manifest.json`,
`story.json`, `translations/*`) from `LANTERN_CONTENT_DIR` (default `tests/game/fixtures`; relative paths
resolve from the repository root). Expected text is always read from the served content files. Tests that
need `translations/en.reference.json` or `translations/example_student_export_intro.json` are skipped (with
a message) if the content directory does not have them.

Covered: English default interface and the English/繁體中文 switch in both directions (chrome, mission
names, hints, buttons; dialogue unaffected); all four missions × both endings, every screen, in Original
Chinese and in Reference English (with the "one possible solution" label); the example student file
enables the Student option, shows its text and the "Showing … · simulated (Replay Mode)" indicator, and
does not overwrite the reference; validation errors in English and in 繁體中文; persistence of interface
language and dialogue choice across reload (and graceful behaviour when sessionStorage is blocked); Reset
keeps the interface language, clears the student layer and returns to Original Chinese; HUD placeholders
and the toast line break rendered as a real line break in Chinese and English; paste import and override
order; missing-id notice; HTML/`<script>` shown literally; keyboard; phone width; `file://` message.

## Notes on behaviour

- Dialogue language and interface language are independent. Mission names, buttons, hints and validation
  messages follow the interface; dialogue text, character names and the item name follow the dialogue.
- Only the interface language and dialogue choice are stored (sessionStorage). Imported student files are
  not stored: after a reload "Student" falls back to Original Chinese and the file must be imported again.

## Play the game locally

```bash
node tests/game/server.js                          # fixtures, http://localhost:8123/
LANTERN_CONTENT_DIR=game node tests/game/server.js # real content
# or, from the repository root: python3 -m http.server  → http://localhost:8000/game/
```
