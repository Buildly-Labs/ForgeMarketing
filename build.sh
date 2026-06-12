#!/usr/bin/env bash
set -euo pipefail

# ── build.sh ─────────────────────────────────────────────────
# Initialises git submodules (Producer, and any future ones)
# then runs docker compose build.
#
# Usage:
#   ./build.sh              # init submodules + docker build
#   ./build.sh --no-docker  # init submodules only
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NO_DOCKER=false
SKIP_TESTS=false
for arg in "$@"; do
  case "$arg" in
    --no-docker) NO_DOCKER=true ;;
    --skip-tests) SKIP_TESTS=true ;;
    -h|--help)
      echo "Usage: ./build.sh [--no-docker] [--skip-tests]"
      echo ""
      echo "  --no-docker   Only initialise submodules; skip Docker build"
      echo "  --skip-tests  Skip pytest quality gate before build"
      echo "  -h, --help    Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      exit 1
      ;;
  esac
done

# ── 1. Initialise / update all git submodules ────────────────
echo "── Initialising git submodules ──"
git submodule update --init --recursive

# Verify each submodule directory is non-empty
git submodule foreach --quiet 'if [ -z "$(ls -A .)" ]; then echo "ERROR: submodule $name at $sm_path is empty"; exit 1; fi'
echo "   All submodules ready."

# ── 2. Quality gate tests ───────────────────────────────────
if [ "$SKIP_TESTS" = false ]; then
  echo ""
  echo "── Running quality tests (pytest) ──"
  if command -v pytest >/dev/null 2>&1; then
    pytest
  elif [ -x ".venv/bin/pytest" ]; then
    .venv/bin/pytest
  else
    echo "ERROR: pytest not found. Install test deps (e.g. pip install -r requirements-test.txt)"
    exit 1
  fi
  echo "   Quality tests passed."
fi

# ── 3. Docker build ──────────────────────────────────────────
if [ "$NO_DOCKER" = false ]; then
  echo ""
  echo "── Building Docker images ──"
  docker compose build "$@"
  echo ""
  echo "Done. Start with:  docker compose up -d"
fi
