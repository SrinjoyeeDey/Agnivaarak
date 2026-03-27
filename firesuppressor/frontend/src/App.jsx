// frontend/src/App.jsx
// FireSuppressor Dashboard – React 18 + Tailwind + Recharts
// WebSocket connects to FastAPI /ws for live 10-Hz updates.
// Falls back to simulated demo data if server unreachable.

import { useState, useEffect, useRef, useCallback } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { 
  Shield, AlertTriangle, Zap, User
} from 'lucide-react';

// ── Config ────────────────────────────────────────────────
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";
const WS_URL  = process.env.REACT_APP_WS_URL  || "ws://localhost:8000";

// ── Simulated demo state (used when backend offline) ──────
function makeDemoState() {
  const t = Date.now() / 1000;
  const hasFire  = Math.sin(t * 0.3) > 0.2;
  const hasHuman = Math.sin(t * 0.15) > 0.5;
  return {
    node_id      : 1,
    zone         : "NORTH",
    fire_detected: hasFire,
    camera_angle : (t * 18) % 360,
    emergency_stop: false,
    fires: hasFire ? [
      { id: "demo1", angle: 45, level: "HIGH",   confidence: 0.91,
        bbox: [120,80,90,110], intensity: { level:"HIGH", score:0.82 } },
      { id: "demo2", angle: 200, level: "MEDIUM", confidence: 0.73,
        bbox: [400,200,60,70], intensity: { level:"MEDIUM", score:0.52 } },
    ] : [],
    humans: hasHuman ? [{ bbox: [180,100,30,80], confidence: 0.88 }] : [],
    nozzles: [
      { id:1, active: hasFire && 45  < 46,  pressure: hasFire?"HIGH":"OFF",   angle:0   },
      { id:2, active: hasFire && 90  < 100, pressure: hasFire?"MEDIUM":"OFF", angle:90  },
      { id:3, active: false,                 pressure:"OFF",                   angle:180 },
      { id:4, active: false,                 pressure:"OFF",                   angle:270 },
    ],
    temperature  : 24.5 + Math.sin(t * 0.2) * 2,
    humidity     : 45.0 + Math.cos(t * 0.1) * 5,
    system_pressure: hasFire ? 85.0 + Math.random() * 10 : 0,
    alerts: [],
  };
}

// ── Hooks ─────────────────────────────────────────────────
function useFireSystem() {
  const [state,   setState]   = useState(makeDemoState());
  const [online,  setOnline]  = useState(false);
  const [history, setHistory] = useState([]);
  const wsRef = useRef(null);

  useEffect(() => {
    let ws;
    function connect() {
      try {
        ws = new WebSocket(`${WS_URL}/ws`);
        ws.onopen    = ()  => setOnline(true);
        ws.onclose   = ()  => { setOnline(false); setTimeout(connect, 3000); };
        ws.onerror   = ()  => setOnline(false);
        ws.onmessage = (e) => {
          const data = JSON.parse(e.data);
          setState(data);
          setHistory(h => [...h.slice(-120), {
            t    : new Date().toLocaleTimeString(),
            fires: data.fires?.length ?? 0,
            humans: data.humans?.length ?? 0,
            angle: data.camera_angle ?? 0,
            temp : data.temperature ?? 24,
            hum  : data.humidity ?? 45,
            pres : data.system_pressure ?? 0,
          }]);
        };
        wsRef.current = ws;
      } catch { setOnline(false); }
    }
    connect();

    // Demo refresh when offline
    const demo = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        const d = makeDemoState();
        setState(d);
        setHistory(h => [...h.slice(-120), {
          t    : new Date().toLocaleTimeString(),
          fires: d.fires.length,
          humans: d.humans.length,
          angle: d.camera_angle,
          temp : d.temperature,
          hum  : d.humidity,
          pres : d.system_pressure,
        }]);
      }
    }, 200);

    return () => { ws?.close(); clearInterval(demo); };
  }, []);

  const sendCmd = useCallback(async (endpoint, body={}) => {
    try {
      await fetch(`${API_URL}${endpoint}`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify(body),
      });
    } catch {}
  }, []);

  return { state, online, history, sendCmd, wsRef };
}

function useAudioAlarm(isRinging) {
  const audioCtxRef = useRef(null);
  const oscillatorRef = useRef(null);
  const gainNodeRef = useRef(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!isRinging) {
      if (audioCtxRef.current) audioCtxRef.current.suspend();
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }

    if (!audioCtxRef.current) {
      // Browsers require user interaction before audio plays.
      // This will play as soon as the user clicks anywhere on the dashboard.
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      audioCtxRef.current = new AudioContext();
      
      const osc = audioCtxRef.current.createOscillator();
      const gain = audioCtxRef.current.createGain();
      
      osc.type = "square";
      osc.connect(gain);
      gain.connect(audioCtxRef.current.destination);
      osc.start();
      
      oscillatorRef.current = osc;
      gainNodeRef.current = gain;
    }

    audioCtxRef.current.resume();
    let high = true;
    intervalRef.current = setInterval(() => {
      if (oscillatorRef.current && gainNodeRef.current) {
        oscillatorRef.current.frequency.value = high ? 750 : 500;
        gainNodeRef.current.gain.value = 0.05; // Gentle volume
        high = !high;
      }
    }, 400);

    return () => clearInterval(intervalRef.current);
  }, [isRinging]);
}

// ── Sub-components ─────────────────────────────────────────

function StatusBadge({ online }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold ${
      online ? "bg-emerald-950 text-emerald-400 border border-emerald-700"
             : "bg-yellow-950 text-yellow-400 border border-yellow-700"}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${online?"bg-emerald-400 animate-pulse":"bg-yellow-400"}`}/>
      {online ? "LIVE" : "DEMO"}
    </span>
  );
}

function IntensityBadge({ level }) {
  const map = {
    HIGH  : "bg-red-950    text-red-400    border-red-700",
    MEDIUM: "bg-orange-950 text-orange-400 border-orange-700",
    LOW   : "bg-yellow-950 text-yellow-400 border-yellow-700",
    OFF   : "bg-zinc-800   text-zinc-500   border-zinc-700",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold border ${map[level]||map.OFF}`}>
      {level}
    </span>
  );
}

function CompassRose({ angle, fires }) {
  const cx = 90, cy = 90, r = 72;
  const nozzleAngles = [0, 90, 180, 270];

  return (
    <svg viewBox="0 0 180 180" className="w-44 h-44 mx-auto">
      {/* Gradients for charts */}
      <defs>
        <linearGradient id="gradTemp" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%"  stopColor="#f43f5e" stopOpacity={0.3}/>
          <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}/>
        </linearGradient>
        <linearGradient id="gradPres" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3}/>
          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
        </linearGradient>
        <linearGradient id="gradHum" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%"  stopColor="#10b981" stopOpacity={0.3}/>
          <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
        </linearGradient>
      </defs>
      {/* Outer ring */}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#27272a" strokeWidth="2"/>
      {/* Tick marks */}
      {Array.from({length:36}).map((_,i)=>{
        const a = i*10*Math.PI/180;
        const r1=i%9===0?62:66, r2=70;
        return <line key={i}
          x1={cx+r1*Math.sin(a)} y1={cy-r1*Math.cos(a)}
          x2={cx+r2*Math.sin(a)} y2={cy-r2*Math.cos(a)}
          stroke={i%9===0?"#52525b":"#3f3f46"} strokeWidth={i%9===0?2:1}/>;
      })}
      {/* Cardinal labels */}
      {[["N",0],["E",90],["S",180],["W",270]].map(([l,a])=>{
        const rad=a*Math.PI/180;
        return <text key={l}
          x={cx+58*Math.sin(rad)} y={cy-58*Math.cos(rad)+4}
          textAnchor="middle" fontSize="9" fill="#71717a" fontWeight="bold">{l}</text>;
      })}
      {/* Nozzle sectors */}
      {nozzleAngles.map(a => {
        const rad=(a-15)*Math.PI/180;
        const rad2=(a+15)*Math.PI/180;
        const x1=cx+r*Math.sin(rad),  y1=cy-r*Math.cos(rad);
        const x2=cx+r*Math.sin(rad2), y2=cy-r*Math.cos(rad2);
        return <path key={a}
          d={`M${cx},${cy} L${x1},${y1} A${r},${r} 0 0,1 ${x2},${y2} Z`}
          fill="#1c1917" stroke="#44403c" strokeWidth="1"/>;
      })}
      {/* Fire markers */}
      {fires.map(f => {
        const rad=f.angle*Math.PI/180;
        const fr=50;
        const col=f.level==="HIGH"?"#ef4444":f.level==="MEDIUM"?"#f97316":"#eab308";
        return <g key={f.id}>
          <circle cx={cx+fr*Math.sin(rad)} cy={cy-fr*Math.cos(rad)}
            r="6" fill={col} opacity="0.85">
            <animate attributeName="r" values="6;9;6" dur="1s" repeatCount="indefinite"/>
          </circle>
          <text x={cx+(fr+14)*Math.sin(rad)} y={cy-(fr+14)*Math.cos(rad)+3}
            textAnchor="middle" fontSize="7" fill={col}>🔥</text>
        </g>;
      })}
      {/* Camera direction arrow */}
      <g transform={`rotate(${angle}, ${cx}, ${cy})`}>
        <line x1={cx} y1={cy} x2={cx} y2={cy-58}
          stroke="#38bdf8" strokeWidth="2.5" strokeLinecap="round"/>
        <polygon points={`${cx},${cy-68} ${cx-4},${cy-54} ${cx+4},${cy-54}`}
          fill="#38bdf8"/>
      </g>
      {/* Centre dot */}
      <circle cx={cx} cy={cy} r="4" fill="#38bdf8"/>
    </svg>
  );
}

function PressureGauge({ value }) {
  const max = 150;
  const clamped = Math.min(Math.max(value, 0), max);
  const percent = clamped / max;
  const angle = (percent * 270) - 225; // -225 to 45 deg for 270 deg span
  
  const getColor = (v) => {
    if (v > 120) return "#ef4444"; // Alarm red
    if (v > 90) return "#3b82f6";  // Operational blue
    return "#10b981";             // Safe green
  };

  return (
    <div className="relative w-full aspect-square max-w-[160px] mx-auto">
      <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-2xl">
        {/* Background arc */}
        <path d="M 20 80 A 42 42 0 1 1 80 80" fill="none" stroke="#18181b" strokeWidth="8" strokeLinecap="round"/>
        {/* Colored progress arc */}
        <path d="M 20 80 A 42 42 0 1 1 80 80" fill="none" stroke={getColor(clamped)} strokeWidth="8" strokeLinecap="round"
              strokeDasharray={210} strokeDashoffset={210 - (percent * 210)}
              className="transition-all duration-1000 ease-out opacity-40"/>
        
        {/* Ticks */}
        {[0, 25, 50, 75, 100, 125, 150].map(v => {
          const a = (v / 150 * 270) - 225;
          const r1 = 36, r2 = 42;
          const x1 = 50 + r1 * Math.cos(a * Math.PI / 180);
          const y1 = 50 + r1 * Math.sin(a * Math.PI / 180);
          const x2 = 50 + r2 * Math.cos(a * Math.PI / 180);
          const y2 = 50 + r2 * Math.sin(a * Math.PI / 180);
          return <line key={v} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#3f3f46" strokeWidth="1.5"/>;
        })}

        {/* Needle */}
        <g transform={`rotate(${angle}, 50, 50)`} className="transition-transform duration-500 ease-in-out">
          <path d="M 48 50 L 50 15 L 52 50 Z" fill={getColor(clamped)} />
          <circle cx="50" cy="50" r="4" fill="#09090b" stroke={getColor(clamped)} strokeWidth="2"/>
        </g>

        {/* Digital Value */}
        <text x="50" y="75" textAnchor="middle" fill="white" className="text-[12px] font-black tracking-tighter italic">
          {clamped.toFixed(1)}
        </text>
        <text x="50" y="85" textAnchor="middle" fill="#52525b" className="text-[6px] font-black uppercase tracking-[0.2em]">
          SYSTEM PSI
        </text>
      </svg>
    </div>
  );
}

function NozzleCard({ nozzle }) {
  const ZONE = {1:"North",2:"East",3:"South",4:"West"};
  const active = nozzle.active;
  return (
    <div className={`rounded-xl border p-3 transition-all duration-300 ${
      active ? "border-blue-600 bg-blue-950/40 shadow-lg shadow-blue-950"
             : "border-zinc-800 bg-zinc-900/50"}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold text-zinc-400 uppercase tracking-widest">DEVICE {nozzle.device_id || nozzle.id}</span>
        <span className="text-[10px] text-zinc-600 font-bold uppercase">{ZONE[nozzle.id] || "Global"}</span>
      </div>
      
      <div className="flex items-center gap-2 mb-3">
        <span className="text-3xl">{active ? "🌊" : "⭕"}</span>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-bold truncate ${active ? "text-blue-400" : "text-zinc-600"}`}>
            {active ? nozzle.status : "IDLE / SCANNING"}
          </div>
          <div className="flex flex-wrap gap-1 mt-1">
            <IntensityBadge level={nozzle.pressure}/>
            {active && nozzle.agent && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-400 font-bold uppercase">
                {nozzle.agent}
              </span>
            )}
          </div>
        </div>
      </div>

      {active && (
        <div className="space-y-2 border-t border-white/5 pt-2">
          <div className="grid grid-cols-2 gap-2 text-[10px] uppercase font-bold text-zinc-500">
            <div>
              <span className="block text-[8px] opacity-60">FIRE TYPE</span>
              <span className="text-zinc-300">{nozzle.label || nozzle.fire_type || "NORMAL"}</span>
            </div>
            <div>
              <span className="block text-[8px] opacity-60">INTENSITY</span>
              <span className="text-zinc-300">{nozzle.intensity || "LOW"}</span>
            </div>
            <div>
              <span className="block text-[8px] opacity-60">PAN</span>
              <span className="text-blue-400 font-mono">{nozzle.pan?.toFixed(1)}°</span>
            </div>
            <div>
              <span className="block text-[8px] opacity-60">TILT</span>
              <span className="text-blue-400 font-mono">{nozzle.tilt?.toFixed(1)}°</span>
            </div>
          </div>
          
          <div className="h-1 rounded-full bg-zinc-800 overflow-hidden mt-1">
            <div className={`h-full rounded-full animate-pulse transition-all duration-500 ${
              nozzle.pressure==="HIGH"?"w-full bg-red-500":
              nozzle.pressure==="MEDIUM"?"w-2/3 bg-orange-500":"w-1/3 bg-yellow-500"}`}/>
          </div>
        </div>
      )}
    </div>
  );
}

function FireCard({ fire, humans }) {
  const nearHuman = humans.some(h => {
    const hcx=h.bbox[0]+h.bbox[2]/2, hcy=h.bbox[1]+h.bbox[3]/2;
    const fcx=fire.bbox[0]+fire.bbox[2]/2, fcy=fire.bbox[1]+fire.bbox[3]/2;
    return Math.hypot(fcx-hcx, fcy-hcy) < 80;
  });
  return (
    <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-3 text-sm">
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-xs text-red-500 uppercase tracking-tighter">ID: {fire.id?.slice(0,8)}</span>
        <IntensityBadge level={fire.level||fire.intensity?.level}/>
      </div>
      <div className="text-zinc-300 text-[10px] space-y-0.5 mt-2">
        <div className="flex justify-between">
          <span className="text-zinc-500 font-bold">TYPE</span>
          <span className="text-white font-bold uppercase">{fire.label || "DETECTING..."}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500 font-bold">ANGLE</span>
          <span className="text-white font-semibold">{fire.angle?.toFixed(1)}°</span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500 font-bold">CONFIDENCE</span>
          <span className="text-white">{(fire.confidence*100).toFixed(0)}%</span>
        </div>
        {nearHuman && (
          <div className="text-yellow-400 font-bold mt-2 pt-1 border-t border-yellow-400/20 animate-pulse">
            ⚠️ HUMAN NEARBY - SURROUND
          </div>
        )}
      </div>
    </div>
  );
}

function MetricChart({ title, data, dataKey, color, gradientId, unit, domain }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5 h-[190px] flex flex-col hover:border-zinc-700 transition-colors group">
      <div className="flex justify-between items-center mb-3">
        <span className="text-[10px] font-bold text-zinc-500 tracking-[0.2em] uppercase group-hover:text-zinc-400 transition-colors">{title}</span>
        <span className="text-sm font-mono font-bold" style={{ color }}>
          {data[data.length - 1]?.[dataKey]?.toFixed(1)}{unit}
        </span>
      </div>
      <div className="flex-1 w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={color} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={color} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <XAxis dataKey="t" hide />
            <YAxis domain={domain || [0, 'auto']} hide />
            <Tooltip
              contentStyle={{ background: "#09090b", border: "1px solid #27272a", borderRadius: 8, fontSize: 10, color: "#fff" }}
              itemStyle={{ color: color }}
              labelStyle={{ display: "none" }}
            />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              strokeWidth={2}
              fillOpacity={1}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────
export default function App() {
  const { state, online, history, sendCmd } = useFireSystem();
  useAudioAlarm(state.fire_detected);
  
  const [manualNozzle,   setManualNozzle]   = useState(1);
  const [manualPressure, setManualPressure] = useState("MEDIUM");
  const [manualAgent,    setManualAgent]    = useState("WATER");

  const eStop        = ()  => sendCmd("/emergency-stop");
  const clearEStop   = ()  => sendCmd("/clear-emergency-stop");
  const manualSpray  = ()  => sendCmd("/manual-control",
    { nozzle_id: manualNozzle, pressure: manualPressure, agent: manualAgent });

  const fireCount  = state.fires?.length ?? 0;
  const humanCount = state.humans?.length ?? 0;
  const estop      = state.emergency_stop;

  return (
    <div className="min-h-screen bg-black text-zinc-100 font-sans p-4"
         style={{fontFamily:"'IBM Plex Mono', monospace"}}>
      
      {/* Custom Scrollbar Styles */}
      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #27272a; border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #3f3f46; }
      `}</style>

      {/* ── Header ───────────────────────────────────────── */}
      <header className="flex items-center justify-between mb-8 border-b border-zinc-900 pb-4">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-red-600 rounded-lg flex items-center justify-center shadow-lg shadow-red-900/20">
            <span className="text-2xl">🔥</span>
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tighter uppercase italic">Agnivaarak <span className="text-zinc-500 font-light not-italic text-sm ml-2">v1.0.4</span></h1>
            <p className="text-[10px] text-zinc-600 font-bold tracking-[0.2em] uppercase">
              Terminal {state.node_id} / Zone {state.zone} / System Secure
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right mr-4">
             <div className="text-[10px] text-zinc-600 font-bold uppercase">Uptime</div>
             <div className="text-xs font-mono text-zinc-400">04:12:09:44</div>
          </div>
          <StatusBadge online={online}/>
          {estop && (
            <span className="px-4 py-1.5 bg-red-600 text-white text-[10px] font-black
                             rounded-sm animate-pulse shadow-lg shadow-red-900/40">
              CRITICAL: E-STOP
            </span>
          )}
        </div>
      </header>

      {/* ── Emergency Modal ────────────────────────────── */}
      {state.emergency_dispatched && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-red-950/90 backdrop-blur-xl p-4 md:p-8">
          <div className="bg-zinc-950 border-2 border-red-600 rounded-lg p-6 md:p-10 max-w-4xl w-full max-h-[95vh] overflow-y-auto shadow-[0_0_100px_rgba(220,38,38,0.3)] custom-scrollbar">
            <div className="text-6xl md:text-8xl mb-6">📢</div>
            <h2 className="text-3xl md:text-5xl font-black text-white tracking-tighter uppercase mb-6 italic leading-none">
              Fire Department <br/><span className="text-red-600">Dispatched</span>
            </h2>
            <p className="text-base md:text-xl text-zinc-400 mb-8 border-l-4 border-red-600 pl-6 leading-relaxed">
              Automatic escalation triggered. Emergency units are en route to <span className="text-white font-bold">{state.zone}</span>. 
              Live surveillance feed and metadata have been uplined to regional dispatch.
            </p>
            
            {state.emergency_snapshot_url && (
              <div className="mb-8 rounded-lg overflow-hidden border border-zinc-800 bg-black aspect-video flex items-center justify-center relative shadow-2xl group">
                <div className="absolute top-4 left-4 bg-red-600 text-[10px] font-bold px-2 py-1 text-white uppercase animate-pulse z-10">Live Evidence Buffer</div>
                <img src={state.emergency_snapshot_url} alt="Snap" className="max-h-full w-full object-contain" />
                <div className="absolute inset-0 bg-red-600/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              <div className="space-y-4">
                <div className="text-[10px] text-zinc-500 font-black uppercase tracking-[0.2em]">Safety Protocols</div>
                <div className="space-y-2">
                  {[
                    "Evacuate building immediately via nearest exit",
                    "Do not use elevators - use stairwells only",
                    "Assemble at designated North-Wing point",
                    "Await further instructions from first responders"
                  ].map((text, i) => (
                    <div key={i} className="flex items-start gap-3 bg-zinc-900/50 p-3 rounded border border-zinc-800/50">
                      <div className="mt-0.5"><Shield size={14} className="text-emerald-500" /></div>
                      <span className="text-xs text-zinc-300 font-bold leading-tight">{text}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="space-y-4">
                <div className="text-[10px] text-zinc-500 font-black uppercase tracking-[0.2em]">Emergency Status</div>
                <div className="bg-red-950/20 rounded-xl border border-red-900/40 p-5 space-y-4">
                   <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-zinc-400">911 Dispatch</span>
                      <span className="text-[10px] font-black text-emerald-400 animate-pulse uppercase tracking-wider">Connected</span>
                   </div>
                   <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-zinc-400">Call Reference</span>
                      <span className="text-[10px] font-mono text-white">#FIRE-DX-{Math.floor(Math.random()*9000)+1000}</span>
                   </div>
                   <div className="h-0.5 bg-zinc-800 w-full" />
                   <div className="flex items-center gap-3">
                      <AlertTriangle size={18} className="text-red-500 animate-bounce" />
                      <div>
                        <div className="text-xs font-black text-white italic uppercase tracking-tighter">Emergency Out Of Control</div>
                        <div className="text-[9px] text-red-500 font-bold uppercase">Automated Suppression Overwhelmed</div>
                      </div>
                   </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 bg-zinc-900 rounded border border-zinc-800">
                <div className="text-[10px] text-zinc-600 font-bold uppercase mb-1">Status</div>
                <div className="text-red-500 font-bold uppercase tracking-widest animate-pulse">EVACUATE IMMEDIATELY</div>
              </div>
              <div className="p-4 bg-zinc-900 rounded border border-zinc-800 text-center flex items-center justify-center">
                 <button onClick={() => sendCmd("/clear-emergency-stop")} className="text-xs font-bold text-zinc-500 hover:text-white transition-colors uppercase tracking-widest border border-zinc-700 px-6 py-2 rounded hover:border-zinc-500">Acknowledge & Clear</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── System Safety Banner ─────────────────────── */}
      <div className={`mb-6 px-5 py-4 rounded-xl border-l-4 flex items-center justify-between transition-all duration-500 overflow-hidden relative ${
        estop ? "bg-red-950/40 border-red-600 text-red-500 shadow-lg shadow-red-900/10" :
        fireCount > 0 ? "bg-orange-950/40 border-orange-500 text-orange-400 shadow-lg shadow-orange-900/10" :
        "bg-emerald-950/20 border-emerald-600 text-emerald-500 shadow-lg shadow-emerald-900/5"
      }`}>
        <div className="flex items-center gap-4 z-10">
          <div className={`w-2 h-2 rounded-full animate-ping ${estop?"bg-red-500":fireCount>0?"bg-orange-500":"bg-emerald-500"}`}/>
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.3em] opacity-60 mb-0.5">System Health & Safety Status</div>
            <div className="text-sm font-black uppercase italic tracking-tight">
              {estop ? "CRITICAL: EMERGENCY STOP ENGAGED" :
               fireCount > 0 ? `WARNING: ${fireCount} FIRE VECTOR(S) DETECTED` :
               "SAFETY CHECK: ALL SECTORS SECURE"}
            </div>
          </div>
        </div>
        <div className="flex gap-8 text-right z-10">
           <div>
             <div className="text-[9px] font-bold uppercase opacity-40">Active Hazards</div>
             <div className={`text-sm font-mono font-bold ${fireCount>0?"text-red-500":"text-zinc-600"}`}>{fireCount}</div>
           </div>
           <div className="border-l border-white/5 pl-8">
             <div className="text-[9px] font-bold uppercase opacity-40">Bio Signatures</div>
             <div className={`text-sm font-mono font-bold ${humanCount>0?"text-yellow-500":"text-emerald-500"}`}>{humanCount}</div>
           </div>
        </div>
        {/* Background glow effects */}
        <div className={`absolute right-0 top-0 w-64 h-full opacity-20 blur-3xl pointer-events-none ${
          estop ? "bg-red-600" : fireCount > 0 ? "bg-orange-600" : "bg-emerald-600"
        }`}/>
      </div>

      {/* ── Dashboard Grid ──────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 content-start">

        {/* ── Charts column ────────────────────────────── */}
        <div className="xl:col-span-1 space-y-4">
          <MetricChart 
            title="Fire Vectors" 
            data={history} 
            dataKey="fires" 
            color="#ef4444" 
            gradientId="gradFire"
            unit="" 
            domain={[0, 5]}
          />
          <MetricChart 
            title="Ambient Temp" 
            data={history} 
            dataKey="temp" 
            color="#f43f5e" 
            gradientId="gradTemp"
            unit="°C"
            domain={[20, 100]}
          />
          <MetricChart 
            title="System Pressure" 
            data={history} 
            dataKey="pres" 
            color="#3b82f6" 
            gradientId="gradPres"
            unit=" PSI"
            domain={[0, 150]}
          />
          <MetricChart 
            title="Relative Hum" 
            data={history} 
            dataKey="hum" 
            color="#10b981" 
            gradientId="gradHum"
            unit="%"
            domain={[20, 100]}
          />
        </div>

        {/* ── Main content (2 cols) ─────────────────────── */}
        <div className="xl:col-span-2 space-y-6">
          
          {/* Top Row: Map and Active Fires */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
            {/* Compass Area */}
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/30 p-6 flex flex-col items-center justify-center min-h-[380px]">
              <div className="w-full flex justify-between items-center mb-6">
                <span className="text-[10px] font-bold text-zinc-500 tracking-[0.3em] uppercase underline decoration-sky-500 underline-offset-4">Spatial Awareness</span>
                <span className="text-[10px] font-mono text-zinc-600 uppercase">Radar v2.4</span>
              </div>
              <CompassRose angle={state.camera_angle??0} fires={state.fires??[]}/>
              <div className="mt-8 grid grid-cols-3 gap-4 w-full">
                 <div className="text-center">
                   <div className="text-[8px] text-zinc-600 font-bold uppercase mb-1 tracking-widest leading-none">Scanning</div>
                   <div className="text-base font-mono text-zinc-100 italic">{(state.camera_angle??0).toFixed(1)}°</div>
                 </div>
                 <div className="text-center border-l border-zinc-800">
                   <div className="text-[8px] text-zinc-600 font-bold uppercase mb-1 tracking-widest leading-none">Fire Cnt</div>
                   <div className={`text-base font-mono italic ${fireCount > 0 ? "text-red-500" : "text-emerald-500"}`}>{fireCount}</div>
                 </div>
                 <div className="text-center border-l border-zinc-800">
                   <div className="text-[8px] text-zinc-600 font-bold uppercase mb-1 tracking-widest leading-none">Bio Cnt</div>
                   <div className={`text-base font-mono italic ${humanCount > 0 ? "text-yellow-500" : "text-emerald-500"}`}>{humanCount}</div>
                 </div>
              </div>
            </div>

            {/* Active Fires List */}
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/30 p-6 flex flex-col h-full min-h-[380px]">
              <div className="text-[10px] font-bold text-zinc-500 tracking-[0.3em] uppercase mb-4">Active Fire Vectors</div>
              <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
                {fireCount > 0 ? (
                  <div className="space-y-3">
                    {state.fires.map(f => (
                      <FireCard key={f.id} fire={f} humans={state.humans??[]}/>
                    ))}
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-zinc-700 italic border-2 border-dashed border-zinc-900 rounded-xl">
                    <span className="text-4xl mb-2 opacity-20">🛡️</span>
                    <span className="text-[10px] uppercase font-bold tracking-widest">Sectors Secured</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Bottom Row: Nozzle Array */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <div className="text-[10px] font-bold text-zinc-500 tracking-[0.3em] uppercase">Actuator Node Array // Active Status</div>
              <div className="text-[10px] font-mono text-zinc-700 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">4x S-PUMP NODES ONLINE</div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-4">
              {(state.nozzles??[]).map(n => (
                <NozzleCard key={n.id} nozzle={n}/>
              ))}
            </div>
          </div>
        </div>

        {/* ── Right column ─────────────────────────────── */}
        <div className="xl:col-span-1 space-y-6">
          
          {/* Pressure Hub */}
          <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-inner relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
              <Zap size={60} className="text-blue-500" />
            </div>
            <div className="text-[10px] font-bold text-zinc-500 tracking-[0.3em] uppercase mb-4 relative z-10">Pressure Output Hub</div>
            <PressureGauge value={state.system_pressure || 0} />
            <div className="mt-4 grid grid-cols-2 gap-2">
              <div className="bg-zinc-900/50 p-2 rounded border border-zinc-800/50 text-center">
                 <div className="text-[8px] text-zinc-600 font-bold uppercase">Line Status</div>
                 <div className="text-[10px] font-black text-emerald-500 italic uppercase italic">Stabilized</div>
              </div>
              <div className="bg-zinc-900/50 p-2 rounded border border-zinc-800/50 text-center">
                 <div className="text-[8px] text-zinc-600 font-bold uppercase">Pump Load</div>
                 <div className={`text-[10px] font-black italic uppercase italic ${state.system_pressure > 80 ? 'text-blue-400' : 'text-zinc-600'}`}>
                    {state.system_pressure > 80 ? 'Heavy' : 'Standby'}
                 </div>
              </div>
            </div>
          </div>
          
          {/* Manual Control */}
          <div className="rounded-2xl border border-blue-900/40 bg-zinc-900/50 p-6 shadow-lg shadow-blue-950/10">
            <div className="text-[10px] font-bold text-blue-500 tracking-[0.3em] uppercase mb-6 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"/> Manual Override
            </div>
            
            {!estop ? (
              <button onClick={eStop}
                className="w-full py-4 rounded bg-red-600/10 hover:bg-red-600/20
                           active:scale-[0.98] text-red-500 font-black text-xs
                           transition-all duration-150 mb-6 border border-red-600/30 uppercase tracking-[0.2em] shadow-lg shadow-red-950/20">
                Init Emergency Stop
              </button>
            ) : (
              <button onClick={clearEStop}
                className="w-full py-4 rounded bg-emerald-600/10 hover:bg-emerald-600/20
                           active:scale-[0.98] text-emerald-500 font-black text-xs
                           transition-all duration-150 mb-6 border border-emerald-600/30 uppercase tracking-[0.2em] shadow-lg shadow-emerald-950/20">
                Release System Lock
              </button>
            )}

            <div className="space-y-4 pt-4 border-t border-zinc-800/50">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[9px] text-zinc-600 font-bold uppercase mb-2 block tracking-widest">Port</label>
                  <select value={manualNozzle}
                    onChange={e=>setManualNozzle(+e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-sm
                               px-3 py-2 text-xs text-zinc-200 focus:outline-none font-bold uppercase tracking-tighter">
                    {[1,2,3,4].map(n=>(
                      <option key={n} value={n}>N-{n} ({(n-1)*90}°)</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[9px] text-zinc-600 font-bold uppercase mb-2 block tracking-widest">Level</label>
                  <select value={manualPressure}
                    onChange={e=>setManualPressure(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-sm
                               px-3 py-2 text-xs text-zinc-200 focus:outline-none font-bold uppercase tracking-tighter">
                    {["LOW","MEDIUM","HIGH"].map(p=>(
                      <option key={p}>{p}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-[9px] text-zinc-600 font-bold uppercase mb-2 block tracking-widest">Suppressant agent</label>
                <select value={manualAgent}
                  onChange={e=>setManualAgent(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-sm
                             px-3 py-2 text-xs text-zinc-200 focus:outline-none font-bold uppercase tracking-tighter">
                  {["WATER","FOAM","CO2","POWDER"].map(a=>(
                    <option key={a}>{a}</option>
                  ))}
                </select>
              </div>
              <button onClick={manualSpray} disabled={estop}
                className="w-full py-3 rounded bg-blue-600 hover:bg-blue-500
                           disabled:bg-zinc-900 disabled:text-zinc-700
                           active:scale-[0.98] text-white font-black text-xs
                           transition-all duration-150 uppercase tracking-[0.2em] shadow-xl shadow-blue-900/10 border border-blue-400/20">
                Manual Discharge
              </button>
            </div>
          </div>

          {/* Tactical Intel / Missing graphs */}
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
            <div className="text-[10px] font-bold text-zinc-500 tracking-[0.3em] uppercase mb-4">Tactical Safety Status</div>
            
            <div className="space-y-5">
              <div className="space-y-4">
                <MetricChart 
                  title="Bio Correlation" 
                  data={history} 
                  dataKey="humans" 
                  color="#fbbf24" 
                  gradientId="gradHumans"
                  unit=" Bio-Sigs" 
                  domain={[0, 5]}
                />
              </div>

              <div className="p-5 bg-black/60 rounded-xl border border-zinc-800 shadow-inner">
                <div className="text-[10px] text-zinc-500 font-black uppercase mb-4 tracking-[0.2em]">
                  HUMAN DETECTION
                </div>
                {state.humans?.length > 0 ? (
                  <div className="space-y-3">
                    {state.humans.map((h,i) => {
                      const [x1, y1, x2, y2] = h.bbox || [0,0,0,0];
                      const cx = Math.round((x1 + x2) / 2);
                      const cy = Math.round((y1 + y2) / 2);
                      return (
                        <div key={i} className="flex items-center gap-3">
                          <User size={14} className="text-indigo-500 fill-indigo-500/20" />
                          <div className="flex items-baseline gap-2">
                            <span className="text-xs font-bold text-amber-500">Person at ({cx}, {cy})</span>
                            <span className="text-[10px] font-mono text-zinc-600">{(h.confidence*100).toFixed(0)}%</span>
                          </div>
                        </div>
                      );
                    })}
                    
                    {fireCount > 0 && (
                      <div className="pt-3 mt-3 border-t border-zinc-900 flex items-center gap-2">
                        <AlertTriangle size={12} className="text-amber-600" />
                        <span className="text-[10px] font-bold text-amber-600 uppercase tracking-tight italic">
                          Spray path adjusted – SURROUND mode active
                        </span>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-6 flex flex-col items-center justify-center border border-dashed border-zinc-900 rounded-lg">
                    <Shield size={20} className="text-zinc-800 mb-2" />
                    <span className="text-[9px] uppercase font-bold text-zinc-700 tracking-widest">No Bio-Intrusion</span>
                  </div>
                )}
              </div>

              <div className="p-4 bg-zinc-900/50 rounded border border-zinc-800/50">
                <div className="text-[9px] text-zinc-600 font-bold uppercase mb-2 tracking-[0.2em]">Diagnostic Link</div>
                <div className="grid grid-cols-2 gap-y-2 text-[10px] font-mono">
                  <span className="text-zinc-600">ID:</span> <span className="text-zinc-400">AGNI-0x{state.node_id?.toString(16).toUpperCase()}</span>
                  <span className="text-zinc-600">LINK:</span> <span className={online ? "text-emerald-500" : "text-yellow-500"}>{online ? "CRYPTED_AES" : "OFFLINE_LOC"}</span>
                  <span className="text-zinc-600">MODE:</span> <span className="text-blue-500">AUTO_FIRE_S</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Footer ───────────────────────────────────────── */}
      <footer className="mt-12 flex justify-between items-center text-[9px] text-zinc-800 font-bold tracking-[0.4em] uppercase border-t border-zinc-900 pt-6">
          <div>Agnivaarak Advanced Fire Defense • Unit 2026.x</div>
          <div className="flex gap-6">
             <span>Simulation: {state.fire_detected ? "Active" : "Neutral"}</span>
             <span>Network: Secure</span>
          </div>
      </footer>
    </div>
  );
}
