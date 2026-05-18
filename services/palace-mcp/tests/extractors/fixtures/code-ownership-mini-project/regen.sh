#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$HERE/repo"

rm -rf "$TARGET"
mkdir -p "$TARGET/apps"
cd "$TARGET"

git init --initial-branch=main
git config user.name "Anton S"
git config user.email "old@example.com"

cat > .mailmap <<'EOF'
Anton Stavnichiy <new@example.com> Anton S <old@example.com>
EOF

cat > apps/main.py <<'EOF'
def main():
    return 1
EOF
git add .mailmap apps/main.py
GIT_AUTHOR_DATE="2026-01-01T10:00:00Z" GIT_COMMITTER_DATE="2026-01-01T10:00:00Z" \
  git commit -m "init main.py" --quiet

cat > apps/util.py <<'EOF'
def util():
    return 2
EOF
git config user.name "Other Human"
git config user.email "other@example.com"
git add apps/util.py
GIT_AUTHOR_DATE="2026-01-02T10:00:00Z" GIT_COMMITTER_DATE="2026-01-02T10:00:00Z" \
  git commit -m "add util.py" --quiet

git config user.name "Anton S"
git config user.email "old@example.com"
cat > apps/legacy.py <<'EOF'
def legacy():
    return "legacy"
EOF
git add apps/legacy.py
GIT_AUTHOR_DATE="2026-01-03T10:00:00Z" GIT_COMMITTER_DATE="2026-01-03T10:00:00Z" \
  git commit -m "add legacy.py" --quiet

# Anton switches to new identity
git config user.email "new@example.com"
git config user.name "Anton Stavnichiy"
cat > apps/main.py <<'EOF'
def main():
    return 42
def helper():
    return "h"
EOF
git add apps/main.py
GIT_AUTHOR_DATE="2026-01-04T10:00:00Z" GIT_COMMITTER_DATE="2026-01-04T10:00:00Z" \
  git commit -m "expand main.py (new email)" --quiet

# binary file
printf '\x89PNG\r\n\x1a\n\x00\x00\x00fakepng' > apps/binary.png
git add apps/binary.png
GIT_AUTHOR_DATE="2026-01-05T10:00:00Z" GIT_COMMITTER_DATE="2026-01-05T10:00:00Z" \
  git commit -m "add binary.png" --quiet

# Other Human modifies main.py
git config user.name "Other Human"
git config user.email "other@example.com"
cat > apps/main.py <<'EOF'
def main():
    return 100
def helper():
    return "h"
def extra():
    return "e"
EOF
git add apps/main.py
GIT_AUTHOR_DATE="2026-01-06T10:00:00Z" GIT_COMMITTER_DATE="2026-01-06T10:00:00Z" \
  git commit -m "Other expands main.py" --quiet

# Side branch for merge commit
git checkout -b side
cat > apps/merge_target.py <<'EOF'
def from_side():
    return "side"
EOF
git add apps/merge_target.py
GIT_AUTHOR_DATE="2026-01-07T10:00:00Z" GIT_COMMITTER_DATE="2026-01-07T10:00:00Z" \
  git commit -m "add merge_target.py on side" --quiet

git checkout main
GIT_AUTHOR_DATE="2026-01-08T10:00:00Z" GIT_COMMITTER_DATE="2026-01-08T10:00:00Z" \
  git merge --no-ff side -m "merge side into main" --quiet
git branch -D side

# Bot commit
git config user.name "dependabot[bot]"
git config user.email "bot@example.com"
cat > apps/util.py <<'EOF'
def util():
    return 3  # bumped
EOF
git add apps/util.py
GIT_AUTHOR_DATE="2026-01-09T10:00:00Z" GIT_COMMITTER_DATE="2026-01-09T10:00:00Z" \
  git commit -m "deps: bump util" --quiet

# Anton final tweak (under canonical email)
git config user.name "Anton Stavnichiy"
git config user.email "new@example.com"
cat > apps/main.py <<'EOF'
def main():
    return 100
def helper():
    return "h2"
def extra():
    return "e"
EOF
git add apps/main.py
GIT_AUTHOR_DATE="2026-01-10T10:00:00Z" GIT_COMMITTER_DATE="2026-01-10T10:00:00Z" \
  git commit -m "tweak helper" --quiet

# Delete legacy.py
git rm apps/legacy.py
GIT_AUTHOR_DATE="2026-01-11T10:00:00Z" GIT_COMMITTER_DATE="2026-01-11T10:00:00Z" \
  git commit -m "drop legacy.py" --quiet

echo "fixture rebuilt at: $TARGET"
git -C "$TARGET" log --oneline
