#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DATA_DIR="$ROOT_DIR/datasets/water_public"
ARCHIVE=${ARCHIVE:-/tmp/Puddle.v1i.yolov11.zip}
URL="https://github.com/xhy2539/icar-ros2-patrol/releases/download/water-dataset-v1/Puddle.v1i.yolov11.zip"

mkdir -p "$DATA_DIR"

if [ ! -f "$ARCHIVE" ]; then
    echo "Downloading water segmentation dataset..."
    curl -L --fail --progress-bar "$URL" -o "$ARCHIVE"
fi

echo "Extracting dataset to $DATA_DIR..."
unzip -q -o "$ARCHIVE" -d "$DATA_DIR"

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
