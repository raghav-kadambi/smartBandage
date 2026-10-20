/*
  WoundSense smart bandage -- ESP32 firmware

  Reads the four bandage signals and POSTs them as JSON to the WoundSense Flask server
  every SEND_INTERVAL_MS:

    POST {SERVER_URL}            (e.g. http://192.168.1.20:5000/api/device/reading)
    Header  X-Device-Token: <token from the dashboard's ESP32 panel>
    Body    {"temperature":37.1,"humidity":72.0,"heart_rate":82,"systolic_bp":121,"diastolic_bp":79}

  Setup
    1. In the web app choose "Connect ESP32 bandage" and copy the Server endpoint + Device token.
    2. Fill in WIFI_SSID / WIFI_PASSWORD / SERVER_URL / DEVICE_TOKEN below.
    3. Keep SIMULATE_SENSORS = true to test the Wi-Fi + server path first, then set it to
       false and fill in the four read*() functions for your sensor modules.
    4. Board: "ESP32 Dev Module". Only the built-in ESP32 core libraries are used.

  The laptop running `python app.py` must be on the same Wi-Fi network as the ESP32.
*/

#include <WiFi.h>
#include <HTTPClient.h>

// ---------------- configuration ----------------
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL    = "http://192.168.1.20:5000/api/device/reading";  // from the dashboard
const char* DEVICE_TOKEN  = "PASTE_DEVICE_TOKEN_HERE";                       // from the dashboard

const bool SIMULATE_SENSORS = true;        // false once real sensors are wired
const unsigned long SEND_INTERVAL_MS = 5000;

// The model expects BODY temperature (core-equivalent, ~36.5-37.5 degC when well).
// A skin/dressing thermistor reads lower; calibrate this against a clinical thermometer.
const float SKIN_TO_CORE_OFFSET_C = 3.5;

// ---------------- sensor reads ----------------
// Replace the bodies of these four functions with your sensor drivers.
// Each returns NAN on a failed read so that the sample is skipped instead of sent.

float readTemperatureC() {
  if (SIMULATE_SENSORS) return 36.8 + random(-30, 30) / 100.0;
  // e.g. DS18B20 / MLX90614 / NTC thermistor on the dressing:
  // float skin = sensor.getTempCByIndex(0);
  // return skin + SKIN_TO_CORE_OFFSET_C;
  return NAN;
}

float readHumidityPct() {
  if (SIMULATE_SENSORS) return 70.0 + random(-50, 50) / 10.0;
  // e.g. DHT22 / SHT31 placed under the dressing:
  // return dht.readHumidity();
  return NAN;
}

float readHeartRateBpm() {
  if (SIMULATE_SENSORS) return 78 + random(-6, 6);
  // e.g. MAX30102 (SparkFun MAX3010x library, beat detection averaged over ~10 s)
  return NAN;
}

bool readBloodPressure(float& systolic, float& diastolic) {
  if (SIMULATE_SENSORS) {
    systolic = 120 + random(-6, 6);
    diastolic = 78 + random(-4, 4);
    return true;
  }
  // e.g. a cuff BP module that prints "SYS,DIA,PULSE" over UART2:
  // if (Serial2.available()) { ...parse... ; return true; }
  return false;
}

// ---------------- networking ----------------

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWi-Fi connected, IP %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nWi-Fi connection failed; will retry");
  }
}

void sendReading(float temp, float hum, float hr, float sys, float dia) {
  char body[192];
  snprintf(body, sizeof(body),
           "{\"temperature\":%.2f,\"humidity\":%.1f,\"heart_rate\":%.0f,\"systolic_bp\":%.0f,\"diastolic_bp\":%.0f}",
           temp, hum, hr, sys, dia);

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  http.setTimeout(8000);
  int code = http.POST(body);
  String resp = http.getString();
  http.end();

  Serial.printf("POST %s -> %d %s\n", body, code, resp.c_str());
  if (code == 401) Serial.println("Token rejected: copy the current token from the dashboard.");
}

// ---------------- main loop ----------------

void setup() {
  Serial.begin(115200);
  delay(200);
  randomSeed(esp_random());
  connectWiFi();
}

unsigned long lastSend = 0;

void loop() {
  if (millis() - lastSend < SEND_INTERVAL_MS) return;
  lastSend = millis();

  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return;

  float temp = readTemperatureC();
  float hum = readHumidityPct();
  float hr = readHeartRateBpm();
  float sys = NAN, dia = NAN;
  bool bpOk = readBloodPressure(sys, dia);

  if (isnan(temp) || isnan(hum) || isnan(hr) || !bpOk) {
    Serial.println("Sensor read failed; skipping this sample");
    return;
  }
  sendReading(temp, hum, hr, sys, dia);
}
