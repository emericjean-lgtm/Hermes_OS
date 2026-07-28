#!/usr/bin/env node
// Install backend Python dependencies.
//
// Creates an optional virtualenv at the repo root (.venv/) and installs
// backend/requirements.txt into it. Cross-platform: detects `python3` /
// `python` / `py` on Windows, uses the right Scripts/ vs bin/ layout for
// the venv, and exposes env vars to tweak behaviour.
//
//   HERMES_NO_VENV=1   — skip virtualenv, install into the system Python
//   HERMES_PYTHON=...  — explicit interpreter to use
//
// Node.js >= 18.18 only (engines in package.json). No external deps.

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const VENV = resolve(ROOT, '.venv');
const REQFILE = resolve(ROOT, 'backend', 'requirements.txt');

const IS_WIN = process.platform === 'win32';
const PY_CANDIDATES = IS_WIN ? ['python', 'python3', 'py'] : ['python3', 'python'];

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: 'inherit', ...opts });
    child.on('error', reject);
    child.on('exit', (code) =>
      code === 0 ? resolve() : reject(new Error(`${cmd} exited with code ${code}`)),
    );
  });
}

async function findPython() {
  // 1. Honorer HERMES_PYTHON explicite.
  if (process.env.HERMES_PYTHON) return process.env.HERMES_PYTHON;
  // 2. Sinon, tester chaque candidat connu.
  for (const cmd of PY_CANDIDATES) {
    try {
      await run(cmd, ['--version']);
      return cmd;
    } catch {
      // try next
    }
  }
  return null;
}

async function ensureVenv(python) {
  if (existsSync(VENV)) {
    console.log(`[install:backend] Virtualenv existant détecté : ${VENV}`);
    return;
  }
  console.log(`[install:backend] Création du virtualenv dans : ${VENV}`);
  await run(python, ['-m', 'venv', VENV]);
}

function venvPython() {
  const filename = IS_WIN ? 'python.exe' : 'python';
  return resolve(VENV, IS_WIN ? 'Scripts' : 'bin', filename);
}

function venvPip() {
  const filename = IS_WIN ? 'pip.exe' : 'pip';
  return resolve(VENV, IS_WIN ? 'Scripts' : 'bin', filename);
}

async function main() {
  if (!existsSync(REQFILE)) {
    console.error(`[install:backend] Fichier requis introuvable : ${REQFILE}`);
    console.error("Vérifie l'arborescence : le backend Python est attendu sous backend/.");
    process.exit(1);
  }

  const noVenv = process.env.HERMES_NO_VENV === '1';
  const python = await findPython();
  if (!python) {
    console.error(
      `[install:backend] Aucun interpréteur Python trouvé. Candidats testés : ${PY_CANDIDATES.join(', ')}`,
    );
    console.error('Installe Python 3.11+ depuis https://www.python.org/downloads/ puis relance.');
    process.exit(1);
  }
  console.log(`[install:backend] Python détecté : ${python}`);

  let pipCmd, pipArgs;
  if (noVenv) {
    console.log('[install:backend] HERMES_NO_VENV=1 → installation système (déconseillé).');
    pipCmd = python;
    pipArgs = ['-m', 'pip'];
  } else {
    await ensureVenv(python);
    pipCmd = venvPip();
    if (!existsSync(pipCmd)) {
      console.error(`[install:backend] pip absent dans le venv (${pipCmd}). Re-crée le venv.`);
      process.exit(1);
    }
    pipArgs = [];
  }

  console.log(`[install:backend] Installation depuis backend/requirements.txt`);
  await run(pipCmd, [...pipArgs, 'install', '-r', REQFILE]);

  console.log('[install:backend] ✓ Terminé.');
  if (!noVenv) {
    console.log('Pour activer le venv :');
    console.log(IS_WIN ? '  .venv\\Scripts\\activate' : '  source .venv/bin/activate');
  }
}

main().catch((err) => {
  console.error(`[install:backend] Échec : ${err.message}`);
  process.exit(1);
});
