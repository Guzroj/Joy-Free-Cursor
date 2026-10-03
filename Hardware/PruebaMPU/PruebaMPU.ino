#include <Wire.h>
#include <MPU6050_light.h>

MPU6050 mpu(Wire);

float minX, maxX, minY, maxY, minZ, maxZ;

void resetMinMax() {
  minX = minY = minZ = 9999;
  maxX = maxY = maxZ = -9999;
}

void actualizarMinMax() {
  float x = mpu.getAngleX();
  float y = mpu.getAngleY();
  float z = mpu.getAngleZ();

  if (x < minX) minX = x;
  if (x > maxX) maxX = x;
  if (y < minY) minY = y;
  if (y > maxY) maxY = y;
  if (z < minZ) minZ = z;
  if (z > maxZ) maxZ = z;
}

void imprimirResumen(String fase) {
  Serial.println("--- Resumen " + fase + " ---");
  Serial.print("X: min "); Serial.print(minX); Serial.print(" max "); Serial.print(maxX);
  Serial.print("  (rango "); Serial.print(maxX - minX); Serial.println(")");
  Serial.print("Y: min "); Serial.print(minY); Serial.print(" max "); Serial.print(maxY);
  Serial.print("  (rango "); Serial.print(maxY - minY); Serial.println(")");
  Serial.print("Z: min "); Serial.print(minZ); Serial.print(" max "); Serial.print(maxZ);
  Serial.print("  (rango "); Serial.print(maxZ - minZ); Serial.println(")");
  Serial.println("");
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  // SCL 22  SDA 21

  byte status = mpu.begin();
  while (status != 0) { }

  Serial.println("Calculando offsets, no muevas el sensor...");
  delay(1000);
  mpu.calcOffsets();
  Serial.println("Listo!");
  delay(2000);

  // FASE IZQUIERDA
  Serial.println("=== Mueve hacia la IZQUIERDA ahora (5 segundos) ===");
  resetMinMax();
  unsigned long t0 = millis();
  while (millis() - t0 < 5000) {
    mpu.update();
    actualizarMinMax();
    delay(50);
  }
  imprimirResumen("IZQUIERDA");

  // PAUSA PARA RECENTRAR ANTES DE DERECHA
  Serial.println(">>> Acomoda el módulo de vuelta al centro <<<");
  delay(3000);

  // FASE DERECHA
  Serial.println("=== Mueve hacia la DERECHA ahora (5 segundos) ===");
  resetMinMax();
  t0 = millis();
  while (millis() - t0 < 5000) {
    mpu.update();
    actualizarMinMax();
    delay(50);
  }
  imprimirResumen("DERECHA");

  Serial.println("Prueba terminada.");
}

void loop() {
}