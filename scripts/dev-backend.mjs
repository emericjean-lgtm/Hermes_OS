#!/usr/bin/env node
// Launch the Hermes FastAPI backend in development mode.
//
//   uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
//       --reload --reload-dir backend
//
// Reads (in priority order):
//   HERMES_BACKEND_PORT / BACKEND_PORT / PORT   → port (default 8000)
//   HERMES_BACKEND_HOST                          → host (default 0.0.0.0)
//
// Prefers the venv created by install-backend.mjs (.venv/), falls back to
// `python3` / `python` / `py` if missing. Cross-platform.

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const VENV = resolve(ROOT, '.venv');

const IS_WIN = process.platform === 'win32';
const PORT = process.env.HERMES_BACKEND_PORT || process.env.BACKEND_PORT || process.env.PORT || '8000';
const HOST = process.env.HERMES_BACKEND_HOST || '0.0.0.0';

function resolvePython() {
  if (process.env.HERMES_PYTHON) return process.env.HERMES_PYTHON;
  if (existsSync(VENV)) {
    const pyExe = resolve(VENV, IS_WIN ? 'Scripts' : 'bin', IS_WIN ? 'python.exe' : 'python');
    if (existsSync(pyExe)) return pyExe;
  }
  // Fallback : laisser Node spawn() chercher dans PATH.
  return IS_WIN ? 'python' : 'python3';
}

const python = resolvePython();
const args = [
  '-m', 'uvicorn',
  'backend.main:app',
  '--host', HOST,
  '--port', String(PORT),
  '--reload',
  // --reload-dir backend empêche le reloader de watcher frontend/node_modules
  // (sinon chaque `pnpm install` relance uvicorn). Voir README.md.
  '--reload-dir', 'backend',
];

console.log(`[dev:backend] ${python} ${args.join(' ')}`);

const child = spawn(python, args, { cwd: ROOT, stdio: 'inherit' });
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => {
  console.error(`[dev:backend] Échec du lancement : ${err.message}`);
  process.exit(1);
});
