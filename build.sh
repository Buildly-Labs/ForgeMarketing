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
for arg in "$@"; do
  case "$arg" in
    --no-docker) NO_DOCKER=true ;;
    -h|--help)
      echo "Usage: ./build.sh [--no-docker]"
      echo ""
      echo "  --no-docker   Only initialise submodules; skip Docker build"
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

# ── 2. Docker build ──────────────────────────────────────────
if [ "$NO_DOCKER" = false ]; then
  echo ""
  echo "── Building Docker images ──"
  docker compose build "$@"
  echo ""
  echo "Done. Start with:  docker compose up -d"
fi
