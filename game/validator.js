/*!
 * The Lantern Mystery — translation file validator (Game Localisation Studio v0.3)
 *
 * Implements docs/CONTRACTS.md §5. Pure functions, no DOM access.
 * Works in the browser (window.LanternValidator) and in Node (module.exports).
 *
 * Each issue is {severity, code, string_id, message, fix_hint, message_zh, fix_hint_zh}.
 * `message`/`fix_hint` are plain English (the contract fields); the `_zh` fields are
 * Traditional Chinese versions for the game's 繁體中文 interface. Codes match Python.
 *
 * Note: duplicate JSON keys (`duplicate_id`) cannot be detected here because
 * JSON.parse silently keeps the last value. The Python validator detects them.
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module && module.exports) {
    module.exports = api;
  } else {
    root.LanternValidator = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var FORMAT = 'lantern-mystery-translation';
  var MAX_FILE_BYTES = 100 * 1024;
  var MAX_CHARACTER_NAME = 20;
  var ALLOWED_SOURCES = ['live', 'replay', 'mixed', 'original', 'reference'];
  var FILE_LOCALES = ['en-GB', 'en-US', 'en', 'zh-Hant-HK'];

  var PLACEHOLDER_RE = /\{[a-z_][a-z0-9_]*\}/g;
  var CJK_RE = /[㐀-鿿]/;
  var LONE_SURROGATE_RE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?:^|[^\uD800-\uDBFF])[\uDC00-\uDFFF]/;
  // Control characters (C0 except \n, DEL, C1) — CONTRACTS §5 "control chars (other than \n)".
  var CONTROL_RE = /[\u0000-\u0009\u000B-\u001F\u007F-\u009F]/;
  var NEWLINE_RE = /[\n\r]/;

  /** Every issue code this validator can produce (identical to the Python codes). */
  var ISSUE_CODES = [
    'invalid_json', 'wrong_format', 'bad_structure', 'unknown_id', 'missing_id', 'empty_text',
    'placeholder_missing', 'placeholder_extra', 'placeholder_broken', 'too_long',
    'newline_not_allowed', 'bad_encoding', 'file_too_large',
    'untranslated_cjk', 'whitespace', 'angle_brackets', 'near_limit'
  ];
  /** Python-only code (documented): JSON.parse cannot see duplicate keys. */
  var PYTHON_ONLY_CODES = ['duplicate_id'];

  /** Short generic zh-Hant explanation per code (also used as a fallback by the game). */
  var CODE_TITLES_ZH = {
    invalid_json: '檔案不是有效的 JSON',
    wrong_format: '檔案格式不正確',
    bad_structure: '檔案結構不正確',
    unknown_id: '未知的字串 ID',
    duplicate_id: '字串 ID 重複',
    missing_id: '缺少字串',
    empty_text: '譯文是空白的',
    placeholder_missing: '缺少佔位符',
    placeholder_extra: '多出了佔位符',
    placeholder_broken: '佔位符格式錯誤',
    too_long: '譯文超出字數上限',
    newline_not_allowed: '此處不可換行',
    bad_encoding: '含有損壞或隱藏字元',
    file_too_large: '檔案太大',
    untranslated_cjk: '仍有中文字',
    whitespace: '多餘的空格',
    angle_brackets: '含有 < 或 >',
    near_limit: '接近字數上限'
  };
  var CODE_TITLES_EN = {
    invalid_json: 'Not valid JSON', wrong_format: 'Wrong file format', bad_structure: 'Wrong file structure',
    unknown_id: 'Unknown string id', duplicate_id: 'Duplicate string id', missing_id: 'Missing string',
    empty_text: 'Empty translation', placeholder_missing: 'Missing placeholder', placeholder_extra: 'Extra placeholder',
    placeholder_broken: 'Broken placeholder', too_long: 'Too long', newline_not_allowed: 'Line break not allowed',
    bad_encoding: 'Damaged or invisible character', file_too_large: 'File too large',
    untranslated_cjk: 'Chinese characters left', whitespace: 'Extra spaces', angle_brackets: 'Contains < or >',
    near_limit: 'Close to the length limit'
  };

  var TYPE_LABELS = {
    ui: 'button/interface text',
    narration: 'narration line',
    dialogue: 'dialogue line',
    choice: 'choice button',
    ending: 'ending text'
  };
  var TYPE_LABELS_ZH = {
    ui: '介面／按鈕文字',
    narration: '旁白',
    dialogue: '對白',
    choice: '選項按鈕',
    ending: '結局文字'
  };

  function hasOwn(obj, key) {
    return obj !== null && typeof obj === 'object' && Object.prototype.hasOwnProperty.call(obj, key);
  }

  function isPlainObject(v) {
    return v !== null && typeof v === 'object' && !Array.isArray(v);
  }

  /** Number of Unicode code points (what CONTRACTS calls "characters"). */
  function codePointLength(text) {
    var n = 0;
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i);
      if (c >= 0xD800 && c <= 0xDBFF && i + 1 < text.length) {
        var d = text.charCodeAt(i + 1);
        if (d >= 0xDC00 && d <= 0xDFFF) i++;
      }
      n++;
    }
    return n;
  }

  /** UTF-8 byte length without relying on TextEncoder (lone surrogates count as 3 bytes). */
  function utf8ByteLength(text) {
    var bytes = 0;
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i);
      if (c < 0x80) bytes += 1;
      else if (c < 0x800) bytes += 2;
      else if (c >= 0xD800 && c <= 0xDBFF && i + 1 < text.length &&
               text.charCodeAt(i + 1) >= 0xDC00 && text.charCodeAt(i + 1) <= 0xDFFF) {
        bytes += 4; i++;
      } else bytes += 3;
    }
    return bytes;
  }

  /** All well-formed placeholder tokens, e.g. ["{player_name}", "{coins}"]. */
  function extractPlaceholders(text) {
    if (typeof text !== 'string') return [];
    return text.match(PLACEHOLDER_RE) || [];
  }

  /** Stray braces left over once the well-formed tokens are removed (e.g. "{player name}"). */
  function findBrokenPlaceholders(text) {
    var rest = text.replace(PLACEHOLDER_RE, '\u0000');
    var broken = [];
    var re = /\{[^{}\u0000]{0,30}\}?|\}/g;
    var m;
    while ((m = re.exec(rest)) !== null) broken.push(m[0]);
    return broken;
  }

  /** Manifest placeholder entries may be written "{name}" or "name"; normalise to "{name}". */
  function normalisePlaceholder(p) {
    p = String(p);
    return p.charAt(0) === '{' ? p : '{' + p + '}';
  }

  function countTokens(list) {
    var counts = Object.create(null);
    list.forEach(function (t) { counts[t] = (counts[t] || 0) + 1; });
    return counts;
  }

  function quote(text) {
    var s = String(text).replace(/\s+/g, ' ');
    var chars = Array.from(s);
    if (chars.length > 60) s = chars.slice(0, 57).join('') + '…';
    return '‘' + s + '’';
  }
  function quoteZh(text) {
    var q = quote(text);
    return '「' + q.slice(1, -1) + '」';
  }

  function issue(severity, code, stringId, message, fixHint, messageZh, fixHintZh) {
    return {
      severity: severity, code: code, string_id: stringId === undefined ? null : stringId,
      message: message, fix_hint: fixHint,
      message_zh: messageZh || CODE_TITLES_ZH[code] || message,
      fix_hint_zh: fixHintZh || fixHint
    };
  }

  function critical(code, id, en, enHint, zh, zhHint) { return issue('CRITICAL', code, id, en, enHint, zh, zhHint); }
  function warning(code, id, en, enHint, zh, zhHint) { return issue('WARNING', code, id, en, enHint, zh, zhHint); }

  function getMissionIds(manifest, missionId) {
    var missions = (manifest && Array.isArray(manifest.missions)) ? manifest.missions : [];
    for (var i = 0; i < missions.length; i++) {
      if (missions[i] && missions[i].id === missionId) return (missions[i].string_ids || []).slice();
    }
    var out = [];
    var strings = (manifest && manifest.strings) || {};
    Object.keys(strings).forEach(function (id) {
      if (strings[id] && strings[id].mission === missionId) out.push(id);
    });
    return out;
  }

  /**
   * Validate one translated string against its manifest spec.
   * Returns a list of issues (CRITICAL and WARNING).
   */
  function validateString(id, text, spec) {
    var out = [];
    var label = TYPE_LABELS[spec && spec.type] || 'text';
    var Label = label.charAt(0).toUpperCase() + label.slice(1);
    var zl = TYPE_LABELS_ZH[spec && spec.type] || '文字';

    if (typeof text !== 'string') {
      var kind = text === null ? 'null' : Array.isArray(text) ? 'a list' : typeof text;
      out.push(critical('bad_structure', id,
        'The value for "' + id + '" is not text (it is ' + kind + ').',
        'Write the translation as text in double quotes, e.g. "' + id + '": "Your translation".',
        '「' + id + '」的值不是文字。',
        '請把譯文寫成雙引號內的文字，例如 "' + id + '": "Your translation"。'));
      return out;
    }
    if (text.trim() === '') {
      out.push(critical('empty_text', id,
        'The ' + label + ' "' + id + '" is empty.',
        'Type an English translation for this string, or remove the line so the game keeps the Chinese.',
        zl + '「' + id + '」是空白的。',
        '請為這句輸入英文譯文，或刪除這一行，讓遊戲保留中文原文。'));
      return out;
    }

    // Encoding
    if (LONE_SURROGATE_RE.test(text) || CONTROL_RE.test(text) || text.indexOf('�') !== -1) {
      var surrogate = LONE_SURROGATE_RE.test(text);
      var fffd = text.indexOf('�') !== -1;
      var what = surrogate ? 'a broken (half) emoji or symbol'
        : fffd ? 'the replacement character � (a sign of a damaged file)'
        : 'an invisible control character (such as a tab)';
      var whatZh = surrogate ? '損壞的（只有一半的）表情符號或符號'
        : fffd ? '替代字元 �（代表檔案已損壞）'
        : '看不見的控制字元（例如 Tab）';
      out.push(critical('bad_encoding', id,
        'The ' + label + ' ' + quote(text) + ' contains ' + what + '.',
        'Retype the text in a plain editor and save the file as UTF-8; remove tabs and other invisible characters.',
        zl + quoteZh(text) + '含有' + whatZh + '。',
        '請在純文字編輯器重新輸入，並以 UTF-8 儲存；刪除 Tab 及其他看不見的字元。'));
    }

    // Placeholders
    var expected = (spec && Array.isArray(spec.placeholders) ? spec.placeholders : []).map(normalisePlaceholder);
    var found = extractPlaceholders(text);
    var broken = findBrokenPlaceholders(text);
    broken.forEach(function (b) {
      out.push(critical('placeholder_broken', id,
        'The ' + label + ' ' + quote(text) + ' has a damaged placeholder ' + quote(b) + '.',
        'Placeholders must be copied exactly, in English, lower case, with both curly braces and no spaces' +
        (expected.length ? ' — for this string: ' + expected.join(', ') + '.' : '. This string needs no placeholders, so remove the braces.'),
        zl + quoteZh(text) + '中的佔位符' + quoteZh(b) + '格式錯誤。',
        '佔位符必須原樣照抄：英文小寫、保留兩邊的大括號、不可有空格' +
        (expected.length ? '——這句應該是：' + expected.join('、') + '。' : '。這句不需要佔位符，請刪除大括號。')));
    });
    var expCounts = countTokens(expected);
    var gotCounts = countTokens(found);
    Object.keys(expCounts).forEach(function (t) {
      var diff = expCounts[t] - (gotCounts[t] || 0);
      if (diff > 0) {
        out.push(critical('placeholder_missing', id,
          'The ' + label + ' ' + quote(text) + ' is missing the placeholder ' + t + (diff > 1 ? ' (' + diff + ' times)' : '') + '.',
          'Put ' + t + ' back into the sentence exactly as written — the game replaces it with a real value. Do not translate it.',
          zl + quoteZh(text) + '缺少佔位符 ' + t + (diff > 1 ? '（' + diff + ' 次）' : '') + '。',
          '請把 ' + t + ' 原樣放回句子中——遊戲會把它換成真正的數值。不要翻譯它。'));
      }
    });
    Object.keys(gotCounts).forEach(function (t) {
      var diff = gotCounts[t] - (expCounts[t] || 0);
      if (diff > 0) {
        out.push(critical('placeholder_extra', id,
          'The ' + label + ' ' + quote(text) + ' has an extra placeholder ' + t +
          (expCounts[t] ? ' (it should appear only ' + expCounts[t] + ' time' + (expCounts[t] > 1 ? 's' : '') + ')' : ' that the Chinese does not have') + '.',
          expected.length
            ? 'Use only these placeholders, once each: ' + expected.join(', ') + '.'
            : 'Remove ' + t + ' — this string has no placeholders.',
          zl + quoteZh(text) + '多出了佔位符 ' + t + (expCounts[t] ? '（只應出現 ' + expCounts[t] + ' 次）' : '（中文原文沒有）') + '。',
          expected.length
            ? '只可使用以下佔位符，每個一次：' + expected.join('、') + '。'
            : '請刪除 ' + t + '——這句沒有佔位符。'));
      }
    });

    // Length
    var len = codePointLength(text);
    var maxLen = spec && typeof spec.max_len === 'number' ? spec.max_len : null;
    if (maxLen !== null) {
      if (len > maxLen) {
        var short = spec.type === 'ui' || spec.type === 'choice';
        out.push(critical('too_long', id,
          'The ' + label + ' ' + quote(text) + ' is ' + len + ' characters, but the limit is ' + maxLen + '.',
          'Shorten it to ' + maxLen + ' characters or fewer (spaces and placeholders such as {coins} count as written)' +
          (short ? ' — try a single verb or a short phrase.' : '.'),
          zl + quoteZh(text) + '有 ' + len + ' 個字元，但上限是 ' + maxLen + '。',
          '請縮短至 ' + maxLen + ' 個字元或以下（空格及 {coins} 等佔位符按原樣計算）' + (short ? '——可試用一個動詞或短語。' : '。')));
      } else if (len * 10 >= maxLen * 9) {
        out.push(warning('near_limit', id,
          Label + ' ' + quote(text) + ' is ' + len + ' of ' + maxLen + ' characters — very close to the limit.',
          'This is allowed, but check it fits on screen; a slightly shorter version is safer.',
          zl + quoteZh(text) + '用了 ' + len + '／' + maxLen + ' 個字元，非常接近上限。',
          '這是允許的，但請確認畫面放得下；稍短一點會更安全。'));
      }
    }

    // Newlines
    if (NEWLINE_RE.test(text) && !(spec && spec.allow_newlines === true)) {
      out.push(critical('newline_not_allowed', id,
        'The ' + label + ' ' + quote(text) + ' contains a line break, which is not allowed here.',
        'Remove the line break (\\n) and keep the text on one line.',
        zl + quoteZh(text) + '含有換行，但這裡不可換行。',
        '請刪除換行（\\n），把文字保持在同一行。'));
    }

    // Warnings
    if (CJK_RE.test(text)) {
      out.push(warning('untranslated_cjk', id,
        Label + ' ' + quote(text) + ' still contains Chinese characters.',
        'Check whether this was left untranslated. Chinese inside an English line is fine only if it is deliberate.',
        zl + quoteZh(text) + '仍然含有中文字。',
        '請檢查是否漏譯。英文句子中出現中文，只有在刻意保留時才合適。'));
    }
    if (/^\s|\s$/.test(text) || / {2}/.test(text)) {
      out.push(warning('whitespace', id,
        Label + ' ' + quote(text) + ' has a space (or an invisible space-like character) at the start or end, or a double space.',
        'Remove the extra spaces.',
        zl + quoteZh(text) + '開頭或結尾有空格，或有連續兩個空格。',
        '請刪除多餘的空格。'));
    }
    if (/[<>]/.test(text)) {
      out.push(warning('angle_brackets', id,
        Label + ' ' + quote(text) + ' contains < or >. The game shows them as plain characters, not as formatting.',
        'Remove < and > unless you really want them to appear on screen.',
        zl + quoteZh(text) + '含有 < 或 >。遊戲會把它們當作普通字元顯示，而不是格式。',
        '除非你真的想在畫面上顯示它們，否則請刪除 < 和 >。'));
    }
    return out;
  }

  function validateCharacters(characters, manifest) {
    var out = [];
    if (characters === undefined) return out;
    if (!isPlainObject(characters)) {
      out.push(critical('bad_structure', null,
        'The "characters" section is not a list of names.',
        'Write it as "characters": {"granny_wong": "Granny Wong"}, or delete the section.',
        '「characters」部分不是角色名稱列表。',
        '請寫成 "characters": {"granny_wong": "Granny Wong"}，或刪除這部分。'));
      return out;
    }
    var known = (manifest && manifest.characters) || {};
    Object.keys(characters).forEach(function (key) {
      var name = characters[key];
      if (!hasOwn(known, key)) {
        out.push(critical('bad_structure', null,
          'The "characters" section mentions "' + key + '", which is not a character in this game.',
          'Use only these character keys: ' + Object.keys(known).join(', ') + '.',
          '「characters」提到「' + key + '」，但遊戲中沒有這個角色。',
          '只可使用這些角色代號：' + Object.keys(known).join('、') + '。'));
        return;
      }
      if (typeof name !== 'string' || name.trim() === '') {
        out.push(critical('bad_structure', null,
          'The English name for character "' + key + '" is empty or not text.',
          'Write a name in double quotes, e.g. "' + key + '": "' + (known[key].name_en_default || 'Name') + '".',
          '角色「' + key + '」的英文名稱是空白或不是文字。',
          '請把名稱寫在雙引號內，例如 "' + key + '": "' + (known[key].name_en_default || 'Name') + '"。'));
        return;
      }
      if (codePointLength(name) > MAX_CHARACTER_NAME || NEWLINE_RE.test(name)) {
        out.push(critical('bad_structure', null,
          'The name ' + quote(name) + ' for character "' + key + '" must be one line of at most ' + MAX_CHARACTER_NAME + ' characters.',
          'Shorten the name and remove any line breaks.',
          '角色「' + key + '」的名稱' + quoteZh(name) + '必須是一行，最多 ' + MAX_CHARACTER_NAME + ' 個字元。',
          '請縮短名稱並刪除換行。'));
        return;
      }
      if (LONE_SURROGATE_RE.test(name) || CONTROL_RE.test(name) || name.indexOf('�') !== -1) {
        out.push(critical('bad_encoding', null,
          'The name for character "' + key + '" contains a damaged or invisible character.',
          'Retype the name and save the file as UTF-8.',
          '角色「' + key + '」的名稱含有損壞或看不見的字元。',
          '請重新輸入名稱，並以 UTF-8 儲存檔案。'));
        return;
      }
      if (CJK_RE.test(name)) {
        out.push(warning('untranslated_cjk', null,
          'The name ' + quote(name) + ' for character "' + key + '" still contains Chinese characters.',
          'Check whether the name should be romanised or translated.',
          '角色「' + key + '」的名稱' + quoteZh(name) + '仍然含有中文字。',
          '請考慮名稱應該音譯還是意譯。'));
      }
    });
    return out;
  }

  /** `source` and `locale` of a game file (CONTRACTS §5 resolution (f)); same rules as Python. */
  function validateMetadata(data) {
    var out = [];
    if (!hasOwn(data, 'source')) {
      out.push(warning('bad_structure', null,
        'The file does not say where the translation came from (no "source").',
        'Use the file exported from the notebook; it sets "source" for you.',
        '檔案沒有註明譯文的來源（缺少「source」）。',
        '請使用從筆記本匯出的檔案；它會自動填上「source」。'));
    } else if (ALLOWED_SOURCES.indexOf(data.source) === -1) {
      var src = JSON.stringify(data.source);
      src = src === undefined ? String(data.source) : src.slice(0, 40);
      out.push(critical('bad_structure', null,
        '"source" must be one of ' + ALLOWED_SOURCES.join(', ') + ', not ' + src + '.',
        'Export the file again from the notebook instead of editing "source" by hand.',
        '「source」必須是 ' + ALLOWED_SOURCES.join('、') + ' 其中之一，而不是 ' + src + '。',
        '請從筆記本重新匯出檔案，不要手動修改「source」。'));
    }
    if (typeof data.locale !== 'string' || FILE_LOCALES.indexOf(data.locale) === -1) {
      var missing = !hasOwn(data, 'locale');
      var loc = missing ? '' : (JSON.stringify(data.locale) || String(data.locale)).slice(0, 40);
      out.push(warning('bad_structure', null,
        'The "locale" should be one of ' + FILE_LOCALES.join(', ') + (missing ? ', but it is missing.' : ', not ' + loc + '.'),
        'Use the file exported from the notebook; it sets the locale for you.',
        '「locale」應該是 ' + FILE_LOCALES.join('、') + ' 其中之一' + (missing ? '，但檔案中沒有。' : '，而不是 ' + loc + '。'),
        '請使用從筆記本匯出的檔案；它會自動設定語言。'));
    }
    return out;
  }

  function fileTooLargeIssue(bytes) {
    var kb = Math.ceil(bytes / 1024);
    return critical('file_too_large', null,
      'This file is ' + kb + ' KB, but the limit is 100 KB.',
      'Make sure you picked the English translation file exported from the notebook (game_translation_en.json).',
      '這個檔案有 ' + kb + ' KB，但上限是 100 KB。',
      '請確認你選擇的是從筆記本匯出的英文翻譯檔（game_translation_en.json）。');
  }

  /**
   * Validate a game translation file (text or already-parsed object).
   *
   * options.requireAllForMission  — mission id: every id of that mission must be present
   *                                 (missing → CRITICAL, like the Python export).
   * options.mission               — game import: missing ids of this mission are WARNINGS.
   *                                 If omitted, missing-id warnings cover every mission the
   *                                 file touches (plus the file's own "mission" field).
   *
   * Returns {ok, critical, warnings, issues, data, strings}. `strings` holds only the
   * ids that are known to the manifest, as a plain null-prototype object.
   */
  function validateTranslationFile(textOrObj, manifest, options) {
    options = options || {};
    var issues = [];
    var data = null;
    var mStrings = (manifest && manifest.strings) || {};

    function finish() {
      var crit = issues.filter(function (i) { return i.severity === 'CRITICAL'; });
      var warn = issues.filter(function (i) { return i.severity === 'WARNING'; });
      var strings = Object.create(null);
      if (data && isPlainObject(data.strings)) {
        Object.keys(data.strings).forEach(function (id) {
          if (hasOwn(mStrings, id) && typeof data.strings[id] === 'string') strings[id] = data.strings[id];
        });
      }
      return { ok: crit.length === 0, critical: crit, warnings: warn, issues: issues, data: data, strings: strings };
    }

    // Size and JSON
    if (typeof textOrObj === 'string') {
      var bytes = utf8ByteLength(textOrObj);
      if (bytes > MAX_FILE_BYTES) {
        issues.push(fileTooLargeIssue(bytes));
        return finish();
      }
      var text = textOrObj.charAt(0) === '﻿' ? textOrObj.slice(1) : textOrObj;
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = null;
        var detail = e && e.message ? ' (' + String(e.message).slice(0, 120) + ')' : '';
        issues.push(critical('invalid_json', null,
          'This is not valid JSON, so the game cannot read it' + detail + '.',
          'Export the file again from the notebook instead of editing it by hand. If you pasted it, make sure you copied everything from the first { to the last }.',
          '這不是有效的 JSON，遊戲無法讀取' + detail + '。',
          '請從筆記本重新匯出檔案，不要手動修改。如果是貼上的，請確認由第一個 { 到最後一個 } 全部複製了。'));
        return finish();
      }
    } else {
      data = textOrObj;
      try {
        var size = utf8ByteLength(JSON.stringify(data) || '');
        if (size > MAX_FILE_BYTES) {
          issues.push(fileTooLargeIssue(size));
          return finish();
        }
      } catch (e2) { /* non-serialisable: caught by structure checks below */ }
    }

    // Envelope
    if (!isPlainObject(data)) {
      issues.push(critical('wrong_format', null,
        'This file is not a Lantern Mystery translation file.',
        'Use the file exported from the notebook (it starts with "format": "lantern-mystery-translation").',
        '這不是《燈籠之謎》的翻譯檔。',
        '請使用從筆記本匯出的檔案（開頭是 "format": "lantern-mystery-translation"）。'));
      data = null;
      return finish();
    }
    if (data.format !== FORMAT) {
      var fmt = data.format === undefined ? 'missing' : JSON.stringify(data.format).slice(0, 60);
      issues.push(critical('wrong_format', null,
        'This file is not a Lantern Mystery translation file ("format" is ' + fmt + ').',
        'Use the file exported from the notebook; it must contain "format": "lantern-mystery-translation".',
        '這不是《燈籠之謎》的翻譯檔（"format" 是 ' + (data.format === undefined ? '缺少的' : fmt) + '）。',
        '請使用從筆記本匯出的檔案；檔案必須包含 "format": "lantern-mystery-translation"。'));
    }
    var sv = data.schema_version;
    var major = (typeof sv === 'string' || typeof sv === 'number') ? String(sv).split('.')[0] : null;
    if (major !== '1') {
      var svText = sv === undefined ? '(missing)' : JSON.stringify(sv).slice(0, 30);
      issues.push(critical('wrong_format', null,
        'This file uses schema version ' + svText + ', but the game reads version 1.x.',
        'Export the file again from the current notebook (Game Localisation Studio v0.3).',
        '這個檔案的版本是 ' + (sv === undefined ? '（缺少）' : svText) + '，但遊戲只讀取 1.x 版。',
        '請用目前的筆記本（Game Localisation Studio v0.3）重新匯出。'));
    }
    issues = issues.concat(validateMetadata(data));
    if (!isPlainObject(data.strings)) {
      issues.push(critical('bad_structure', null,
        'The file has no "strings" section, or it is not a list of id → text pairs.',
        'Use the exported file unchanged: "strings": {"intro.ui.start": "Investigate", …}.',
        '檔案沒有「strings」部分，或它不是「ID → 文字」的列表。',
        '請直接使用匯出的檔案："strings": {"intro.ui.start": "Investigate", …}。'));
      return finish();
    }
    issues = issues.concat(validateCharacters(data.characters, manifest));

    // Strings
    var presentByMission = Object.create(null);
    Object.keys(data.strings).forEach(function (id) {
      var value = data.strings[id];
      if (!hasOwn(mStrings, id)) {
        issues.push(critical('unknown_id', id,
          'The string id "' + id + '" does not exist in this game.',
          'Do not rename or invent ids. Check the spelling against the challenge (ids look like intro.line.granny_greeting).',
          '遊戲中沒有字串 ID「' + id + '」。',
          '不要更改或自創 ID。請對照任務檔案檢查拼寫（ID 的樣子像 intro.line.granny_greeting）。'));
        return;
      }
      var spec = mStrings[id] || {};
      issues = issues.concat(validateString(id, value, spec));
      if (spec.mission) presentByMission[spec.mission] = true;
    });

    // Missing ids
    var required = options.requireAllForMission || null;
    var missionsToCheck = [];
    if (required) missionsToCheck = [required];
    else if (options.mission) missionsToCheck = [options.mission];
    else {
      missionsToCheck = Object.keys(presentByMission);
      if (typeof data.mission === 'string' && missionsToCheck.indexOf(data.mission) === -1 &&
          getMissionIds(manifest, data.mission).length) missionsToCheck.push(data.mission);
    }
    missionsToCheck.forEach(function (mission) {
      getMissionIds(manifest, mission).forEach(function (id) {
        if (hasOwn(data.strings, id)) return; // present (empty values are reported as empty_text)
        if (required) {
          issues.push(critical('missing_id', id,
            'The string "' + id + '" is missing — every string of the "' + mission + '" mission must be translated before export.',
            'Translate this string, then export again.',
            '缺少字串「' + id + '」——匯出前，「' + mission + '」任務的每一句都必須翻譯。',
            '請翻譯這一句，然後重新匯出。'));
        } else {
          issues.push(warning('missing_id', id,
            'The string "' + id + '" is not in this file, so the game will show it in Chinese.',
            'Add a translation for this id if you want the whole mission in English.',
            '檔案中沒有字串「' + id + '」，遊戲會以中文原文顯示這句。',
            '如果想整個任務都以英文顯示，請為這個 ID 加上譯文。'));
        }
      });
    });

    return finish();
  }

  return {
    FORMAT: FORMAT,
    MAX_FILE_BYTES: MAX_FILE_BYTES,
    ISSUE_CODES: ISSUE_CODES.slice(),
    PYTHON_ONLY_CODES: PYTHON_ONLY_CODES.slice(),
    CODE_TITLES_EN: CODE_TITLES_EN,
    CODE_TITLES_ZH: CODE_TITLES_ZH,
    PLACEHOLDER_RE_SOURCE: PLACEHOLDER_RE.source,
    extractPlaceholders: extractPlaceholders,
    findBrokenPlaceholders: findBrokenPlaceholders,
    normalisePlaceholder: normalisePlaceholder,
    codePointLength: codePointLength,
    utf8ByteLength: utf8ByteLength,
    validateString: validateString,
    validateCharacters: validateCharacters,
    validateMetadata: validateMetadata,
    validateTranslationFile: validateTranslationFile,
    fileTooLargeIssue: fileTooLargeIssue,
    getMissionIds: getMissionIds,
    hasOwn: hasOwn
  };
});
