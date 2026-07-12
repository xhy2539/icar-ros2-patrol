#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DATA_DIR="$ROOT_DIR/datasets/water_public"
ARCHIVE=${ARCHIVE:-/tmp/Puddle.v1i.yolov11.zip}
URL="https://github.com/xhy2539/icar-ros2-patrol/releases/download/water-dataset-v1/Puddle.v1i.yolov11.zip"
PART_FILE="${ARCHIVE}.part"
EXTRACT_DIR=$(mktemp -d "$ROOT_DIR/datasets/.water_public.XXXXXX")

cleanup() {
    rm -rf "$EXTRACT_DIR"
}
trap cleanup EXIT

mkdir -p "$DATA_DIR"

if [ ! -f "$ARCHIVE" ]; then
    echo "Downloading water segmentation dataset..."
    rm -f "$PART_FILE"
    curl -L --fail --progress-bar "$URL" -o "$PART_FILE"
    mv "$PART_FILE" "$ARCHIVE"
fi

if ! unzip -tq "$ARCHIVE" >/dev/null; then
    echo "Dataset archive is incomplete or corrupt: $ARCHIVE" >&2
    echo "Remove it and run this script again." >&2
    exit 1
fi

echo "Extracting and regrouping dataset..."
unzip -q "$ARCHIVE" -d "$EXTRACT_DIR"
python3 "$ROOT_DIR/scripts/split_water_dataset.py" --dataset-dir "$EXTRACT_DIR"

rm -rf "$DATA_DIR/train" "$DATA_DIR/valid" "$DATA_DIR/test"
mkdir -p "$DATA_DIR"
mv "$EXTRACT_DIR/train" "$DATA_DIR/train"
mv "$EXTRACT_DIR/valid" "$DATA_DIR/valid"
mv "$EXTRACT_DIR/test" "$DATA_DIR/test"

# Roboflow exports paths for its notebook layout. Keep this configuration
# relative to data.yaml so it works from every clone location.
cat > "$DATA_DIR/data.yaml" <<'YAML'
train: train/images
val: valid/images
test: test/images

nc: 1
names: ['water']

roboflow:
  workspace: puddle-uznq9
  project: puddle-2aodr
  version: 1
  license: CC BY 4.0
  url: https://universe.roboflow.com/puddle-uznq9/puddle-2aodr/dataset/1
YAML

for split in train valid test; do
    count=$(find "$DATA_DIR/$split/images" -type f | wc -l | tr -d ' ')
    echo "$split images: $count"
done

echo "Dataset ready: $DATA_DIR"
