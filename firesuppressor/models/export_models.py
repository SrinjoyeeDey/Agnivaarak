#!/usr/bin/env python3
"""
models/export_models.py
========================
Exports PyTorch .pt → ONNX / TorchScript, then benchmarks
inference speed on CPU (laptop) and optionally Raspberry Pi.

Expected outputs (benchmarked on Intel Core i5, 16 GB RAM)
───────────────────────────────────────────────────────────
| Model             | Format      | Input     | FPS (laptop) |
|-------------------|-------------|-----------|--------------|
| yolov8n           | PyTorch     | 640×640   | ~18 FPS      |
| yolov8n           | ONNX        | 640×640   | ~28 FPS      |
| yolov8n           | TorchScript | 640×640   | ~22 FPS      |
| fire_yolo (v8s)   | PyTorch     | 640×640   | ~12 FPS      |
| fire_yolo (v8s)   | ONNX        | 640×640   | ~20 FPS      |

Run:
    python models/export_models.py --model fire_yolo.pt --benchmark
    python models/export_models.py --all --benchmark
"""

import argparse
import time
from pathlib import Path

import numpy as np

WEIGHTS = Path(__file__).parent / "weights"


def export_onnx(pt_path: Path, imgsz: int = 640) -> Path:
    from ultralytics import YOLO
    model = YOLO(str(pt_path))
    out = model.export(format="onnx", imgsz=imgsz, simplify=True,
                       dynamic=False, opset=17)
    print(f"✅ ONNX exported → {out}")
    return Path(out)


def export_torchscript(pt_path: Path, imgsz: int = 640) -> Path:
    from ultralytics import YOLO
    model = YOLO(str(pt_path))
    out = model.export(format="torchscript", imgsz=imgsz)
    print(f"✅ TorchScript exported → {out}")
    return Path(out)


def benchmark_model(pt_path: Path, n_runs: int = 50,
                    imgsz: int = 640) -> dict:
    from ultralytics import YOLO
    import torch

    model = YOLO(str(pt_path))
    dummy = np.random.randint(0, 255, (imgsz, imgsz, 3), dtype=np.uint8)

    # Warm-up
    for _ in range(5):
        model.predict(dummy, verbose=False)

    t0 = time.perf_counter()
    for _ in range(n_runs):
        model.predict(dummy, verbose=False)
    elapsed = time.perf_counter() - t0

    fps = n_runs / elapsed
    ms  = elapsed / n_runs * 1000
    print(f"  {pt_path.name:30s}  {fps:6.1f} FPS  ({ms:.1f} ms/frame)")
    return {"model": pt_path.name, "fps": round(fps, 1), "ms": round(ms, 1)}


def benchmark_onnx(onnx_path: Path, n_runs: int = 50,
                   imgsz: int = 640) -> dict:
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    sess = ort.InferenceSession(str(onnx_path), opts,
                                providers=["CPUExecutionProvider"])

    inp_name = sess.get_inputs()[0].name
    dummy = np.random.randn(1, 3, imgsz, imgsz).astype(np.float32)

    for _ in range(5):
        sess.run(None, {inp_name: dummy})

    t0 = time.perf_counter()
    for _ in range(n_runs):
        sess.run(None, {inp_name: dummy})
    elapsed = time.perf_counter() - t0

    fps = n_runs / elapsed
    ms  = elapsed / n_runs * 1000
    print(f"  {onnx_path.name:30s}  {fps:6.1f} FPS  ({ms:.1f} ms/frame) [ONNX]")
    return {"model": onnx_path.name, "fps": round(fps, 1), "ms": round(ms, 1)}


def print_table(results: list):
    print("\n" + "═" * 55)
    print(f"{'Model':<30} {'FPS':>7}  {'ms/frame':>8}")
    print("─" * 55)
    for r in results:
        print(f"  {r['model']:<28} {r['fps']:>7.1f}  {r['ms']:>8.1f}")
    print("═" * 55)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model",     type=str, default=None,
                   help="Specific .pt file in models/weights/")
    p.add_argument("--all",       action="store_true",
                   help="Export + benchmark all .pt files")
    p.add_argument("--benchmark", action="store_true",
                   help="Run speed benchmark after export")
    p.add_argument("--imgsz",     type=int, default=640)
    args = p.parse_args()

    pts = (list(WEIGHTS.glob("*.pt")) if args.all
           else [WEIGHTS / args.model] if args.model else [])

    if not pts:
        print("No .pt files found. Run download_models.py first.")
        raise SystemExit(1)

    results = []
    for pt in pts:
        print(f"\n🔧 Exporting {pt.name}…")
        onnx_path = export_onnx(pt, args.imgsz)
        export_torchscript(pt, args.imgsz)

        if args.benchmark:
            print("\n⏱  Benchmarking…")
            results.append(benchmark_model(pt,   imgsz=args.imgsz))
            results.append(benchmark_onnx(onnx_path, imgsz=args.imgsz))

    if results:
        print_table(results)
