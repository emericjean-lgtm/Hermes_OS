#!/bin/bash
# Sequential re-install of Hermes OS's Ollama model roster (HOS-079).
# One model per role: tries the proposed candidate first; on a genuine
# pull failure (tag doesn't exist / not yet published), falls back to the
# previously-working model for that role instead of leaving it empty.
# Never downloads both — that would roughly double disk/bandwidth for no
# reason once the primary succeeds.
set -u

# role|primary|fallback
ROLES=(
  "swift|qwen3.5:2b|qwen3:1.7b"
  "embedding|qwen3-embedding:0.6b|nomic-embed-text"
  "double_check|qwen3.5:4b|qwen3:4b"
  "standard|qwen3.5:9b|qwen3.5:9b"
  "orchestrator|hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M|hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M"
  "vision|gemma4:12b|gemma4:12b"
  "security|phi4-reasoning-plus|phi4-reasoning:14b-q4_K_M"
  "reasoning|deepseek-r1:14b|deepseek-r1:14b"
  "advanced_analysis|gpt-oss:20b|gpt-oss:20b"
  "code|qwen3.6:27b|qwen3-coder:30b"
  "code_agentic|devstral-small-2|devstral"
  "reasoning_escalation|deepseek-r2|deepseek-r1:32b"
)

RESULTS_FILE="/c/Users/emeri/Hermes_OS-main/scripts/ollama-restore/results.txt"
: > "$RESULTS_FILE"

echo "=== Hermes OS model restore — started $(date) ==="
for entry in "${ROLES[@]}"; do
  IFS='|' read -r role primary fallback <<< "$entry"
  echo ""
  echo "--- [$role] Pulling primary: $primary ---"
  if ollama pull "$primary"; then
    echo "PASS: [$role] $primary"
    echo "$role|$primary|primary" >> "$RESULTS_FILE"
  else
    echo "PRIMARY FAILED: [$role] $primary — falling back to $fallback"
    if [ "$primary" = "$fallback" ]; then
      echo "FAIL: [$role] no distinct fallback, giving up on this role"
      echo "$role|NONE|failed" >> "$RESULTS_FILE"
    elif ollama pull "$fallback"; then
      echo "PASS (fallback): [$role] $fallback"
      echo "$role|$fallback|fallback" >> "$RESULTS_FILE"
    else
      echo "FAIL: [$role] both primary and fallback failed"
      echo "$role|NONE|failed" >> "$RESULTS_FILE"
    fi
  fi
done
echo ""
echo "=== Done $(date) ==="
echo "--- Summary ($RESULTS_FILE) ---"
cat "$RESULTS_FILE"
echo "--- Final ollama list ---"
ollama list
