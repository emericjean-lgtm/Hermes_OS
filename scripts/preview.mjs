#!/usr/bin/env node
// preview.mjs — orchestrated "preview" target for Freebuff.
//
// Freebuff preview targets *one* port (the next start server on 3000 by
// default). This script launches:
//   - the Next.js frontend in production mode (`next start`, no HMR),
//     so Freebuff can open it on 0.0.0.0:3000,
//   - and the FastAPI backend on 0.0.0.0:8000, *simultaneously*, so the
//     Chat page can reach /chat. Frontend-only previews would show the
//     UI shell but every request to /chat would 404.
//
// Same conventions que scripts/dev.mjs : préfixage des lignes, cascade-
// kill, dev-free (c'est le mode "preview", pas dev — pas de --reload,
// pas de HMR Next.js). Si tu veux le mode dev (HMR + reload), utilise
// plutôt `pnpm dev` (scripts/dev.mjs).

import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const PORT = process.env.PORT || process.env.HERMES_FRONTEND_PORT || '3000';
process.env.PORT = PORT; // next start lit PORT
const BACKEND_PORT = process.env.HERMES_BACKEND_PORT || process.env.BACKEND_PORT || '8000';

function pad(s, n) { return s.length >= n ? s : s + ' '.repeat(n - s.length); }
function tagFor(name) { return `[${pad(name, 9)}]`; }

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
    stream.on('error', () => {});
  };
  handle(child.stdout, process.stdout);
  handle(child.stderr, process.stderr);
}

const children = [];
function killAll(signal = 'SIGTERM') {
  for (const c of children) if (!c.killed) c.kill(signal);
}
process.on('SIGINT', () => { killAll('SIGINT'); setTimeout(() => process.exit(130), 1500).unref(); });
process.on('SIGTERM', () => { killAll('SIGTERM'); process.exit(143); });

function spawnTagged(name, command, args) {
  const child = spawn(command, args, {
    cwd: ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: USE_SHELL,
    env: { ...process.env, FORCE_COLOR: '1' },
  });
  streamWithPrefix(name, child);
  children.push(child);
  return child;
}

console.log(`[preview] Frontend (next start) sur 0.0.0.0:${PORT} + Backend (uvicorn) sur 0.0.0.0:${BACKEND_PORT}.`);
console.log('[preview] Ni HMR Next.js ni --reload uvicorn — mode "preview" propre.');

// Frontend : `next start`, qui réutilise le build déjà produit par
// `pnpm build:frontend`. L'échec est attendu si la commande build
// n'a pas été lancée avant (`.next/` absent) — lance `pnpm build` d'abord.
spawnTagged('frontend', 'pnpm', ['--dir', 'frontend', 'start']);

spawnTagged('backend', 'node', [resolve(ROOT, 'scripts/start-backend.mjs')]);

for (const child of children) {
  child.on('exit', (code, signal) => {
    const name = children[0] === child ? 'frontend' : 'backend';
    console.log(`[preview] ${name} a quitté (code=${code}, signal=${signal}).`);
    killAll('SIGTERM');
    setTimeout(() => process.exit(code ?? 0), 200).unref();
  });
}
