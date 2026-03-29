/*
 * FireSuppressor v1.1 - Emergency System Firmware (Sample)
 * For Arduino / ESP32
 * 
 * This script demonstrates how to:
 * 1. Parse the new mapped numeric command format: "pan,tilt,pressure,mode,fire_type,intensity\n"
 * 2. Handle Emergency Mode (global state)
 * 3. Report simulated sensor data (IR, Temp) back to the Python backend
 */

#include <Servo.h>

// Servo pins
const int PAN_PIN = 9;
const int TILT_PIN = 10;
const int PUMP_PIN = 11; // PWM or Relay
const int ALARM_PIN = 12;

Servo panServo;
Servo tiltServo;

// System State
int currentMode = 0; // 0=NORMAL, 1=FIRE, 2=EMERGENCY
bool emergencyMode = false;

void setup() {
  Serial.begin(115200);
  
  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(ALARM_PIN, OUTPUT);
  
  // Initial positions
  panServo.write(90);
  tiltServo.write(45);
  digitalWrite(PUMP_PIN, LOW);
  digitalWrite(ALARM_PIN, LOW);
  
  Serial.println("SYSTEM_READY: Agnivaarak v1.1 Emergency Unit");
}

void loop() {
  // 1. Check for incoming commands from Python
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    parseCommand(input);
  }
  
  // 2. Report Sensors periodically (Simulated for this demo)
  static unsigned long lastReport = 0;
  if (millis() - lastReport > 2000) {
    reportSensors();
    lastReport = millis();
  }
  
  // 3. Autonomous Logic (e.g., Local Alarm if Emergency Mode)
  if (emergencyMode) {
    digitalWrite(ALARM_PIN, (millis() / 500) % 2); // Blinking alarm
  } else if (currentMode == 0) {
    digitalWrite(ALARM_PIN, LOW);
  }
}

void parseCommand(String cmd) {
  // Format: pan,tilt,pressure_code,mode_code,type,intensity
  // Example: "90,45,2,1,1,2" (Pan 90, Tilt 45, Med Pressure, Fire Mode, Class A, Med Intensity)
  
  int values[6];
  int count = 0;
  int lastIndex = 0;
  
  for (int i = 0; i < cmd.length(); i++) {
    if (cmd.charAt(i) == ',' || i == cmd.length() - 1) {
      String valStr = cmd.substring(lastIndex, (cmd.charAt(i) == ',') ? i : i + 1);
      values[count++] = valStr.toInt();
      lastIndex = i + 1;
      if (count >= 6) break;
    }
  }
  
  if (count >= 4) {
    int pan = values[0];
    int tilt = values[1];
    int pressure = values[2];
    int mode = values[3];
    
    // Actuate Servos
    panServo.write(constrain(pan, 0, 180));
    tiltServo.write(constrain(tilt, 0, 180));
    
    // Actuate Pump/Pressure
    if (pressure > 0) {
      analogWrite(PUMP_PIN, map(pressure, 1, 3, 100, 255));
    } else {
      digitalWrite(PUMP_PIN, LOW);
    }
    
    // Handle Mode
    currentMode = mode;
    if (mode == 2) {
      emergencyMode = true;
      digitalWrite(ALARM_PIN, HIGH);
    } else if (mode == 0) {
      emergencyMode = false;
    }
  }
}

void reportSensors() {
  // In a real system, you'd read actual hardware sensors here.
  // Example: float temp = dht.readTemperature();
  
  float mockTemp = 24.0 + (random(0, 100) / 10.0);
  int mockIR = random(100, 1000);
  
  // Report back to Python via Serial in JSON or simple KV
  // Python side doesn't parse this yet in the current backend, 
  // but it's good practice for real IoT bi-directional comms.
  Serial.print("SENSOR:TEMP=");
  Serial.print(mockTemp);
  Serial.print(",IR=");
  Serial.println(mockIR);
}
