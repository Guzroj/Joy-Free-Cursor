#include <Wire.h>
#include <MPU6050_light.h>
#include <HijelHID_BLEMouse.h>

#define UUID_SERVICIO "8f3c0001-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_ANGULO   "8f3c0002-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_ZONA     "8f3c0003-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_SENS     "8f3c0004-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_MODO     "8f3c0005-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_ESTADO   "8f3c0006-5b7a-4e2d-9c1a-0d4f6a2b7e10"
#define UUID_EJES     "8f3c0007-5b7a-4e2d-9c1a-0d4f6a2b7e10"   // bit0 = dos ejes activos, bit1 = hombro detectado
#define UUID_ANGULO_Y "8f3c0008-5b7a-4e2d-9c1a-0d4f6a2b7e10"   // angulo del hombro (centesimas de grado)
#define UUID_CENTRAR  "8f3c0009-5b7a-4e2d-9c1a-0d4f6a2b7e10"   // la app escribe 1 para recentrar
#define UUID_ZONA_Y   "8f3c000d-5b7a-4e2d-9c1a-0d4f6a2b7e10"   // zona muerta del hombro (decimas de grado)
#define UUID_PAUSA    "8f3c000e-5b7a-4e2d-9c1a-0d4f6a2b7e10"   // 1 = en pausa (el cursor no se mueve)

// ---- Parámetros ajustables ----
float       zonaMuerta   = 3.0;   // cuello, grados: la app puede cambiarla (entre 1.0 y 8.0)
float       sensibilidad = 1.0;   // factor sobre VEL_MAX (1.0 = 100%), la app puede cambiarlo
const float ANGULO_MAX = 9.0;     // el recorrido del cuello va de -9 a +9 grados
const float VEL_MAX    = 8.0;
const int   SENTIDO    = -1;   // el cuello gira sobre el eje X del sensor: derecha da angulo negativo, esto lo invierte
const int   PERIODO_MS = 20;

// ---- Botones (a GND, con pull-up interno) ----
const int PIN_BOOT    = 0;    // boton BOOT del DevKit: respaldo para recentrar sin la tapa
const int PIN_CENTRAR = 32;   // boton de calibracion = recentrar
const int PIN_PAREO   = 33;   // boton de pareo: mantener 2 s para olvidar emparejamientos
const unsigned long PAREO_MS = 2000;

// ---- Eje del hombro (segundo sensor, 0x69): se integra el giroscopio, igual que el cuello ----
const int   EJE_HOMBRO    = 0;     // eje del giroscopio en que gira el hombro: 0 = X, 1 = Y, 2 = Z
float       zonaMuertaY   = 6.0;   // grados: la app puede cambiarla (entre 1.0 y 20.0)
const float ANGULO_MAX_Y  = 30.0;  // grados para velocidad maxima (debe coincidir con MAX_Y de la app)
const int   SENTIDO_Y     = -1;    // hombro adelante = angulo positivo = cursor ARRIBA. Pon 1 si queda al reves

// ---- Recentrar: mide de nuevo el sesgo del giroscopio con el usuario quieto ----
const unsigned long MIDE_ESPERA_MS = 300;    // se descarta el primer instante (por si el boton movio el sensor)
const unsigned long MIDE_MS        = 1000;   // tiempo de medicion
const float         MIDE_RANGO_MAX = 5.0;    // grados/s: si hubo mas variacion, no estaba quieto y se descarta
const float         MIDE_DERIVA_MAX = 0.6;   // grados/s: si el promedio de la 1a y 2a mitad difiere mas, hubo movimiento lento
const float         MIDE_FIJO = 0.001;       // grados/s: un sensor vivo siempre tiene ruido; variacion menor = lectura congelada

// ---- Vigilancia del sensor del hombro ----
const float LIMITE_HOMBRO = 60.0;              // grados: el angulo del hombro no se aleja mas que esto del centro
const int   HOMBRO_IGUALES_MAX = 150;          // lecturas identicas seguidas (unos 0.3 s) = sensor congelado
const unsigned long HOMBRO_REVISA_MS = 1000;   // cada cuanto se pregunta si 0x69 responde / se intenta reiniciar

// ---- LED RGB ----
const int  LED_R = 25;
const int  LED_G = 26;
const int  LED_B = 27;
const bool LED_ANODO_COMUN = false;   // cátodo común
const uint8_t LED_BRILLO = 30;        // brillo general del LED (0 a 255). Al maximo metia ruido y tumbaba el sensor del hombro

MPU6050 mpu(Wire);      // cuello (0x68), gira sobre el eje X
MPU6050 hombro(Wire);   // hombro (0x69)
HijelBLEMouse mouse("Joy-Free Cursor", "TEC");
NimBLECharacteristic* chAngulo = nullptr;
NimBLECharacteristic* chZona = nullptr;
NimBLECharacteristic* chSens = nullptr;
NimBLECharacteristic* chModo = nullptr;
NimBLECharacteristic* chEstado = nullptr;
NimBLECharacteristic* chEjes = nullptr;
NimBLECharacteristic* chAnguloY = nullptr;
NimBLECharacteristic* chZonaY = nullptr;
NimBLECharacteristic* chPausa = nullptr;

float centro = 0, acumulador = 0;
float anguloCuello = 0;              // giroscopio X integrado (grados)
float centroH = 0, anguloHombro = 0; // giroscopio del hombro integrado (grados) y su cero
float sesgoC = 0, sesgoH = 0;        // sesgo extra del giroscopio (grados/s), se mide al recentrar
unsigned long ultimoMicros = 0;
float acumuladorY = 0;
unsigned long ultimo = 0;
int ciclos = 0;
unsigned long blancoHasta = 0;
unsigned long rojoHasta = 0;

// Medicion del sesgo (la dispara recentrar)
bool midiendo = false;
unsigned long tMide = 0;
float sumaC = 0, sumaH = 0;
float minC = 0, maxC = 0, minH = 0, maxH = 0;
int nMide = 0;
float sumaC1 = 0, sumaH1 = 0;        // primera mitad de la medicion (para ver si hubo movimiento lento)
int nMide1 = 0;

// Modo configuración: la app lo activa y manda un "latido" cada 1 s.
// Si pasan 3 s sin latido (app cerrada o conexión caída), sale solo.
bool modoConfig = false;
unsigned long ultimoLatido = 0;

// Pausa: el cursor no se mueve, pero el Bluetooth y la app siguen funcionando. Siempre arranca activo.
bool pausado = false;
volatile int solicitudPausa = -1;    // la app lo pide por BLE, se aplica en loop()

// Estado de emparejamiento que se le informa a la app (1 = mouse emparejado)
bool pareadoAnterior = false;

// Modo de dos ejes. Siempre arranca apagado: solo cuello.
bool hombroOk = false;               // el sensor 0x69 respondio al arrancar
bool hombroVivo = false;             // el sensor esta entregando datos ahora mismo (se vigila en loop)
int  hombroIguales = 0;
float hgxPrev = 0, hgyPrev = 0, hgzPrev = 0;
unsigned long tRevisaHombro = 0;
float offHX = 0, offHY = 0, offHZ = 0;   // offsets del giroscopio del hombro calculados al arrancar
bool dosEjes = false;                // eje del hombro activo
volatile int solicitudEjes = -1;     // la app lo pide por BLE, se aplica en loop()
volatile bool solicitudCentrar = false;  // la app pide recentrar por BLE, se aplica en loop()

class CbZona : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 2) {
      uint16_t d = c->getValue().getValue<uint16_t>();
      if (d >= 10 && d <= 80) {           // limita entre 1.0° y 8.0° (el recorrido llega a 9°)
        zonaMuerta = d / 10.0;
        Serial.printf("Zona muerta cuello = %.1f\n", zonaMuerta);
      }
    }
  }
};

class CbZonaY : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 2) {
      uint16_t d = c->getValue().getValue<uint16_t>();
      if (d >= 10 && d <= 200) {          // limita entre 1.0° y 20.0°
        zonaMuertaY = d / 10.0;
        Serial.printf("Zona muerta hombro = %.1f\n", zonaMuertaY);
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

class CbEjes : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 1) {
      solicitudEjes = (c->getValue().getValue<uint8_t>() & 1) ? 1 : 0;
    }
  }
};

class CbCentrar : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 1 && c->getValue().getValue<uint8_t>() == 1) solicitudCentrar = true;
  }
};

class CbPausa : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& info) override {
    if (c->getValue().size() >= 1) {
      solicitudPausa = (c->getValue().getValue<uint8_t>() & 1) ? 1 : 0;
    }
  }
};

void ledColor(uint8_t r, uint8_t g, uint8_t b) {
  static int pr = -1, pg = -1, pb = -1;
  if (r == pr && g == pg && b == pb) return;
  pr = r; pg = g; pb = b;
  r = (uint16_t)r * LED_BRILLO / 255;   // todos los colores pasan por aqui: se baja el brillo de todo
  g = (uint16_t)g * LED_BRILLO / 255;
  b = (uint16_t)b * LED_BRILLO / 255;
  if (LED_ANODO_COMUN) { r = 255 - r; g = 255 - g; b = 255 - b; }
  ledcWrite(LED_R, r); ledcWrite(LED_G, g); ledcWrite(LED_B, b);
}

void actualizarLed() {
  unsigned long t = millis();
  if (t < rojoHasta) {                                  // la medicion fallo: rojo fijo, repetir quieto
    ledColor(255, 0, 0);
  } else if (modoConfig || midiendo || t < blancoHasta) {   // configurando o recentrando: blanco parpadeando
    if ((t / 150) % 2 == 0) ledColor(255, 255, 255); else ledColor(0, 0, 0);
  } else if (pausado) {                                 // en pausa: amarillo fijo
    ledColor(255, 160, 0);
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

// Informa a la app: bit0 = dos ejes activos, bit1 = hombro detectado
void publicarEjes() {
  if (!chEjes) return;
  uint8_t v = ((hombroOk && hombroVivo) ? 2 : 0) | (dosEjes ? 1 : 0);
  chEjes->setValue(v);
  chEjes->notify();
}

// Informa a la app si esta en pausa (1) o activo (0)
void publicarPausa() {
  if (!chPausa) return;
  uint8_t v = pausado ? 1 : 0;
  chPausa->setValue(v);
  chPausa->notify();
}

void aplicarPausa(bool on) {
  pausado = on;
  acumulador = 0; acumuladorY = 0;
  publicarPausa();
  Serial.println(pausado ? "PAUSA: el cursor no se mueve" : "Pausa terminada: cursor activo");
}

// Velocidad angular del hombro en el eje elegido (grados/s)
float gyroHombro() {
  if (EJE_HOMBRO == 0) return hombro.getGyroX();
  if (EJE_HOMBRO == 1) return hombro.getGyroY();
  return hombro.getGyroZ();
}

// ---- Vigilancia del hombro: detecta si el sensor deja de entregar datos y lo reinicia ----
bool hombroResponde() {
  Wire.beginTransmission(0x69);
  return Wire.endTransmission() == 0;
}

void marcarHombroCaido(const char* motivo) {
  if (!hombroVivo) return;
  hombroVivo = false;
  acumuladorY = 0;
  Serial.printf("HOMBRO CAIDO (%s): se intentara reiniciar\n", motivo);
  publicarEjes();                       // la app muestra "Sensor del hombro no detectado"
}

void reiniciarHombro() {
  if (!hombroResponde()) return;
  if (hombro.begin() != 0) return;
  hombro.setGyroOffsets(offHX, offHY, offHZ);   // conserva la calibracion del arranque
  hombroVivo = true;
  hombroIguales = 0;
  centroH = anguloHombro; acumuladorY = 0;      // el hombro vuelve con el centro donde esta
  Serial.println("Hombro reiniciado: vuelve a funcionar");
  publicarEjes();
}

void vigilarHombro() {
  float gx = hombro.getGyroX(), gy = hombro.getGyroY(), gz = hombro.getGyroZ();
  if (gx == hgxPrev && gy == hgyPrev && gz == hgzPrev) {
    if (hombroIguales < 100000) hombroIguales++;
  } else {
    hombroIguales = 0;
  }
  hgxPrev = gx; hgyPrev = gy; hgzPrev = gz;

  if (hombroVivo && hombroIguales >= HOMBRO_IGUALES_MAX) marcarHombroCaido("lectura congelada");

  if (millis() - tRevisaHombro >= HOMBRO_REVISA_MS) {
    tRevisaHombro = millis();
    if (hombroVivo) {
      if (!hombroResponde()) marcarHombroCaido("0x69 no responde");
    } else {
      reiniciarHombro();
    }
  }
}

// Empieza a medir el sesgo con el usuario quieto; al terminar deja el cero donde esta
void iniciarMedicion() {
  midiendo = true;
  tMide = millis();
  sumaC = 0; sumaH = 0; nMide = 0;
  sumaC1 = 0; sumaH1 = 0; nMide1 = 0;
  Serial.println("Midiendo sesgo: quedate quieto");
}

// Promedio de la 1a mitad contra la 2a: si cambia, hubo un movimiento lento que el rango no ve
bool mitadesIguales(float suma, float suma1) {
  int n2 = nMide - nMide1;
  if (nMide1 < 10 || n2 < 10) return false;
  float m1 = suma1 / nMide1, m2 = (suma - suma1) / n2;
  return fabs(m1 - m2) < MIDE_DERIVA_MAX;
}

void terminarMedicion() {
  bool usarHombro = hombroOk && hombroVivo;
  bool quietoC = (nMide >= 20) && (maxC - minC < MIDE_RANGO_MAX) && mitadesIguales(sumaC, sumaC1);
  bool fijoH = usarHombro && (nMide >= 20) && (maxH - minH < MIDE_FIJO);
  if (fijoH) marcarHombroCaido("lectura fija al recentrar");   // no se acepta como sesgo
  bool quietoH = !usarHombro ||
                 (!fijoH && (nMide >= 20) && (maxH - minH < MIDE_RANGO_MAX) && mitadesIguales(sumaH, sumaH1));
  if (quietoC) sesgoC = sumaC / nMide;
  if (quietoH && usarHombro && !fijoH) sesgoH = sumaH / nMide;
  if (quietoC && quietoH && !fijoH) {
    Serial.printf("Sesgo cuello %.2f  hombro %.2f grados/s\n", sesgoC, sesgoH);
  } else {
    rojoHasta = millis() + 700;       // no estaba quieto (o el hombro no da datos): se conserva el sesgo anterior
    Serial.printf("Medicion rechazada (cuello %s, hombro %s): se conserva el sesgo anterior. Repite quieto.\n",
                  quietoC ? "ok" : "se movio", fijoH ? "sin datos" : (quietoH ? "ok" : "se movio"));
  }
  centro = anguloCuello; acumulador = 0;
  centroH = anguloHombro; acumuladorY = 0;
  midiendo = false;
  Serial.println("Recentrado");
}

void actualizarMedicion(float gC, float gH) {
  unsigned long t = millis() - tMide;
  if (t >= MIDE_ESPERA_MS) {
    if (nMide == 0) { minC = maxC = gC; minH = maxH = gH; }
    else {
      if (gC < minC) minC = gC;
      if (gC > maxC) maxC = gC;
      if (gH < minH) minH = gH;
      if (gH > maxH) maxH = gH;
    }
    sumaC += gC; sumaH += gH; nMide++;
    if (t < MIDE_ESPERA_MS + MIDE_MS / 2) { sumaC1 += gC; sumaH1 += gH; nMide1++; }
  }
  if (t >= MIDE_ESPERA_MS + MIDE_MS) terminarMedicion();
}

void aplicarEjes(bool on) {
  if (on && !(hombroOk && hombroVivo)) on = false;
  if (on && !dosEjes) iniciarMedicion();   // al activar, mide el sesgo y la postura actual queda como reposo
  dosEjes = on;
  publicarEjes();
  Serial.println(dosEjes ? "Dos ejes: ON" : "Dos ejes: OFF (solo cuello)");
}

// Mide el sesgo del giroscopio (1 s quieto) y pone el "cero" donde esta el usuario (cuello y hombro)
void recentrar() {
  if (midiendo) return;
  iniciarMedicion();
}

// Borra los emparejamientos guardados: el ESP32 queda visible para emparejar con otra PC
void olvidarEmparejamientos() {
  Serial.println("Pareo: olvidando emparejamientos");
  mouse.clearBonds();
  blancoHasta = millis() + 1000;        // confirmacion; despues queda en azul parpadeando
}

void revisarBotones() {
  // Recentrar: boton de calibracion (GPIO 32) o BOOT (GPIO 0), una vez por pulsacion
  static bool centrarPrev = false;
  static unsigned long tCentrar = 0;
  bool centrarAhora = (digitalRead(PIN_CENTRAR) == LOW || digitalRead(PIN_BOOT) == LOW);
  if (centrarAhora && !centrarPrev && millis() - tCentrar > 250) {
    tCentrar = millis();
    recentrar();
  }
  centrarPrev = centrarAhora;

  // Pareo: hay que mantenerlo PAREO_MS para evitar borrados por accidente
  static bool pareoPulsado = false, pareoHecho = false;
  static unsigned long tPareo = 0;
  if (digitalRead(PIN_PAREO) == LOW) {
    if (!pareoPulsado) { pareoPulsado = true; pareoHecho = false; tPareo = millis(); }
    else if (!pareoHecho && millis() - tPareo >= PAREO_MS) {
      pareoHecho = true;
      olvidarEmparejamientos();
    }
  } else {
    pareoPulsado = false;
  }
}

void setup() {
  Serial.begin(115200);
  ledcAttach(LED_R, 5000, 8); ledcAttach(LED_G, 5000, 8); ledcAttach(LED_B, 5000, 8);
  ledColor(255,0,0); delay(300); ledColor(0,255,0); delay(300);
  ledColor(0,0,255); delay(300);
  ledColor(255,255,255);                  // BLANCO FIJO = calibrando: no muevas el dispositivo hasta que se apague

  pinMode(PIN_BOOT, INPUT_PULLUP);
  pinMode(PIN_CENTRAR, INPUT_PULLUP);
  pinMode(PIN_PAREO, INPUT_PULLUP);
  Wire.begin(21, 22);
  if (mpu.begin() != 0) {
    Serial.println("MPU6050 no responde.");
    ledColor(255, 0, 0);
    while (true) delay(100);
  }
  delay(1000);
  mpu.calcOffsets(true, false);           // solo giroscopio: el sensor ya no va plano

  // Segundo sensor (hombro): si no esta, todo sigue funcionando solo con el cuello
  hombro.setAddress(0x69);
  if (hombro.begin() == 0) {
    hombroOk = true;
    hombroVivo = true;
    hombro.calcOffsets(true, false);      // solo giroscopio
    offHX = hombro.getGyroXoffset(); offHY = hombro.getGyroYoffset(); offHZ = hombro.getGyroZoffset();
    Serial.println("Sensor de hombro (0x69) detectado.");
  } else {
    Serial.println("Sensor de hombro NO detectado: solo eje del cuello.");
  }
  ledColor(0, 0, 0);                      // fin de la calibracion

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

    chEjes = svc->createCharacteristic(UUID_EJES, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::NOTIFY);
    uint8_t j0 = (hombroOk && hombroVivo) ? 2 : 0;
    chEjes->setValue(j0);
    chEjes->setCallbacks(new CbEjes());

    chAnguloY = svc->createCharacteristic(UUID_ANGULO_Y, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
    int16_t y0 = 0; chAnguloY->setValue(y0);

    NimBLECharacteristic* chCentrar = svc->createCharacteristic(UUID_CENTRAR, NIMBLE_PROPERTY::WRITE);
    chCentrar->setCallbacks(new CbCentrar());

    chZonaY = svc->createCharacteristic(UUID_ZONA_Y, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE);
    uint16_t zy0 = (uint16_t)(zonaMuertaY * 10);
    chZonaY->setValue(zy0);
    chZonaY->setCallbacks(new CbZonaY());

    chPausa = svc->createCharacteristic(UUID_PAUSA, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::NOTIFY);
    uint8_t p0 = 0;
    chPausa->setValue(p0);
    chPausa->setCallbacks(new CbPausa());

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

  if (solicitudEjes >= 0) {
    aplicarEjes(solicitudEjes == 1);
    solicitudEjes = -1;
  }

  if (solicitudPausa >= 0) {
    aplicarPausa(solicitudPausa == 1);
    solicitudPausa = -1;
  }

  actualizarLed();
  actualizarEstado();
  mpu.update();
  if (hombroOk) {
    hombro.update();
    vigilarHombro();
  }

  // Angulos: se integra el giroscopio (restando el sesgo medido al recentrar).
  // Cuello: giroscopio X (el acelerometro no ve este giro: la gravedad cae sobre X)
  unsigned long ahoraUs = micros();
  float dt = (ultimoMicros != 0) ? (ahoraUs - ultimoMicros) / 1000000.0f : 0.0f;
  ultimoMicros = ahoraUs;
  float gC = mpu.getGyroX();
  float gH = (hombroOk && hombroVivo) ? gyroHombro() : 0.0f;
  anguloCuello += (gC - sesgoC) * dt;
  if (hombroOk && hombroVivo) {
    anguloHombro += (gH - sesgoH) * dt;
    // limite: si el sesgo quedo un poco mal, el angulo no se va lejos y el hombro responde apenas regresa
    if (anguloHombro - centroH > LIMITE_HOMBRO) anguloHombro = centroH + LIMITE_HOMBRO;
    if (anguloHombro - centroH < -LIMITE_HOMBRO) anguloHombro = centroH - LIMITE_HOMBRO;
  }

  if (solicitudCentrar) { solicitudCentrar = false; recentrar(); }
  revisarBotones();

  if (midiendo) {                        // mientras mide el sesgo el cursor no se mueve
    actualizarMedicion(gC, gH);
    return;
  }

  if (millis() - ultimo < PERIODO_MS) return;
  ultimo = millis();

  float z = (anguloCuello - centro) * SENTIDO;
  float dx = 0;
  if (fabs(z) > zonaMuerta) {
    float s = constrain((fabs(z) - zonaMuerta) / (ANGULO_MAX - zonaMuerta), 0.0, 1.0);
    dx = (z > 0 ? 1 : -1) * s * VEL_MAX * sensibilidad;
  }
  acumulador += dx; int paso = (int)acumulador; acumulador -= paso;

  // ---- Eje vertical (hombro), solo si el modo de dos ejes esta activo ----
  float y = 0, dy = 0;
  if (dosEjes && hombroVivo) {
    y = (anguloHombro - centroH) * SENTIDO_Y;
    if (fabs(y) > zonaMuertaY) {
      float sy = constrain((fabs(y) - zonaMuertaY) / (ANGULO_MAX_Y - zonaMuertaY), 0.0, 1.0);
      dy = (y > 0 ? 1 : -1) * sy * VEL_MAX * sensibilidad;
    }
  }
  acumuladorY += dy; int pasoY = (int)acumuladorY; acumuladorY -= pasoY;

  if (!pausado && mouse.isPaired() && (paso != 0 || pasoY != 0)) mouse.move(paso, pasoY);

  if (chAngulo && ++ciclos >= 5) {
    ciclos = 0; int16_t centi = (int16_t)(z * 100);
    chAngulo->setValue(centi); chAngulo->notify();
    if (chAnguloY && dosEjes) {
      int16_t centiY = (int16_t)(y * 100);
      chAnguloY->setValue(centiY); chAnguloY->notify();
    }
  }
}