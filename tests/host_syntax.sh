#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CC="${CC:-cc}"
"$CC" -std=c11 -Wall -Wextra -Werror -fsyntax-only -I"$HERE/stub" -I"$HERE/../src" "$HERE/../src/game.c"
TEST_BIN="$(mktemp "${TMPDIR:-/tmp}/naprider-gameplay.XXXXXX")"
trap 'rm -f "$TEST_BIN"' EXIT
"$CC" -std=c11 -Wall -Wextra -Werror -I"$HERE/stub" -I"$HERE/../src" "$HERE/gameplay.c" -o "$TEST_BIN"
"$TEST_BIN"
