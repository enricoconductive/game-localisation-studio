/*!
 * The Lantern Mystery — game runtime (Game Localisation Studio v0.3)
 *
 * Two independent languages:
 *   - interface (chrome) language: English (default) or 繁體中文
 *   - dialogue language: Original Chinese | Reference English | Student's imported English
 *
 * SECURITY: every piece of content or imported text is rendered with
 * textContent / createTextNode only. Placeholders are substituted on plain
 * strings first. This file never uses innerHTML, outerHTML,
 * insertAdjacentHTML, document.write or eval.
 *
 * Persistence (sessionStorage, optional): the interface language and the
 * dialogue-language choice. Imported student files are deliberately NOT stored:
 * after a reload, "student" falls back to Original Chinese and the file must be
 * imported again (simplest and most predictable; nothing student-written lingers).
 */
(function () {
  'use strict';

  var V = window.LanternValidator;
  var CONTENT = {
    manifest: 'strings_manifest.json',
    story: 'story.json',
    zh: 'translations/zh-Hant.json',
    reference: 'translations/en.reference.json'
  };
  var MAX_BYTES = 100 * 1024;
  var TITLE_CARD = '__title_card__'; // virtual node for missions whose start node is not a `title`
  var PLACEHOLDER_RE = /\{([a-z_][a-z0-9_]*)\}/g;
  var KNOWN_PORTRAITS = { granny_wong: 1, kit: 1, riddle_king: 1 };
  var STORE_UI = 'lantern-mystery.ui-lang';
  var STORE_DIALOGUE = 'lantern-mystery.dialogue';

  // Runtime values supplied by the game (CONTRACTS §2).
  var VALUES = { lantern_count: 3, lantern_total: 5, coins: 120 };
  var ITEM = { zh: '紙燈籠', en: 'Paper Lantern' };
  var DEFAULT_NAME = { zh: '偵探', en: 'Detective' };

  // Fixed bilingual chrome — not translated by students.
  var CHROME = {
    skip: { en: 'Skip to the game', zh: '跳到遊戲' },
    subtitle: { en: 'A Mid-Autumn night-market mystery · translation test build', zh: '中秋夜市懸案 · 翻譯測試版' },
    ui_label: { en: 'Interface', zh: '介面語言' },
    dialogue_label: { en: 'Dialogue language', zh: '對白語言' },
    opt_original: { en: 'Original Chinese (原文)', zh: '原文（中文） Original Chinese' },
    opt_reference: { en: 'Reference English (參考譯文)', zh: '參考譯文（英文） Reference English' },
    opt_student: { en: 'Student\'s imported English (學生譯文)', zh: '學生譯文（英文） Student\'s imported English' },
    opt_unavailable: { en: ' — not available', zh: '（未能載入）' },
    opt_import_first: { en: ' — import a file first', zh: '（請先匯入檔案）' },
    name_label: { en: 'Your name', zh: '你的名字' },
    import: { en: 'Import student JSON', zh: '匯入學生 JSON' },
    paste: { en: 'Paste JSON', zh: '貼上 JSON' },
    reset: { en: 'Reset to 中文', zh: '重設為中文' },
    hint: {
      en: 'How to test your translation: export game_translation_en.json from Colab, press “Import student JSON”, then replay a mission. Use “Dialogue language” to compare it with the original or the reference.',
      zh: '測試你的翻譯：從 Colab 匯出 game_translation_en.json，按「匯入學生 JSON」，然後重玩任務。可用「對白語言」與原文或參考譯文比較。'
    },
    paste_title: { en: 'Paste translation JSON', zh: '貼上翻譯 JSON' },
    paste_apply: { en: 'Check and apply', zh: '檢查並套用' },
    cancel: { en: 'Cancel', zh: '取消' },
    close: { en: 'Close', zh: '關閉' },
    choose_mission: { en: 'Choose a mission', zh: '選擇任務' },
    back_missions: { en: '← Missions', zh: '← 任務列表' },
    footer: { en: 'Original game · Game Localisation Studio v0.3 · translations are shown as plain text only', zh: '原創遊戲 · Game Localisation Studio v0.3 · 所有譯文只以純文字顯示' },
    mission_n: { en: 'Mission {n}', zh: '任務 {n}' },
    play: { en: 'Play ▸', zh: '開始 ▸' },
    start: { en: 'Start', zh: '開始' },
    coverage: { en: '{done}/{total} strings in English', zh: '{done}/{total} 句已有英文' },
    not_playable: { en: 'This mission cannot be played yet', zh: '此任務暫時未能遊玩' },
    next: { en: 'Next ▸', zh: '繼續 ▸' },
    continue: { en: 'Continue ▸', zh: '繼續 ▸' },
    what_now: { en: 'What will you do?', zh: '你會怎樣做？' },
    ending: { en: 'Ending {x}', zh: '結局 {x}' },
    play_again: { en: 'Play again', zh: '再玩一次' },
    choose_again: { en: 'Choose mission', zh: '選擇任務' },
    narration: { en: 'Narration', zh: '旁白' },
    still_chinese: { en: '{n} strings in this mission are still in Chinese.', zh: '此任務仍有 {n} 句以中文原文顯示。' },
    still_chinese_one: { en: '1 string in this mission is still in Chinese.', zh: '此任務仍有 1 句以中文原文顯示。' },
    showing_original: { en: 'Showing: Original Chinese', zh: '正在顯示：中文原文' },
    showing_reference: { en: 'Showing: Reference English (course team) — one possible solution', zh: '正在顯示：參考譯文（課程團隊）— 其中一種可行譯法' },
    showing_student: { en: 'Showing: Student\'s imported English', zh: '正在顯示：學生匯入的英文譯文' },
    showing_replay: { en: ' · simulated (Replay Mode)', zh: ' · 模擬（重播模式）' },
    reference_note: {
      en: 'Reference translation — one possible solution prepared by the course team. It is not the only correct translation.',
      zh: '參考譯文——由課程團隊準備的其中一種可行譯法，並非唯一正確答案。'
    },
    hud_label: { en: 'Game interface preview', zh: '遊戲介面預覽' },
    rejected_title: { en: 'This file was not applied', zh: '未能使用這個檔案' },
    rejected_summary: {
      en: 'We found {n} problem(s) that must be fixed. Nothing in the game was changed. Fix them in the notebook and export again.',
      zh: '找到 {n} 個必須修正的問題。遊戲內容沒有改變。請在筆記本修正後重新匯出。'
    },
    applied_title: { en: 'Student translation applied', zh: '已套用學生譯文' },
    applied_summary: { en: 'Applied {n} English strings from “{file}”. Dialogue now shows the student\'s English.', zh: '已從「{file}」套用 {n} 句英文。對白現在顯示學生譯文。' },
    nothing_title: { en: 'Nothing to apply', zh: '沒有可套用的內容' },
    nothing_summary: { en: 'The file is valid but contains no strings for this game.', zh: '檔案格式正確，但沒有包含本遊戲的字串。' },
    warnings_summary: { en: '{n} note(s) worth checking (they did not block the import)', zh: '{n} 個提示（不影響匯入）' },
    reset_title: { en: 'Back to the original Chinese', zh: '已重設為中文原文' },
    reset_summary: { en: 'The student translation was cleared. The reference translation is still available.', zh: '學生譯文已清除。參考譯文仍可選用。' },
    fix: { en: 'How to fix: ', zh: '修正方法：' },
    sev_CRITICAL: { en: 'Must fix', zh: '必須修正' },
    sev_WARNING: { en: 'Note', zh: '提示' },
    general: { en: 'whole file', zh: '整個檔案' },
    pasted: { en: 'pasted text', zh: '貼上的文字' },
    read_error: { en: 'The browser could not read this file.', zh: '瀏覽器未能讀取這個檔案。' },
    read_error_fix: { en: 'Download the file again and retry.', zh: '請重新下載檔案再試。' },
    broken_node: { en: 'The story data is broken: the next scene could not be found.', zh: '故事資料有誤，找不到下一個場景。' }
  };

  var state = {
    manifest: null,
    story: null,
    zh: Object.create(null),
    uiLang: 'en',
    dialogue: 'original',     // 'original' | 'reference' | 'student'
    reference: null,          // {strings: Map, characters: Map, note: string} or null
    overrides: new Map(),     // student layer: id -> English (later imports override earlier ones)
    characters: new Map(),    // student layer: character key -> English name
    imports: [],              // [{label, source, count}]
    view: 'loading',
    mission: null,
    nodeId: null,
    lastReport: null
  };

  var $ = function (id) { return document.getElementById(id); };
  var has = function (o, k) { return Object.prototype.hasOwnProperty.call(o, k); };

  /* ---------- storage (optional) ---------- */
  function store(key, value) {
    try { window.sessionStorage.setItem(key, value); } catch (e) { /* storage blocked: ignore */ }
  }
  function load(key) {
    try { return window.sessionStorage.getItem(key); } catch (e) { return null; }
  }

  /* ---------- small DOM helpers (text only) ---------- */
  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function button(className, text, onClick) {
    var b = el('button', className, text);
    b.type = 'button';
    if (onClick) b.addEventListener('click', onClick);
    return b;
  }

  /* ---------- languages ---------- */
  function chrome(key, vars) {
    var entry = CHROME[key];
    var s = entry ? entry[state.uiLang] : key;
    if (vars) {
      s = s.replace(/\{([a-z]+)\}/g, function (m, k) { return has(vars, k) ? String(vars[k]) : m; });
    }
    return s;
  }

  function referenceAvailable() { return !!(state.reference && state.reference.strings.size); }
  function studentAvailable() { return state.overrides.size > 0; }
  function dialogueEnglish() { return state.dialogue !== 'original'; }

  function activeLayer() {
    if (state.dialogue === 'reference' && state.reference) return state.reference.strings;
    if (state.dialogue === 'student') return state.overrides;
    return null;
  }
  function activeCharacters() {
    if (state.dialogue === 'reference' && state.reference) return state.reference.characters;
    if (state.dialogue === 'student') return state.characters;
    return null;
  }
  function studentReplay() {
    return state.imports.some(function (i) { return i.source === 'replay' || i.source === 'mixed'; });
  }

  function setDialogue(mode, opts) {
    if (mode === 'reference' && !referenceAvailable()) mode = 'original';
    if (mode === 'student' && !studentAvailable()) mode = 'original';
    if (mode !== 'original' && mode !== 'reference' && mode !== 'student') mode = 'original';
    state.dialogue = mode;
    store(STORE_DIALOGUE, mode);
    refresh(opts);
  }

  function setUiLang(lang) {
    state.uiLang = lang === 'zh' ? 'zh' : 'en';
    store(STORE_UI, state.uiLang);
    refresh({ focus: false });
    if (state.lastReport && !$('report').hidden && state.lastReportRaw) {
      showReport(state.lastReport.kind, state.lastReportRaw.report, state.lastReportRaw.label, true);
    }
  }

  /* ---------- strings ---------- */
  function playerName(strLang) {
    var v = $('player-name').value.replace(/\s+/g, ' ').trim();
    return v || DEFAULT_NAME[strLang];
  }

  /** Replace {placeholders} on a plain string. Unknown tokens stay visible. */
  function fillPlaceholders(text, strLang) {
    return String(text).replace(PLACEHOLDER_RE, function (match, name) {
      if (name === 'player_name') return playerName(strLang);
      if (name === 'item_name') return ITEM[strLang];
      if (has(VALUES, name)) return String(VALUES[name]);
      return match;
    });
  }

  /** {text, lang} for a string id in the current dialogue language, after placeholders. */
  function resolve(id) {
    var layer = activeLayer();
    if (layer && layer.has(id)) return { text: fillPlaceholders(layer.get(id), 'en'), lang: 'en', english: true };
    if (has(state.zh, id)) return { text: fillPlaceholders(state.zh[id], 'zh'), lang: 'zh-Hant', english: false };
    return { text: '[' + id + ']', lang: 'en', english: false, missing: true };
  }

  function setString(node, id) {
    var r = resolve(id);
    node.textContent = r.text;
    node.setAttribute('lang', r.lang);
    node.setAttribute('data-string-id', id);
    return r;
  }

  function manifestString(id) { return has(state.manifest.strings, id) ? state.manifest.strings[id] : null; }

  function character(key) {
    var c = state.manifest.characters || {};
    return key && has(c, key) ? c[key] : null;
  }

  /** Character names follow the dialogue language. */
  function speakerName(key) {
    var c = character(key);
    if (!c) return key || '';
    if (!dialogueEnglish()) return c.name_zh || key;
    var layer = activeCharacters();
    return (layer && layer.get(key)) || c.name_en_default || key;
  }

  function portraitSrc(key) {
    if (/^[a-z_][a-z0-9_]*$/.test(key || '') && KNOWN_PORTRAITS[key]) return 'assets/' + key + '.svg';
    return 'assets/portrait_default.svg';
  }

  function safeColour(c) { return /^#[0-9a-fA-F]{3,8}$/.test(c || '') ? c : '#c0392b'; }

  function missionMeta(id) {
    var list = state.manifest.missions || [];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return { meta: list[i], index: i };
    return { meta: { id: id, title_zh: id, title_en: id, string_ids: [] }, index: -1 };
  }

  /** Mission names are chrome: they follow the interface language. */
  function missionTitle(meta) { return state.uiLang === 'en' ? (meta.title_en || meta.id) : (meta.title_zh || meta.id); }

  function stillChinese(missionId) {
    var layer = activeLayer();
    if (!layer) return 0;
    var n = 0;
    (missionMeta(missionId).meta.string_ids || []).forEach(function (id) { if (!layer.has(id)) n++; });
    return n;
  }

  function showingText() {
    if (state.dialogue === 'reference') return chrome('showing_reference');
    if (state.dialogue === 'student') return chrome('showing_student') + (studentReplay() ? chrome('showing_replay') : '');
    return chrome('showing_original');
  }

  /* ---------- chrome ---------- */
  function applyChrome() {
    var U = state.uiLang;
    document.documentElement.setAttribute('lang', U === 'en' ? 'en' : 'zh-Hant-HK');
    document.querySelectorAll('[data-chrome]').forEach(function (n) {
      n.textContent = chrome(n.getAttribute('data-chrome'));
    });
    $('ui-en').setAttribute('aria-pressed', String(U === 'en'));
    $('ui-zh').setAttribute('aria-pressed', String(U === 'zh'));
    $('player-name').setAttribute('placeholder', DEFAULT_NAME[dialogueEnglish() ? 'en' : 'zh']);

    var sel = $('dialogue-select');
    var opts = sel.options;
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i];
      if (o.value === 'original') { o.textContent = chrome('opt_original'); o.disabled = false; }
      if (o.value === 'reference') {
        o.disabled = !referenceAvailable();
        o.textContent = chrome('opt_reference') + (o.disabled ? chrome('opt_unavailable') : '');
      }
      if (o.value === 'student') {
        o.disabled = !studentAvailable();
        o.textContent = chrome('opt_student') + (o.disabled ? chrome('opt_import_first') : '');
      }
    }
    sel.value = state.dialogue;

    var text = showingText();
    var replay = state.dialogue === 'student' && studentReplay();
    ['showing-badge', 'scene-showing'].forEach(function (id) {
      var b = $(id);
      b.textContent = text;
      b.setAttribute('data-mode', state.dialogue);
      b.classList.toggle('is-replay', replay);
    });
    var note = $('reference-note');
    if (state.dialogue === 'reference') {
      note.textContent = chrome('reference_note');
      note.hidden = false;
    } else {
      note.hidden = true;
      note.textContent = '';
    }
  }

  function refresh(opts) {
    if (!state.manifest) { applyChromeSafe(); return; }
    applyChrome();
    if (state.view === 'missions') renderMissions();
    else if (state.view === 'scene') renderScene(opts || { focus: false });
  }

  /** Chrome before content has loaded (e.g. the load-error screen). */
  function applyChromeSafe() {
    document.documentElement.setAttribute('lang', state.uiLang === 'en' ? 'en' : 'zh-Hant-HK');
    document.querySelectorAll('[data-chrome]').forEach(function (n) { n.textContent = chrome(n.getAttribute('data-chrome')); });
    $('ui-en').setAttribute('aria-pressed', String(state.uiLang === 'en'));
    $('ui-zh').setAttribute('aria-pressed', String(state.uiLang === 'zh'));
  }

  /* ---------- views ---------- */
  function showView(name) {
    state.view = name;
    $('loading').hidden = true;
    $('view-missions').hidden = name !== 'missions';
    $('view-scene').hidden = name !== 'scene';
  }

  function renderMissions(focus) {
    showView('missions');
    var list = $('mission-list');
    clear(list);
    var layer = activeLayer();
    (state.manifest.missions || []).forEach(function (m, i) {
      var playable = !!(state.story.missions && state.story.missions[m.id]);
      var li = el('li', 'mission-item');
      var b = button('mission-card', null, function () { startMission(m.id); });
      b.setAttribute('data-mission', m.id);
      b.disabled = !playable;
      var lantern = el('img', 'mission-lantern');
      lantern.src = 'assets/logo.svg'; lantern.alt = ''; lantern.width = 36; lantern.height = 36;
      b.appendChild(lantern);
      var txt = el('span', 'mission-text');
      txt.appendChild(el('span', 'mission-num', chrome('mission_n', { n: i + 1 })));
      var title = el('span', 'mission-title', missionTitle(m));
      title.setAttribute('lang', state.uiLang === 'en' ? 'en' : 'zh-Hant');
      txt.appendChild(title);
      var other = el('span', 'mission-alt', state.uiLang === 'en' ? m.title_zh : m.title_en);
      other.setAttribute('lang', state.uiLang === 'en' ? 'zh-Hant' : 'en');
      txt.appendChild(other);
      if (layer) {
        var total = (m.string_ids || []).length;
        txt.appendChild(el('span', 'mission-cov', chrome('coverage', { done: total - stillChinese(m.id), total: total })));
      }
      if (!playable) txt.appendChild(el('span', 'mission-cov', chrome('not_playable')));
      b.appendChild(txt);
      b.appendChild(el('span', 'mission-play', chrome('play')));
      li.appendChild(b);
      list.appendChild(li);
    });
    if (focus) {
      var first = list.querySelector('button:not([disabled])');
      if (first) first.focus();
    }
  }

  function startMission(id) {
    var graph = state.story.missions[id];
    var first = graph && graph.nodes && has(graph.nodes, graph.start) ? graph.nodes[graph.start] : null;
    state.mission = id;
    state.nodeId = first && first.kind !== 'title' ? TITLE_CARD : graph.start;
    showView('scene');
    renderScene({ focus: true });
  }

  function go(nextId) {
    state.nodeId = nextId;
    renderScene({ focus: true });
  }

  function announce(text) {
    var live = $('dialogue-live');
    live.textContent = '';
    window.setTimeout(function () { live.textContent = text; }, 30);
  }

  function currentNode() {
    var graph = state.story && state.mission ? state.story.missions[state.mission] : null;
    if (!graph) return null;
    if (state.nodeId === TITLE_CARD) return { kind: 'title', text: null, next: graph.start };
    return graph.nodes && has(graph.nodes, state.nodeId) ? graph.nodes[state.nodeId] : null;
  }

  function renderScene(opts) {
    opts = opts || {};
    showView('scene');
    var meta = missionMeta(state.mission);
    $('scene-mission-title').textContent = chrome('mission_n', { n: meta.index + 1 }) + ' · ' + missionTitle(meta.meta);

    var notice = $('chinese-notice');
    var remaining = stillChinese(state.mission);
    if (remaining > 0) {
      notice.textContent = remaining === 1 ? chrome('still_chinese_one') : chrome('still_chinese', { n: remaining });
      notice.hidden = false;
    } else {
      notice.hidden = true;
      notice.textContent = '';
    }

    var body = $('scene-body');
    clear(body);
    var node = currentNode();
    var primary = null;
    var spoken = '';
    body.setAttribute('data-kind', node ? node.kind : 'error');

    if (!node) {
      body.appendChild(el('p', 'scene-error', chrome('broken_node')));
      primary = button('btn btn-gold', chrome('choose_again'), function () { renderMissions(true); });
      body.appendChild(primary);
    } else if (node.kind === 'title') {
      var card = el('div', 'title-card');
      var logo = el('img', 'title-logo'); logo.src = 'assets/logo.svg'; logo.alt = ''; logo.width = 96; logo.height = 96;
      card.appendChild(logo);
      card.appendChild(el('p', 'title-num', chrome('mission_n', { n: meta.index + 1 })));
      card.appendChild(el('h3', 'title-name', missionTitle(meta.meta)));
      primary = button('btn btn-start', null, function () { go(node.next); });
      if (node.text) setString(primary, node.text);
      else primary.textContent = chrome('start');
      primary.id = 'btn-start';
      card.appendChild(primary);
      body.appendChild(card);
      spoken = missionTitle(meta.meta);
    } else if (node.kind === 'line') {
      var spec = manifestString(node.text) || {};
      var speaker = spec.speaker || null;
      var wrap = el('div', 'dialogue-wrap' + (speaker ? '' : ' is-narration'));
      if (speaker) {
        var fig = el('figure', 'portrait');
        var img = el('img'); img.src = portraitSrc(speaker); img.alt = ''; img.width = 120; img.height = 120;
        fig.appendChild(img);
        wrap.appendChild(fig);
        wrap.style.setProperty('--speaker', safeColour((character(speaker) || {}).colour));
      }
      var box = el('div', 'dialogue-box');
      var name = el('p', 'speaker-name', speaker ? speakerName(speaker) : chrome('narration'));
      name.id = 'speaker-name';
      box.appendChild(name);
      var p = el('p', 'dialogue-text');
      p.id = 'dialogue-text';
      var r = setString(p, node.text);
      box.appendChild(p);
      primary = button('btn btn-next', chrome('next'), function () { go(node.next); });
      primary.id = 'btn-next';
      box.appendChild(primary);
      wrap.appendChild(box);
      body.appendChild(wrap);
      spoken = (speaker ? speakerName(speaker) + ': ' : '') + r.text;
    } else if (node.kind === 'choice') {
      var cw = el('div', 'choice-wrap');
      cw.appendChild(el('p', 'choice-prompt', chrome('what_now')));
      var optsBox = el('div', 'choice-options');
      (node.options || []).forEach(function (opt, i) {
        var b = button('btn btn-choice', null, function () { go(opt.next); });
        b.setAttribute('data-option', String(i));
        setString(b, opt.text);
        optsBox.appendChild(b);
        if (!primary) primary = b;
      });
      cw.appendChild(optsBox);
      body.appendChild(cw);
      spoken = chrome('what_now');
    } else if (node.kind === 'hud') {
      body.appendChild(renderHud(node));
      primary = button('btn btn-next btn-hud-next', chrome('continue'), function () { go(node.next); });
      primary.id = 'btn-next';
      body.appendChild(primary);
      spoken = chrome('hud_label');
    } else if (node.kind === 'ending') {
      var ec = el('div', 'ending-card');
      var letter = String(node.ending || '?').slice(0, 3);
      var badge = el('p', 'ending-badge ending-' + (letter === 'A' ? 'a' : 'b'), chrome('ending', { x: letter }));
      badge.id = 'ending-badge';
      badge.setAttribute('data-ending', letter);
      ec.appendChild(badge);
      var et = el('p', 'ending-text');
      et.id = 'ending-text';
      var er = setString(et, node.text);
      ec.appendChild(et);
      var row = el('div', 'row');
      primary = button('btn btn-gold', chrome('play_again'), function () { startMission(state.mission); });
      primary.id = 'btn-again';
      row.appendChild(primary);
      var back = button('btn', chrome('choose_again'), function () { renderMissions(true); });
      back.id = 'btn-choose';
      row.appendChild(back);
      ec.appendChild(row);
      body.appendChild(ec);
      spoken = chrome('ending', { x: letter }) + '. ' + er.text;
    } else {
      body.appendChild(el('p', 'scene-error', chrome('broken_node')));
    }

    if (opts.focus !== false) announce(spoken);
    if (opts.focus && primary) primary.focus();
  }

  /** Which part of the mock interface a hud string belongs to (heuristic on the id). */
  function hudSlot(id, node) {
    if (node.slots && typeof node.slots === 'object' && has(node.slots, id)) {
      var s = node.slots[id];
      if (s === 'status' || s === 'inventory' || s === 'toast' || s === 'button') return s;
    }
    var name = String(id).split('.').pop();
    if (/(^|_)(btn|button)(_|$)/.test(name)) return 'button';
    if (/toast|notice|popup|alert|message|msg|reward|found|got|obtain/.test(name)) return 'toast';
    if (/inventory|bag|backpack|item|pocket/.test(name)) return 'inventory';
    if (/status|lantern|coin|gold|money|score|count|level|time|hp|bar|title|label/.test(name)) return 'status';
    if (/^(use|equip|open|close|confirm|cancel|back|menu|settings|sell|buy|save|load|quit|start|continue|retry|ok|map|shop)/.test(name)) return 'button';
    return 'status';
  }

  function renderHud(node) {
    var hud = el('div', 'hud');
    hud.setAttribute('role', 'group');
    hud.setAttribute('aria-label', chrome('hud_label'));
    var status = el('div', 'hud-status');
    var main = el('div', 'hud-main');
    var inv = el('div', 'hud-inventory');
    var slot = el('div', 'hud-slot');
    var icon = el('img', 'hud-slot-icon'); icon.src = 'assets/logo.svg'; icon.alt = ''; icon.width = 40; icon.height = 40;
    slot.appendChild(icon);
    var itemLang = dialogueEnglish() ? 'en' : 'zh';
    var itemName = el('span', 'hud-item-name', ITEM[itemLang]);
    itemName.setAttribute('lang', itemLang === 'en' ? 'en' : 'zh-Hant');
    slot.appendChild(itemName);
    var buttons = el('div', 'hud-buttons');
    var toasts = el('div', 'hud-toasts');
    var invLabels = el('div', 'hud-inv-labels');

    (node.texts || []).forEach(function (id) {
      var where = hudSlot(id, node);
      var n;
      if (where === 'button') {
        n = button('hud-btn');
        n.addEventListener('click', function () { n.classList.remove('pulse'); void n.offsetWidth; n.classList.add('pulse'); });
        buttons.appendChild(n);
      } else if (where === 'toast') {
        n = el('p', 'hud-toast');
        n.setAttribute('role', 'status');
        toasts.appendChild(n);
      } else if (where === 'inventory') {
        n = el('p', 'hud-inv-label');
        invLabels.appendChild(n);
      } else {
        n = el('p', 'hud-stat');
        status.appendChild(n);
      }
      n.classList.add('hud-text');
      n.setAttribute('data-slot', where);
      setString(n, id);
    });

    inv.appendChild(invLabels);
    inv.appendChild(slot);
    main.appendChild(inv);
    if (buttons.firstChild) main.appendChild(buttons);
    if (status.firstChild) hud.appendChild(status);
    hud.appendChild(main);
    if (toasts.firstChild) hud.appendChild(toasts);
    return hud;
  }

  /* ---------- import / report ---------- */
  function showReport(kind, report, label, keepFocus) {
    var panel = $('report');
    panel.hidden = false;
    panel.className = 'panel report report-' + kind;
    $('report-title').textContent = chrome(kind + '_title');
    var summary = '';
    if (kind === 'rejected') summary = chrome('rejected_summary', { n: report.critical.length });
    else if (kind === 'applied') summary = chrome('applied_summary', { n: Object.keys(report.strings).length, file: label });
    else if (kind === 'nothing') summary = chrome('nothing_summary');
    else if (kind === 'reset') summary = chrome('reset_summary');
    $('report-summary').textContent = summary;

    var critList = $('report-critical');
    clear(critList);
    var warnBox = $('report-warnings-box');
    var warnList = $('report-warnings');
    clear(warnList);
    warnBox.hidden = true;
    if (report) {
      report.critical.forEach(function (i) { critList.appendChild(issueItem(i)); });
      if (kind !== 'rejected' && report.warnings.length) {
        report.warnings.forEach(function (i) { warnList.appendChild(issueItem(i)); });
        $('report-warnings-summary').textContent = chrome('warnings_summary', { n: report.warnings.length });
        warnBox.hidden = false;
      }
    }
    state.lastReportRaw = { report: report, label: label };
    state.lastReport = report ? {
      kind: kind,
      critical: report.critical.map(function (i) { return { code: i.code, string_id: i.string_id }; }),
      warnings: report.warnings.map(function (i) { return { code: i.code, string_id: i.string_id }; })
    } : { kind: kind, critical: [], warnings: [] };
    if (kind === 'rejected' && !keepFocus) panel.focus();
  }

  function issueItem(i) {
    var zh = state.uiLang === 'zh';
    var li = el('li', 'issue issue-' + i.severity.toLowerCase());
    li.setAttribute('data-code', i.code);
    var head = el('p', 'issue-head');
    var title = (zh ? V.CODE_TITLES_ZH : V.CODE_TITLES_EN)[i.code] || i.code;
    head.appendChild(el('span', 'issue-code', chrome('sev_' + i.severity) + ' · ' + title + ' (' + i.code + ')'));
    head.appendChild(el('span', 'issue-id', i.string_id || chrome('general')));
    li.appendChild(head);
    var msg = el('p', 'issue-msg', zh ? (i.message_zh || i.message) : i.message);
    msg.setAttribute('lang', zh ? 'zh-Hant' : 'en');
    li.appendChild(msg);
    var fix = el('p', 'issue-fix');
    fix.appendChild(el('strong', null, chrome('fix')));
    fix.appendChild(document.createTextNode(zh ? (i.fix_hint_zh || i.fix_hint) : i.fix_hint));
    fix.setAttribute('lang', zh ? 'zh-Hant' : 'en');
    li.appendChild(fix);
    return li;
  }

  function singleIssueReport(issue) {
    return { ok: false, critical: [issue], warnings: [], issues: [issue], strings: Object.create(null), data: null };
  }

  function importText(text, label) {
    var report = V.validateTranslationFile(text, state.manifest);
    if (!report.ok) { showReport('rejected', report, label); return false; }
    var ids = Object.keys(report.strings);
    if (!ids.length) { showReport('nothing', report, label); return false; }
    ids.forEach(function (id) { state.overrides.set(id, report.strings[id]); });
    var chars = report.data && report.data.characters;
    if (chars && typeof chars === 'object') {
      Object.keys(chars).forEach(function (k) {
        if (character(k) && typeof chars[k] === 'string') state.characters.set(k, chars[k].trim());
      });
    }
    state.imports.push({ label: label, source: report.data.source, count: ids.length });
    setDialogue('student', { focus: false });
    showReport('applied', report, label);
    return true;
  }

  function handleFile(file) {
    if (!file) return;
    if (file.size > MAX_BYTES) { showReport('rejected', singleIssueReport(V.fileTooLargeIssue(file.size)), file.name); return; }
    var reader = new FileReader();
    reader.onload = function () { importText(String(reader.result), file.name); };
    reader.onerror = function () {
      showReport('rejected', singleIssueReport({
        severity: 'CRITICAL', code: 'invalid_json', string_id: null,
        message: CHROME.read_error.en, fix_hint: CHROME.read_error_fix.en,
        message_zh: CHROME.read_error.zh, fix_hint_zh: CHROME.read_error_fix.zh
      }), file.name);
    };
    reader.readAsText(file, 'utf-8');
  }

  function resetToChinese() {
    state.overrides.clear();
    state.characters.clear();
    state.imports = [];
    setDialogue('original', { focus: false });
    showReport('reset', null);
  }

  /* ---------- wiring ---------- */
  function wire() {
    $('ui-en').addEventListener('click', function () { setUiLang('en'); });
    $('ui-zh').addEventListener('click', function () { setUiLang('zh'); });
    $('dialogue-select').addEventListener('change', function (e) { setDialogue(e.target.value, { focus: false }); });
    $('btn-import').addEventListener('click', function () { $('file-input').click(); });
    $('file-input').addEventListener('change', function (e) {
      var f = e.target.files && e.target.files[0];
      handleFile(f);
      e.target.value = '';
    });
    $('btn-paste').addEventListener('click', function () {
      var panel = $('paste-panel');
      panel.hidden = !panel.hidden;
      $('btn-paste').setAttribute('aria-expanded', String(!panel.hidden));
      if (!panel.hidden) $('paste-text').focus();
    });
    $('btn-paste-cancel').addEventListener('click', function () {
      $('paste-panel').hidden = true;
      $('btn-paste').setAttribute('aria-expanded', 'false');
      $('btn-paste').focus();
    });
    $('btn-paste-apply').addEventListener('click', function () {
      var text = $('paste-text').value;
      var bytes = V.utf8ByteLength(text);
      if (bytes > MAX_BYTES) { showReport('rejected', singleIssueReport(V.fileTooLargeIssue(bytes)), chrome('pasted')); return; }
      if (importText(text, chrome('pasted'))) {
        $('paste-panel').hidden = true;
        $('btn-paste').setAttribute('aria-expanded', 'false');
      }
    });
    $('btn-reset').addEventListener('click', resetToChinese);
    $('btn-report-close').addEventListener('click', function () { $('report').hidden = true; });
    $('btn-back').addEventListener('click', function () { renderMissions(true); });
    $('player-name').addEventListener('input', function () {
      if (state.view === 'scene') renderScene({ focus: false });
    });
  }

  function exposeDebugHook() {
    var hook = {};
    Object.defineProperties(hook, {
      ready: { get: function () { return state.view !== 'loading' && state.view !== 'error'; } },
      view: { get: function () { return state.view; } },
      uiLang: { get: function () { return state.uiLang; } },
      dialogue: { get: function () { return state.dialogue; } },
      lang: { get: function () { return dialogueEnglish() ? 'en' : 'zh'; } },
      mission: { get: function () { return state.mission; } },
      nodeId: { get: function () { return state.nodeId; } },
      nodeKind: { get: function () { var n = currentNode(); return state.view === 'scene' && n ? n.kind : null; } },
      overrideCount: { get: function () { return state.overrides.size; } },
      referenceAvailable: { get: referenceAvailable },
      studentAvailable: { get: studentAvailable },
      replay: { get: function () { return state.dialogue === 'student' && studentReplay(); } },
      showing: { get: function () { return $('showing-badge').textContent; } },
      imports: { get: function () { return state.imports.map(function (i) { return { label: i.label, source: i.source, count: i.count }; }); } },
      lastReport: { get: function () { return state.lastReport ? JSON.parse(JSON.stringify(state.lastReport)) : null; } },
      values: {
        get: function () {
          return { lantern_count: VALUES.lantern_count, lantern_total: VALUES.lantern_total, coins: VALUES.coins,
                   item_name_zh: ITEM.zh, item_name_en: ITEM.en,
                   player_name_zh: playerName('zh'), player_name_en: playerName('en') };
        }
      },
      stillChinese: { get: function () { return state.mission ? stillChinese(state.mission) : null; } }
    });
    hook.text = function (id) { return resolve(String(id)).text; };
    window.__lantern = Object.freeze(hook);
  }

  function showLoadError(detail) {
    state.view = 'error';
    $('loading').hidden = true;
    $('load-error').hidden = false;
    $('load-error-detail').textContent = detail;
  }

  function fetchJson(path) {
    return fetch(path, { cache: 'no-cache', credentials: 'same-origin' }).then(function (res) {
      if (!res.ok) throw new Error(path + ' (HTTP ' + res.status + ')');
      return res.json().catch(function () { throw new Error(path + ' is not valid JSON'); });
    }, function () {
      throw new Error(path + ' could not be fetched');
    });
  }

  function loadReference(obj) {
    if (!obj) return null;
    var report = V.validateTranslationFile(obj, state.manifest);
    if (!report.ok) return null;
    var strings = new Map();
    Object.keys(report.strings).forEach(function (id) { strings.set(id, report.strings[id]); });
    var characters = new Map();
    if (obj.characters && typeof obj.characters === 'object') {
      Object.keys(obj.characters).forEach(function (k) {
        if (character(k) && typeof obj.characters[k] === 'string') characters.set(k, obj.characters[k].trim());
      });
    }
    return { strings: strings, characters: characters, note: typeof obj.note === 'string' ? obj.note : '' };
  }

  function start() {
    var savedUi = load(STORE_UI);
    state.uiLang = savedUi === 'zh' ? 'zh' : 'en';
    exposeDebugHook();
    wire();
    applyChromeSafe();
    if (location.protocol === 'file:') {
      showLoadError('You opened the game directly from a file on your computer (file://). Browsers block the game from reading its story files this way.');
      return;
    }
    var optionalReference = fetchJson(CONTENT.reference).catch(function () { return null; });
    Promise.all([fetchJson(CONTENT.manifest), fetchJson(CONTENT.story), fetchJson(CONTENT.zh), optionalReference]).then(function (res) {
      var manifest = res[0], story = res[1], zh = res[2];
      if (!manifest || typeof manifest.strings !== 'object' || !Array.isArray(manifest.missions)) throw new Error(CONTENT.manifest + ' does not look like a strings manifest');
      if (!story || typeof story.missions !== 'object') throw new Error(CONTENT.story + ' does not look like a story graph');
      if (!zh || typeof zh.strings !== 'object') throw new Error(CONTENT.zh + ' does not look like a translation file');
      state.manifest = manifest;
      state.story = story;
      Object.keys(zh.strings).forEach(function (id) {
        if (typeof zh.strings[id] === 'string') state.zh[id] = zh.strings[id];
      });
      state.reference = loadReference(res[3]);
      // Restore the dialogue choice; "student" falls back to Original Chinese because imports are not stored.
      var savedDialogue = load(STORE_DIALOGUE);
      state.dialogue = savedDialogue === 'reference' && referenceAvailable() ? 'reference' : 'original';
      store(STORE_DIALOGUE, state.dialogue);
      applyChrome();
      renderMissions(false);
    }).catch(function (err) {
      showLoadError('Problem: ' + (err && err.message ? err.message : String(err)) + '.');
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
