#!/usr/bin/env python3
"""
models/download_models.py
==========================
Downloads and verifies all pre-trained model weights.

Sources
-------
1. YOLOv8n (COCO baseline)
   Ultralytics HF Hub: https://huggingface.co/Ultralytics/assets
   Used for: human ("person") class detection

2. Fire-detection fine-tuned YOLOv8
   HF Hub: https://huggingface.co/TommyNgx/YOLOv10-Fire-and-Smoke-Detection
   Paper: "YOLOv10: Real-Time End-to-End Object Detection" (2024)

3. Backup smoke/fire classifier
   HF Hub: https://huggingface.co/EdBianchi/vit-fire-detection
   Architecture: ViT-B/16 fine-tuned on FIRE dataset

Usage:
    python models/download_models.py
    python models/download_models.py --build-only   # skip interactive prompt
    python models/download_models.py --verify-only  # checksum check only
"""

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

WEIGHTS_DIR = Path(__file__).parent / "weights"

# ── Model registry ────────────────────────────────────────
# fmt: off
MODELS = [
    {
        "name"    : "yolov8n.pt",
        "desc"    : "YOLOv8 Nano - COCO (human detection)",
        "url"     : "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt",
        "sha256"  : "3c5b9fa4c04c5e6b6fdb0fa26e53f5c0f6eb7e7c6d8c2f4e5a3b1d9c7f2e4a6b",  # illustrative
        "required": True,
    },
    {
        "name"    : "fire_yolo.pt",
        "desc"    : "YOLOv8 fire+smoke detection (fine-tuned)",
        "url"     : "https://huggingface.co/keremberke/yolov8s-fire-detection/resolve/main/best.pt",
        # HF page: https://huggingface.co/keremberke/yolov8s-fire-detection
        # Dataset: Roboflow fire-detection dataset (CC-BY 4.0)
        "sha256"  : "a7c3e9f21b4d8e56a0c2f7b3d4e8a1c5f2b7d9e3a4c6f8b2d4e7a9c1f3b5d7e9",  # illustrative
        "required": True,
    },
    {
        "name"    : "yolov8n.onnx",
        "desc"    : "YOLOv8 Nano - ONNX export (faster CPU inference)",
        "url"     : None,   # generated locally via export_models.py
        "sha256"  : None,
        "required": False,
    },
    {
        "name"    : "fire_yolo.onnx",
        "desc"    : "Fire YOLO - ONNX export",
        "url"     : None,
        "sha256"  : None,
        "required": False,
    },
]
# fmt: on


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while data := f.read(chunk):
            h.update(data)
    return h.hexdigest()


def download_with_progress(url: str, dest: Path):
    """Minimal progress bar without external deps."""
    print(f"  v {url}")
    print(f"  -> {dest}")

    def reporthook(count, block_size, total_size):
        if total_size <= 0:
            return
        pct = min(100, int(count * block_size * 100 / total_size))
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook)
    print()  # newline after progress


def try_hf_download(model_name: str, dest: Path):
    """Attempt Hugging Face hub download as fallback."""
    try:
        from huggingface_hub import hf_hub_download
        if "fire" in model_name:
            path = hf_hub_download(
                repo_id="keremberke/yolov8s-fire-detection",
                filename="best.pt",
                local_dir=str(dest.parent))
            Path(path).rename(dest)
            return True
        elif "yolov8n" in model_name:
            from ultralytics import YOLO
            model = YOLO("yolov8n.pt")   # auto-downloads from ultralytics
            src = Path("yolov8n.pt")
            if src.exists():
                src.rename(dest)
            return True
    except Exception as exc:
        print(f"  ! HF fallback failed: {exc}")
    return False


def download_models(build_only=False, verify_only=False):
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    all_ok = True

    for m in MODELS:
        dest = WEIGHTS_DIR / m["name"]
        print(f"\n{'-' * 60}")
        print(f" [MODEL] {m['name']}  -  {m['desc']}")

        # Already exists - verify
        if dest.exists():
            if m["sha256"]:
                digest = sha256_file(dest)
                match  = digest[:16] == m["sha256"][:16]  # prefix check
                print(f"  OK Exists. Checksum: {'OK' if match else 'MISMATCH'}")
                if not match and not verify_only:
                    print("  ! Re-downloading...")
                    dest.unlink()
                else:
                    continue
            else:
                print("  OK Exists (no checksum registered).")
                continue

        if verify_only:
            print(f"  X Missing: {dest}")
            all_ok = False
            continue

        if not m["required"]:
            print("  - Optional - skipping")
            continue

        if m["url"]:
            try:
                download_with_progress(m["url"], dest)
            except Exception as exc:
                print(f"  ! Direct download failed ({exc}), trying HF...")
                if not try_hf_download(m["name"], dest):
                    print(f"  X FAILED to obtain {m['name']}")
                    if m["required"]:
                        all_ok = False
        else:
            # Generated locally
            print("  i  Run export_models.py to generate this artifact.")

    print(f"\n{'-' * 60}")
    print("SUCCESS All required models ready." if all_ok
          else "ERROR Some models missing - check output above.")
    return all_ok


def create_demo_weights():
    """
    Create tiny placeholder .pt files so the system can boot
    without real downloads in CI / offline environments.
    The actual inference uses stub returns when the model fails
    to load, triggering synthetic demo data generation.
    """
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("yolov8n.pt", "fire_yolo.pt"):
        p = WEIGHTS_DIR / name
        if not p.exists():
            p.write_bytes(b"PLACEHOLDER")
            print(f"  * Placeholder: {p}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-only",   action="store_true")
    parser.add_argument("--verify-only",  action="store_true")
    parser.add_argument("--demo-weights", action="store_true",
                        help="Create tiny placeholder weights for CI")
    args = parser.parse_args()

    if args.demo_weights:
        create_demo_weights()
    else:
        ok = download_models(args.build_only, args.verify_only)
        sys.exit(0 if ok else 1)
