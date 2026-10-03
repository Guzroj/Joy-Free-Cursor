#include <HijelHID_BLEMouse.h>

HijelBLEMouse mouse("Joy-Free Cursor", "TEC");

void setup() {
  Serial.begin(115200);
  mouse.setLogLevel(HIDLogLevel::Normal);  // muestra conexión y emparejamiento por serial
  mouse.begin();
}

void loop() {
  if (mouse.isPaired()) {
    for (int i = 0; i < 100; i++) { mouse.move(3, 0);  delay(10); }  // derecha
    delay(500);
    for (int i = 0; i < 100; i++) { mouse.move(-3, 0); delay(10); }  // izquierda
    delay(500);
  } else {
    delay(200);
  }
}