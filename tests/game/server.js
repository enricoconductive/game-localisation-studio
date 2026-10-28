'use strict';
/*
 * Tiny static server for the game tests.
 *
 * Serves the game code from game/ and overlays the content files
 * (strings_manifest.json, story.json, translations/*) from a content directory:
 *   LANTERN_CONTENT_DIR=tests/game/fixtures   (default: the fixtures)
 *   LANTERN_CONTENT_DIR=game                  (the real content)
 * Relative paths are resolved from the repository root.
 *
 * Run by hand: node tests/game/server.js  → http://localhost:8123/
 */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const REPO = path.resolve(__dirname, '..', '..');
const GAME_DIR = path.join(REPO, 'game');
const DEFAULT_CONTENT = path.join(__dirname, 'fixtures');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon'
};

function contentDir() {
  const v = process.env.LANTERN_CONTENT_DIR;
  if (!v) return DEFAULT_CONTENT;
  return path.isAbsolute(v) ? v : path.resolve(REPO, v);
}

function isContentPath(rel) {
  return rel === 'strings_manifest.json' || rel === 'story.json' || rel.startsWith('translations/');
}

function safeJoin(base, rel) {
  const p = path.resolve(base, rel);
  return p === base || p.startsWith(base + path.sep) ? p : null;
}

function createServer() {
  const content = contentDir();
  return http.createServer((req, res) => {
    let rel;
    try {
      rel = decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/^\/+/, '');
    } catch (e) {
      res.writeHead(400); res.end('bad request'); return;
    }
    if (rel === '' || rel.endsWith('/')) rel += 'index.html';
    const candidates = [];
    if (isContentPath(rel)) candidates.push(safeJoin(content, rel));
    candidates.push(safeJoin(GAME_DIR, rel));
    for (const file of candidates) {
      if (file && fs.existsSync(file) && fs.statSync(file).isFile()) {
        res.writeHead(200, {
          'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream',
          'Cache-Control': 'no-store'
        });
        fs.createReadStream(file).pipe(res);
        return;
      }
    }
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('not found');
  });
}

function start(port) {
  return new Promise((resolve) => {
    const server = createServer();
    server.listen(port || 0, '127.0.0.1', () => {
      const { port: p } = server.address();
      resolve({ server, url: `http://127.0.0.1:${p}/`, contentDir: contentDir() });
    });
  });
}

module.exports = { start, contentDir, GAME_DIR, REPO };

if (require.main === module) {
  start(Number(process.env.PORT) || 8123).then(({ url, contentDir: c }) => {
    console.log(`The Lantern Mystery test server: ${url}  (content from ${c})`);
  });
}
