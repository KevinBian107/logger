#!/usr/bin/env bash
# Seeds a throwaway demo DB, boots the real dev servers against it, drives
# the app with Playwright to capture the walkthrough screenshots + clips,
# then tears everything down. Never touches the real dev/app database.
#
# Usage: ./scripts/walkthrough/run.sh
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

SCRATCH_DIR="$(mktemp -d)"
SCRATCH_DB="$SCRATCH_DIR/walkthrough_demo.db"
echo "== Seeding demo DB at $SCRATCH_DB =="
LOGGER_DB_PATH="$SCRATCH_DB" uv run --project backend python scripts/walkthrough/seed_demo_data.py

echo "== Starting backend on :8000 against the demo DB =="
(cd backend && LOGGER_DB_PATH="$SCRATCH_DB" uv run uvicorn logger.main:app --port 8000) &
BACKEND_PID=$!

cleanup() {
  echo "== Stopping backend and frontend =="
  kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  # uv run / vite may spawn children with different PIDs -- belt and suspenders.
  lsof -ti:8000 -sTCP:LISTEN | xargs -r kill 2>/dev/null || true
  lsof -ti:5173 -sTCP:LISTEN | xargs -r kill 2>/dev/null || true
  # The scratch DB carries a copy of the anthropic_api_key blob -- don't
  # leave it (or the demo data) sitting around in the temp dir.
  echo "== Removing scratch DB =="
  rm -rf "$SCRATCH_DIR"
}
trap cleanup EXIT

echo "== Waiting for backend =="
for _ in $(seq 1 30); do
  curl -sf http://localhost:8000/api/health >/dev/null 2>&1 && break
  sleep 1
done

echo "== Starting frontend on :5173 =="
pnpm --dir frontend dev &
FRONTEND_PID=$!

echo "== Waiting for frontend =="
for _ in $(seq 1 30); do
  curl -sf http://localhost:5173/ >/dev/null 2>&1 && break
  sleep 1
done

echo "== Capturing =="
node scripts/walkthrough/capture.mjs

echo "== Transcoding video clips to compressed, Safari-friendly mp4 =="
for webm in website/assets/walkthrough/*.webm; do
  [ -e "$webm" ] || continue
  mp4="${webm%.webm}.mp4"
  ffmpeg -y -i "$webm" -an -vcodec libx264 -crf 26 -preset veryslow -movflags +faststart -pix_fmt yuv420p "$mp4"
  rm "$webm"
done

echo "== Done. Assets in website/assets/walkthrough/ =="
ls -la website/assets/walkthrough/
