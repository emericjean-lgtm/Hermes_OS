#!/usr/bin/env bash
# Hermes OS - Claude Code status line v3
# Affiche uniquement des métriques déjà fournies par Claude Code :
# répertoire, modèle, effort, contexte, tokens, cache, coût, limites.
# Aucune requête réseau supplémentaire : la status line reste locale.

set -e

STDIN_JSON="$(cat 2>/dev/null || true)"

extract_json() {
  python -c '
import json, sys
try:
    d = json.loads(sys.stdin.read() or "{}")
except Exception:
    d = {}
try:
    v = '"$1"'
except Exception:
    v = ""
print("" if v is None else v)
' <<<"$STDIN_JSON" 2>/dev/null
}

MODEL_DISPLAY="$(extract_json 'd.get("model", {}).get("display_name") or d.get("model", {}).get("id")')"
EFFORT="$(extract_json 'd.get("effort", {}).get("level")')"
CTX_PCT="$(extract_json 'd.get("context_window", {}).get("used_percentage")')"
CTX_SIZE="$(extract_json 'd.get("context_window", {}).get("context_window_size")')"
INPUT_TOKENS="$(extract_json 'd.get("context_window", {}).get("total_input_tokens")')"
OUTPUT_TOKENS="$(extract_json 'd.get("context_window", {}).get("total_output_tokens")')"
CACHE_HIT_RATIO="$(extract_json 'd.get("prompt_cache", {}).get("hit_ratio")')"
CACHE_MISSES="$(extract_json 'd.get("prompt_cache", {}).get("misses")')"
SESSION_COST="$(extract_json 'd.get("cost", {}).get("total_cost_usd")')"
FIVE_HOUR="$(extract_json 'd.get("rate_limits", {}).get("five_hour", {}).get("used_percentage")')"
SEVEN_DAY="$(extract_json 'd.get("rate_limits", {}).get("seven_day", {}).get("used_percentage")')"

[ -z "$MODEL_DISPLAY" ] && MODEL_DISPLAY="${CLAUDE_MODEL:-unknown-model}"
[ -z "$EFFORT" ] && EFFORT="?"

format_pct() {
  if [ -z "$1" ]; then printf '%s' "n/a"; else printf '%.0f%%' "$1" 2>/dev/null || printf 'n/a'; fi
}

CWD="${CLAUDE_PROJECT_DIR:-$PWD}"
CWD_DISPLAY="$CWD"
if [ "${#CWD_DISPLAY}" -gt 50 ]; then
  CWD_DISPLAY=".../$(echo "$CWD_DISPLAY" | sed 's|.*/||')"
fi

CTX_BAR="--------------------"
CTX_PCT_STR="n/a"
if [ -n "$CTX_PCT" ]; then
  PCT_NUM="$(printf '%.0f' "$CTX_PCT" 2>/dev/null || echo 0)"
  [ "$PCT_NUM" -lt 0 ] && PCT_NUM=0
  [ "$PCT_NUM" -gt 100 ] && PCT_NUM=100
  FILLED=$(( PCT_NUM * 20 / 100 ))
  EMPTY=$(( 20 - FILLED ))
  CTX_BAR="$(printf "%${FILLED}s" '' | tr ' ' '#')$(printf "%${EMPTY}s" '' | tr ' ' '-')"
  CTX_PCT_STR="${PCT_NUM}%"
fi

CACHE_STR="n/a"
if [ -n "$CACHE_HIT_RATIO" ]; then
  CACHE_STR="$(format_pct "$CACHE_HIT_RATIO")"
  [ -n "$CACHE_MISSES" ] && CACHE_STR="${CACHE_STR}/${CACHE_MISSES}m"
fi

TOKENS_STR=""
[ -n "$INPUT_TOKENS" ] && TOKENS_STR="in:${INPUT_TOKENS}"
[ -n "$OUTPUT_TOKENS" ] && TOKENS_STR="${TOKENS_STR}${TOKENS_STR:+ }out:${OUTPUT_TOKENS}"
[ -z "$TOKENS_STR" ] && TOKENS_STR="n/a"

COST_STR=""
if [ -n "$SESSION_COST" ] && [ "$SESSION_COST" != "0" ] && [ "$SESSION_COST" != "0.0" ]; then
  COST_STR=" \$${SESSION_COST}"
fi

LIMITS_STR="5h:$(format_pct "$FIVE_HOUR") 7d:$(format_pct "$SEVEN_DAY")"

if [ -t 1 ]; then
  CYAN='\033[36m'; AMBER='\033[33m'; GREEN='\033[32m'; RED='\033[31m'
  DIM='\033[2m'; BOLD='\033[1m'; RESET='\033[0m'
else
  CYAN=''; AMBER=''; GREEN=''; RED=''; DIM=''; BOLD=''; RESET=''
fi

CTX_COLOR="$GREEN"
if [ "$CTX_PCT_STR" != "n/a" ]; then
  PCT_NUM="${CTX_PCT_STR%%%}"
  if [ "$PCT_NUM" -ge 75 ]; then CTX_COLOR="$RED"
  elif [ "$PCT_NUM" -ge 50 ]; then CTX_COLOR="$AMBER"
  fi
fi

printf "${CYAN}[cwd]${RESET} ${BOLD}%s${RESET} ${DIM}|${RESET} ${AMBER}[mdl]${RESET} %s ${DIM}|${RESET} ${AMBER}[eff]${RESET} %s\n" \
  "$CWD_DISPLAY" "$MODEL_DISPLAY" "$EFFORT"
printf "  ${CTX_COLOR}ctx:${RESET} [${CTX_COLOR}%s${RESET}] ${BOLD}%s${RESET}" "$CTX_BAR" "$CTX_PCT_STR"
[ -n "$CTX_SIZE" ] && printf " ${DIM}(${CTX_SIZE})${RESET}"
printf " ${DIM}|${RESET} ${GREEN}tokens:${RESET} %s ${DIM}|${RESET} ${GREEN}cache:${RESET} %s ${DIM}|${RESET}" "$TOKENS_STR" "$CACHE_STR"
[ -n "$COST_STR" ] && printf " ${GREEN}cost:${RESET}%s ${DIM}|${RESET}" "$COST_STR"
printf " ${DIM}%s${RESET}\n" "$LIMITS_STR"
