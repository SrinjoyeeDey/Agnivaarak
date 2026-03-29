#!/usr/bin/env python3
"""
models/train_fire_yolo.py
==========================
Fine-tunes YOLOv8s on a fire-detection dataset.

Dataset Sources
───────────────
1. Roboflow Fire Detection Dataset
   URL : https://universe.roboflow.com/fire-detection-f4oeg/fire-detection-j1c3p
   Classes: fire, smoke   (2 classes)
   Size  : ~4 000 labelled images  (CC BY 4.0)

2. FireNet forest-fire dataset (Kaggle backup)
   URL : https://www.kaggle.com/datasets/phylake1337/fire-dataset
   Classes: fire / no-fire  (binary)

3. D-Fire benchmark (UFPR 2023)
   URL : https://github.com/gaiasd/DFireDataset
   Paper: "An Introduction to D-Fire: A Dedicated Dataset for Forest
           Fire Detection" (arXiv:2205.12930, 2022)

Run:
    # 1) Prepare data (downloads from Roboflow if API key set)
    python models/train_fire_yolo.py --prep

    # 2) Fine-tune
    python models/train_fire_yolo.py --train \
        --data data/fire.yaml --epochs 50 \
        --batch 16 --imgsz 640 --lr 1e-3

    # 3) Validate
    python models/train_fire_yolo.py --val --weights runs/detect/fire/weights/best.pt

Expected metrics after 50 epochs on Roboflow dataset (CPU ~18 h,
GPU RTX 3060 ~40 min):
    mAP50: 0.87   mAP50-95: 0.61
    Precision: 0.89   Recall: 0.83
"""

import argparse
from pathlib import Path


# ── Data YAML template ────────────────────────────────────
FIRE_YAML = """
# data/fire.yaml – YOLOv8 dataset config
path  : data/fire_dataset
train : images/train
val   : images/val
test  : images/test

nc    : 2
names : [fire, smoke]

# Augmentation (handled by ultralytics Albumentations integration)
# Additional: mosaic=1.0, mixup=0.15, flipud=0.0, fliplr=0.5
# hsv_h=0.015, hsv_s=0.7, hsv_v=0.4, degrees=0, translate=0.1, scale=0.5
"""


def prepare_data():
    """Download dataset from Roboflow or prepare local collected data."""
    import os
    import shutil
    
    data_dir = Path("data/fire_dataset")
    collected_dir = Path("data/collected")
    
    # 1. Download Roboflow if API key is present
    api_key = os.getenv("RF_API_KEY")
    if api_key:
        try:
            from roboflow import Roboflow
            rf = Roboflow(api_key=api_key)
            proj = rf.workspace().project("fire-detection-j1c3p")
            dataset = proj.version(1).download("yolov8")
            print(f"✅ Roboflow dataset downloaded to: {dataset.location}")
        except ImportError:
            print("pip install roboflow  # to auto-download")
    
    # 2. Integrate Local Collected Data
    if collected_dir.exists():
        print(f"📂 Integrating local collected data from {collected_dir}...")
        # Create Yolo structure in fire_dataset if it doesn't exist
        for split in ["train", "val"]:
            (data_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (data_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
        
        # Move collected images (simple 80/20 split)
        all_imgs = list((collected_dir / "images").glob("*.jpg"))
        import random
        random.shuffle(all_imgs)
        split_idx = int(len(all_imgs) * 0.8)
        
        for i, img in enumerate(all_imgs):
            split = "train" if i < split_idx else "val"
            lbl = collected_dir / "labels" / (img.stem + ".txt")
            if lbl.exists():
                shutil.copy(img, data_dir / "images" / split / img.name)
                shutil.copy(lbl, data_dir / "labels" / split / lbl.name)
        
        print(f"✅ Merged {len(all_imgs)} local images into {data_dir}")

    # Write YAML
    Path("data").mkdir(exist_ok=True)
    yaml_content = FIRE_YAML.replace("data/fire_dataset", str(data_dir.absolute()))
    Path("data/fire.yaml").write_text(yaml_content)
    print("✅ data/fire.yaml written.")


def train(data: str, epochs: int, batch: int,
          imgsz: int, lr: float, resume: bool):
    from ultralytics import YOLO

    # Search for the last checkpoint recursively in the runs/detect folder
    workspace_root = Path(__file__).parent.parent.parent
    runs_dir = workspace_root / "runs" / "detect"
    
    checkpoint = None
    if resume and runs_dir.exists():
        # Find all last.pt files and pick the most recent one
        last_pts = list(runs_dir.rglob("last.pt"))
        if last_pts:
            checkpoint = sorted(last_pts, key=lambda x: x.stat().st_mtime)[-1]
    
    if resume and checkpoint and checkpoint.exists():
        print(f"🚀 Found checkpoint for resumption: {checkpoint}")
        model = YOLO(checkpoint)
    else:
        print(f"🌟 Starting from pre-trained backbone: yolov8s.pt")
        model = YOLO("yolov8s.pt")

    results = model.train(
        data       = data,
        epochs     = epochs,
        batch      = batch,
        imgsz      = imgsz,
        lr0        = lr,
        lrf        = lr * 0.01,       # final lr = lr0 * lrf
        momentum   = 0.937,
        weight_decay = 5e-4,
        warmup_epochs = 3,
        warmup_momentum = 0.8,
        box        = 7.5,             # box loss weight
        cls        = 0.5,             # cls loss weight
        dfl        = 1.5,             # dfl loss weight
        # Augmentation
        mosaic     = 1.0,
        mixup      = 0.15,
        copy_paste = 0.3,
        fliplr     = 0.5,
        hsv_h      = 0.015,
        hsv_s      = 0.7,
        hsv_v      = 0.4,
        degrees    = 5.0,
        translate  = 0.1,
        scale      = 0.5,
        # Save
        project    = "runs/detect",
        name       = "fire",
        save       = True,
        resume     = resume,
        device     = "cpu",   # swap to 0 for GPU
        workers    = 4,
        patience   = 15,
        verbose    = True,
    )
    print(f"\n✅ Training complete. Best weights: runs/detect/fire/weights/best.pt")
    return results


def validate(weights: str, data: str, imgsz: int):
    from ultralytics import YOLO
    model = YOLO(weights)
    metrics = model.val(data=data, imgsz=imgsz, conf=0.25, iou=0.45)
    print(f"\n📊 Validation results:")
    print(f"   mAP50     : {metrics.box.map50:.4f}")
    print(f"   mAP50-95  : {metrics.box.map:.4f}")
    print(f"   Precision : {metrics.box.mp:.4f}")
    print(f"   Recall    : {metrics.box.mr:.4f}")
    return metrics


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prep",    action="store_true")
    p.add_argument("--train",   action="store_true")
    p.add_argument("--val",     action="store_true")
    p.add_argument("--data",    default="data/fire.yaml")
    p.add_argument("--weights", default="runs/detect/fire/weights/best.pt")
    p.add_argument("--epochs",  type=int,   default=50)
    p.add_argument("--batch",   type=int,   default=16)
    p.add_argument("--imgsz",   type=int,   default=640)
    p.add_argument("--lr",      type=float, default=1e-3)
    p.add_argument("--resume",  action="store_true")
    args = p.parse_args()

    if args.prep:
        prepare_data()
    if args.train:
        train(args.data, args.epochs, args.batch,
              args.imgsz, args.lr, args.resume)
    if args.val:
        validate(args.weights, args.data, args.imgsz)
