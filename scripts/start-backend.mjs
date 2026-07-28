#!/usr/bin/env node
// Launch the Hermes FastAPI backend in production-like mode (no --reload).
//
// Used by `pnpm start:backend` and `pnpm preview:backend`.
//
// Reads (in priority order):
//   HERMES_BACKEND_PORT / BACKEND_PORT / PORT   → port (default 8000)
//   HERMES_BACKEND_HOST                          → host (default 0.0.0.0)

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
  return IS_WIN ? 'python' : 'python3';
}

const python = resolvePython();
const args = [
  '-m', 'uvicorn',
  'backend.main:app',
  '--host', HOST,
  '--port', String(PORT),
  // No --reload here : c'est le mode start ; pas en dev.
  // workers=1 par défaut. Augmenter `workers` requiert de remplacer
  // les in-memory state (lru_cache singletons) — voir §24 backend.
];
console.log(`[start:backend] ${python} ${args.join(' ')}`);

const child = spawn(python, args, { cwd: ROOT, stdio: 'inherit' });
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => {
  console.error(`[start:backend] Échec du lancement : ${err.message}`);
  process.exit(1);
});
