#!/usr/bin/env python3

import argparse
import random
import shutil
from collections import defaultdict
from pathlib import Path


SPLITS = ("train", "valid", "test")
RATIOS = {"train": 0.7, "valid": 0.2, "test": 0.1}


def source_key(path):
    return path.name.split(".rf.", 1)[0]


def collect_samples(dataset_dir):
    groups = defaultdict(list)
    for split in SPLITS:
        image_dir = dataset_dir / split / "images"
        label_dir = dataset_dir / split / "labels"
        if not image_dir.is_dir() or not label_dir.is_dir():
            raise RuntimeError(f"missing Roboflow split: {split}")
        for image_path in sorted(image_dir.iterdir()):
            if not image_path.is_file():
                continue
            label_path = label_dir / f"{image_path.stem}.txt"
            if not label_path.is_file():
                raise RuntimeError(f"missing label for {image_path.name}")
            groups[source_key(image_path)].append((image_path, label_path))
    return groups


def assign_groups(groups, seed):
    rng = random.Random(seed)
    items = list(groups.items())
    rng.shuffle(items)
    items.sort(key=lambda item: len(item[1]), reverse=True)

    total = sum(len(samples) for _, samples in items)
    targets = {split: total * RATIOS[split] for split in SPLITS}
    counts = {split: 0 for split in SPLITS}
    assignments = {}
    for key, samples in items:
        split = min(SPLITS, key=lambda name: counts[name] / targets[name])
        assignments[key] = split
        counts[split] += len(samples)
    return assignments, counts


def move_samples(dataset_dir, groups, assignments):
    staging = dataset_dir / ".grouped_splits"
    if staging.exists():
        shutil.rmtree(staging)
    for split in SPLITS:
        (staging / split / "images").mkdir(parents=True)
        (staging / split / "labels").mkdir(parents=True)

    for key, samples in groups.items():
        split = assignments[key]
        for image_path, label_path in samples:
            image_target = staging / split / "images" / image_path.name
            label_target = staging / split / "labels" / label_path.name
            if image_target.exists() or label_target.exists():
                raise RuntimeError(f"duplicate exported filename: {image_path.name}")
            image_path.replace(image_target)
            label_path.replace(label_target)

    for split in SPLITS:
        shutil.rmtree(dataset_dir / split)
        (staging / split).replace(dataset_dir / split)
    staging.rmdir()


def main():
    parser = argparse.ArgumentParser(
        description="Regroup Roboflow water data without source leakage"
    )
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dataset_dir = args.dataset_dir.resolve()
    groups = collect_samples(dataset_dir)
    assignments, counts = assign_groups(groups, args.seed)
    move_samples(dataset_dir, groups, assignments)

    print(f"source groups: {len(groups)}")
    for split in SPLITS:
        print(f"{split} images: {counts[split]}")


if __name__ == "__main__":
    main()
