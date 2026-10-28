'use strict';
// Static security checks on the game code (no browser needed).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const GAME = path.join(__dirname, '..', '..', 'game');
const read = (f) => fs.readFileSync(path.join(GAME, f), 'utf8');
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

test('no HTML-injection sinks or eval in game code', () => {
  for (const f of ['game.js', 'validator.js']) {
    const code = stripComments(read(f));
    for (const sink of ['innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function', 'setTimeout("', "setTimeout('", 'srcdoc', 'createContextualFragment', 'DOMParser']) {
      assert.ok(!code.includes(sink), `${f} must not use ${sink}`);
    }
  }
});

test('index.html has the CSP meta tag, no inline scripts and no external resources', () => {
  const html = read('index.html');
  assert.match(html, /<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'">/);
  const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 2);
  for (const [, attrs, body] of scripts) {
    assert.match(attrs, /src="(validator|game)\.js"/);
    assert.equal(body.trim(), '');
  }
  for (const f of ['index.html', 'style.css', 'game.js']) {
    assert.ok(!/https?:\/\//.test(stripComments(read(f)).replace(/http:\/\/localhost:8000\/game\//, '')), `${f} must not load external URLs`);
  }
  assert.ok(!/\son[a-z]+=/i.test(html), 'no inline event handlers');
});

test('SVG assets are small and contain no scripts or external references', () => {
  const dir = path.join(GAME, 'assets');
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.svg'))) {
    const svg = fs.readFileSync(path.join(dir, f), 'utf8');
    assert.ok(svg.length < 8000, `${f} is small`);
    assert.ok(!/<script|on[a-z]+=|href="http/i.test(svg), `${f} is inert`);
  }
});
