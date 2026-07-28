#!/usr/bin/env node
// Run frontend dev server AND backend dev server concurrently.
//
// Streams from both processes are merged into this terminal with a
// [frontend ] / [backend  ] prefix on each line, so the logs stay
// readable. CTRL+C propagates to both children ; they cascade-kill if
// the other one dies first.
//
// This script adds no new dependency: it uses only node:child_process
// and a hand-rolled line buffer / prefix injector. The dev server is
// bound to 0.0.0.0 (HERMES_BACKEND_PORT defaults to 8000, PORT
// defaults to 3000 for the frontend per the Freebuff preview convention).

import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const PORT = process.env.PORT || process.env.HERMES_FRONTEND_PORT || '3000';
process.env.PORT = PORT; // next dev lit PORT en priorité
const BACKEND_PORT = process.env.HERMES_BACKEND_PORT || process.env.BACKEND_PORT || '8000';

function pad(s, n) { return s.length >= n ? s : s + ' '.repeat(n - s.length); }
function tagFor(name) { return `[${pad(name, 9)}]`; }

// On Windows, pnpm ships as pnpm.cmd → Node's spawn needs shell:true to
// resolve the .cmd shim. On POSIX the binary is found directly.
const USE_SHELL = process.platform === 'win32';

function streamWithPrefix(name, child) {
  const tag = tagFor(name);
  const handle = (stream, out) => {
    if (!stream) return;
    let buf = '';
    stream.setEncoding('utf8');
    stream.on('data', (chunk) => {
      buf += chunk;
      let idx;
      while ((idx = buf.indexOf('\n')) !== -1) {
        out.write(`${tag} ${buf.slice(0, idx)}\n`);
        buf = buf.slice(idx + 1);
      }
    });
    stream.on('end', () => { if (buf.length) out.write(`${tag} ${buf}\n`); });
    stream.on('error', () => {}); // already closed → swallow
  };
  handle(child.stdout, process.stdout);
  handle(child.stderr, process.stderr);
}

const children = [];
let ctrlc = 0;

function killAll(signal = 'SIGTERM') {
  for (const c of children) if (!c.killed) c.kill(signal);
}

process.on('SIGINT', () => {
  killAll('SIGINT');
  ctrlc += 1;
  if (ctrlc >= 2) {
    // Second Ctrl+C : on force.
    process.exit(130);
  }
  setTimeout(() => process.exit(130), 1500).unref();
});
process.on('SIGTERM', () => { killAll('SIGTERM'); process.exit(143); });

function spawnTagged(name, command, args, opts = {}) {
  const child = spawn(command, args, {
    cwd: ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: USE_SHELL,
    env: { ...process.env, FORCE_COLOR: '1' },
    ...opts,
  });
  streamWithPrefix(name, child);
  children.push(child);
  return child;
}

console.log(`[dev] Lancement frontend (port ${PORT}) + backend (port ${BACKEND_PORT}).`);
console.log('[dev] Les deux serveurs écoutent sur 0.0.0.0 (requis par Freebuff).');
console.log('[dev] CTRL+C deux fois pour forcer la sortie.');

// On utilise `pnpm --dir frontend dev` (cross-platform via pnpm).
// shell:true ne sert qu'à résoudre pnpm.cmd sur Windows.
spawnTagged('frontend', 'pnpm', ['--dir', 'frontend', 'dev']);

// Le backend se lance via le script dev-backend.mjs (qui configure
// lui-même --reload, --reload-dir backend, --host 0.0.0.0, --port).
spawnTagged('backend', 'node', [resolve(ROOT, 'scripts/dev-backend.mjs')]);

// Si l'un des deux enfants se termine, on termine les autres.
for (const child of children) {
  child.on('exit', (code, signal) => {
    const name = children[0] === child ? 'frontend' : 'backend';
    console.log(`[dev] ${name} a quitté (code=${code}, signal=${signal}).`);
    killAll('SIGTERM');
    setTimeout(() => process.exit(code ?? 0), 200).unref();
  });
}
