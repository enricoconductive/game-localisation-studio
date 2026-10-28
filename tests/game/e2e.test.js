'use strict';
/*
 * End-to-end tests for The Lantern Mystery (Playwright + node:test).
 *
 *   cd tests/game && npm install && npm run test:e2e                       # fixtures
 *   LANTERN_CONTENT_DIR=game npm run test:e2e                              # real content
 *
 * The tests read whatever content the server serves and derive every expected
 * string from it, so they work for the fixtures and for the real game content.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { start, contentDir, GAME_DIR } = require('./server.js');

const CONTENT = contentDir();
const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const manifest = readJson(path.join(CONTENT, 'strings_manifest.json'));
const story = readJson(path.join(CONTENT, 'story.json'));
const zh = readJson(path.join(CONTENT, 'translations', 'zh-Hant.json')).strings;
const REF_PATH = path.join(CONTENT, 'translations', 'en.reference.json');
const STUDENT_PATH = path.join(CONTENT, 'translations', 'example_student_export_intro.json');
const reference = fs.existsSync(REF_PATH) ? readJson(REF_PATH) : null;
const student = fs.existsSync(STUDENT_PATH) ? readJson(STUDENT_PATH) : null;
const NO_REF = !reference && `en.reference.json not present in ${CONTENT}`;
const NO_STUDENT = !student && `example_student_export_intro.json not present in ${CONTENT}`;

const PH_RE = /\{([a-z_][a-z0-9_]*)\}/g;
const CJK = /[㐀-鿿]/;
const norm = (p) => (p.startsWith('{') ? p : `{${p}}`);
const missionIds = (m) => manifest.missions.find((x) => x.id === m).string_ids;

let server, baseUrl, browser;

test.before(async () => {
  ({ server, url: baseUrl } = await start(0));
  browser = await chromium.launch();
});
test.after(async () => {
  if (browser) await browser.close();
  if (server) server.close();
});

/* ---------- helpers ---------- */

/** Synthetic English for one id: obeys placeholders, max_len and newline rules. */
function englishFor(id, k) {
  const spec = manifest.strings[id];
  const ph = (spec.placeholders || []).map(norm);
  let text = ['Tx' + k].concat(ph).join(' ');
  if (spec.max_len && [...text].length > spec.max_len) text = ph.join('') || 'Tx';
  return text;
}
function englishFile(mission, overrides, extra) {
  const strings = {};
  missionIds(mission).forEach((id, i) => { strings[id] = englishFor(id, i + 1); });
  Object.assign(strings, overrides || {});
  return Object.assign({
    format: 'lantern-mystery-translation', schema_version: '1.0', locale: 'en-GB',
    mission, source: 'replay', strings
  }, extra || {});
}
function fill(text, lang, values, name) {
  return text.replace(PH_RE, (m, n) => {
    if (n === 'player_name') return name || (lang === 'en' ? 'Detective' : '偵探');
    if (n === 'item_name') return lang === 'en' ? values.item_name_en : values.item_name_zh;
    if (n in values) return String(values[n]);
    return m;
  });
}
/** Expected on-screen text for an id given a layer {strings} (falls back to Chinese). */
function expected(id, layer, values, name) {
  if (layer && typeof layer.strings[id] === 'string') return fill(layer.strings[id], 'en', values, name);
  return fill(zh[id], 'zh', values, name);
}
function expectedSpeaker(key, layer) {
  const c = manifest.characters[key];
  if (!layer) return c.name_zh;
  return (layer.characters && layer.characters[key]) || c.name_en_default;
}
/** For each ending letter, the sequence of option indexes that reaches it (DFS). */
function endingPaths(mission) {
  const g = story.missions[mission];
  const out = {};
  (function walk(id, choices, seen) {
    const n = g.nodes[id];
    if (!n || seen.has(id)) return;
    seen = new Set(seen).add(id);
    if (n.kind === 'ending') { if (!out[n.ending]) out[n.ending] = choices; return; }
    if (n.kind === 'choice') n.options.forEach((o, i) => walk(o.next, choices.concat(i), seen));
    else walk(n.next, choices, seen);
  })(g.start, [], new Set());
  return out;
}
function nodesOnPath(mission, choices) {
  const g = story.missions[mission];
  const list = [];
  let id = g.start; const c = choices.slice();
  for (let i = 0; i < 100 && g.nodes[id]; i++) {
    const n = g.nodes[id];
    list.push(n);
    if (n.kind === 'ending') break;
    id = n.kind === 'choice' ? n.options[c.shift()].next : n.next;
  }
  return list;
}
function hudMission() {
  return Object.keys(story.missions).find((m) => Object.values(story.missions[m].nodes).some((n) => n.kind === 'hud'));
}

async function openGame(opts, initScript, suffix) {
  const context = await browser.newContext(opts || {});
  if (initScript) await context.addInitScript(initScript);
  const page = await context.newPage();
  const errors = [];
  const dialogs = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    // a missing optional reference file is handled by the game (option disabled); ignore the browser's 404 line
    if (!reference && /en\.reference\.json$/.test((m.location() || {}).url || '')) return;
    errors.push(m.text());
  });
  page.on('dialog', (d) => { dialogs.push(d.message()); d.dismiss().catch(() => {}); });
  await page.goto(baseUrl + (suffix || ''));
  await ready(page);
  return { page, context, errors, dialogs };
}
const ready = (page) => page.waitForFunction(() => window.__lantern && window.__lantern.view === 'missions');
const L = (page) => page.evaluate(() => ({
  uiLang: __lantern.uiLang, dialogue: __lantern.dialogue, lang: __lantern.lang, view: __lantern.view,
  mission: __lantern.mission, nodeId: __lantern.nodeId, kind: __lantern.nodeKind, overrides: __lantern.overrideCount,
  replay: __lantern.replay, showing: __lantern.showing, report: __lantern.lastReport, values: __lantern.values,
  stillChinese: __lantern.stillChinese, referenceAvailable: __lantern.referenceAvailable, studentAvailable: __lantern.studentAvailable
}));

async function importFile(page, content, name) {
  await page.evaluate(() => { document.getElementById('report').hidden = true; });
  const buffer = Buffer.isBuffer(content) ? content : Buffer.from(typeof content === 'string' ? content : JSON.stringify(content, null, 2), 'utf8');
  await page.setInputFiles('#file-input', { name: name || 'game_translation_en.json', mimeType: 'application/json', buffer });
  await page.waitForSelector('#report:not([hidden])');
}
const optionDisabled = (page, v) => page.$eval(`#dialogue-select option[value="${v}"]`, (o) => o.disabled);

/** Play a mission following `choices`; calls onNode(kind, node) at every screen. Returns the ending letter. */
async function play(page, mission, choices, onNode) {
  if ((await L(page)).view !== 'missions') await page.click('#btn-back');
  await page.click(`[data-mission="${mission}"]`);
  const c = choices.slice();
  for (let i = 0; i < 60; i++) {
    const s = await L(page);
    const node = story.missions[mission].nodes[s.nodeId] || null;
    if (onNode) await onNode(s.kind, node, page);
    if (s.kind === 'title') await page.click('#btn-start');
    else if (s.kind === 'line' || s.kind === 'hud') await page.click('#btn-next');
    else if (s.kind === 'choice') await page.click(`[data-option="${c.shift()}"]`);
    else if (s.kind === 'ending') return page.getAttribute('#ending-badge', 'data-ending');
    else throw new Error('unexpected node kind ' + s.kind);
  }
  throw new Error('mission did not end');
}

/** Checks every visible string on the current screen against the expected layer. */
async function checkScreen(page, kind, node, layer, name) {
  const values = (await L(page)).values;
  const exp = (id) => expected(id, layer, values, name);
  if (kind === 'title' && node) assert.equal(await page.textContent('#btn-start'), exp(node.text), node.text);
  if (kind === 'line') {
    assert.equal(await page.textContent('#dialogue-text'), exp(node.text), node.text);
    const sp = manifest.strings[node.text].speaker;
    if (sp) assert.equal(await page.textContent('#speaker-name'), expectedSpeaker(sp, layer), node.text + ' speaker');
  }
  if (kind === 'choice') {
    const opts = await page.$$eval('.btn-choice', (els) => els.map((e) => e.textContent));
    assert.deepEqual(opts, node.options.map((o) => exp(o.text)));
  }
  if (kind === 'hud') {
    const texts = await page.$$eval('.hud-text', (els) => els.map((e) => ({ id: e.dataset.stringId, text: e.textContent })));
    assert.deepEqual(texts.map((t) => t.id).sort(), node.texts.slice().sort());
    for (const t of texts) assert.equal(t.text, exp(t.id), t.id);
  }
  if (kind === 'ending') assert.equal(await page.textContent('#ending-text'), exp(node.text), node.text);
}

/* ---------- tests ---------- */

test('content sanity: four missions, each with endings A and B reachable in the graph', () => {
  assert.equal(manifest.missions.length, 4);
  for (const m of manifest.missions) {
    assert.ok(story.missions[m.id], m.id);
    assert.deepEqual(Object.keys(endingPaths(m.id)).sort(), ['A', 'B'], m.id);
  }
});

test('default interface is English; the switch changes all chrome in both directions', async () => {
  const { page, context, errors } = await openGame();
  let s = await L(page);
  assert.equal(s.uiLang, 'en');
  assert.equal(s.dialogue, 'original');
  assert.equal(await page.getAttribute('html', 'lang'), 'en');
  const chromeSnapshot = async () => ({
    import: await page.textContent('#btn-import'),
    paste: await page.textContent('#btn-paste'),
    reset: await page.textContent('#btn-reset'),
    hint: await page.textContent('#hint'),
    heading: await page.textContent('#missions-title'),
    dialogueLabel: await page.textContent('label[for="dialogue-select"]'),
    titles: await page.$$eval('.mission-title', (els) => els.map((e) => e.textContent)),
    showing: await page.textContent('#showing-badge')
  });
  const en = await chromeSnapshot();
  assert.equal(en.import, 'Import student JSON');
  assert.equal(en.reset, 'Reset to 中文');
  assert.match(en.hint, /^How to test your translation/);
  assert.equal(en.heading, 'Choose a mission');
  assert.equal(en.showing, 'Showing: Original Chinese');
  assert.deepEqual(en.titles, manifest.missions.map((m) => m.title_en));
  for (const [k, v] of Object.entries(en)) if (k !== 'titles' && k !== 'reset') assert.ok(!CJK.test(v.replace(/[（(][^)）]*[)）]/g, '')), `${k} is English: ${v}`);

  await page.click('#ui-zh');
  s = await L(page);
  assert.equal(s.uiLang, 'zh');
  assert.equal(await page.getAttribute('html', 'lang'), 'zh-Hant-HK');
  assert.equal(await page.getAttribute('#ui-zh', 'aria-pressed'), 'true');
  const zhUi = await chromeSnapshot();
  assert.equal(zhUi.import, '匯入學生 JSON');
  assert.equal(zhUi.reset, '重設為中文');
  assert.equal(zhUi.heading, '選擇任務');
  assert.equal(zhUi.showing, '正在顯示：中文原文');
  assert.deepEqual(zhUi.titles, manifest.missions.map((m) => m.title_zh));
  for (const [k, v] of Object.entries(zhUi)) if (k !== 'titles') assert.ok(CJK.test(String(v)), `${k} is Chinese: ${v}`);

  // inside a scene: buttons and badges follow the interface language; dialogue does not
  await page.click('[data-mission="intro"]');
  await page.click('#btn-start');
  assert.equal(await page.textContent('#btn-next'), '繼續 ▸');
  const zhLine = await page.textContent('#dialogue-text');
  await page.click('#ui-en');
  assert.equal(await page.textContent('#btn-next'), 'Next ▸');
  assert.equal(await page.textContent('#btn-back'), '← Missions');
  assert.equal(await page.textContent('#dialogue-text'), zhLine, 'dialogue language is independent of the interface');
  assert.equal((await L(page)).dialogue, 'original');
  assert.deepEqual(errors, []);
  await context.close();
});

test('Original Chinese: all four missions, both endings, every screen', async () => {
  const { page, context, errors } = await openGame();
  for (const m of manifest.missions) {
    const paths = endingPaths(m.id);
    for (const letter of ['A', 'B']) {
      const kinds = [];
      const got = await play(page, m.id, paths[letter], async (kind, node) => { kinds.push(kind); await checkScreen(page, kind, node, null); });
      assert.equal(got, letter, `${m.id} ending ${letter}`);
      assert.equal(kinds[0], 'title', 'every mission opens on a title card');
      assert.equal(await page.textContent('#ending-badge'), `Ending ${letter}`);
    }
  }
  await page.click('#btn-again');
  assert.equal((await L(page)).kind, 'title');
  await page.click('#btn-back');
  assert.equal((await L(page)).view, 'missions');
  assert.deepEqual(errors, []);
  await context.close();
});

test('Reference English: all four missions, both endings, every screen, clearly labelled', { skip: NO_REF }, async () => {
  const { page, context, errors } = await openGame();
  assert.equal(await optionDisabled(page, 'reference'), false);
  await page.selectOption('#dialogue-select', 'reference');
  const s = await L(page);
  assert.equal(s.dialogue, 'reference');
  assert.equal(s.showing, 'Showing: Reference English (course team) — one possible solution');
  assert.match(await page.textContent('#reference-note'), /one possible solution.*not the only correct translation/);
  await page.fill('#player-name', 'Mei');
  for (const m of manifest.missions) {
    const paths = endingPaths(m.id);
    for (const letter of ['A', 'B']) {
      const got = await play(page, m.id, paths[letter], async (kind, node) => {
        await checkScreen(page, kind, node, reference, 'Mei');
        if (kind !== 'title') assert.match(await page.textContent('#scene-showing'), /Reference English/);
      });
      assert.equal(got, letter);
    }
    const missing = missionIds(m.id).filter((id) => typeof reference.strings[id] !== 'string').length;
    assert.equal(await page.isVisible('#chinese-notice'), missing > 0, m.id);
  }
  // zh interface labels the reference as one possible solution too
  await page.click('#ui-zh');
  assert.match(await page.textContent('#showing-badge'), /參考譯文.*其中一種可行譯法/);
  assert.deepEqual(errors, []);
  await context.close();
});

test('importing the example student file enables the Student option and shows its text', { skip: NO_STUDENT }, async () => {
  const { page, context, errors } = await openGame();
  assert.equal(await optionDisabled(page, 'student'), true, 'disabled before any import');
  await importFile(page, fs.readFileSync(STUDENT_PATH), 'example_student_export_intro.json');
  const s = await L(page);
  assert.equal(s.report.kind, 'applied', JSON.stringify(s.report));
  assert.equal(await optionDisabled(page, 'student'), false);
  assert.equal(s.dialogue, 'student');
  assert.equal(await page.$eval('#dialogue-select', (e) => e.value), 'student');
  const replay = student.source === 'replay' || student.source === 'mixed';
  assert.equal(s.showing, "Showing: Student's imported English" + (replay ? ' · simulated (Replay Mode)' : ''));
  for (const letter of ['A', 'B']) {
    await play(page, 'intro', endingPaths('intro')[letter], async (kind, node) => {
      await checkScreen(page, kind, node, student);
      if (kind !== 'title') assert.match(await page.textContent('#scene-showing'), /Student/);
    });
  }
  // the reference layer is untouched by the student import
  if (reference) {
    await page.selectOption('#dialogue-select', 'reference');
    await play(page, 'intro', endingPaths('intro').A, async (kind, node) => { await checkScreen(page, kind, node, reference); });
    const differs = missionIds('intro').some((id) => student.strings[id] && reference.strings[id] && student.strings[id] !== reference.strings[id]);
    assert.ok(differs, 'student wording differs from the reference');
  }
  await page.selectOption('#dialogue-select', 'original');
  await play(page, 'intro', endingPaths('intro').A, async (kind, node) => { await checkScreen(page, kind, node, null); });
  assert.deepEqual(errors, []);
  await context.close();
});

test('valid synthetic import: placeholders, speaker names, choices', async () => {
  const { page, context, errors } = await openGame();
  await page.fill('#player-name', 'Mei');
  const file = englishFile('intro', null, { characters: { granny_wong: 'Grandma Wong' } });
  await importFile(page, file);
  const s = await L(page);
  assert.equal(s.report.kind, 'applied');
  assert.equal(s.dialogue, 'student');
  assert.equal(s.overrides, missionIds('intro').length);
  for (const letter of ['A', 'B']) {
    await play(page, 'intro', endingPaths('intro')[letter], async (kind, node) => { await checkScreen(page, kind, node, file, 'Mei'); });
  }
  const withName = missionIds('intro').find((id) => (manifest.strings[id].placeholders || []).map(norm).includes('{player_name}'));
  if (withName) {
    const shown = await page.evaluate((id) => __lantern.text(id), withName);
    assert.ok(shown.includes('Mei') && !shown.includes('{'), shown);
  }
  assert.deepEqual(errors, []);
  await context.close();
});

test('invalid files are rejected; messages show in English and in 繁體中文; Chinese unchanged', async () => {
  const { page, context, errors } = await openGame();
  const phId = Object.keys(manifest.strings).find((id) => (manifest.strings[id].placeholders || []).length > 0);
  const cases = [
    [englishFile('intro', { [phId]: 'Broken {player name} text' }), 'placeholder_broken'],
    [englishFile('intro', { 'intro.line.not_real': 'Hello' }), 'unknown_id'],
    [englishFile('intro', null, { format: 'something-else' }), 'wrong_format'],
    ['{"format": "lantern-mystery-translation", "strings": {', 'invalid_json'],
    [englishFile('intro', { [missionIds('intro')[0]]: '   ' }), 'empty_text'],
    [Buffer.alloc(101 * 1024, 0x20), 'file_too_large']
  ];
  for (const uiLang of ['en', 'zh']) {
    await page.click(uiLang === 'en' ? '#ui-en' : '#ui-zh');
    for (const [content, code] of cases) {
      await importFile(page, content, 'bad.json');
      const s = await L(page);
      assert.equal(s.report.kind, 'rejected', code);
      assert.ok(s.report.critical.some((i) => i.code === code), code + ' ' + JSON.stringify(s.report.critical));
      assert.equal(s.dialogue, 'original');
      assert.equal(s.overrides, 0);
      assert.equal(await optionDisabled(page, 'student'), true);
      const sel = `#report-critical li[data-code="${code}"]`;
      assert.ok(await page.isVisible(sel), code);
      const msg = await page.textContent(`${sel} .issue-msg`);
      const fix = await page.textContent(`${sel} .issue-fix`);
      const title = await page.textContent('#report-title');
      if (uiLang === 'en') {
        assert.equal(title, 'This file was not applied');
        assert.match(await page.textContent(sel), /Must fix/);
        assert.match(fix, /^How to fix: /);
        assert.ok(!CJK.test(fix), fix);
      } else {
        assert.equal(title, '未能使用這個檔案');
        assert.match(await page.textContent(sel), /必須修正/);
        assert.match(fix, /^修正方法：/);
        assert.ok(CJK.test(msg) && CJK.test(fix), msg + ' / ' + fix);
      }
      assert.ok(msg.length > 5);
    }
  }
  // an open report switches language with the interface
  await page.click('#ui-en');
  assert.equal(await page.textContent('#report-title'), 'This file was not applied');
  // the broken-placeholder report names the string id
  await importFile(page, englishFile('intro', { [phId]: 'Broken {player name} text' }));
  assert.ok((await page.textContent('#report-critical li[data-code="placeholder_broken"]')).includes(phId));
  await play(page, 'intro', endingPaths('intro').A, async (kind, node) => { await checkScreen(page, kind, node, null); });
  assert.deepEqual(errors, []);
  await context.close();
});

test('paste import works, and later imports override earlier ones', async () => {
  const { page, context, errors } = await openGame();
  await page.click('#btn-paste');
  assert.equal(await page.isVisible('#paste-panel'), true);
  const first = englishFile('intro', null, { source: 'live' });
  await page.fill('#paste-text', JSON.stringify(first));
  await page.click('#btn-paste-apply');
  await page.waitForFunction(() => __lantern.dialogue === 'student');
  assert.equal(await page.isVisible('#paste-panel'), false);
  assert.equal((await L(page)).showing, "Showing: Student's imported English", 'live source: no replay label');
  const id = missionIds('intro').find((x) => manifest.strings[x].max_len === null || manifest.strings[x].max_len >= 12);
  const ph = (manifest.strings[id].placeholders || []).map(norm).join(' ');
  const second = { format: 'lantern-mystery-translation', schema_version: '1.0', locale: 'en', source: 'mixed', strings: { [id]: ('Override ' + ph).trim() } };
  await page.click('#btn-paste');
  await page.fill('#paste-text', JSON.stringify(second));
  await page.click('#btn-paste-apply');
  await page.waitForFunction(() => __lantern.imports.length === 2);
  const s = await L(page);
  assert.equal(await page.evaluate((i) => __lantern.text(i), id), fill(second.strings[id], 'en', s.values));
  const other = missionIds('intro').find((x) => x !== id);
  assert.equal(await page.evaluate((i) => __lantern.text(i), other), fill(first.strings[other], 'en', s.values));
  assert.equal(s.replay, true);
  assert.match(s.showing, /simulated \(Replay Mode\)$/);
  await page.click('#btn-paste');
  await page.fill('#paste-text', 'not json at all');
  await page.click('#btn-paste-apply');
  assert.equal((await L(page)).report.kind, 'rejected');
  assert.equal((await L(page)).overrides, missionIds('intro').length);
  assert.deepEqual(errors, []);
  await context.close();
});

test('missing ids stay Chinese with a visible notice (English and 繁體中文 interface)', async () => {
  const { page, context, errors } = await openGame();
  const ids = missionIds('intro');
  const file = englishFile('intro');
  const lineIds = Object.values(story.missions.intro.nodes).filter((n) => n.kind === 'line').map((n) => n.text);
  const dropped = [lineIds[0], ids.find((id) => id !== lineIds[0])];
  dropped.forEach((id) => delete file.strings[id]);
  await importFile(page, file);
  const s = await L(page);
  assert.equal(s.report.kind, 'applied');
  assert.equal(s.report.warnings.filter((w) => w.code === 'missing_id').length, 2);
  await page.click('[data-mission="intro"]');
  assert.equal(await page.textContent('#chinese-notice'), '2 strings in this mission are still in Chinese.');
  await page.click('#ui-zh');
  assert.equal(await page.textContent('#chinese-notice'), '此任務仍有 2 句以中文原文顯示。');
  assert.equal(await page.evaluate((i) => __lantern.text(i), dropped[0]), fill(zh[dropped[0]], 'zh', s.values));
  assert.deepEqual(errors, []);
  await context.close();
});

test('HTML/script in a translation is shown as literal text and never executed', async () => {
  const { page, context, errors, dialogs } = await openGame();
  const lineNode = nodesOnPath('intro', endingPaths('intro').A).find((n) => n.kind === 'line' && !manifest.strings[n.text].max_len);
  assert.ok(lineNode, 'an intro line without max_len');
  const ph = (manifest.strings[lineNode.text].placeholders || []).map(norm).join(' ');
  const payload = `<img src=x onerror="window.__pwned=1;alert(1)"><script>window.__pwned=2;alert(2)</script> ${ph}`.trim();
  const choiceId = missionIds('intro').find((id) => manifest.strings[id].type === 'choice' && (!manifest.strings[id].max_len || manifest.strings[id].max_len >= 20));
  const overrides = { [lineNode.text]: payload };
  if (choiceId) overrides[choiceId] = '<b>bold</b>?';
  await importFile(page, englishFile('intro', overrides, { characters: { kit: '<i>Kit</i>', granny_wong: '<svg onload=alert()>' } }));
  const s = await L(page);
  assert.equal(s.report.kind, 'applied', JSON.stringify(s.report));
  assert.ok(s.report.warnings.some((w) => w.code === 'angle_brackets'));
  await page.click('#report-warnings-box summary');
  await play(page, 'intro', endingPaths('intro').A, async (kind, node) => {
    if (node === lineNode) {
      assert.equal(await page.textContent('#dialogue-text'), fill(payload, 'en', s.values));
      assert.equal(await page.$$eval('#dialogue-text *', (els) => els.length), 0);
    }
    if (kind === 'choice' && choiceId) assert.ok((await page.$$eval('.btn-choice', (e) => e.map((x) => x.textContent))).includes('<b>bold</b>?'));
  });
  await page.click('#ui-zh'); // re-render the report in zh: still text
  await page.waitForTimeout(300);
  const dom = await page.evaluate(() => ({
    pwned: window.__pwned,
    imgX: document.querySelectorAll('img[src="x"]').length,
    scripts: [...document.scripts].map((s) => s.getAttribute('src')),
    svg: document.querySelectorAll('svg').length,
    bold: document.querySelectorAll('b, i').length
  }));
  assert.equal(dom.pwned, undefined);
  assert.equal(dom.imgX, 0);
  assert.deepEqual(dom.scripts, ['validator.js', 'game.js']);
  assert.equal(dom.svg, 0);
  assert.equal(dom.bold, 0);
  assert.deepEqual(dialogs, []);
  await importFile(page, englishFile('intro', { '<img src=x onerror=alert(4)>': 'x' }));
  assert.equal(await page.evaluate(() => document.querySelectorAll('img[src="x"]').length), 0);
  assert.deepEqual(dialogs, []);
  assert.deepEqual(errors, []);
  await context.close();
});

/** "#t=<base64url(UTF-8 compact JSON)>", built like src/exports.py game_play_url. */
const playHash = (obj) => '#t=' + Buffer.from(JSON.stringify(obj), 'utf8').toString('base64url').replace(/=+$/, '');
const hashNow = (page) => page.evaluate(() => location.hash);

test('a Colab game link (#t=…) loads the student translation; the hash is removed and a reload does not re-apply it', async () => {
  const file = student || englishFile('intro');
  const { page, context, errors } = await openGame(null, null, playHash(file));
  let s = await L(page);
  assert.equal(s.report.kind, 'applied', JSON.stringify(s.report));
  assert.equal(s.dialogue, 'student');
  assert.equal(await page.$eval('#dialogue-select', (e) => e.value), 'student');
  assert.equal(await optionDisabled(page, 'student'), false);
  assert.match(await page.$eval('#dialogue-select', (e) => e.selectedOptions[0].textContent), /^Student's imported English/);
  const replay = file.source === 'replay' || file.source === 'mixed';
  assert.equal(s.showing, "Showing: Student's imported English" + (replay ? ' · simulated (Replay Mode)' : ''));
  assert.deepEqual((await page.evaluate(() => __lantern.imports)).map((i) => i.label), ['link from Colab']);
  assert.match(await page.textContent('#report-summary'), /link from Colab/);
  assert.equal(await hashNow(page), '');
  assert.equal(page.url(), baseUrl);
  await play(page, 'intro', endingPaths('intro').A, async (kind, node) => { await checkScreen(page, kind, node, file); });
  // reload: no fragment any more, imports are not stored → Student disabled, Original Chinese
  await page.reload();
  await ready(page);
  s = await L(page);
  assert.equal(s.dialogue, 'original');
  assert.equal(s.studentAvailable, false);
  assert.equal(s.overrides, 0);
  assert.equal(s.report, null);
  assert.equal(await optionDisabled(page, 'student'), true);
  assert.equal(await hashNow(page), '');
  // the ordinary skip link (#stage) is not mistaken for a game link
  await page.evaluate(() => { location.hash = '#stage'; });
  await page.waitForTimeout(100);
  assert.equal((await L(page)).report, null);
  assert.equal(await hashNow(page), '#stage');
  assert.deepEqual(errors, []);
  await context.close();
});

test('broken or invalid game links show the error panel (English and 繁體中文); Chinese unchanged', async () => {
  const good = playHash(student || englishFile('intro'));
  const { page, context, errors } = await openGame(null, null, '#t=not$base64');
  const check = async (code, uiLang) => {
    const s = await L(page);
    assert.equal(s.report.kind, 'rejected', code);
    assert.ok(s.report.critical.some((i) => i.code === code), code + ' ' + JSON.stringify(s.report.critical));
    assert.equal(s.dialogue, 'original');
    assert.equal(s.overrides, 0);
    assert.equal(await optionDisabled(page, 'student'), true);
    assert.equal(await page.isVisible(`#report-critical li[data-code="${code}"]`), true, code);
    assert.equal(await page.textContent('#report-title'), uiLang === 'en' ? 'This file was not applied' : '未能使用這個檔案');
    const msg = await page.textContent(`#report-critical li[data-code="${code}"] .issue-msg`);
    assert.equal(CJK.test(msg), uiLang === 'zh', msg);
    assert.equal(await hashNow(page), '');
  };
  await check('invalid_link', 'en');
  // the same page receiving a new link (hashchange) is handled too
  await page.click('#ui-zh');
  const nav = async (hash) => {
    await page.evaluate(() => { document.getElementById('report').hidden = true; });
    await page.evaluate((h) => { location.hash = h; }, hash);
    await page.waitForSelector('#report:not([hidden])');
  };
  await nav('#t=' + Buffer.from([0xff, 0xfe, 0x7b]).toString('base64url'));
  await check('invalid_link', 'zh');
  await nav(good.slice(0, Math.floor(good.length / 2)));          // cut short → not valid JSON (or not UTF-8)
  const cut = (await L(page)).report.critical.map((i) => i.code);
  assert.ok(cut.includes('invalid_json') || cut.includes('invalid_link'), JSON.stringify(cut));
  await check(cut[0], 'zh');
  await nav(playHash(englishFile('intro', { 'intro.line.not_real': 'Hello' })));   // decodes, fails validation
  await check('unknown_id', 'zh');
  await nav('#t=' + 'A'.repeat(140 * 1024));
  await check('file_too_large', 'zh');
  await page.click('#ui-en');
  await play(page, 'intro', endingPaths('intro').A, async (kind, node) => { await checkScreen(page, kind, node, null); });
  assert.deepEqual(errors, []);
  await context.close();
});

test('persistence across reload: interface language and dialogue choice (sessionStorage)', async () => {
  const { page, context, errors } = await openGame();
  await page.click('#ui-zh');
  const choice = reference ? 'reference' : 'original';
  if (reference) await page.selectOption('#dialogue-select', 'reference');
  await page.reload();
  await ready(page);
  let s = await L(page);
  assert.equal(s.uiLang, 'zh');
  assert.equal(s.dialogue, choice);
  assert.equal(await page.textContent('#btn-import'), '匯入學生 JSON');
  assert.equal(await page.$eval('#dialogue-select', (e) => e.value), choice);
  // student choice is not restorable (imports are not stored) → Original Chinese
  await importFile(page, englishFile('intro'));
  assert.equal((await L(page)).dialogue, 'student');
  await page.reload();
  await ready(page);
  s = await L(page);
  assert.equal(s.uiLang, 'zh');
  assert.equal(s.dialogue, 'original');
  assert.equal(s.studentAvailable, false);
  assert.equal(await optionDisabled(page, 'student'), true);
  assert.deepEqual(errors, []);
  await context.close();
});

test('the game still works when sessionStorage is blocked', async () => {
  const block = () => {
    const thrower = () => { throw new DOMException('blocked', 'SecurityError'); };
    Object.defineProperty(window, 'sessionStorage', { get: thrower, configurable: true });
  };
  const { page, context, errors } = await openGame({}, block);
  await page.click('#ui-zh');
  assert.equal((await L(page)).uiLang, 'zh');
  await importFile(page, englishFile('intro'));
  assert.equal((await L(page)).dialogue, 'student');
  await page.reload();
  await ready(page);
  assert.equal((await L(page)).uiLang, 'en', 'nothing persisted, defaults used');
  assert.deepEqual(errors, []);
  await context.close();
});

test('Reset keeps the interface language, clears the student layer and returns to Original Chinese', async () => {
  const { page, context, errors } = await openGame();
  await page.click('#ui-zh');
  await importFile(page, englishFile('intro'));
  await importFile(page, englishFile(hudMission() || 'ui'));
  assert.equal((await L(page)).dialogue, 'student');
  await page.click('#btn-reset');
  const s = await L(page);
  assert.equal(s.uiLang, 'zh');
  assert.equal(s.dialogue, 'original');
  assert.equal(s.overrides, 0);
  assert.equal(s.report.kind, 'reset');
  assert.equal(await optionDisabled(page, 'student'), true);
  assert.equal(await optionDisabled(page, 'reference'), !reference, 'reference survives the reset');
  assert.equal(await page.textContent('#showing-badge'), '正在顯示：中文原文');
  assert.equal(await page.textContent('#btn-import'), '匯入學生 JSON');
  await play(page, 'intro', endingPaths('intro').A, async (kind, node) => { await checkScreen(page, kind, node, null); });
  assert.deepEqual(errors, []);
  await context.close();
});

test('HUD mission: mock interface, placeholders filled, toast line break rendered (Chinese and English)', async () => {
  const mission = hudMission();
  assert.ok(mission, 'a mission with a hud node');
  const { page, context, errors } = await openGame();
  await page.fill('#player-name', 'Ada');
  const hud = Object.values(story.missions[mission].nodes).find((n) => n.kind === 'hud');
  const layers = [['original', null], ['student', englishFile(mission)]];
  if (reference) layers.push(['reference', reference]);
  let newlineChecks = 0;
  for (const [mode, layer] of layers) {
    if (mode === 'student') await importFile(page, layer);
    await page.selectOption('#dialogue-select', mode);
    let checked = false;
    await play(page, mission, endingPaths(mission).A, async (kind, node) => {
      if (kind !== 'hud') return;
      await checkScreen(page, kind, node, layer, 'Ada');
      const texts = await page.$$eval('.hud-text', (els) => els.map((e) => ({ id: e.dataset.stringId, text: e.textContent, inner: e.innerText })));
      const values = (await L(page)).values;
      for (const t of texts) {
        assert.ok(!/\{[a-z_]+\}/.test(t.text), 'no raw placeholder: ' + t.text);
        if (t.text.includes('\n')) {
          // innerText reflects rendering: with white-space: pre-line the \n is a real line break
          assert.ok(t.inner.includes('\n'), `${mode}: ${t.id} renders a line break`);
          const lines = await page.$eval(`.hud-text[data-string-id="${t.id}"]`, (e) => {
            const r = document.createRange(); r.selectNodeContents(e);
            return new Set([...r.getClientRects()].map((x) => Math.round(x.top))).size;
          });
          assert.ok(lines >= 2, `${mode}: ${t.id} occupies ${lines} lines`);
          newlineChecks++;
        }
      }
      const all = texts.map((t) => t.text).join(' ');
      for (const p of hud.texts.flatMap((id) => manifest.strings[id].placeholders.map(norm))) {
        if (p === '{coins}') assert.ok(all.includes(String(values.coins)));
        if (p === '{lantern_count}') assert.ok(all.includes(String(values.lantern_count)));
        if (p === '{player_name}') assert.ok(all.includes('Ada'));
      }
      checked = true;
    });
    assert.ok(checked, mode);
  }
  const zhHasNewline = hud.texts.some((id) => zh[id].includes('\n'));
  if (zhHasNewline) assert.ok(newlineChecks >= 1);
  if (reference && hud.texts.some((id) => (reference.strings[id] || '').includes('\n'))) assert.ok(newlineChecks >= 2, 'English line break checked too');
  assert.deepEqual(errors, []);
  await context.close();
});

test('keyboard only: interface switch, missions and dialogue reachable with Enter', async () => {
  const { page, context, errors } = await openGame();
  await page.focus('#ui-zh');
  await page.keyboard.press('Enter');
  assert.equal((await L(page)).uiLang, 'zh');
  await page.focus('[data-mission="intro"]');
  await page.keyboard.press('Enter');
  assert.equal((await L(page)).kind, 'title');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'btn-start');
  await page.keyboard.press('Enter');
  assert.notEqual((await L(page)).kind, 'title');
  assert.ok(await page.evaluate(() => document.activeElement.tagName === 'BUTTON'));
  assert.equal(await page.getAttribute('#dialogue-live', 'aria-live'), 'polite');
  assert.deepEqual(errors, []);
  await context.close();
});

test('phone width: no horizontal scrolling', async () => {
  const { page, context, errors } = await openGame({ viewport: { width: 360, height: 740 } });
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(await overflow() <= 0, 'missions');
  if (reference) await page.selectOption('#dialogue-select', 'reference');
  await page.click('[data-mission="intro"]');
  await page.click('#btn-start');
  assert.ok(await overflow() <= 0, 'dialogue');
  const m = hudMission();
  if (m) await play(page, m, endingPaths(m).A, async (kind) => { if (kind === 'hud') assert.ok(await overflow() <= 0, 'hud'); });
  await page.click('#ui-zh');
  assert.ok(await overflow() <= 0, 'zh interface');
  assert.deepEqual(errors, []);
  await context.close();
});

test('opening index.html from file:// shows a friendly message', async () => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('file://' + path.join(GAME_DIR, 'index.html'));
  await page.waitForTimeout(300);
  assert.ok(await page.isVisible('#load-error') || await page.isVisible('#loading'));
  assert.match(await page.textContent('body'), /GitHub Pages/);
  await context.close();
});
