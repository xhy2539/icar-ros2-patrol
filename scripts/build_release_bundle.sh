#!/usr/bin/env bash
# Build a versioned ROS2/source release bundle without contacting the car.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VERSION=${1:-$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || date -u +%Y%m%d%H%M%S)}
DIST_DIR=${ICAR_DIST_DIR:-"$ROOT/dist"}

if [[ ! "$VERSION" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "版本号只能包含字母、数字、点、下划线和连字符: $VERSION" >&2
  exit 2
fi

INCLUDED=(
  README.md
  app
  app_control
  audio
  cloud_bridge
  config
  docs
  icar_interfaces
  llm
  navigation
  scripts
  sensor
  task_manager
  vision
  voice
  web
  pubspec.yaml
  pubspec.lock
)

for path in "${INCLUDED[@]}"; do
  if [[ ! -e "$ROOT/$path" ]]; then
    echo "发布所需路径不存在: $path" >&2
    exit 1
  fi
done

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

mkdir -p "$DIST_DIR"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/icar-release.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT
STAGE="$TMP_DIR/icar-ros2-patrol"
mkdir -p "$STAGE"

(cd "$ROOT" && COPYFILE_DISABLE=1 tar -cf - "${INCLUDED[@]}") | \
  (cd "$STAGE" && tar -xf -)

SOURCE_REVISION=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown')
if git -C "$ROOT" diff --quiet --ignore-submodules HEAD 2>/dev/null && \
   [[ -z $(git -C "$ROOT" ls-files --others --exclude-standard 2>/dev/null) ]]; then
  DIRTY=false
else
  DIRTY=true
fi
GENERATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

printf '%s\n' "$SOURCE_REVISION-$VERSION" > "$STAGE/.icar_deploy_revision"
printf '%s\n' "$VERSION" > "$STAGE/.icar_release_version"

VERSION="$VERSION" SOURCE_REVISION="$SOURCE_REVISION" DIRTY="$DIRTY" \
GENERATED_AT="$GENERATED_AT" python3 - "$STAGE/release-manifest.json" <<'PY'
import json
import os
import sys

manifest = {
    "schema_version": 1,
    "version": os.environ["VERSION"],
    "source_revision": os.environ["SOURCE_REVISION"],
    "source_dirty": os.environ["DIRTY"] == "true",
    "generated_at_utc": os.environ["GENERATED_AT"],
    "startup_script": "scripts/icar_startup.sh",
    "health_endpoint": "http://127.0.0.1:6500/health",
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write("\n")
PY

ARCHIVE="$DIST_DIR/icar-ros2-$VERSION.tar.gz"
COPYFILE_DISABLE=1 tar -C "$TMP_DIR" -czf "$ARCHIVE" icar-ros2-patrol
HASH=$(sha256_file "$ARCHIVE")
printf '%s  %s\n' "$HASH" "$(basename "$ARCHIVE")" > "$ARCHIVE.sha256"

echo "发布包: $ARCHIVE"
echo "校验文件: $ARCHIVE.sha256"
echo "SHA-256: $HASH"
