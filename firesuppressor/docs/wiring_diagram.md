# FireSuppressor – Hardware Wiring Reference
# ===========================================
# ⚠️  WARNING: This document describes REAL HARDWARE connections.
#     All code defaults to SIMULATION mode.
#     Only follow this guide when deploying to physical hardware.

## Raspberry Pi GPIO → Nozzle Mapping (BCM numbering)

```
Nozzle 1 (North, 0°)
  Solenoid valve:   GPIO 17  (pin 11)  → relay IN1
  Pump relay:       GPIO 27  (pin 13)  → relay IN2

Nozzle 2 (East, 90°)
  Solenoid valve:   GPIO 22  (pin 15)  → relay IN3
  Pump relay:       GPIO 23  (pin 16)  → relay IN4

Nozzle 3 (South, 180°)
  Solenoid valve:   GPIO 24  (pin 18)  → relay IN5
  Pump relay:       GPIO 25  (pin 22)  → relay IN6

Nozzle 4 (West, 270°)
  Solenoid valve:   GPIO 5   (pin 29)  → relay IN7
  Pump relay:       GPIO 6   (pin 31)  → relay IN8
```

## Relay Board Connections
```
RPi 5V  → Relay VCC  (5 V logic)
RPi GND → Relay GND
Relay COM → 240V AC (mains) or 12V DC pump
Relay NO  → Load (solenoid or pump)
```

## Pan-Tilt Camera (PCA9685 + Raspberry Pi I²C)
```
RPi GPIO 2 (SDA, pin 3) → PCA9685 SDA
RPi GPIO 3 (SCL, pin 5) → PCA9685 SCL
RPi 3.3V   (pin 1)      → PCA9685 VCC
External 5V PSU         → PCA9685 V+ (servo power)
Common GND

PCA9685 Ch 0 → Pan  servo signal (Hitec HS-422)
PCA9685 Ch 1 → Tilt servo signal (MG996R)
```

## Emergency Stop Circuit
```
Physical E-stop button (NC contact) → GPIO 4 (pull-up enabled)
Software polls GPIO 4; LOW = button pressed → triggers estop()
Also wired to cut main relay power rail (hardware interlock)
```

## Pixel-to-Angle Calibration Procedure
```
1. python hardware/camera_controller.py --calibrate --real-hardware
2. System prompts: "Position camera to 0° and press Enter"
3. Record PWM pulse width at each cardinal angle
4. Values saved to docs/servo_calibration.json
5. Reload with: python main.py --load-calibration docs/servo_calibration.json
```

## Power Budget (per node)
```
Raspberry Pi 4B:    5W
PCA9685:            0.1W
2× Servos (active): 4W   (1W idle each)
4× Relay board:     0.4W
4× Solenoid valves: 20W  (5W each @ 12V)
4× Water pumps:     80W  (20W each @ 12V, 1 GPM)
──────────────────────────
Total peak:         ~110W per node
Recommended PSU:    12V 15A + 5V 5A (separate rails)
```
