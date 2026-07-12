#!/usr/bin/env python3

import argparse
from pathlib import Path

import torch
from ultralytics import YOLO


ROOT_DIR = Path(__file__).resolve().parents[1]


def default_device():
    if torch.cuda.is_available():
        return "0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    parser = argparse.ArgumentParser(description="Train the iCar water segmentation model")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--device", default=default_device())
    parser.add_argument("--name", default="water_seg_v1")
    args = parser.parse_args()

    data_yaml = ROOT_DIR / "datasets" / "water_public" / "data.yaml"
    if not data_yaml.exists():
        raise SystemExit("Dataset missing. Run scripts/download_water_dataset.sh first.")

    local_base = ROOT_DIR / "models" / "base" / "yolo11n-seg.pt"
    model = YOLO(str(local_base) if local_base.exists() else "yolo11n-seg.pt")
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        project=str(ROOT_DIR / "runs" / "water"),
        name=args.name,
        patience=10,
    )


if __name__ == "__main__":
    main()
