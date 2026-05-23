#include <M5StickCPlus.h>

namespace {

constexpr uint32_t kScreenRefreshMs = 250;
constexpr uint32_t kSerialImuMs = 1000;

bool buttonAState = false;
bool buttonBState = false;
float accelX = 0.0F;
float accelY = 0.0F;
float accelZ = 0.0F;
uint32_t lastScreenRefresh = 0;
uint32_t lastSerialImu = 0;

void drawStatusScreen() {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setCursor(8, 8);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("StickWords");

  M5.Lcd.setTextSize(1);
  M5.Lcd.println("Stage 3A Hardware Check");
  M5.Lcd.println();

  M5.Lcd.printf("Button A: %s\n", buttonAState ? "pressed" : "released");
  M5.Lcd.printf("Button B: %s\n", buttonBState ? "pressed" : "released");
  M5.Lcd.println();
  M5.Lcd.printf("ax: %.2f\n", accelX);
  M5.Lcd.printf("ay: %.2f\n", accelY);
  M5.Lcd.printf("az: %.2f\n", accelZ);
}

void readImu() {
  M5.IMU.getAccelData(&accelX, &accelY, &accelZ);
}

void logButtonTransitions() {
  if (M5.BtnA.wasPressed()) {
    Serial.println("Button A pressed");
  }
  if (M5.BtnA.wasReleased()) {
    Serial.println("Button A released");
  }

  if (M5.BtnB.wasPressed()) {
    Serial.println("Button B pressed");
  }
  if (M5.BtnB.wasReleased()) {
    Serial.println("Button B released");
  }
}

void logImuPeriodically(uint32_t now) {
  if (now - lastSerialImu < kSerialImuMs) {
    return;
  }

  lastSerialImu = now;
  Serial.printf("IMU ax=%.2f ay=%.2f az=%.2f\n", accelX, accelY, accelZ);
}

void refreshScreenPeriodically(uint32_t now) {
  if (now - lastScreenRefresh < kScreenRefreshMs) {
    return;
  }

  lastScreenRefresh = now;
  drawStatusScreen();
}

}  // namespace

void setup() {
  M5.begin();
  M5.Imu.Init();
  Serial.begin(115200);
  delay(200);

  M5.Lcd.setRotation(1);
  M5.Lcd.setTextFont(1);
  M5.Lcd.setTextDatum(TL_DATUM);

  Serial.println("StickWords Stage 3A boot");
  readImu();
  drawStatusScreen();
}

void loop() {
  M5.update();

  buttonAState = M5.BtnA.isPressed();
  buttonBState = M5.BtnB.isPressed();
  readImu();

  const uint32_t now = millis();
  logButtonTransitions();
  logImuPeriodically(now);
  refreshScreenPeriodically(now);

  delay(20);
}
