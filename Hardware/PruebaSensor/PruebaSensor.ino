#include <Wire.h>
#include <MPU6050_light.h>
#include <HijelHID_BLEMouse.h>

#define UUID_SERVICIO "8f3c0001-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_ANGULO   "8f3c0002-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_ZONA     "8f3c0003-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_SENS     "8f3c0004-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_MODO     "8f3c0005-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_ESTADO   "8f3c0006-5b7a-4e2d-9c1a-0d4f6a2b7e10"

// ---- Parámetros ajustables ----
float       zonaMuerta   = 5.0;   // la app puede cambiarla
float       sensibilidad = 1.0;   // factor sobre VEL_MAX (1.0 = 100%), la app puede cambiarlo
const float ANGULO_MAX = 25.0;
const float VEL_MAX    = 8.0;
const int   SENTIDO    = 1;
const int   PERIODO_MS = 20;
const int   PIN_RECENTRAR = 0;

// ---- LED RGB ----
const int  LED_R = 25;
const int  LED_G = 26;
const int  LED_B = 27;
const bool LED_ANODO_COMUN = false;   // cátodo común

MPU6050 mpu(Wire);
HijelBLEMouse mouse("Joy-Free Cursor", "TEC");
NimBLECharacteristic* chAngulo = nullptr;
NimBLECharacteristic* chZona = nullptr;
NimBLECharacteristic* chSens = nullptr;
NimBLECharacteristic* chModo = nullptr;
NimBLECharacteristic* chEstado = nullptr;

float centro = 0, acumulador = 0;
unsigned long ultimo = 0;
int ciclos = 0;
unsigned long blancoHasta = 0;

// Modo configuración: la app lo activa y manda un "latido" cada 1 s.
// Si pasan 3 s sin latido (app cerrada o conexión caída), sale solo.
bool modoConfig = false;
unsigned long ultimoLatido = 0;

// Estado de emparejamiento que se le informa a la app (1 = mouse emparejado)
bool pareadoAnterior = false;

class CbZona : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 2) {
      uint16_t d = c->getValue().getValue<uint16_t>();
      if (d >= 10 && d <= 200) {          // limita entre 1.0° y 20.0°
        zonaMuerta = d / 10.0;
        Serial.printf("Zona muerta = %.1f\n", zonaMuerta);
      }
    }
  }
};

class CbSens : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 2) {
      uint16_t p = c->getValue().getValue<uint16_t>();
      if (p >= 20 && p <= 300) {          // limita entre 20% y 300%
        sensibilidad = p / 100.0;
        Serial.printf("Sensibilidad = %.2f\n", sensibilidad);
      }
    }
  }
};

class CbModo : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 1) {
      bool nuevo = (c->getValue().getValue<uint8_t>() == 1);
      if (nuevo != modoConfig) Serial.println(nuevo ? "Modo configuracion: ON" : "Modo configuracion: OFF");
      modoConfig = nuevo;
      ultimoLatido = millis();
    }
  }
};

void ledColor(uint8_t r, uint8_t g, uint8_t b) {
  static int pr = -1, pg = -1, pb = -1;
  if (r == pr && g == pg && b == pb) return;
  pr = r; pg = g; pb = b;
  if (LED_ANODO_COMUN) { r = 255 - r; g = 255 - g; b = 255 - b; }
  ledcWrite(LED_R, r); ledcWrite(LED_G, g); ledcWrite(LED_B, b);
}

void actualizarLed() {
  unsigned long t = millis();
  if (modoConfig || t < blancoHasta) {          // configurando o recentrando: blanco parpadeando
    if ((t / 150) % 2 == 0) ledColor(255, 255, 255); else ledColor(0, 0, 0);
  } else if (mouse.isPaired()) {
    ledColor(0, 255, 0);
  } else {
    if ((t / 500) % 2 == 0) ledColor(0, 0, 255); else ledColor(0, 0, 0);
  }
}

// Avisa a la app cuando el mouse se empareja o se desempareja
void actualizarEstado() {
  bool p = mouse.isPaired();
  if (chEstado && p != pareadoAnterior) {
    pareadoAnterior = p;
    uint8_t e = p ? 1 : 0;
    chEstado->setValue(e);
    chEstado->notify();
    Serial.println(p ? "Mouse emparejado" : "Mouse desemparejado");
  }
}

void setup() {
  Serial.begin(115200);
  ledcAttach(LED_R, 5000, 8); ledcAttach(LED_G, 5000, 8); ledcAttach(LED_B, 5000, 8);
  ledColor(255,0,0); delay(300); ledColor(0,255,0); delay(300);
  ledColor(0,0,255); delay(300); ledColor(255,255,255); delay(300); ledColor(0,0,0);

  pinMode(PIN_RECENTRAR, INPUT_PULLUP);
  Wire.begin(21, 22);
  if (mpu.begin() != 0) { Serial.println("MPU6050 no responde."); while (true) delay(100); }
  delay(1000);
  mpu.calcOffsets();

  mouse.setLogLevel(HIDLogLevel::Normal);
  mouse.begin();

  NimBLEServer* servidor = NimBLEDevice::getServer();
  if (servidor == nullptr) {
    Serial.println("No hay servidor BLE.");
  } else {
    NimBLEService* svc = servidor->createService(UUID_SERVICIO);

    chAngulo = svc->createCharacteristic(UUID_ANGULO, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
    int16_t cero = 0; chAngulo->setValue(cero);

    chZona = svc->createCharacteristic(UUID_ZONA, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE);
    uint16_t z0 = (uint16_t)(zonaMuerta * 10);
    chZona->setValue(z0);
    chZona->setCallbacks(new CbZona());

    chSens = svc->createCharacteristic(UUID_SENS, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE);
    uint16_t s0 = (uint16_t)(sensibilidad * 100);
    chSens->setValue(s0);
    chSens->setCallbacks(new CbSens());

    chModo = svc->createCharacteristic(UUID_MODO, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE);
    uint8_t m0 = 0;
    chModo->setValue(m0);
    chModo->setCallbacks(new CbModo());

    chEstado = svc->createCharacteristic(UUID_ESTADO, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
    uint8_t e0 = 0;
    chEstado->setValue(e0);

    bool ok = servidor->start();
    Serial.print("servidor->start(): "); Serial.println(ok ? "OK" : "FALLO");
    NimBLEDevice::getAdvertising()->start();
  }
  Serial.print("Direccion BLE: "); Serial.println(NimBLEDevice::getAddress().toString().c_str());
}

void loop() {
  static unsigned long ultimoAdv = 0;
  if (millis() - ultimoAdv > 2000) {
    ultimoAdv = millis();
    NimBLEServer* s = NimBLEDevice::getServer();
    NimBLEAdvertising* a = NimBLEDevice::getAdvertising();
    if (s && !a->isAdvertising() && s->getConnectedCount() < 2) a->start();
  }

  if (modoConfig && millis() - ultimoLatido > 3000) {
    modoConfig = false;
    Serial.println("Modo configuracion: OFF (sin latido de la app)");
  }

  actualizarLed();
  actualizarEstado();
  mpu.update();

  if (digitalRead(PIN_RECENTRAR) == LOW) {
    centro = mpu.getAngleZ(); acumulador = 0; blancoHasta = millis() + 1000; delay(200);
  }

  if (millis() - ultimo < PERIODO_MS) return;
  ultimo = millis();

  float z = (mpu.getAngleZ() - centro) * SENTIDO;
  float dx = 0;
  if (fabs(z) > zonaMuerta) {
    float s = constrain((fabs(z) - zonaMuerta) / (ANGULO_MAX - zonaMuerta), 0.0, 1.0);
    dx = (z > 0 ? 1 : -1) * s * VEL_MAX * sensibilidad;
  }
  acumulador += dx; int paso = (int)acumulador; acumulador -= paso;
  if (mouse.isPaired() && paso != 0) mouse.move(paso, 0);

  if (chAngulo && ++ciclos >= 5) {
    ciclos = 0; int16_t centi = (int16_t)(z * 100);
    chAngulo->setValue(centi); chAngulo->notify();
  }
}