#!/usr/bin/env bash
set -euo pipefail
cd /ssebench/harness

OUT="$(cargo run --offline --quiet)"

# Extract sanitized output block: everything after the marker, excluding the marker line.
SANITIZED="$(printf "%s\n" "$OUT" | sed -n '/===== Sanitized Output =====/,$p' | sed '1d')"

echo "----- Sanitized Output -----"
echo "$SANITIZED"
echo "----------------------------"

# Collapse whitespace/newlines to make pattern matching robust across formatting
ONE_LINE="$(printf "%s" "$SANITIZED" | tr '\n\r\t' ' ' | sed -E 's/[[:space:]]+/ /g')"
LOWER="$(printf "%s" "$ONE_LINE" | tr '[:upper:]' '[:lower:]')"

# Check if there is any iframe tag at all
HAS_IFRAME=$(printf "%s" "$LOWER" | grep -Eiq '<iframe\b' && echo yes || echo no)

# Check raw-text breakout pattern
HAS_BREAKOUT=$(printf "%s" "$LOWER" | grep -Eiq '</iframe>[[:space:]]*<(img|script|svg|math|iframe)\b' && echo yes || echo no)

if [[ "$HAS_IFRAME" == "yes" && "$HAS_BREAKOUT" == "yes" ]]; then
  echo "[!] FAIL: iframe raw-text breakout sequence detected"
  exit 1
else
  echo "[+] OK: no iframe raw-text breakout risk detected"
  exit 0
fi

