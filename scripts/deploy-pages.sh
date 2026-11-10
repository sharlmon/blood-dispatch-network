#!/usr/bin/env bash
# Build the Nuxt app as a static site and publish it to the gh-pages branch.
# Usage: scripts/deploy-pages.sh            (demo build, no login)
#        NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_... scripts/deploy-pages.sh   (with Clerk login)
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
REPO="$(basename "$(git -C "$ROOT" remote get-url origin)" .git)"
URL="$(git -C "$ROOT" remote get-url origin)"

cd "$ROOT/frontend"
GH_PAGES=1 NUXT_APP_BASE_URL="/$REPO/" npx nuxt generate

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
