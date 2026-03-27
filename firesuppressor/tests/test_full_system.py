"""
tests/test_full_system.py
==========================
Pytest test suite covering:
  • Vision pipeline (fire/human detection, intensity)
  • Decision engine (direct/surround/overload/estop)
  • Fire queue (priority, IoU matching, staleness)
  • Nozzle selector (angle → nozzle mapping)
  • Nozzle controller (simulated path)
  • FastAPI endpoints (status, manual-control, emergency-stop)
  • WebSocket connection

Run:
    pytest tests/ -v --tb=short
    pytest tests/ -v --cov=. --cov-report=term-missing
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from httpx import AsyncClient

# ── Fix import paths ──────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
def make_fire(x=100, y=100, w=60, h=80, level="MEDIUM", angle=90.0):
    return {
        "id"        : "test001",
        "bbox"      : [x, y, w, h],
        "confidence": 0.85,
        "class_name": "fire",
        "angle"     : angle,
        "intensity" : {"score": 0.55, "level": level,
                       "pressure": {"label": level, "psi_equiv": 3}},
    }

def make_human(x=200, y=150, w=30, h=80):
    return {"bbox": [x, y, w, h], "confidence": 0.78}

def make_frame(w=640, h=480):
    return np.zeros((h, w, 3), dtype=np.uint8)

def orange_frame(w=640, h=480):
    """Frame with orange region simulating fire."""
    f = np.zeros((h, w, 3), dtype=np.uint8)
    f[100:200, 200:350, 2] = 220   # R channel
    f[100:200, 200:350, 1] = 90    # G channel
    return f


# ─────────────────────────────────────────────────────────
# IntensityAnalyzer
# ─────────────────────────────────────────────────────────
class TestIntensityAnalyzer:
    def setup_method(self):
        from vision.intensity_analyzer import IntensityAnalyzer
        self.analyzer = IntensityAnalyzer()

    def test_empty_bbox_returns_low(self):
        frame  = make_frame()
        result = self.analyzer.estimate(frame, [0, 0, 0, 0])
        assert result["level"] == "LOW"
        assert result["score"] == 0.0

    def test_large_bright_orange_is_high(self):
        frame  = orange_frame()
        # Large fire covering most frame
        result = self.analyzer.estimate(frame, [0, 0, 640, 480])
        assert result["level"] in ("MEDIUM", "HIGH")

    def test_tiny_box_is_low(self):
        frame  = orange_frame()
        result = self.analyzer.estimate(frame, [200, 100, 5, 5])
        assert result["level"] == "LOW"

    def test_score_in_range(self):
        frame  = orange_frame()
        result = self.analyzer.estimate(frame, [100, 80, 200, 150])
        assert 0.0 <= result["score"] <= 1.0

    def test_pressure_keys_present(self):
        frame  = make_frame()
        result = self.analyzer.estimate(frame, [50, 50, 100, 100])
        assert "label" in result["pressure"]
        assert "psi_equiv" in result["pressure"]


# ─────────────────────────────────────────────────────────
# FireQueue
# ─────────────────────────────────────────────────────────
class TestFireQueue:
    def setup_method(self):
        from logic.fire_queue import FireQueue
        self.q = FireQueue(max_targets=4)

    def test_add_single_fire(self):
        self.q.update([make_fire()])
        assert len(self.q.all()) == 1

    def test_iou_matching_updates_existing(self):
        self.q.update([make_fire(x=100, y=100)])
        self.q.update([make_fire(x=102, y=101)])   # slight shift → same target
        assert len(self.q.all()) == 1

    def test_distinct_fires_add_separately(self):
        self.q.update([make_fire(x=10, y=10),
                       make_fire(x=500, y=400)])
        assert len(self.q.all()) == 2

    def test_high_priority_first(self):
        self.q.update([make_fire(level="LOW"),
                       make_fire(x=300, level="HIGH")])
        top = self.q.top(2)
        assert top[0]["level"] == "HIGH"

    def test_stale_fires_removed(self):
        from logic.fire_queue import STALE_TIMEOUT
        self.q.update([make_fire()])
        # Patch last_seen to simulate staleness
        for t in self.q._targets.values():
            t.last_seen = time.time() - STALE_TIMEOUT - 1
        self.q.update([])   # trigger cleanup
        assert len(self.q.all()) == 0

    def test_max_targets_respected(self):
        fires = [make_fire(x=i*50, y=i*30) for i in range(10)]
        self.q.update(fires)
        assert len(self.q.all()) <= 8   # buffer = max * 2


# ─────────────────────────────────────────────────────────
# NozzleSelector
# ─────────────────────────────────────────────────────────
class TestNozzleSelector:
    def setup_method(self):
        from logic.nozzle_selector import NozzleSelector
        self.sel = NozzleSelector()

    def test_0_deg_selects_nozzle1(self):
        assert self.sel.closest(0.0) == 1

    def test_90_deg_selects_nozzle2(self):
        assert self.sel.closest(90.0) == 2

    def test_180_deg_selects_nozzle3(self):
        assert self.sel.closest(180.0) == 3

    def test_270_deg_selects_nozzle4(self):
        assert self.sel.closest(270.0) == 4

    def test_45_deg_selects_nozzle1_or_2(self):
        assert self.sel.closest(45.0) in (1, 2)

    def test_359_deg_selects_nozzle1(self):
        assert self.sel.closest(359.0) == 1

    def test_ranked_returns_all_4(self):
        ranked = self.sel.ranked(45.0)
        assert len(ranked) == 4
        assert set(ranked) == {1, 2, 3, 4}


# ─────────────────────────────────────────────────────────
# DecisionEngine
# ─────────────────────────────────────────────────────────
class TestDecisionEngine:
    def setup_method(self):
        from logic.fire_queue import FireQueue
        from logic.decision_engine import DecisionEngine, Action
        self.Action = Action
        self.fq     = FireQueue()
        self.engine = DecisionEngine(self.fq, node_id=1)

    def test_direct_spray_no_humans(self):
        actions = self.engine.decide([make_fire(angle=90.0)], [])
        assert len(actions) == 1
        assert actions[0].mode == self.Action.DIRECT

    def test_surround_when_human_nearby(self):
        # Fire at (100,100), human at (130,120) → within 60 px radius
        fire  = make_fire(x=100, y=100, angle=90.0)
        human = make_human(x=130, y=120)
        actions = self.engine.decide([fire], [human])
        assert actions[0].mode == self.Action.SURROUND

    def test_emergency_stop_returns_stop_action(self):
        self.engine.trigger_emergency_stop()
        actions = self.engine.decide([make_fire()], [])
        assert actions[0].mode == self.Action.STOP

    def test_clear_emergency_stop(self):
        self.engine.trigger_emergency_stop()
        self.engine.clear_emergency_stop()
        actions = self.engine.decide([make_fire(angle=0.0)], [])
        assert actions[0].mode != self.Action.STOP

    def test_high_intensity_pressure(self):
        fire = make_fire(level="HIGH", angle=90.0)
        actions = self.engine.decide([fire], [])
        assert actions[0].pressure == "HIGH"

    def test_overload_boosts_pressure(self):
        # 5 fires → overload → all should be HIGH
        fires = [make_fire(x=i*100, y=i*50, level="LOW", angle=i*15.0)
                 for i in range(5)]
        actions = self.engine.decide(fires, [])
        pressures = {a.pressure for a in actions}
        assert "HIGH" in pressures


# ─────────────────────────────────────────────────────────
# NozzleController (simulated)
# ─────────────────────────────────────────────────────────
class TestNozzleControllerSim:
    def setup_method(self):
        from hardware.nozzle_controller import NozzleController
        from logic.decision_engine import Action
        self.ctrl   = NozzleController(simulated=True)
        self.Action = Action

    def test_initial_state_all_off(self):
        for n in self.ctrl.status():
            assert not n["active"]

    def test_execute_activates_nozzle(self):
        action = self.Action(nozzle_id=2, angle=90.0,
                             mode=self.Action.DIRECT, pressure="MEDIUM",
                             fire_id="f1")
        self.ctrl.execute(action)
        status = {n["id"]: n for n in self.ctrl.status()}
        assert status[2]["active"]
        assert status[2]["pressure"] == "MEDIUM"

    def test_emergency_stop_deactivates_all(self):
        action = self.Action(nozzle_id=1, angle=0.0,
                             mode=self.Action.DIRECT, pressure="HIGH",
                             fire_id="f1")
        self.ctrl.execute(action)
        self.ctrl.emergency_stop()
        for n in self.ctrl.status():
            assert not n["active"]

    def test_manual_activate(self):
        ok = self.ctrl.manual_activate(3, "HIGH")
        assert ok
        status = {n["id"]: n for n in self.ctrl.status()}
        assert status[3]["active"]

    def test_invalid_nozzle_manual(self):
        ok = self.ctrl.manual_activate(99, "HIGH")
        assert not ok

    def test_cooldown_deactivates_stale(self):
        action = self.Action(nozzle_id=1, angle=0.0,
                             mode=self.Action.DIRECT, pressure="LOW",
                             fire_id="f1")
        self.ctrl.execute(action)
        # Force old timestamp
        self.ctrl._nozzles[1].last_activated = time.time() - 10
        self.ctrl.cooldown()
        status = {n["id"]: n for n in self.ctrl.status()}
        assert not status[1]["active"]


# ─────────────────────────────────────────────────────────
# FastAPI Endpoints
# ─────────────────────────────────────────────────────────
@pytest.fixture
def app_and_mocks():
    from hardware.nozzle_controller import NozzleController
    from logic.fire_queue import FireQueue
    from logic.decision_engine import DecisionEngine
    from backend.app import create_app

    nozzle   = NozzleController(simulated=True)
    fq       = FireQueue()
    decision = DecisionEngine(fq, node_id=1)
    state    = {
        "node_id"       : 1,
        "zone"          : "NORTH",
        "fire_detected" : False,
        "fires"         : [],
        "humans"        : [],
        "nozzles"       : nozzle.status(),
        "alerts"        : [],
        "camera_angle"  : 0.0,
        "emergency_stop": False,
    }
    app = create_app(state, nozzle, decision)
    return app, state, nozzle, decision


@pytest.mark.asyncio
async def test_root_health(app_and_mocks):
    app, *_ = app_and_mocks
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "FireSuppressor"


@pytest.mark.asyncio
async def test_status_endpoint(app_and_mocks):
    app, state, *_ = app_and_mocks
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "fire_detected" in body
    assert "nozzles" in body


@pytest.mark.asyncio
async def test_manual_control_success(app_and_mocks):
    app, *_ = app_and_mocks
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/manual-control",
            json={"nozzle_id": 2, "pressure": "HIGH"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_manual_control_blocked_during_estop(app_and_mocks):
    app, state, *_ = app_and_mocks
    state["emergency_stop"] = True
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/manual-control",
            json={"nozzle_id": 1, "pressure": "LOW"})
    assert resp.status_code == 423


@pytest.mark.asyncio
async def test_emergency_stop_endpoint(app_and_mocks):
    app, state, *_ = app_and_mocks
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/emergency-stop")
    assert resp.status_code == 200
    assert state["emergency_stop"] is True


@pytest.mark.asyncio
async def test_clear_emergency_stop(app_and_mocks):
    app, state, *_ = app_and_mocks
    state["emergency_stop"] = True
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/clear-emergency-stop")
    assert resp.status_code == 200
    assert state["emergency_stop"] is False


@pytest.mark.asyncio
async def test_alerts_empty(app_and_mocks):
    app, *_ = app_and_mocks
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/alerts")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
