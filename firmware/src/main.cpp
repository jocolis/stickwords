#include <M5StickCPlus.h>

void setup() {
  M5.begin();
  M5.Lcd.setRotation(1);
  Serial.begin(115200);
  Serial.println("StickWords Stage 3A boot");
}

void loop() {
  M5.update();

  float ax = 0.0F;
  float ay = 0.0F;
  float az = 0.0F;
  M5.IMU.getAccelData(&ax, &ay, &az);

  if (M5.BtnA.wasPressed()) {
    Serial.println("Button A pressed");
  }

  if (M5.BtnB.wasPressed()) {
    Serial.println("Button B pressed");
  }

  delay(100);
}
