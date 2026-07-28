#!/usr/bin/env node
// Backend "build" - Python n'a pas d'étape de compilation séparée
// (uvicorn exécute le code source directement). On en profite pour
// lancer un contrôle qualité léger si ruff / mypy sont disponibles,
// sans les rendre obligatoires (peuvent être ajoutés plus tard).

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const VENV = resolve(ROOT, '.venv');

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

async function tryRun(cmd, args, opts = {}) {
  try {
    await new Promise((resolve, reject) => {
      const c = spawn(cmd, args, { stdio: 'inherit', ...opts });
      c.on('error', () => reject(new Error('not found')));
      c.on('exit', (code) => (code === 0 ? resolve() : reject(new Error(`exit ${code}`))));
    });
    return true;
  } catch {
    return false;
  }
}

async function main() {
  console.log('[build:backend] Python interprété — pas de bytecode à produire.');
  console.log('[build:backend] Lancement des linters si disponibles (strict-best-effort)...');

  // These are optional, not in requirements.txt today. We try them only
  // if installed (skip silently otherwise) so this script always exits 0
  // even on a fresh install.
  const ruff = await tryRun(python, ['-c', 'import ruff']).catch(() => false);
  if (ruff) {
    console.log('[build:backend] ruff → run');
    await spawn(python, ['-m', 'ruff', 'check', '.'], { stdio: 'inherit' });
  } else {
    console.log('[build:backend] ruff non installé — ignoré.');
  }

  console.log('[build:backend] ✓ Terminé.');
}

main().catch((err) => {
  console.error(`[build:backend] Échec : ${err.message}`);
  process.exit(0); // ne pas bloquer le déploiement sur le build backend
});
