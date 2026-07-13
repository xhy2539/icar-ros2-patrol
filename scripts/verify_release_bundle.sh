#!/usr/bin/env bash
# Verify a release checksum and safely extract/inspect its manifest.

set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "用法: $0 <archive.tar.gz> <archive.sha256> [extract-dir]" >&2
  exit 2
fi

ARCHIVE=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
CHECKSUM=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
EXTRACT_DIR=${3:-}

[[ -f "$ARCHIVE" ]] || { echo "发布包不存在: $ARCHIVE" >&2; exit 1; }
[[ -f "$CHECKSUM" ]] || { echo "校验文件不存在: $CHECKSUM" >&2; exit 1; }

EXPECTED=$(awk 'NF {print $1; exit}' "$CHECKSUM")
if [[ ! "$EXPECTED" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "无效的 SHA-256 校验文件: $CHECKSUM" >&2
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL=$(sha256sum "$ARCHIVE" | awk '{print $1}')
else
  ACTUAL=$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')
fi
EXPECTED=$(printf '%s' "$EXPECTED" | tr '[:upper:]' '[:lower:]')
ACTUAL=$(printf '%s' "$ACTUAL" | tr '[:upper:]' '[:lower:]')
[[ "$ACTUAL" == "$EXPECTED" ]] || {
  echo "SHA-256 不匹配，拒绝安装" >&2
  exit 1
}

TEMP_CREATED=0
if [[ -z "$EXTRACT_DIR" ]]; then
  EXTRACT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/icar-verify.XXXXXX")
  TEMP_CREATED=1
fi
mkdir -p "$EXTRACT_DIR"

python3 - "$ARCHIVE" "$EXTRACT_DIR" <<'PY'
import json
import os
import pathlib
import sys
import tarfile

archive, destination = sys.argv[1:]
destination_path = pathlib.Path(destination).resolve()
with tarfile.open(archive, "r:gz") as bundle:
    members = bundle.getmembers()
    for member in members:
        target = (destination_path / member.name).resolve()
        if target != destination_path and destination_path not in target.parents:
            raise SystemExit(f"发布包包含不安全路径: {member.name}")
        if member.issym() or member.islnk():
            link_target = pathlib.PurePosixPath(member.linkname)
            if link_target.is_absolute() or ".." in link_target.parts:
                raise SystemExit(f"发布包包含不安全链接: {member.name}")
    bundle.extractall(destination)

manifest_path = destination_path / "icar-ros2-patrol" / "release-manifest.json"
if not manifest_path.is_file():
    raise SystemExit("发布包缺少 release-manifest.json")
with manifest_path.open(encoding="utf-8") as handle:
    manifest = json.load(handle)
if manifest.get("schema_version") != 1:
    raise SystemExit("不支持的发布清单版本")
version = manifest.get("version")
if not isinstance(version, str) or not version:
    raise SystemExit("发布清单缺少版本号")
required = ["scripts/icar_startup.sh", "cloud_bridge", "app_control", "icar_interfaces"]
root = manifest_path.parent
missing = [path for path in required if not (root / path).exists()]
if missing:
    raise SystemExit("发布包缺少必要内容: " + ", ".join(missing))
print(version)
PY

if [[ "$TEMP_CREATED" == 1 ]]; then
  rm -rf "$EXTRACT_DIR"
fi
echo "发布包校验通过: $(basename "$ARCHIVE")"
