#include <Wire.h>
#include <MPU6050_light.h>
#include <HijelHID_BLEMouse.h>

// ---- Parámetros ajustables----
const float ZONA_MUERTA  = 5.0;   // grados alrededor del centro sin respuesta
const float ANGULO_MAX   = 25.0;  // grados a los que se alcanza la velocidad máxima
const float VEL_MAX      = 8.0;   // píxeles por ciclo a velocidad máxima
const int   SENTIDO      = 1;     // cambia a -1 si el cursor va al lado contrario
const int   PERIODO_MS   = 20;    // 50 Hz

const int PIN_RECENTRAR = 0;      // botón BOOT del DevKit

MPU6050 mpu(Wire);
HijelBLEMouse mouse("Joy-Free Cursor", "TEC");

float centro = 0;
float acumulador = 0;
unsigned long ultimo = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RECENTRAR, INPUT_PULLUP);
  Wire.begin(21, 22);

  byte estado = mpu.begin();
  if (estado != 0) {
    Serial.println("MPU6050 no responde, revisa el cableado.");
    while (true) delay(100);
  }
  Serial.println("Calibrando offsets, deja el sensor quieto y plano...");
  delay(1000);
  mpu.calcOffsets();
  Serial.println("Listo.");

  mouse.begin();
}

void loop() {
  mpu.update();

  if (digitalRead(PIN_RECENTRAR) == LOW) {   // recentrar manualmente
    centro = mpu.getAngleZ();
    acumulador = 0;
    delay(200);
  }

  if (millis() - ultimo < PERIODO_MS) return;
  ultimo = millis();

  float z = (mpu.getAngleZ() - centro) * SENTIDO;
  float dx = 0;

  if (fabs(z) > ZONA_MUERTA) {
    float s = (fabs(z) - ZONA_MUERTA) / (ANGULO_MAX - ZONA_MUERTA);
    s = constrain(s, 0.0, 1.0);
    dx = (z > 0 ? 1 : -1) * s * VEL_MAX;
  }

  acumulador += dx;
  int paso = (int)acumulador;
  acumulador -= paso;

  if (mouse.isPaired() && paso != 0) {
    mouse.move(paso, 0);
  }
}