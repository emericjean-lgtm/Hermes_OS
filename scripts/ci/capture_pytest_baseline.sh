#!/usr/bin/env bash
# scripts/ci/capture_pytest_baseline.sh
#
# Capture la baseline pytest du projet — HOS-000 foundation.
#
# Usage :
#   HERMES_OS_HOS=HOS-000  ./scripts/ci/capture_pytest_baseline.sh
#   ./scripts/ci/capture_pytest_baseline.sh         # défaut : HOS-000
#
# Le baseline est un SNAPSHOT (pas un gate CI) : il est sauvegardé
# dans tests/architecture/baselines/BASELINE-PRE-<TAG>.txt.
# Les PRs HOS-XXX suivantes régénèrent leur baseline respective et
# comparent le diff pour détecter toute régression non intentionnelle.
#
# HOS-000 introduit ce script. Les PRs suivantes (HOS-001, HOS-002, …)
# le réutilisent sans modification.
#
set -uo pipefail

# --- Configuration -------------------------------------------------------

TAG="${HERMES_OS_HOS:-HOS-000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

OUT_DIR="tests/architecture/baselines"
OUT="${OUT_DIR}/BASELINE-PRE-${TAG}.txt"

# --- Préparation ---------------------------------------------------------

mkdir -p "${OUT_DIR}"

# --- Capture -------------------------------------------------------------
#
# Un échec pytest NE DOIT PAS stopper le script : un snapshot sert
# précisément à archiver les échecs pour diagnostic ultérieur.
# L'option `|| true` est ici intentionnelle (ne pas la retirer).
#
echo "[capture_pytest_baseline] tag=${TAG}"
echo "[capture_pytest_baseline] out=${OUT}"
echo "[capture_pytest_baseline] running pytest on backend/tests tests/architecture ..."

HERMES_OS_HOS="${TAG}" pytest backend/tests tests/architecture \
    -q --tb=line --no-header --color=no \
    > "${OUT}" 2>&1 || true

LINES="$(wc -l < "${OUT}")"
echo "[capture_pytest_baseline] baseline saved (${LINES} lines) at ${OUT}"
