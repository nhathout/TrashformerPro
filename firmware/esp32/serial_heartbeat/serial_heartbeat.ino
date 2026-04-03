const unsigned long kHeartbeatIntervalMs = 2000;
const unsigned long kBaudRate = 115200;

unsigned long lastHeartbeatMs = 0;

void setup() {
  Serial.begin(kBaudRate);
  delay(500);
  Serial.println("esp32-ready");
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    line.toLowerCase();

    if (line == "ping") {
      Serial.println("pong");
    } else if (line == "id") {
      Serial.println("trashformer-esp32");
    } else {
      Serial.print("unknown-command:");
      Serial.println(line);
    }
  }

  unsigned long now = millis();
  if (now - lastHeartbeatMs >= kHeartbeatIntervalMs) {
    Serial.print("heartbeat:");
    Serial.println(now);
    lastHeartbeatMs = now;
  }
}
