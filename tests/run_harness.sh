#!/usr/bin/env bash
# Behavioural harness: a bot plays the whole campaign against a software model
# of both PRG32 display back ends; see tests/harness/run_harness.c.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CC_BIN="${CC:-cc}"
BIN="$(mktemp "${TMPDIR:-/tmp}/naprider-harness.XXXXXX")"
trap 'rm -f "$BIN"' EXIT
SRC="$ROOT/tests/harness/run_harness.c"
COMMON=(-std=c11 -Wall -Wextra -Werror -O1 -I"$ROOT/tests/stub" -I"$ROOT/src")
if ! "$CC_BIN" "${COMMON[@]}" -fsanitize=address,undefined "$SRC" -o "$BIN" 2>/dev/null; then
  "$CC_BIN" "${COMMON[@]}" "$SRC" -o "$BIN"
fi
"$BIN"
