#!/usr/bin/env bash
# Hermes OS - Claude Code status line v2
# Affiche : repertoire courant - modele - barre de contexte - tokens - cout
#
# Seuil d'alerte visuelle abaisse a 50% (vert <50%, ambre 50-65%, rouge >=65%).

set -e

# --- Lecture stdin (Claude Code envoie le contexte ici) ---
STDIN_JSON="$(cat 2>/dev/null || true)"

# --- Helper : extraction d'un champ JSON via Python (toujours disponible) ---
extract_json() {
  python -c "
import json, sys
try:
    d = json.loads(sys.stdin.read() or '{}')
except Exception:
    d = {}
v = ($1)
print('' if v is None else v)
" <<<"$2" 2>/dev/null
}

# --- Champs ---
MODEL_DISPLAY="$(extract_json 'd.get("model", {}).get("display_name") or d.get("model", {}).get("id")' "$STDIN_JSON")"
CTX_PCT="$(extract_json 'd.get("context_window", {}).get("used_percentage")' "$STDIN_JSON")"
CTX_USED="$(extract_json 'd.get("context_window", {}).get("used_tokens") or d.get("context_window", {}).get("total_input_tokens")' "$STDIN_JSON")"
CTX_SIZE="$(extract_json 'd.get("context_window", {}).get("context_window_size")' "$STDIN_JSON")"
SESSION_TOKENS="$(extract_json 'd.get("session", {}).get("total_tokens")' "$STDIN_JSON")"
SESSION_COST="$(extract_json 'd.get("cost", {}).get("total_cost_usd")' "$STDIN_JSON")"

# --- Fallbacks ---
if [ -z "$MODEL_DISPLAY" ] && [ -n "$CLAUDE_MODEL" ]; then
  MODEL_DISPLAY="$CLAUDE_MODEL"
fi
[ -z "$MODEL_DISPLAY" ] && MODEL_DISPLAY="unknown-model"
if [ -z "$SESSION_TOKENS" ] && [ -n "$CLAUDE_SESSION_TOKENS" ]; then
  SESSION_TOKENS="$CLAUDE_SESSION_TOKENS"
fi
[ -z "$SESSION_TOKENS" ] && SESSION_TOKENS="0"

# --- Repertoire courant (dernier segment si > 50 chars) ---
CWD="${CLAUDE_PROJECT_DIR:-$PWD}"
CWD_DISPLAY="$CWD"
if [ "${#CWD_DISPLAY}" -gt 50 ]; then
  CWD_DISPLAY=".../$(echo "$CWD_DISPLAY" | sed 's|.*/||')"
fi

# --- Barre de contexte visuelle (20 segments ASCII) ---
CTX_BAR=""
CTX_PCT_STR="n/a"
if [ -n "$CTX_PCT" ]; then
  PCT_NUM="$(printf '%.0f' "$CTX_PCT" 2>/dev/null || echo 0)"
  FILLED=$(( PCT_NUM * 20 / 100 ))
  if [ "$FILLED" -gt 20 ]; then FILLED=20; fi
  if [ "$FILLED" -lt 0 ]; then FILLED=0; fi
  EMPTY=$(( 20 - FILLED ))
  FULL_CHAR='#'
  EMPTY_CHAR='-'
  CTX_BAR="$(printf "%${FILLED}s" '' | tr ' ' "$FULL_CHAR")$(printf "%${EMPTY}s" '' | tr ' ' "$EMPTY_CHAR")"
  CTX_PCT_STR="${PCT_NUM}%"
else
  CTX_BAR="--------------------"
fi

# --- Couleurs ANSI (desactivees si pas un TTY) ---
if [ -t 1 ]; then
  CYAN='\033[36m'; AMBER='\033[33m'; GREEN='\033[32m'
  RED='\033[31m'; DIM='\033[2m'; BOLD='\033[1m'; RESET='\033[0m'
else
  CYAN=''; AMBER=''; GREEN=''; RED=''; DIM=''; BOLD=''; RESET=''
fi

# Couleur du contexte (vert <50, ambre 50-65, rouge >=65)
CTX_COLOR="$DIM"
if [ -n "$CTX_PCT" ]; then
  PCT_NUM="$(printf '%.0f' "$CTX_PCT" 2>/dev/null || echo 0)"
  if   [ "$PCT_NUM" -ge 65 ]; then CTX_COLOR="$RED"
  elif [ "$PCT_NUM" -ge 50 ]; then CTX_COLOR="$AMBER"
  else                              CTX_COLOR="$GREEN"
  fi
fi

# --- Cout ---
COST_STR=""
if [ -n "$SESSION_COST" ] && [ "$SESSION_COST" != "0" ] && [ "$SESSION_COST" != "0.0" ]; then
  COST_STR=" \$${SESSION_COST}"
fi

# --- Raccourcis (toujours affiches, format court) ---
SHORTCUTS="${DIM}[/]${RESET}cmd ${DIM}[?]${RESET}help ${DIM}[!]${RESET}bash ${DIM}[@]${RESET}file ${DIM}[#]${RESET}compact"

# --- Ligne 1 : repertoire + modele ---
printf "${CYAN}[cwd]${RESET} ${BOLD}%s${RESET} ${DIM}|${RESET} ${AMBER}[mdl]${RESET} %s\n" \
  "$CWD_DISPLAY" \
  "$MODEL_DISPLAY"

# --- Ligne 2 : barre contexte + tokens + cout + raccourcis ---
printf "  ${CTX_COLOR}ctx:${RESET} [${CTX_COLOR}%s${RESET}] ${BOLD}%s${RESET} ${DIM}|${RESET} ${GREEN}tokens:${RESET} %s${COST_STR} ${DIM}|${RESET} %s\n" \
  "$CTX_BAR" \
  "$CTX_PCT_STR" \
  "$SESSION_TOKENS" \
  "$SHORTCUTS"
