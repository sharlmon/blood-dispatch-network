#!/usr/bin/env bash
# Build the Nuxt app as a static site and publish it to the gh-pages branch.
# Usage: scripts/deploy-pages.sh            (demo build, no login, no API)
#        NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_... scripts/deploy-pages.sh   (with Clerk login)
#        NUXT_PUBLIC_API_BASE=https://api.example.org scripts/deploy-pages.sh   (with a hosted API)
# The API comes from the shell only: frontend/.env's NUXT_PUBLIC_API_BASE (localhost, for
# development) is ignored, or every visitor's browser would call localhost.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
REPO="$(basename "$(git -C "$ROOT" remote get-url origin)" .git)"
URL="$(git -C "$ROOT" remote get-url origin)"

cd "$ROOT/frontend"
# Set even when empty: nuxt fills a variable from .env only when it is not set at all.
API_BASE="${NUXT_PUBLIC_API_BASE-}"
echo "API: ${API_BASE:-none, static demo}"
GH_PAGES=1 NUXT_PUBLIC_API_BASE="$API_BASE" NUXT_APP_BASE_URL="/$REPO/" npx nuxt generate

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if git ls-remote --exit-code --heads origin gh-pages >/dev/null 2>&1; then
  git clone --quiet --branch gh-pages --single-branch "$URL" "$TMP"
else
  git -C "$TMP" init --quiet -b gh-pages
  git -C "$TMP" remote add origin "$URL"
fi
rsync -a --delete --exclude .git .output/public/ "$TMP/"
git -C "$TMP" add -A
if git -C "$TMP" diff --cached --quiet; then echo "Nothing changed."; exit 0; fi
git -C "$TMP" commit --quiet -m "Deploy site from $(git -C "$ROOT" rev-parse --short HEAD)"
git -C "$TMP" push origin gh-pages
echo "Published: https://$(git -C "$ROOT" remote get-url origin | sed -E 's#.*github.com[:/]([^/]+)/.*#\1#').github.io/$REPO/"
