'use strict';
// Unit tests for game/validator.js (CONTRACTS §5). Run: node --test tests/game/validator.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const V = require('../../game/validator.js');
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'strings_manifest.json'), 'utf8'));

const INTRO_EN = {
  'intro.ui.start': 'Investigate',
  'intro.narration.arrival': 'Mid-Autumn night. {player_name} reaches the market: Granny Wong’s biggest rabbit lantern is gone.',
  'intro.line.granny_greeting': 'At last! Someone has stolen my rabbit lantern!',
  'intro.line.kit_joke': 'Granny, that rabbit is huge — unless it hopped back to the moon!',
  'intro.choice.follow': 'Follow the tall hat',
  'intro.choice.ask': 'Ask the neighbours',
  'intro.ending.a': 'At the end of the street you find the Riddle King — he only borrowed it!',
  'intro.ending.b': 'The neighbours all talk at once. By the time you finish, the lantern is back.'
};

function file(strings, extra) {
  return Object.assign({
    format: 'lantern-mystery-translation',
    schema_version: '1.0',
    locale: 'en-GB',
    mission: 'intro',
    source: 'replay',
    strings: strings
  }, extra || {});
}
function codes(report, severity) {
  return report.issues.filter((i) => !severity || i.severity === severity).map((i) => i.code);
}
function withString(id, text) {
  return file(Object.assign({}, INTRO_EN, { [id]: text }));
}
function assertIssueShape(report) {
  for (const i of report.issues) {
    assert.ok(i.severity === 'CRITICAL' || i.severity === 'WARNING');
    assert.equal(typeof i.code, 'string');
    assert.ok(i.string_id === null || typeof i.string_id === 'string');
    assert.ok(i.message.length > 10, 'plain-English message');
    assert.ok(i.fix_hint.length > 5, 'fix hint');
  }
}

test('a valid complete file has no CRITICAL issues (text and object input)', () => {
  for (const input of [file(INTRO_EN), JSON.stringify(file(INTRO_EN), null, 2)]) {
    const r = V.validateTranslationFile(input, manifest);
    assert.equal(r.ok, true, JSON.stringify(r.critical));
    assert.deepEqual(r.critical, []);
    assert.equal(Object.keys(r.strings).length, 8);
    assert.ok(!codes(r).includes('missing_id'));
    assertIssueShape(r);
  }
});

test('the fixture zh-Hant source validates structurally (only CJK warnings)', () => {
  const zh = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'translations', 'zh-Hant.json'), 'utf8'));
  const r = V.validateTranslationFile(zh, manifest);
  assert.equal(r.ok, true, JSON.stringify(r.critical));
  assert.ok(codes(r, 'WARNING').every((c) => c === 'untranslated_cjk' || c === 'near_limit'));
});

test('BOM at the start of the text is tolerated', () => {
  const r = V.validateTranslationFile('﻿' + JSON.stringify(file(INTRO_EN)), manifest);
  assert.equal(r.ok, true);
});

test('unknown id is CRITICAL and names the id', () => {
  const r = V.validateTranslationFile(withString('intro.line.made_up', 'Hello'), manifest);
  assert.equal(r.ok, false);
  const i = r.critical.find((x) => x.code === 'unknown_id');
  assert.equal(i.string_id, 'intro.line.made_up');
  assert.match(i.message, /does not exist/);
});

test('prototype-ish ids are unknown, never crash or pollute', () => {
  const text = '{"format":"lantern-mystery-translation","schema_version":"1.0","strings":{"__proto__":"x","constructor":"y","toString":"z"}}';
  const r = V.validateTranslationFile(text, manifest);
  assert.deepEqual(codes(r, 'CRITICAL').sort(), ['unknown_id', 'unknown_id', 'unknown_id']);
  assert.equal(({}).polluted, undefined);
  assert.equal(Object.keys(r.strings).length, 0);
});

test('missing id is a WARNING on game import, CRITICAL when requireAllForMission', () => {
  const partial = Object.assign({}, INTRO_EN);
  delete partial['intro.choice.ask'];
  const game = V.validateTranslationFile(file(partial), manifest);
  assert.equal(game.ok, true);
  const w = game.warnings.find((x) => x.code === 'missing_id');
  assert.equal(w.string_id, 'intro.choice.ask');
  assert.equal(game.warnings.filter((x) => x.code === 'missing_id').length, 1);

  const exp = V.validateTranslationFile(file(partial), manifest, { requireAllForMission: 'intro' });
  assert.equal(exp.ok, false);
  assert.equal(exp.critical[0].code, 'missing_id');
});

test('missing-id warnings cover only missions the file touches', () => {
  const r = V.validateTranslationFile(file({ 'voice.choice.joke': 'Joke along' }, { mission: undefined }), manifest);
  const missing = r.warnings.filter((x) => x.code === 'missing_id').map((x) => x.string_id);
  assert.ok(missing.length === 5 && missing.every((id) => id.startsWith('voice.')));
  const r2 = V.validateTranslationFile(file({ 'voice.choice.joke': 'Joke along' }), manifest, { mission: 'pun' });
  assert.ok(r2.warnings.filter((x) => x.code === 'missing_id').every((x) => x.string_id.startsWith('pun.')));
});

test('empty and whitespace-only text is CRITICAL empty_text', () => {
  for (const t of ['', '   ', '\n']) {
    const r = V.validateTranslationFile(withString('intro.ending.b', t), manifest);
    assert.deepEqual(codes(r, 'CRITICAL'), ['empty_text']);
  }
});

test('placeholder missing / extra / broken / translated', () => {
  const id = 'intro.narration.arrival';
  const cases = [
    ['At last! Someone stole my lantern!', ['placeholder_missing']],
    ['{player_name}, {player_name}! My lantern!', ['placeholder_extra']],
    ['{player_name}, you have {coins} coins', ['placeholder_extra']],
    ['{player name}, at last!', ['placeholder_broken', 'placeholder_missing']],
    ['{玩家}, at last!', ['placeholder_broken', 'placeholder_missing']],
    ['{player_name, at last!', ['placeholder_broken', 'placeholder_missing']],
    ['player_name}, at last!', ['placeholder_broken', 'placeholder_missing']],
    ['{Player_Name}, at last!', ['placeholder_broken', 'placeholder_missing']],
    ['{player_name}, at last! {}', ['placeholder_broken']]
  ];
  for (const [text, expected] of cases) {
    const r = V.validateTranslationFile(withString(id, text), manifest);
    assert.deepEqual(codes(r, 'CRITICAL').sort(), expected.slice().sort(), text);
    assert.ok(r.critical.every((i) => i.string_id === id));
  }
  // a string with no placeholders that gains one
  const r = V.validateTranslationFile(withString('intro.choice.ask', 'Ask {player_name}'), manifest);
  assert.deepEqual(codes(r, 'CRITICAL'), ['placeholder_extra']);
});

test('placeholder multiset with several tokens (hud status)', () => {
  const ok = V.validateTranslationFile(file({ 'ui.hud.status': 'Lanterns {lantern_count}/{lantern_total} Coins {coins}' }), manifest);
  assert.equal(ok.ok, true, JSON.stringify(ok.critical));
  const swapped = V.validateTranslationFile(file({ 'ui.hud.status': '{coins} coins, {lantern_total}/{lantern_count}' }), manifest);
  assert.equal(swapped.ok, true, 'order may change');
  const bad = V.validateTranslationFile(file({ 'ui.hud.status': 'Lanterns {lantern_count}/{lantern_count}' }), manifest);
  assert.deepEqual(codes(bad, 'CRITICAL').sort(), ['placeholder_extra', 'placeholder_missing', 'placeholder_missing']);
});

test('extractPlaceholders and normalisePlaceholder', () => {
  assert.deepEqual(V.extractPlaceholders('Hi {player_name}, {coins} and {Bad} {x1}'), ['{player_name}', '{coins}', '{x1}']);
  assert.deepEqual(V.extractPlaceholders('none'), []);
  assert.equal(V.normalisePlaceholder('coins'), '{coins}');
  assert.equal(V.normalisePlaceholder('{coins}'), '{coins}');
});

test('too_long counts code points, placeholders literally; near_limit warns at >= 90%', () => {
  const long = V.validateTranslationFile(withString('intro.ui.start', 'Start investigating'), manifest);
  const i = long.critical.find((x) => x.code === 'too_long');
  assert.match(i.message, /19 characters, but the limit is 12/);
  assert.equal(V.validateTranslationFile(withString('intro.ui.start', 'Investigate!'), manifest).ok, true); // 12 = limit
  const near = V.validateTranslationFile(withString('intro.ui.start', 'Investigate'), manifest); // 11 >= 10.8
  assert.ok(codes(near, 'WARNING').includes('near_limit'));
  const emoji = V.validateTranslationFile(withString('intro.ui.start', '\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}\u{1F3EE}'), manifest);
  assert.equal(emoji.ok, true, '12 emoji = 12 code points (24 UTF-16 units)');
  // ui.hud.inventory max 28: '{item_name}' counts as 11
  const toast = V.validateTranslationFile(file({ 'ui.hud.inventory': 'Put in bag: {item_name}!!!!!!' }), manifest); // 29
  assert.ok(codes(toast, 'CRITICAL').includes('too_long'));
});

test('newline rule respects allow_newlines', () => {
  const bad = V.validateTranslationFile(withString('intro.choice.ask', 'Ask the\nneighbours'), manifest);
  assert.deepEqual(codes(bad, 'CRITICAL'), ['newline_not_allowed']);
  const cr = V.validateTranslationFile(withString('intro.choice.ask', 'Ask the\rneighbours'), manifest);
  assert.ok(codes(cr, 'CRITICAL').includes('newline_not_allowed'));
  const ok = V.validateTranslationFile(file({ 'ui.hud.toast': 'New clue!\n{player_name} found some rabbit fur.' }), manifest);
  assert.equal(ok.ok, true, JSON.stringify(ok.critical));
  const notOk = V.validateTranslationFile(withString('intro.ending.b', 'Line one.\nLine two.'), manifest);
  assert.deepEqual(codes(notOk, 'CRITICAL'), ['newline_not_allowed']);
});

test('bad_encoding: lone surrogates, control characters, U+FFFD', () => {
  for (const t of ['Ask \uD83C now', 'Ask \uDFEE now', 'Ask\tnow', 'Ask\u0007now', 'Ask \u0085now', 'Ask � now']) {
    const r = V.validateTranslationFile(withString('intro.choice.ask', t), manifest);
    assert.ok(codes(r, 'CRITICAL').includes('bad_encoding'), JSON.stringify(t));
  }
});

test('Unicode, accents and emoji are fine', () => {
  const r = V.validateTranslationFile(withString('intro.line.kit_joke', 'Gran — café, naïve, \u{1F3EE}\u{1F407} “quotes” … £'), manifest);
  assert.equal(r.ok, true, JSON.stringify(r.critical));
  assert.ok(!codes(r).includes('bad_encoding'));
});

test('wrong format / version, invalid JSON, non-object top level', () => {
  assert.deepEqual(codes(V.validateTranslationFile(file(INTRO_EN, { format: 'other' }), manifest), 'CRITICAL'), ['wrong_format']);
  assert.deepEqual(codes(V.validateTranslationFile(file(INTRO_EN, { schema_version: '2.0' }), manifest), 'CRITICAL'), ['wrong_format']);
  assert.deepEqual(codes(V.validateTranslationFile(file(INTRO_EN, { schema_version: undefined }), manifest), 'CRITICAL'), ['wrong_format']);
  assert.equal(V.validateTranslationFile(file(INTRO_EN, { schema_version: '1.7' }), manifest).ok, true);
  assert.deepEqual(codes(V.validateTranslationFile('{"format": ', manifest)), ['invalid_json']);
  assert.deepEqual(codes(V.validateTranslationFile('', manifest)), ['invalid_json']);
  assert.deepEqual(codes(V.validateTranslationFile('[1,2]', manifest)), ['wrong_format']);
  assert.deepEqual(codes(V.validateTranslationFile('null', manifest)), ['wrong_format']);
});

test('strings must be an object of string to string', () => {
  assert.deepEqual(codes(V.validateTranslationFile(file(undefined), manifest)), ['bad_structure']);
  assert.deepEqual(codes(V.validateTranslationFile(file(['a']), manifest)), ['bad_structure']);
  assert.deepEqual(codes(V.validateTranslationFile(file('text'), manifest)), ['bad_structure']);
  const r = V.validateTranslationFile(file(Object.assign({}, INTRO_EN, { 'intro.ui.start': 42, 'intro.choice.ask': null, 'intro.choice.follow': { t: 'x' } })), manifest);
  assert.deepEqual(codes(r, 'CRITICAL'), ['bad_structure', 'bad_structure', 'bad_structure']);
  assert.ok(!('intro.ui.start' in r.strings));
});

test('characters validation', () => {
  assert.equal(V.validateTranslationFile(file(INTRO_EN, { characters: { granny_wong: 'Grandma Wong', kit: 'Kit' } }), manifest).ok, true);
  const bad = [
    { characters: 'Granny' },
    { characters: ['Granny'] },
    { characters: { granny_wong: '' } },
    { characters: { granny_wong: 42 } },
    { characters: { granny_wong: 'A name that is far too long to fit' } },
    { characters: { granny_wong: 'Granny\nWong' } },
    { characters: { nobody: 'Nobody' } }
  ];
  for (const extra of bad) {
    const r = V.validateTranslationFile(file(INTRO_EN, extra), manifest);
    assert.deepEqual(codes(r, 'CRITICAL'), ['bad_structure'], JSON.stringify(extra));
  }
  const cjk = V.validateTranslationFile(file(INTRO_EN, { characters: { granny_wong: '黃婆婆' } }), manifest);
  assert.equal(cjk.ok, true);
  assert.ok(codes(cjk, 'WARNING').includes('untranslated_cjk'));
});

test('file size: over 100 KB is CRITICAL before parsing', () => {
  const big = JSON.stringify(file(INTRO_EN, { padding: 'x'.repeat(102400) }));
  const r = V.validateTranslationFile(big, manifest);
  assert.deepEqual(codes(r), ['file_too_large']);
  const notJsonButBig = '{' + 'x'.repeat(110 * 1024);
  assert.deepEqual(codes(V.validateTranslationFile(notJsonButBig, manifest)), ['file_too_large']);
  assert.deepEqual(codes(V.validateTranslationFile(file(INTRO_EN, { padding: 'x'.repeat(102400) }), manifest)), ['file_too_large']);
  // multi-byte characters count in UTF-8 bytes: 35,000 CJK chars ≈ 105 KB
  assert.deepEqual(codes(V.validateTranslationFile(JSON.stringify(file(INTRO_EN, { p: '燈'.repeat(35000) })), manifest)), ['file_too_large']);
});

test('CJK left in an English string is a WARNING, not CRITICAL', () => {
  const r = V.validateTranslationFile(withString('intro.choice.ask', 'Ask 街坊'), manifest);
  assert.equal(r.ok, true);
  assert.ok(codes(r, 'WARNING').includes('untranslated_cjk'));
});

test('angle brackets and whitespace are WARNINGS', () => {
  const r = V.validateTranslationFile(withString('intro.line.kit_joke', '<img src=x onerror=alert(1)>'), manifest);
  assert.equal(r.ok, true);
  assert.ok(codes(r, 'WARNING').includes('angle_brackets'));
  for (const t of [' Ask', 'Ask ', 'Ask  them']) {
    const w = V.validateTranslationFile(withString('intro.choice.ask', t), manifest);
    assert.equal(w.ok, true);
    assert.ok(codes(w, 'WARNING').includes('whitespace'), t);
  }
});

test('U+FEFF and other Unicode spaces at the start or end are a whitespace WARNING', () => {
  for (const t of ['Ask\uFEFF', '\uFEFFAsk', 'Ask\u00A0', '\u3000Ask']) {
    const w = V.validateTranslationFile(withString('intro.choice.ask', t), manifest);
    assert.equal(w.ok, true);
    assert.ok(codes(w, 'WARNING').includes('whitespace'), JSON.stringify(t));
  }
  const ok = V.validateTranslationFile(withString('intro.choice.ask', 'Ask\u200Bthem'), manifest);
  assert.ok(!codes(ok).includes('whitespace'));   // zero-width space is not \s in JS or Python
});

test('source and locale: invalid source is CRITICAL, missing source or odd locale a WARNING', () => {
  const bad = V.validateTranslationFile(file(INTRO_EN, { source: 'chatgpt' }), manifest);
  assert.equal(bad.ok, false);
  assert.deepEqual(codes(bad, 'CRITICAL'), ['bad_structure']);
  assert.ok(/source/.test(bad.critical[0].message) && /[\u3400-\u9fff]/.test(bad.critical[0].message_zh));
  const noSource = file(INTRO_EN);
  delete noSource.source;
  for (const f of [noSource, file(INTRO_EN, { locale: 'fr-FR' }), file(INTRO_EN, { locale: 5 })]) {
    const r = V.validateTranslationFile(f, manifest);
    assert.equal(r.ok, true);
    assert.deepEqual(codes(r, 'WARNING').filter((c) => c !== 'near_limit'), ['bad_structure']);
    assertIssueShape(r);
  }
  for (const source of ['live', 'replay', 'mixed', 'original', 'reference']) {
    for (const locale of ['en-GB', 'en-US', 'en', 'zh-Hant-HK']) {
      const r = V.validateTranslationFile(file(INTRO_EN, { source, locale }), manifest);
      assert.ok(!codes(r).includes('bad_structure'), source + ' ' + locale);
    }
  }
});

test('messages are plain English and quote the text', () => {
  const r = V.validateTranslationFile(withString('intro.ui.start', 'Start investigating'), manifest);
  const i = r.critical[0];
  assert.equal(i.string_id, 'intro.ui.start');
  assert.match(i.message, /button\/interface text .Start investigating. is 19 characters/);
  assert.match(i.fix_hint, /Shorten/);
  assertIssueShape(r);
});

// ---- bilingual messages ----
const CJK = /[㐀-鿿]/;
function triggerAll() {
  // one input per issue code (game import semantics + export semantics for missing_id)
  const big = JSON.stringify(file(INTRO_EN, { p: 'x'.repeat(102400) }));
  const many = file(Object.assign({}, INTRO_EN, {
    'intro.made.up': 'x',
    'intro.ui.start': 'Start investigating',
    'intro.choice.ask': 'Ask\tthe\nneighbours',
    'intro.choice.follow': '   ',
    'intro.narration.arrival': '{player name} {coins} 街坊 <b>  x ',
    'intro.ending.a': 42
  }));
  delete many.strings['intro.ending.b'];
  return [
    V.validateTranslationFile('{oops', manifest),
    V.validateTranslationFile(big, manifest),
    V.validateTranslationFile(file(INTRO_EN, { format: 'nope' }), manifest),
    V.validateTranslationFile(many, manifest),
    V.validateTranslationFile(many, manifest, { requireAllForMission: 'intro' }),
    V.validateTranslationFile(withString('intro.ui.start', 'Investigate'), manifest),
    V.validateTranslationFile(withString('intro.line.kit_joke', 'Fine {player_name}'), manifest),
    V.validateTranslationFile(file(INTRO_EN, { characters: { nobody: 'x', kit: 'Kit\u0007' } }), manifest)
  ].flatMap((r) => r.issues);
}

test('every issue code is produced with English and zh-Hant message and fix hint', () => {
  const issues = triggerAll();
  const seen = new Set(issues.map((i) => i.code));
  for (const code of V.ISSUE_CODES) assert.ok(seen.has(code), 'not triggered: ' + code);
  for (const i of issues) {
    for (const k of ['message', 'fix_hint', 'message_zh', 'fix_hint_zh']) assert.equal(typeof i[k], 'string', k);
    assert.ok(CJK.test(i.message_zh), 'zh message for ' + i.code + ': ' + i.message_zh);
    assert.ok(CJK.test(i.fix_hint_zh), 'zh fix hint for ' + i.code + ': ' + i.fix_hint_zh);
    assert.ok(!CJK.test(i.fix_hint), 'English fix hint stays English: ' + i.code);
  }
});

test('code titles exist in both languages for every code (incl. Python-only duplicate_id)', () => {
  for (const code of V.ISSUE_CODES.concat(V.PYTHON_ONLY_CODES)) {
    assert.ok(V.CODE_TITLES_EN[code], code);
    assert.ok(CJK.test(V.CODE_TITLES_ZH[code]), code);
  }
  assert.deepEqual(V.PYTHON_ONLY_CODES, ['duplicate_id']);
});

test('fixture reference and example student files validate', () => {
  const dir = path.join(__dirname, 'fixtures', 'translations');
  const ref = V.validateTranslationFile(fs.readFileSync(path.join(dir, 'en.reference.json'), 'utf8'), manifest);
  assert.equal(ref.ok, true, JSON.stringify(ref.critical));
  assert.equal(ref.data.source, 'reference');
  for (const m of manifest.missions) {
    assert.equal(V.validateTranslationFile(ref.data, manifest, { requireAllForMission: m.id }).ok, true, m.id);
  }
  const stu = V.validateTranslationFile(fs.readFileSync(path.join(dir, 'example_student_export_intro.json'), 'utf8'), manifest, { requireAllForMission: 'intro' });
  assert.equal(stu.ok, true, JSON.stringify(stu.critical));
});

// ---- real content (runs once game/strings_manifest.json exists) ----
const GAME = path.join(__dirname, '..', '..', 'game');
const realManifestPath = path.join(GAME, 'strings_manifest.json');
const haveReal = fs.existsSync(realManifestPath);
const realFile = (f) => path.join(GAME, 'translations', f);

test('real content: zh-Hant.json validates and placeholders are game-supplied', { skip: !haveReal && 'real content not present' }, () => {
  const real = JSON.parse(fs.readFileSync(realManifestPath, 'utf8'));
  const zh = V.validateTranslationFile(fs.readFileSync(realFile('zh-Hant.json'), 'utf8'), real);
  assert.equal(zh.ok, true, JSON.stringify(zh.critical));
  const supplied = ['{player_name}', '{lantern_count}', '{lantern_total}', '{coins}', '{item_name}'];
  for (const [id, spec] of Object.entries(real.strings)) {
    for (const p of spec.placeholders) assert.ok(supplied.includes(V.normalisePlaceholder(p)), id + ' ' + p);
  }
});

test('real content: en.reference.json covers every mission', { skip: !(haveReal && fs.existsSync(realFile('en.reference.json'))) && 'en.reference.json not present yet' }, () => {
  const real = JSON.parse(fs.readFileSync(realManifestPath, 'utf8'));
  const text = fs.readFileSync(realFile('en.reference.json'), 'utf8');
  for (const m of real.missions) {
    const r = V.validateTranslationFile(text, real, { requireAllForMission: m.id });
    assert.equal(r.ok, true, m.id + ' ' + JSON.stringify(r.critical));
  }
});

test('real content: example_student_export_intro.json is a valid intro file', { skip: !(haveReal && fs.existsSync(realFile('example_student_export_intro.json'))) && 'example student file not present yet' }, () => {
  const real = JSON.parse(fs.readFileSync(realManifestPath, 'utf8'));
  const r = V.validateTranslationFile(fs.readFileSync(realFile('example_student_export_intro.json'), 'utf8'), real, { requireAllForMission: 'intro' });
  assert.equal(r.ok, true, JSON.stringify(r.critical));
});

/* ---------- shared links: #t=<base64url(UTF-8 JSON)> (CONTRACTS §5, §12) ---------- */

const b64url = (buf) => Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const linkFor = (obj) => '#t=' + b64url(Buffer.from(JSON.stringify(obj), 'utf8'));
function assertLinkError(r, code) {
  assert.equal(r.ok, false);
  assert.equal(r.code, code);
  assert.ok(r.message.length > 10 && !CJK_RE_LINK.test(r.message), r.message);
  assert.ok(CJK_RE_LINK.test(r.message_zh), r.message_zh);
  assert.ok(r.fix_hint.length > 5 && CJK_RE_LINK.test(r.fix_hint_zh));
  assert.equal(r.issue.severity, 'CRITICAL');
  assert.equal(r.issue.code, code);
  assert.ok(V.CODE_TITLES_EN[code] && CJK_RE_LINK.test(V.CODE_TITLES_ZH[code]));
}
const CJK_RE_LINK = /[㐀-鿿]/;

test('decodeSharedTranslation: a valid link round-trips (Unicode, CJK, emoji) and validates', () => {
  const obj = file(Object.assign({}, INTRO_EN, { 'intro.ui.start': 'Go 🏮 中秋' }));
  const text = JSON.stringify(obj);
  for (const frag of [linkFor(obj), linkFor(obj).slice(1), '#a=1&' + linkFor(obj).slice(1)]) {
    const r = V.decodeSharedTranslation(frag);
    assert.equal(r.ok, true, JSON.stringify(r));
    assert.equal(r.text, text);
    assert.equal(r.bytes, Buffer.byteLength(text, 'utf8'));
  }
  assert.equal(V.PLAY_PARAM, 't');
  assert.ok(V.validateTranslationFile(V.decodeSharedTranslation(linkFor(obj)).text, manifest).ok);
});

test('decodeSharedTranslation: padding is optional (none, one or two "=")', () => {
  for (const s of ['a', 'ab', 'abc', 'abcd', '中', '🏮x']) {
    const std = Buffer.from(s, 'utf8').toString('base64').replace(/\+/g, '-').replace(/\//g, '_');
    for (const enc of [std, std.replace(/=+$/, ''), std.replace(/=/g, '%3D')]) {
      const r = V.decodeSharedTranslation('#t=' + enc);
      assert.equal(r.ok, true, enc);
      assert.equal(r.text, s);
    }
  }
});

test('decodeSharedTranslation: bad base64 is invalid_link', () => {
  for (const bad of ['#t=abc$def', '#t=ab+c', '#t=ab/c', '#t=a', '#t=abcde', '#t=ab cd', '#t=%E0%A4%A']) {
    assertLinkError(V.decodeSharedTranslation(bad), 'invalid_link');
  }
});

test('decodeSharedTranslation: bytes that are not UTF-8 are invalid_link', () => {
  for (const bytes of [[0xff, 0xfe, 0x7b], [0x7b, 0xc3], [0xed, 0xa0, 0x80], [0xc0, 0xaf]]) {
    assertLinkError(V.decodeSharedTranslation('#t=' + b64url(Buffer.from(bytes))), 'invalid_link');
  }
});

test('decodeSharedTranslation: missing or empty parameter is invalid_link', () => {
  for (const frag of ['', '#', '#stage', '#x=abc', 'tt=abc', '#t=', '#t==', null, undefined]) {
    assertLinkError(V.decodeSharedTranslation(frag), 'invalid_link');
  }
});

test('decodeSharedTranslation: decoded payload over 100 KB is file_too_large; exactly 100 KB is fine', () => {
  const exact = Buffer.alloc(V.MAX_FILE_BYTES, 0x61);
  assert.equal(V.decodeSharedTranslation('#t=' + b64url(exact)).ok, true);
  assertLinkError(V.decodeSharedTranslation('#t=' + b64url(Buffer.alloc(V.MAX_FILE_BYTES + 1, 0x61))), 'file_too_large');
  assertLinkError(V.decodeSharedTranslation('#t=' + 'A'.repeat(2 * 1024 * 1024)), 'file_too_large');
  assert.ok(V.LINK_CODES.includes('invalid_link') && !V.ISSUE_CODES.includes('invalid_link'));
});
