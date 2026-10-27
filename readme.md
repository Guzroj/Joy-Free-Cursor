# Joy-Free Cursor

Dispositivo embebido que funciona como **mouse alternativo** para usuarios con movilidad manual limitada. Capta el movimiento residual del cuerpo (rotación del cuello y, más adelante, inclinación del hombro) con sensores inerciales y lo envía a la computadora como un periférico **Bluetooth Low Energy HID** estándar, sin drivers ni software adicional.

Proyecto del curso **CE-1114 Proyecto de Aplicación de la Ingeniería en Computadores**, Escuela de Ingeniería en Computadores, Instituto Tecnológico de Costa Rica (TEC), sede Cartago.

**Autor:** Gabriel José Guzmán Rojas

---

## ¿Qué problema resuelve?

Los mouse y joysticks convencionales requieren fuerza de agarre y motricidad fina de los dedos. Las alternativas comerciales (controles operados con la boca, por ejemplo) existen, pero suelen ser costosas. Joy-Free Cursor propone una alternativa accesible y de bajo costo, basada en hardware común y software de código abierto.

## ¿Cómo funciona?

```
 IMU cuello ──┐
 (MPU-6050)   ├─ I2C ─► ESP32 ──► BLE HID ──────────► PC (mouse estándar)
 IMU hombro ──┘          │
 (planeado)              └──► BLE (servicio de configuración) ──► App de configuración
```

1. **Captura:** un MPU-6050 mide la rotación del cuello (izquierda/derecha).
2. **Procesamiento:** el firmware aplica una **zona muerta** (ignora movimientos pequeños) y convierte el ángulo en **velocidad** del cursor: mientras más se gira, más rápido se mueve.
3. **Salida:** el ESP32 se presenta ante la PC como un mouse Bluetooth.
4. **Configuración:** sobre la misma radio, el ESP32 expone un servicio BLE propio que la app de escritorio usa para leer el ángulo en vivo y ajustar parámetros.



## Hardware

- ESP32 DevKit (ESP32-WROOM-32)
- Sensor inercial MPU-6050 (GY-521) por I2C
- LED RGB de cátodo común
- Botón BOOT del DevKit (GPIO 0) para recentrar

Conexiones actuales:

| Elemento | Pin del ESP32 |
|---|---|
| MPU-6050 SDA / SCL | GPIO 21 / GPIO 22 |
| MPU-6050 VCC / GND | 3.3 V / GND |
| LED RGB (R / G / B) | GPIO 25 / 26 / 27 (con resistencias en serie) |
| Recentrar | GPIO 0 (botón BOOT) |

El sensor se monta en posición horizontal y se usa el eje Z (giro izquierda/derecha). Al no tener magnetómetro, el ángulo se integra del giroscopio y puede derivar con el tiempo; el recentrado manual lo compensa.

## Estados del LED

| Color | Significado |
|---|---|
| Azul parpadeando | Buscando conexión |
| Verde fijo | Mouse emparejado |
| Blanco parpadeando | Recentrando |

## Firmware

Se programa con **Arduino IDE** (core ESP32 3.x). Bibliotecas necesarias:

- `MPU6050_light`
- `NimBLE-Arduino` 2.5.1
- `HijelHID_BLEMouse` 0.1.0 (**con una modificación local**, ver más abajo)

Pasos:

1. Instalar las bibliotecas desde el Gestor de bibliotecas.
2. Reemplazar `HijelHID_BLEMouse.h` y `HijelHID_BLEMouse.cpp` por las versiones modificadas del proyecto (carpeta `src` de la biblioteca).
3. Abrir el sketch, seleccionar la placa ESP32 y el puerto, y subirlo.
4. Emparejar **Joy-Free Cursor** desde la configuración Bluetooth del sistema operativo.

> Si se cambia el descriptor HID o los servicios BLE, hay que quitar el dispositivo de la lista Bluetooth del sistema y volver a emparejarlo; Windows guarda en caché lo anterior.

### Modificación a HijelHID_BLEMouse

La biblioteca original asume una sola conexión: al desconectarse *cualquier* cliente borraba el estado de emparejamiento, por lo que cerrar la app de configuración dejaba al mouse sin funcionar. La versión modificada distingue la conexión HID (`_hidHandle`) del resto y solo limpia el estado cuando se cae esa conexión.

### Servicio BLE de configuración

Servicio `8f3c0001-5b7a-4e2d-9c1a-0d4f6a2b7e10`:

| Característica | UUID (termina en `...-5b7a-4e2d-9c1a-0d4f6a2b7e10`) | Acceso | Formato |
|---|---|---|---|
| Ángulo del cuello | `8f3c0002` | Lectura + notificación (cada 100 ms) | `int16` little-endian, centésimas de grado |
| Zona muerta | `8f3c0003` | Lectura + escritura | `uint16` little-endian, décimas de grado (rango 10–200) |
| Sensibilidad | `8f3c0004` | Lectura + escritura | `uint16` little-endian, porcentaje (rango 20–300) |



## Aplicación

```bash
pip install PySide6 bleak qasync
python joyfree_app.py
```

Antes de ejecutarla hay que poner la dirección BLE del ESP32 en la constante `DIRECCION` de `joyfree_app.py`. El firmware la imprime por el monitor serial al iniciar (`Direccion BLE: ...`).

## Estructura sugerida del repositorio

```
.
├── firmware/        # sketch de Arduino
├── app/             # joyfree_app.py (interfaz de configuración)
├── lib-modificada/  # HijelHID_BLEMouse modificada
└── README.md
```

## Limitaciones conocidas

- El ángulo deriva con el tiempo (giroscopio sin magnetómetro); se corrige recentrando.
- No hay compatibilidad con consolas (PlayStation, Xbox): exigen protocolos propietarios fuera del estándar HID genérico.
- La lectura de batería no está disponible mientras se alimenta con powerbank.

## Documentación del proyecto

El diseño completo (plan de proyecto, requerimientos y documento de diseño) se mantiene como documentos del curso, fuera de este repositorio.