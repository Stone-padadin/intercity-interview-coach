'use strict';
// Static prototype only. Records remain in the browser, not on this server.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const files = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/lab.css', ['lab.css', 'text/css; charset=utf-8']],
  ['/lab-store.js', ['lab-store.js', 'text/javascript; charset=utf-8']],
  ['/lab.js', ['lab.js', 'text/javascript; charset=utf-8']]
]);
function createServer() {
  return http.createServer((req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (!['GET', 'HEAD'].includes(req.method)) {
      res.writeHead(405, { Allow: 'GET, HEAD' }); return res.end();
    }
    const pathname = new URL(req.url, 'http://127.0.0.1').pathname;
    if (pathname === '/api/health') {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      return res.end(req.method === 'HEAD' ? undefined : JSON.stringify({ ok: true, service: 'lab-assistant-prototype', storage: 'browser-local', voice: false, video: false, ai: false }));
    }
    const file = files.get(pathname);
    if (!file) { res.writeHead(404); return res.end('Not found'); }
    fs.readFile(path.join(__dirname, file[0]), (error, data) => {
      if (error) { res.writeHead(500); return res.end('Unable to read page'); }
      res.writeHead(200, { 'Content-Type': file[1], 'Cache-Control': 'no-cache' });
      res.end(req.method === 'HEAD' ? undefined : data);
    });
  });
}
if (require.main === module) {
  const port = Number(process.env.PORT || 8765);
  const host = process.env.HOST || '127.0.0.1';
  createServer().listen(port, host, () => console.log(`AI lab assistant prototype: http://${host}:${port}`));
}
module.exports = { createServer };
