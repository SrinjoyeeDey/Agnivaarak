"""
backend/app.py
==============
FastAPI application factory.

Endpoints
─────────────────────────────────────────────────────────────
GET  /                          → health check
GET  /status                    → full system state
GET  /alerts                    → last 50 fire alerts
POST /manual-control            → activate nozzle manually
POST /emergency-stop            → engage e-stop
POST /clear-emergency-stop      → release e-stop
WS   /ws                        → WebSocket live feed (10 Hz)
─────────────────────────────────────────────────────────────
"""

import asyncio
import json
import time
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from loguru import logger


# ── Request / Response schemas ────────────────────────────
class ManualControlRequest(BaseModel):
    nozzle_id: int = Field(..., ge=1, le=4,
                           description="Nozzle to activate (1–4)")
    pressure : str = Field("MEDIUM",
                            pattern="^(LOW|MEDIUM|HIGH|MAX|CRITICAL|OFF)$")
    agent    : str = Field("WATER", description="Suppression agent (WATER, FOAM, CO2, DRY_POWDER)")

class ManualControlResponse(BaseModel):
    success  : bool
    nozzle_id: int
    pressure : str
    message  : str

class NozzleDetailed(BaseModel):
    device_id : int
    pan       : float
    tilt      : float
    status    : str
    active    : bool
    mode      : str
    pressure  : str
    agent     : str | None = None
    fire_type : str | None = None
    intensity : str | None = None

class StatusResponse(BaseModel):
    node_id      : int
    zone         : str
    fire_detected: bool
    fires        : list
    humans       : list
    nozzles      : list[NozzleDetailed]
    camera_angle : float
    emergency_stop: bool
    emergency_mode: bool = False
    infrared     : float = 0.0
    temperature  : float = 25.0
    nearby_stations: list = []
    ts           : float


# ── WebSocket connection manager ──────────────────────────
class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connected (total={})", len(self._connections))

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# ── Factory ───────────────────────────────────────────────
def create_app(state: Dict[str, Any],
               nozzle_ctrl,
               decision) -> FastAPI:

    app = FastAPI(
        title       = "FireSuppressor API",
        description = "Autonomous fire detection & suppression system",
        version     = "1.0.0",
        docs_url    = "/docs",
        redoc_url   = "/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins  = ["*"],
        allow_methods  = ["*"],
        allow_headers  = ["*"],
    )
    
    # Expose emergency snapshots to the dashboard
    import os
    os.makedirs("emergency_snapshots", exist_ok=True)
    app.mount("/snapshots", StaticFiles(directory="emergency_snapshots"), name="snapshots")

    ws_manager = ConnectionManager()

    # ── Background WS broadcaster ─────────────────────────
    @app.on_event("startup")
    async def start_ws_broadcaster():
        async def _broadcast():
            while True:
                # Add dynamic sensor data if not present (for simulation)
                if "temperature" not in state: state["temperature"] = 25.0
                if "infrared" not in state: state["infrared"] = 100.0
                
                payload = {**state, "ts": time.time()}
                # Convert non-serialisable objects
                payload = json.loads(json.dumps(payload, default=str))
                await ws_manager.broadcast(payload)
                await asyncio.sleep(0.1)   # 10 Hz
        asyncio.create_task(_broadcast())

    # ─────────────────────────────────────────────────────
    @app.get("/", tags=["health"])
    async def root():
        return {
            "service": "FireSuppressor",
            "node"   : state.get("node_id"),
            "zone"   : state.get("zone"),
            "status" : "ok",
            "ts"     : time.time(),
        }

    @app.get("/status", response_model=StatusResponse, tags=["monitoring"])
    async def get_status():
        """Full system snapshot."""
        return StatusResponse(
            node_id       = state["node_id"],
            zone          = state["zone"],
            fire_detected = state["fire_detected"],
            fires         = state["fires"],
            humans        = state["humans"],
            nozzles       = state["nozzles"],
            camera_angle  = state["camera_angle"],
            emergency_stop= state["emergency_stop"],
            emergency_mode= state.get("emergency_mode", False),
            infrared      = state.get("infrared", 0.0),
            temperature   = state.get("temperature", 25.0),
            nearby_stations= state.get("nearby_stations", []),
            ts            = time.time(),
        )

    @app.get("/emergency/status", tags=["emergency"])
    async def get_emergency_status():
        """Returns current emergency mode state."""
        return {
            "emergency_mode": state.get("emergency_mode", False),
            "emergency_stop": state.get("emergency_stop", False),
            "fire_detected": state.get("fire_detected", False),
            "ts": time.time()
        }

    @app.get("/sensors", tags=["monitoring"])
    async def get_sensors():
        """Returns real-time sensor data."""
        return {
            "temperature": state.get("temperature", 25.0),
            "infrared": state.get("infrared", 0.0),
            "humidity": state.get("humidity", 45.0),
            "ts": time.time()
        }

    @app.post("/sos-alert", tags=["emergency"])
    async def post_sos_alert(payload: dict):
        """Simulate sending SOS to fire department."""
        logger.warning("🚨 SOS ALERT SENT: {}", payload)
        state.setdefault("alerts", []).append({
            "type": "SOS",
            "payload": payload,
            "ts": time.time()
        })
        return {"status": "SOS_DISPATCHED", "ref": f"SOS-{int(time.time())}"}

    @app.post("/speaker-control", tags=["emergency"])
    async def post_speaker_control(req: dict):
        """Control building speakers."""
        message = req.get("message", "Evacuate immediately")
        logger.info("🔊 SPEAKER BROADCAST: '{}'", message)
        return {"status": "broadcast_sent", "message": message}

    @app.get("/emergency/nearby-stations", tags=["emergency"])
    async def get_nearby_stations(lat: float = 0.0, lon: float = 0.0):
        """Fetches nearby fire stations via Overpass API (mocked for now)."""
        # In a real system, we'd use requests to Overpass API:
        # url = f"https://overpass-api.de/api/interpreter?data=[out:json];node(around:5000,{lat},{lon})[amenity=fire_station];out;"
        # For this demo, we'll return a fixed set of stations.
        stations = [
            {"name": "Central Fire Station", "dist": "1.2 km", "lat": lat+0.01, "lon": lon+0.01},
            {"name": "North-Wing Station 4", "dist": "3.5 km", "lat": lat+0.03, "lon": lon-0.02},
            {"name": "Industrial Safety Hub", "dist": "0.8 km", "lat": lat-0.005, "lon": lon+0.005},
        ]
        state["nearby_stations"] = stations
        return {"stations": stations}

    @app.get("/alerts", tags=["monitoring"])
    async def get_alerts():
        """Returns last 50 fire alerts."""
        return {"alerts": state.get("alerts", []), "count": len(state.get("alerts", []))}

    @app.post("/manual-control",
              response_model=ManualControlResponse,
              tags=["control"])
    async def manual_control(req: ManualControlRequest):
        """
        Manually activate a nozzle.

        Example:
            POST /manual-control
            {"nozzle_id": 2, "pressure": "HIGH"}
        """
        if state.get("emergency_stop"):
            raise HTTPException(
                status_code=423,
                detail="Emergency stop is active. Clear it first.")

        ok = nozzle_ctrl.manual_activate(req.nozzle_id, req.pressure, req.agent)
        state["nozzles"] = nozzle_ctrl.status()
        return ManualControlResponse(
            success   = ok,
            nozzle_id = req.nozzle_id,
            pressure  = req.pressure,
            message   = ("Nozzle activated" if ok
                         else "Invalid nozzle ID"),
        )

    @app.post("/emergency-stop", tags=["safety"])
    async def emergency_stop():
        """
        ⛔ Immediately deactivate all nozzles.
        Also propagates to all MQTT peers.
        """
        state["emergency_stop"] = True
        decision.trigger_emergency_stop()
        nozzle_ctrl.emergency_stop()
        state["nozzles"] = nozzle_ctrl.status()
        logger.critical("⛔ Emergency stop via REST API")
        return {"status": "emergency_stop_engaged", "ts": time.time()}

    @app.post("/clear-emergency-stop", tags=["safety"])
    async def clear_emergency_stop():
        """Release emergency stop and resume normal operation."""
        state["emergency_stop"] = False
        decision.clear_emergency_stop()
        logger.warning("✅ Emergency stop cleared via REST API")
        return {"status": "emergency_stop_cleared", "ts": time.time()}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        """
        Live system state pushed at 10 Hz.
        Clients can also send:  {"cmd": "emergency_stop"}
        """
        await ws_manager.connect(ws)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(ws.receive_text(), timeout=0.05)
                    msg  = json.loads(data)
                    if msg.get("cmd") == "emergency_stop":
                        state["emergency_stop"] = True
                        nozzle_ctrl.emergency_stop()
                except asyncio.TimeoutError:
                    pass  # no incoming data – keep loop alive
                except Exception:
                    break
        except WebSocketDisconnect:
            pass
        finally:
            ws_manager.disconnect(ws)

    return app
