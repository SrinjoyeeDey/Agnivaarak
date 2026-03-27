#!/usr/bin/env python3
"""
scripts/demo_simulation.py
===========================
Standalone demo script that requires NO camera, NO model weights,
and NO hardware.  Produces realistic console output for hackathon
presentations.

Usage:
    python scripts/demo_simulation.py
    python scripts/demo_simulation.py --duration 60   # run 60 s
    python scripts/demo_simulation.py --speed 2       # 2× playback

Example output:
    📷 Camera at angle 0°
    🔥 Fire detected at (320, 240) | confidence=0.89 | intensity=MEDIUM
    💧 Activating nozzle_2 at 90° with intensity MEDIUM
    📷 Camera at angle 15°
    ⚠️  Human detected near fire – switching to SURROUND mode
    🌊 Activating nozzle_2 at 90° with intensity MEDIUM | mode=SURROUND
    📷 Camera at angle 45°
    🔥 Second fire detected at (120, 300) | intensity=HIGH
    💧 Activating nozzle_1 at 0° with intensity HIGH
    📡 MQTT → firesuppressor/1/fire_event
"""

import argparse
import json
import math
import random
import time
import sys
from dataclasses import dataclass, field
from typing import List, Optional


# ── ANSI colours ─────────────────────────────────────────
R  = "\033[91m"   # red
Y  = "\033[93m"   # yellow
G  = "\033[92m"   # green
B  = "\033[94m"   # blue
M  = "\033[95m"   # magenta
C  = "\033[96m"   # cyan
W  = "\033[97m"   # white
DIM = "\033[2m"
RST = "\033[0m"


def c(color, text): return f"{color}{text}{RST}"


# ── Scenario script ───────────────────────────────────────
# Each event: (time_offset_s, event_type, params)
SCENARIO = [
    (0,  "sweep",  {"start": 0,   "end": 360, "duration": 30}),
    (3,  "fire",   {"x": 320, "y": 240, "intensity": "MEDIUM", "confidence": 0.89}),
    (6,  "human",  {"x": 380, "y": 260}),
    (10, "fire",   {"x": 120, "y": 300, "intensity": "HIGH",   "confidence": 0.93}),
    (14, "clear",  {"fire_id": 0}),
    (18, "fire",   {"x": 500, "y": 180, "intensity": "LOW",    "confidence": 0.71}),
    (20, "human",  None),
    (22, "fire",   {"x": 220, "y": 350, "intensity": "HIGH",   "confidence": 0.95}),
    (26, "overload", {}),
    (30, "estop",  {}),
    (32, "clear_estop", {}),
    (35, "fire",   {"x": 400, "y": 200, "intensity": "LOW",    "confidence": 0.68}),
    (40, "resolved", {}),
]

NOZZLE_ANGLES = {1: 0, 2: 90, 3: 180, 4: 270}

def closest_nozzle(angle: float) -> int:
    return min(NOZZLE_ANGLES,
               key=lambda nid: abs((angle - NOZZLE_ANGLES[nid] + 180) % 360 - 180))

def pixel_to_angle(px: int, cam_angle: float,
                   frame_w: int = 640, fov: float = 90.0) -> float:
    norm   = (px / frame_w) - 0.5
    offset = norm * fov
    return (cam_angle + offset) % 360

def intensity_score(level: str) -> float:
    return {"LOW": 0.25, "MEDIUM": 0.55, "HIGH": 0.85}[level]

def print_separator():
    print(c(DIM, "─" * 65))

def print_mqtt(topic: str, payload: dict):
    print(c(C, f"  📡 MQTT → {topic}"))
    print(c(DIM, f"     {json.dumps(payload, separators=(',', ':'))[:80]}"))

def run_demo(duration: float = 45.0, speed: float = 1.0):
    print()
    print(c(R, "╔══════════════════════════════════════════════════════════╗"))
    print(c(R, "║") + c(W, "      🔥 FireSuppressor v1.0 – DEMO SIMULATION           ") + c(R, "║"))
    print(c(R, "║") + c(Y, "   ⚠️  ALL OUTPUTS ARE SIMULATED – NO REAL HARDWARE      ") + c(R, "║"))
    print(c(R, "╚══════════════════════════════════════════════════════════╝"))
    print()

    t_start    = time.time()
    cam_angle  = 0.0
    fires      = []       # active fires
    humans     = []       # active humans
    nozzles    = {i: {"active": False, "pressure": "OFF"} for i in range(1, 5)}
    estop      = False
    frame_id   = 0

    scenario_idx = 0

    while True:
        elapsed = (time.time() - t_start) * speed
        if elapsed > duration:
            break

        frame_id  += 1
        cam_angle  = (cam_angle + 1.5) % 360

        # ── Camera sweep log every 15° ─────────────────────
        if frame_id % 10 == 0:
            print(c(C, f"  📷 Camera at angle {cam_angle:.0f}°"))

        # ── Trigger scenario events ─────────────────────────
        while (scenario_idx < len(SCENARIO) and
               SCENARIO[scenario_idx][0] <= elapsed):
            _, ev_type, params = SCENARIO[scenario_idx]
            scenario_idx += 1
            _handle_event(ev_type, params, fires, humans, nozzles,
                          cam_angle, estop)

        # ── Continuous detection prints ─────────────────────
        if fires and not estop:
            for i, fire in enumerate(fires):
                fire_angle = pixel_to_angle(fire["x"], cam_angle)
                nozzle_id  = closest_nozzle(fire_angle)
                level      = fire["intensity"]
                near_human = any(
                    abs(h["x"] - fire["x"]) < 80 for h in humans)

                mode = "SURROUND" if near_human else "DIRECT"
                emoji = "🌊" if near_human else "💧"

                if frame_id % 8 == i:
                    print(c(Y, f"  🔥 Fire #{i+1} at pixel ({fire['x']},{fire['y']}) "
                               f"→ angle {fire_angle:.1f}°  "
                               f"confidence={fire['confidence']:.2f}  "
                               f"intensity={level}"))
                    if near_human:
                        print(c(M, f"  ⚠️  Human detected near fire #{i+1} – "
                                   "switching to SURROUND mode"))
                    print(c(B, f"  {emoji} Activating nozzle_{nozzle_id} at "
                               f"{NOZZLE_ANGLES[nozzle_id]}° with intensity {level} "
                               f"| mode={mode}"))
                    nozzles[nozzle_id] = {"active": True, "pressure": level}

                    # MQTT output every 3 fires
                    if frame_id % 24 == 0:
                        print_mqtt(
                            f"firesuppressor/1/fire_event",
                            {"device": 1, "fire_angle": round(fire_angle, 1),
                             "intensity": intensity_score(level),
                             "level": level, "nozzle_id": nozzle_id})

        elif estop:
            if frame_id % 30 == 0:
                print(c(R, "  ⛔ EMERGENCY STOP ACTIVE – all nozzles offline"))

        time.sleep(0.12 / speed)

    print()
    print_separator()
    print(c(G, "  ✅ Demo complete. Summary:"))
    print(c(W, f"     Frames processed : {frame_id}"))
    print(c(W, f"     Duration         : {elapsed:.1f}s"))
    print(c(W, f"     Peak fires       : {len(fires)}"))
    print_separator()


def _handle_event(ev_type, params, fires, humans, nozzles,
                  cam_angle, estop):
    print_separator()
    if ev_type == "fire":
        fires.append(params)
        print(c(R, f"  🔥 Fire detected at ({params['x']},{params['y']}) "
                   f"| confidence={params['confidence']} "
                   f"| intensity={params['intensity']}"))
    elif ev_type == "human":
        if params:
            humans.append(params)
            print(c(M, f"  👤 Human detected at ({params['x']},{params['y']})"))
        else:
            humans.clear()
            print(c(G, "  👤 Human cleared from zone"))
    elif ev_type == "clear":
        if fires:
            fires.pop(0)
        print(c(G, "  ✅ Fire #1 suppressed – removing from queue"))
    elif ev_type == "overload":
        print(c(Y, "  ⚡ OVERLOAD: >4 active fires – boosting pressure to HIGH"))
        print(c(C, "  📡 MQTT → firesuppressor/global/assist_request"))
        print_mqtt("firesuppressor/global/assist_request",
                   {"requesting_node": 1, "overloaded": True, "active_fires": 5})
    elif ev_type == "estop":
        print(c(R, "  ⛔ EMERGENCY STOP ENGAGED (via REST /emergency-stop)"))
        for nid in nozzles:
            nozzles[nid] = {"active": False, "pressure": "OFF"}
        print(c(R, "  ⛔ All nozzles deactivated"))
    elif ev_type == "clear_estop":
        print(c(G, "  ✅ Emergency stop cleared. Resuming normal operation."))
    elif ev_type == "resolved":
        fires.clear()
        print(c(G, "  ✅ All fires resolved. System returning to standby."))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="FireSuppressor demo simulation")
    p.add_argument("--duration", type=float, default=45.0,
                   help="Simulation duration in seconds")
    p.add_argument("--speed",    type=float, default=1.0,
                   help="Playback speed multiplier")
    args = p.parse_args()
    run_demo(args.duration, args.speed)
