#!/usr/bin/env node
// Run the backend test suite (pytest) with the venv Python when available.
//
//   pnpm test:backend → uses this script
//   pnpm test:backend -- -k test_aegis   → forwarded to pytest

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const VENV = resolve(ROOT, '.venv');
const BACKEND = resolve(ROOT, 'backend');

const IS_WIN = process.platform === 'win32';

function resolvePython() {
  if (process.env.HERMES_PYTHON) return process.env.HERMES_PYTHON;
  if (existsSync(VENV)) {
    const pyExe = resolve(VENV, IS_WIN ? 'Scripts' : 'bin', IS_WIN ? 'python.exe' : 'python');
    if (existsSync(pyExe)) return pyExe;
  }
  return IS_WIN ? 'python' : 'python3';
}

const python = resolvePython();
const args = ['-m', 'pytest', '-v', ...process.argv.slice(2)];
console.log(`[test:backend] ${python} ${args.join(' ')}`);

const child = spawn(python, args, { cwd: BACKEND, stdio: 'inherit' });
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => {
  console.error(`[test:backend] Échec du lancement : ${err.message}`);
  process.exit(1);
});
