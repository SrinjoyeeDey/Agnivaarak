# 🔥 FireSuppressor v1.0
### Autonomous Fire Detection & Suppression System

> **Hackathon Build · Indoor Mall · 3-Day Sprint**
> 
> ⚠️ **All actuator code is SIMULATED by default. No real water is released unless `--real-hardware` is explicitly set on a properly wired Raspberry Pi.**

---

## Quick Start (Laptop / Demo Mode)

```bash
# 1. Clone
git clone https://github.com/your-team/firesuppressor
cd firesuppressor

# 2. Create virtual environment (Python 3.10 required)
python3.10 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download / create placeholder model weights
python models/download_models.py   # real download (~200 MB)
# OR for offline / CI:
python models/download_models.py --demo-weights

# 5. Run full demo (no camera, no hardware)
python main.py --demo

# 6. In a second terminal – start React dashboard
cd frontend && npm install && npm start
# Open http://localhost:3000
```

---

## Docker (All-in-one)

```bash
# Build
docker build -t firesuppressor:latest .

# Run single node (demo)
docker run --rm -p 8000:8000 -e DEMO_MODE=1 firesuppressor:latest

# Run 3-node simulation + MQTT broker + frontend
docker-compose up --build
```

After startup:
| Service       | URL                        |
|---------------|----------------------------|
| API Node 1    | http://localhost:8001/docs  |
| API Node 2    | http://localhost:8002/docs  |
| API Node 3    | http://localhost:8003/docs  |
| Dashboard     | http://localhost:3000       |
| MQTT          | localhost:1883              |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     INDOOR MALL NODE                          │
│                                                              │
│  ┌──────────┐   ┌───────────┐   ┌──────────────────────┐   │
│  │FrameSource│──▶│FireDetector│  │HumanDetector (COCO)  │   │
│  │(OpenCV)  │   │(YOLOv8s)  │  └──────────┬───────────┘   │
│  └──────────┘   └─────┬─────┘             │               │
│                       │fires               │humans          │
│                       ▼                   ▼               │
│               ┌───────────────────────────────┐           │
│               │     IntensityAnalyzer          │           │
│               │  (bbox area + brightness + HSV)│           │
│               └──────────────┬────────────────┘           │
│                              │                             │
│                              ▼                             │
│                    ┌──────────────────┐                   │
│                    │  DecisionEngine  │                   │
│                    │  ┌────────────┐  │                   │
│                    │  │ FireQueue  │  │                   │
│                    │  │(priority)  │  │                   │
│                    │  └────────────┘  │                   │
│                    │  ┌────────────┐  │                   │
│                    │  │NozzleSel.  │  │                   │
│                    │  │(angle map) │  │                   │
│                    │  └────────────┘  │                   │
│                    └────────┬─────────┘                   │
│                             │ Actions                      │
│                             ▼                             │
│                  ┌─────────────────────┐                  │
│                  │  NozzleController   │                  │
│                  │  (SIM or GPIO/PWM)  │                  │
│                  └─────────────────────┘                  │
│                             │                             │
│            ┌────────────────┼──────────────┐             │
│            ▼                ▼              ▼             │
│      nozzle_1 (0°)   nozzle_2 (90°)  ...  nozzle_4 (270°)│
│                                                          │
│  ┌────────────────────────────────┐                      │
│  │  FastAPI  /status  /ws  /alerts│                      │
│  │  + MQTT publish (paho)         │◀─────── Other nodes  │
│  └────────────────────────────────┘                      │
└──────────────────────────────────────────────────────────────┘
```

---

## AI Models

| Model | Source | Purpose | mAP50 |
|-------|--------|---------|-------|
| YOLOv8s (fire fine-tuned) | [keremberke/yolov8s-fire-detection](https://huggingface.co/keremberke/yolov8s-fire-detection) | Detect fire & smoke bounding boxes | ~0.87 |
| YOLOv8n (COCO) | [Ultralytics](https://github.com/ultralytics/assets) | Human detection (person class) | ~0.55 |
| Colour HSV fallback | Rule-based | Offline fire detection | — |

---

## API Reference

```bash
# Health
curl http://localhost:8000/

# Full status snapshot
curl http://localhost:8000/status

# Last 50 alerts
curl http://localhost:8000/alerts

# Manual nozzle activation
curl -X POST http://localhost:8000/manual-control \
  -H "Content-Type: application/json" \
  -d '{"nozzle_id": 2, "pressure": "HIGH"}'

# Emergency stop
curl -X POST http://localhost:8000/emergency-stop

# Clear emergency stop
curl -X POST http://localhost:8000/clear-emergency-stop

# WebSocket (curl example)
# wscat -c ws://localhost:8000/ws
```

---

## Training (Optional – Already Pre-trained)

```bash
# 1. Prepare dataset
export RF_API_KEY=your_roboflow_key
python models/train_fire_yolo.py --prep

# 2. Fine-tune YOLOv8s on fire dataset
python models/train_fire_yolo.py --train \
  --data data/fire.yaml \
  --epochs 50 \
  --batch 16 \
  --imgsz 640 \
  --lr 1e-3

# 3. Export to ONNX + benchmark
python models/export_models.py --all --benchmark
```

---

## Model Performance

| Model | Format | FPS (i5 CPU) | FPS (RPi 4) |
|-------|--------|-------------|-------------|
| YOLOv8n | PyTorch | ~18 | ~4 |
| YOLOv8n | ONNX | ~28 | ~7 |
| YOLOv8s (fire) | PyTorch | ~12 | ~2.5 |
| YOLOv8s (fire) | ONNX | ~20 | ~5 |

*Both models run concurrently; total pipeline: ~8–10 FPS on laptop CPU.*

---

## Testing

```bash
pytest tests/ -v --tb=short
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Safety Interlocks

1. **Simulation-first**: All actuators print logs; no GPIO unless `--real-hardware`
2. **Human exclusion**: 60 px radius → SURROUND mode (no direct spray)
3. **Emergency stop**: REST `/emergency-stop`, WS `{"cmd":"emergency_stop"}`, MQTT global topic
4. **Max nozzles**: Hard limit of 4 concurrent; excess → pressure boost, no new activations
5. **Cooldown**: Nozzles auto-deactivate 2 s after last fire detection
6. **Hardware interlock**: Physical NC e-stop button cuts main relay power rail

---

## 3-Day Gantt

```
Day 1 (Setup + Vision)
  AM: Environment, Docker, model download
  PM: Fire detector, human detector, intensity analyzer

Day 2 (Logic + Backend + Hardware)
  AM: Decision engine, fire queue, nozzle selector
  PM: Nozzle controller (sim), FastAPI endpoints, MQTT

Day 3 (Integration + Frontend + Demo)
  AM: React dashboard, WebSocket, multi-node test
  PM: Demo script, tests, documentation, presentation
```

---

## Project Structure

```
firesuppressor/
├── main.py                    ← Entry point
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── models/
│   ├── weights/               ← Downloaded .pt / .onnx files
│   ├── download_models.py     ← Fetch + verify weights
│   ├── export_models.py       ← ONNX export + benchmark
│   └── train_fire_yolo.py     ← Fine-tuning script
├── vision/
│   ├── capture.py             ← Frame source (webcam/video/demo)
│   ├── fire_detector.py       ← YOLOv8 fire/smoke detection
│   ├── human_detector.py      ← YOLOv8 person detection
│   └── intensity_analyzer.py  ← Rule-based intensity scoring
├── logic/
│   ├── decision_engine.py     ← Core decision logic + safety
│   ├── fire_queue.py          ← Priority target queue
│   └── nozzle_selector.py     ← Angle → nozzle mapping
├── hardware/
│   ├── nozzle_controller.py   ← Simulated + GPIO actuator
│   └── camera_controller.py   ← Pan-tilt simulation + PCA9685
├── network/
│   ├── mqtt_client.py         ← paho-mqtt wrapper
│   └── device_coordinator.py  ← Multi-node coordination
├── backend/
│   └── app.py                 ← FastAPI app factory
├── frontend/
│   ├── src/App.jsx            ← React dashboard
│   └── package.json
├── scripts/
│   └── demo_simulation.py     ← Standalone demo (no deps)
├── tests/
│   └── test_full_system.py    ← Full pytest suite
└── docs/
    ├── wiring_diagram.md
    └── mosquitto.conf
```

## Srinjoyee Dey
