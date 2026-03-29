# 🔥 FireSuppressor v1.0
### Autonomous Fire Detection & Suppression System

> **Development Version: 2026.03.27-v21 (4-Nozzle / Expert Classification)**
>
> ⚠️ **All actuator code is SIMULATED by default. No real water is released unless `--real-hardware` is explicitly set on a properly wired Raspberry Pi or Arduino.**

---

## 🌟 New Features (v21)

- **Fire Authenticity Verification**: Advanced temporal analysis (flicker, motion, shape variance) to eliminate false positives from screens or reflections.
- **Expert Classification**: Real-time distinction between **NORMAL (Class A)** and **Blue Flame (Class B)** fires with optimized HSV thresholds.
- **Emergency Dashboard**: Dedicated surveillance tab with real-time sensor graphs (Temperature, IR, Humidity), SOS alerts, and nearby station tracking.
- **Hardware Sensor Fusion**: Integrated physical validation using infrared and thermal sensor data.
- **Arduino Serial Bridge**: Robust 1:1 decision-to-hardware communication protocol for precise pan/tilt and pump control.
- **Intensity-Aware Physics**: Simulated pressure gauge that reacts dynamically to fire severity and suppression activity.

---

## Quick Start

### 🖥️ Windows (Automated)
If you are on Windows, simply run the setup script:
```powershell
./setup_windows.bat
```
This will create a virtual environment, install dependencies, and download the model weights.

### 🐧 Linux / 🍎 macOS
```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download model weights
python models/download_models.py
```

### 🚀 Running the System

1. **Start the Backend Node** (Terminal 1)
```bash
# Core execution with camera 0
python firesuppressor/main.py --camera 0

# Expert simulation mode (authenticity tests)
python firesuppressor/main.py --demo --simulate-fake-fire --simulate-sensors
```

2. **Start the Dashboard** (Terminal 2)
```bash
cd firesuppressor/frontend
npm install
npm start
```
Open [http://localhost:3000](http://localhost:3000) to view the live dashboard.

---

## CLI Reference

| Flag | Description |
|------|-------------|
| `--demo` | Synthetic simulation mode (no camera required) |
| `--camera <id>` | Use local webcam index (e.g., 0) |
| `--video <path>` | Process a recorded video file |
| `--real-hardware` | ⚠️ Enable GPIO/Serial communication for physical actuators |
| `--simulate-sensors` | Add real-time jitter and heat/IR variance to sensor readings |
| `--simulate-fake-fire` | Force low authenticity scores (for screen testing) |
| `--simulate-real-fire` | Force high authenticity scores (physical fire test) |
| `--collect-data` | Save detection frames for model fine-tuning |

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                           INDOOR MALL NODE (v21)                              │
│                                                                               │
│  ┌──────────┐    ┌─────────────┐    ┌───────────────────────────────────┐    │
│  │FrameSource│──▶│FireDetector │    │ FireAuthenticityAnalyzer (NEW)    │    │
│  │(OpenCV)   │    │(YOLOv8s)    │──▶ │ (Flicker/Motion/Sensor Fusion)    │    │
│  └──────────┘    └──────┬──────┘    └─────────────────┬─────────────────┘    │
│                         │fires                        │verified score        │
│                         ▼                             ▼                      │
│                  ┌──────────────────────────────────────────────┐            │
│                  │           DecisionEngine (Expert)            │            │
│                  │  (1:1 Assignment / Intensity-Aware Scaling)  │            │
│                  └──────────────┬───────────────────────────────┘            │
│                                 │ Actions                                    │
│                                 ▼                                            │
│                  ┌─────────────────────────────────────────────┐             │
│                  │            Hardware Controller              │             │
│                  │  ┌──────────────────┐  ┌────────────────┐  │             │
│                  │  │ Nozzle (GPIO)    │  │ Arduino Serial │  │             │
│                  │  └──────────────────┘  └────────────────┘  │             │
│                  └──────────────┬─────────────────────────────┘             │
│                                 │                                            │
│            ┌────────────────────┼─────────────────────┐                      │
│            ▼                    ▼                     ▼                      │
│      Nozzle 1 (0°)        Nozzle 2 (90°)        ...   Nozzle 4 (270°)        │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │  FastAPI (v1.0) /status /emergency /sensors /ws           │              │
│  │  + MQTT Enhanced Event Bus (Real-time telemetry)           │◀── Other Nodes│
│  └────────────────────────────────────────────────────────────┘              │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## AI & Vision Pipeline

| Component | Method | Purpose |
|-------|--------|---------|
| **Primary Detector** | YOLOv8s | Detect fire & smoke bounding boxes (mAP50: 0.87) |
| **Authenticity** | Temporal | Flicker analysis (10Hz) & variance tracking |
| **Classifier** | HSV/Expert | Class A (Orange/Yellow) vs Class B (Blue) distinction |
| **Human Safe** | YOLOv8n | 60px safety radius; shifts to "SURROUND" mode near humans |

---

## API Reference (Emergency v2)

```bash
# System Readiness
curl http://localhost:8000/status

# Real-time Sensors
curl http://localhost:8000/sensors

# Trigger SOS Dispatch
curl -X POST http://localhost:8000/sos-alert \
  -H "Content-Type: application/json" \
  -d '{"location": "Section-A", "severity": "CRITICAL"}'

# Speaker Announcement
curl -X POST http://localhost:8000/speaker-control \
  -H "Content-Type: application/json" \
  -d '{"message": "Fire detected in North Wing. Evacuate!"}'

# Manual Override
curl -X POST http://localhost:8000/manual-control \
  -H "Content-Type: application/json" \
  -d '{"nozzle_id": 1, "pressure": "HIGH", "agent": "FOAM"}'

# Emergency Snapshot Retrieval
# Photos are automatically saved to /emergency_snapshots and served via
# http://localhost:8000/snapshots/<filename>.jpg
```

---

## Project Structure

```
firesuppressor/
├── main.py                    ← Orchestrator (entry point)
├── vision/
│   ├── fire_detector.py       ← YOLOv8 detection
│   ├── fire_authenticity.py   ← NEW: Flicker/Motion analysis
│   └── fire_classifier.py     ← Expert Class A/B logic
├── logic/
│   ├── decision_engine.py     ← Real-time strategy & assignment
│   └── fire_queue.py          ← Priority-based target tracking
├── hardware/
│   ├── arduino_comm.py        ← NEW: Serial bridge for Arduino
│   └── nozzle_controller.py   ← 4-Port GPIO abstraction
├── network/
│   ├── mqtt_client.py         ← Telemetry broadcasting
│   └── emergency_notifier.py  ← Screenshot & dispatch logic
├── backend/
│   └── app.py                 ← FastAPI REST/WebSocket server
├── frontend/                  ← React Dashboard (Pressure Gauge/Sensor Graphs)
└── tests/                     ← Comprehensive Pytest suite
```

---

## Safety & Compliance

1. **Self-Monitoring**: System checks infrared/heat variance before activation.
2. **Human Safety**: Active human tracking disables direct spray zones.
3. **Hardware Watchdog**: Arduino bridge resets to safe state if serial heartbeat is lost.
4. **Non-Destructive Testing**: Full simulation mode available using `--demo` and `--simulate-fake-fire`.
