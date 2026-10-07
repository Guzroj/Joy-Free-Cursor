#include <Wire.h>
#include <MPU6050_light.h>
#include <HijelHID_BLEMouse.h>

#define UUID_SERVICIO "8f3c0001-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_ANGULO   "8f3c0002-5b7a-4e2d-9c1a-0d4f6a2b7e10"

const float ZONA_MUERTA = 5.0;
const float ANGULO_MAX  = 25.0;
const float VEL_MAX     = 8.0;
const int   SENTIDO     = 1;
const int   PERIODO_MS  = 20;
const int   PIN_RECENTRAR = 0;

// ---- LED RGB (indicador + calibración, un solo LED por ahora) ----
const int  LED_R = 25;
const int  LED_G = 26;
const int  LED_B = 27;
const bool LED_ANODO_COMUN = false;   // false si tu LED es de cátodo común

MPU6050 mpu(Wire);
HijelBLEMouse mouse("Joy-Free Cursor", "TEC");
NimBLECharacteristic* chAngulo = nullptr;

float centro = 0, acumulador = 0;
unsigned long ultimo = 0;
int ciclos = 0;
unsigned long blancoHasta = 0;       // mientras millis() < esto, el LED parpadea en blanco

void ledColor(uint8_t r, uint8_t g, uint8_t b) {
  static int pr = -1, pg = -1, pb = -1;      // solo escribe si el color cambió
  if (r == pr && g == pg && b == pb) return;
  pr = r; pg = g; pb = b;
  if (LED_ANODO_COMUN) { r = 255 - r; g = 255 - g; b = 255 - b; }
  ledcWrite(LED_R, r);
  ledcWrite(LED_G, g);
  ledcWrite(LED_B, b);
}

void actualizarLed() {
  unsigned long t = millis();
  if (t < blancoHasta) {                     // recentrando: blanco parpadeando
    if ((t / 150) % 2 == 0) ledColor(255, 255, 255);
    else                    ledColor(0, 0, 0);
  } else if (mouse.isPaired()) {             // mouse emparejado: verde fijo
    ledColor(0, 255, 0);
  } else {                                   // buscando conexión: azul parpadeando
    if ((t / 500) % 2 == 0) ledColor(0, 0, 255);
    else                    ledColor(0, 0, 0);
  }
}

void setup() {
  Serial.begin(115200);

  ledcAttach(LED_R, 5000, 8);
  ledcAttach(LED_G, 5000, 8);
  ledcAttach(LED_B, 5000, 8);
  ledColor(255, 0, 0);     delay(300);   // prueba de cableado: rojo, verde, azul, blanco
  ledColor(0, 255, 0);     delay(300);
  ledColor(0, 0, 255);     delay(300);
  ledColor(255, 255, 255); delay(300);
  ledColor(0, 0, 0);

  pinMode(PIN_RECENTRAR, INPUT_PULLUP);
  Wire.begin(21, 22);

  if (mpu.begin() != 0) {
    Serial.println("MPU6050 no responde.");
    while (true) delay(100);
  }
  delay(1000);
  mpu.calcOffsets();

  mouse.setLogLevel(HIDLogLevel::Normal);
  mouse.begin();

  // --- Canal nuevo para la interfaz ---
  NimBLEServer* servidor = NimBLEDevice::getServer();
  if (servidor == nullptr) {
    Serial.println("No hay servidor BLE.");
  } else {
    NimBLEService* svc = servidor->createService(UUID_SERVICIO);
    chAngulo = svc->createCharacteristic(UUID_ANGULO,
                 NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
    int16_t cero = 0;
    chAngulo->setValue(cero);
    bool ok = servidor->start();
    Serial.print("servidor->start(): ");
    Serial.println(ok ? "OK" : "FALLO");
    NimBLEDevice::getAdvertising()->start();
  }
  Serial.print("Direccion BLE: ");
  Serial.println(NimBLEDevice::getAddress().toString().c_str());
}

void loop() {
  // Mantiene el anuncio activo para aceptar una segunda conexión
  static unsigned long ultimoAdv = 0;
  if (millis() - ultimoAdv > 2000) {
    ultimoAdv = millis();
    NimBLEServer* s = NimBLEDevice::getServer();
    NimBLEAdvertising* a = NimBLEDevice::getAdvertising();
    if (s && !a->isAdvertising() && s->getConnectedCount() < 2) a->start();
  }

  actualizarLed();
  mpu.update();

  if (digitalRead(PIN_RECENTRAR) == LOW) {
    centro = mpu.getAngleZ();
    acumulador = 0;
    blancoHasta = millis() + 1000;
    delay(200);
  }

  if (millis() - ultimo < PERIODO_MS) return;
  ultimo = millis();

  float z = (mpu.getAngleZ() - centro) * SENTIDO;
  float dx = 0;
  if (fabs(z) > ZONA_MUERTA) {
    float s = constrain((fabs(z) - ZONA_MUERTA) / (ANGULO_MAX - ZONA_MUERTA), 0.0, 1.0);
    dx = (z > 0 ? 1 : -1) * s * VEL_MAX;
  }
  acumulador += dx;
  int paso = (int)acumulador;
  acumulador -= paso;
  if (mouse.isPaired() && paso != 0) mouse.move(paso, 0);

  // Cada 100 ms manda el ángulo (en centésimas de grado) al canal nuevo
  if (chAngulo && ++ciclos >= 5) {
    ciclos = 0;
    int16_t centi = (int16_t)(z * 100);
    chAngulo->setValue(centi);
    chAngulo->notify();
  }
}