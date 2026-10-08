import asyncio
import math
import struct
import sys
from pathlib import Path

import qasync
from bleak import BleakClient
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QStackedWidget,
                               QVBoxLayout, QWidget)

DIRECCION = "00:70:07:e7:98:56"
UUID_ANGULO = "8f3c0002-5b7a-4e2d-9c1a-0d4f6a2b7e10"
UUID_ZONA = "8f3c0003-5b7a-4e2d-9c1a-0d4f6a2b7e10"
UUID_SENS = "8f3c0004-5b7a-4e2d-9c1a-0d4f6a2b7e10"
UUID_MODO = "8f3c0005-5b7a-4e2d-9c1a-0d4f6a2b7e10"
UUID_ESTADO = "8f3c0006-5b7a-4e2d-9c1a-0d4f6a2b7e10"   # 1 = mouse emparejado en el sistema
DEF_ZONA = 50      # 5.0° (décimas de grado)
DEF_SENS = 100     # 100 %
ANGULO_MAX = 25.0
LOGO = Path(__file__).parent / "logo.png"   # debe estar junto a este archivo

AZUL = "#2F6BFF"
VERDE = "#14804A"
GRIS = "#9AA6B8"

ESTILO = """
QWidget { background: #F3F6FB; color: #1F2937; font-family: "Segoe UI"; font-size: 14px; }
QLabel { background: transparent; }
QFrame#tarjeta { background: white; border: 1px solid #E3E8F0; border-radius: 14px; }
QLabel#titulo { font-size: 22px; font-weight: 700; }
QLabel#bienvenida { font-size: 26px; font-weight: 700; color: #1F2937; }
QLabel#sub { color: #6B7280; }
QLabel#etiqueta { color: #6B7280; font-size: 12px; font-weight: 600; }
QLabel#valor { font-size: 17px; font-weight: 700; }
QLabel#angulo { font-size: 44px; font-weight: 700; color: #2F6BFF; }
QLabel#chip { background: #DDF6E6; color: #14804A; border-radius: 12px;
              padding: 4px 12px; font-weight: 700; }
QSlider { background: transparent; min-height: 22px; }
QSlider::groove:horizontal { height: 6px; background: #DCE6F7; border-radius: 3px; margin: 0; }
QSlider::add-page:horizontal { background: #DCE6F7; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #2F6BFF; border-radius: 3px; }
QSlider::handle:horizontal { background: white; border: 2px solid #2F6BFF;
                             width: 16px; height: 16px; margin: -6px 0; border-radius: 9px; }
QSlider::sub-page:horizontal:disabled { background: #C4CBD6; border-radius: 3px; }
QSlider::handle:horizontal:disabled { border-color: #C4CBD6; }
QPushButton { background: #2F6BFF; color: white; border: none; border-radius: 10px;
              padding: 10px 18px; font-weight: 700; }
QPushButton:disabled { background: #DCE1E9; color: #9AA6B8; }
QPushButton#secundario { background: white; color: #2F6BFF; border: 2px solid #2F6BFF; }
QPushButton#secundario:disabled { background: #F3F6FB; color: #9AA6B8; border: 2px solid #DCE1E9; }
"""


def logo_label(tam):
    """QLabel con el logo escalado a tam×tam px, o None si falta logo.png."""
    if not LOGO.exists():
        return None
    lbl = QLabel()
    lbl.setPixmap(QPixmap(str(LOGO)).scaled(tam, tam, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lbl.setFixedSize(tam, tam)
    return lbl


def tarjeta():
    f = QFrame()
    f.setObjectName("tarjeta")
    return f


class Medidor(QWidget):
    """Medio círculo: izquierda = -25°, derecha = +25°."""

    def __init__(self):
        super().__init__()
        self.valor = 0.0
        self.zona = 5.0
        self.setMinimumSize(380, 210)

    def set_valor(self, v):
        self.valor = v
        self.update()

    def set_zona(self, z):
        self.zona = z
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        grosor = 18
        r = min(w / 2 - 40, h - 60)
        cx, cy = w / 2, h - 36
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        def arco(color, inicio, tramo):
            p.setPen(QPen(QColor(color), grosor, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(rect, int(inicio * 16), int(tramo * 16))

        k = 90 / ANGULO_MAX                 # grados de dibujo por grado real
        zd = self.zona * k
        arco("#DCE6F7", 0, 180)             # pista
        arco("#C4CBD6", 90 - zd, 2 * zd)    # zona muerta

        v = max(-ANGULO_MAX, min(ANGULO_MAX, self.valor))
        if v > self.zona:                   # derecha
            arco(AZUL, 90 - zd, -(v - self.zona) * k)
        elif v < -self.zona:                # izquierda
            arco(AZUL, 90 + zd, (-v - self.zona) * k)

        a = math.radians(90 - v * k)        # aguja
        x = cx + (r - 6) * math.cos(a)
        y = cy - (r - 6) * math.sin(a)
        p.setPen(QPen(QColor("#1F2937"), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(int(cx), int(cy), int(x), int(y))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1F2937"))
        p.drawEllipse(int(cx - 9), int(cy - 9), 18, 18)

        p.setPen(QColor("#6B7280"))
        p.drawText(QRectF(cx - r - 35, cy + 8, 70, 20), Qt.AlignCenter, "Izquierda")
        p.drawText(QRectF(cx + r - 35, cy + 8, 70, 20), Qt.AlignCenter, "Derecha")
        p.drawText(QRectF(cx - 35, cy + 12, 70, 20), Qt.AlignCenter, "0°")


class Ventana(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Joy-Free Cursor")
        if LOGO.exists():
            self.setWindowIcon(QIcon(str(LOGO)))
        self.resize(1000, 600)
        self.setMinimumSize(860, 520)
        self.setStyleSheet(ESTILO)
        self.cliente = None          # conexión BLE activa (None si no hay)
        self.conectado_ble = False   # la app ya habla con el ESP32
        self.emparejado = False      # el sistema operativo ya emparejó el mouse
        self.en_config = False
        self._tareas = set()
        self.latido = QTimer(self)   # mientras se configura, avisa al ESP32 cada 1 s
        self.latido.setInterval(1000)
        self.latido.timeout.connect(self.enviar_latido)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        self.pila = QStackedWidget()
        raiz.addWidget(self.pila)
        self.pila.addWidget(self.crear_bienvenida())
        self.pila.addWidget(self.crear_panel())

        self.puntos = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animar_busqueda)
        self.timer.start(450)

    # ---------- pantallas ----------
    def crear_bienvenida(self):
        pag = QWidget()
        lay = QVBoxLayout(pag)
        lay.setContentsMargins(30, 30, 30, 30)
        t = tarjeta()
        tl = QVBoxLayout(t)
        tl.setContentsMargins(30, 60, 30, 60)
        tl.addStretch()
        grande = logo_label(130)
        if grande:
            tl.addWidget(grande, alignment=Qt.AlignCenter)
            tl.addSpacing(18)
        self.msg = msg = QLabel("Bienvenido,\npor favor conectar\nel Joy-Free Cursor")
        msg.setObjectName("bienvenida")
        msg.setAlignment(Qt.AlignCenter)
        tl.addWidget(msg)
        self.lbl_busca = QLabel("Buscando dispositivo")
        self.lbl_busca.setObjectName("sub")
        self.lbl_busca.setAlignment(Qt.AlignCenter)
        tl.addSpacing(20)
        tl.addWidget(self.lbl_busca)
        tl.addStretch()
        lay.addWidget(t)
        return pag

    def crear_panel(self):
        pag = QWidget()
        lay = QVBoxLayout(pag)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        cab = QHBoxLayout()
        titulo = QLabel("Joy-Free Cursor")
        titulo.setObjectName("titulo")
        self.chip = QLabel("● Conectado")
        self.chip.setObjectName("chip")
        self.chip.setMinimumWidth(140)
        self.chip.setAlignment(Qt.AlignCenter)
        pequeno = logo_label(44)
        if pequeno:
            cab.addWidget(pequeno)
            cab.addSpacing(6)
        cab.addWidget(titulo)
        cab.addStretch()
        cab.addWidget(self.chip)
        lay.addLayout(cab)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(14)
        izq = QVBoxLayout()
        der = QVBoxLayout()
        der.setSpacing(14)

        fila = QHBoxLayout()
        fila.setSpacing(14)
        fila.addWidget(self.dato("CONEXIÓN", "Bluetooth LE", AZUL))
        fila.addWidget(self.dato("BATERÍA", "No disponible", GRIS))
        der.addLayout(fila)

        # medidor
        t = tarjeta()
        tl = QVBoxLayout(t)
        tl.setContentsMargins(16, 14, 16, 14)
        et = QLabel("ÁNGULO DEL CUELLO")
        et.setObjectName("etiqueta")
        tl.addWidget(et)
        self.medidor = Medidor()
        tl.addWidget(self.medidor)
        self.lbl_angulo = QLabel("+0.0°")
        self.lbl_angulo.setObjectName("angulo")
        self.lbl_angulo.setAlignment(Qt.AlignCenter)
        tl.addWidget(self.lbl_angulo)
        izq.addWidget(t)

        # ajustes
        t2 = tarjeta()
        al = QVBoxLayout(t2)
        al.setContentsMargins(16, 14, 16, 14)
        al.setSpacing(8)
        et2 = QLabel("AJUSTES")
        et2.setObjectName("etiqueta")
        al.addWidget(et2)

        self.btn_config = QPushButton("Entrar en modo configuración")
        self.btn_config.clicked.connect(self.alternar_config)
        al.addWidget(self.btn_config)
        self.lbl_ayuda = QLabel("Activa el modo configuración para cambiar los valores.")
        self.lbl_ayuda.setObjectName("sub")
        self.lbl_ayuda.setWordWrap(True)
        al.addWidget(self.lbl_ayuda)

        lay_z, self.sl_zona, self.lbl_zona = self.crear_slider(
            "Zona muerta", 10, 200, DEF_ZONA, lambda v: f"{v / 10:.1f}°")
        lay_s, self.sl_sens, self.lbl_sens = self.crear_slider(
            "Sensibilidad", 20, 300, DEF_SENS, lambda v: f"{v} %")
        al.addLayout(lay_z)
        al.addLayout(lay_s)

        # los cambios se mandan 200 ms después de dejar de mover el slider
        self.t_zona = QTimer(self)
        self.t_zona.setSingleShot(True)
        self.t_zona.setInterval(200)
        self.t_zona.timeout.connect(lambda: self.enviar(UUID_ZONA, self.sl_zona.value()))
        self.t_sens = QTimer(self)
        self.t_sens.setSingleShot(True)
        self.t_sens.setInterval(200)
        self.t_sens.timeout.connect(lambda: self.enviar(UUID_SENS, self.sl_sens.value()))
        self.sl_zona.valueChanged.connect(self.zona_cambio)
        self.sl_sens.valueChanged.connect(self.sens_cambio)

        self.btn_reset = QPushButton("Restablecer valores")
        self.btn_reset.setObjectName("secundario")
        self.btn_reset.clicked.connect(self.restablecer)
        al.addWidget(self.btn_reset)

        btn = QPushButton("Recentrar")
        btn.setObjectName("secundario")
        btn.setEnabled(False)
        al.addWidget(btn)
        self.aplicar_modo(enviar=False)
        der.addWidget(t2)
        der.addStretch()
        cuerpo.addLayout(izq, 3)
        cuerpo.addLayout(der, 2)
        lay.addLayout(cuerpo)
        return pag

    def dato(self, etiqueta, valor, color):
        t = tarjeta()
        tl = QVBoxLayout(t)
        tl.setContentsMargins(16, 12, 16, 12)
        a = QLabel(etiqueta)
        a.setObjectName("etiqueta")
        b = QLabel(valor)
        b.setObjectName("valor")
        b.setStyleSheet(f"color: {color};")
        tl.addWidget(a)
        tl.addWidget(b)
        return t

    def crear_slider(self, nombre, minimo, maximo, inicial, formato):
        fila = QHBoxLayout()
        lbl = QLabel(nombre)
        lbl.setMinimumWidth(100)
        sl = QSlider(Qt.Horizontal)
        sl.setRange(minimo, maximo)
        sl.setValue(inicial)
        val = QLabel(formato(inicial))
        val.setMinimumWidth(52)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val.setObjectName("valor")
        sl._formato = formato
        fila.addWidget(lbl)
        fila.addWidget(sl)
        fila.addWidget(val)
        return fila, sl, val

    # ---------- acciones ----------
    def animar_busqueda(self):
        self.puntos = (self.puntos + 1) % 4
        base = "Esperando emparejamiento" if self.conectado_ble else "Buscando dispositivo"
        self.lbl_busca.setText(base + "." * self.puntos)

    def mostrar(self, conectado):
        """Estado de la conexión BLE con el ESP32 (no implica que esté emparejado)."""
        self.conectado_ble = conectado
        if not conectado:
            self.cliente = None
            self.emparejado = False
        self.refrescar_pantalla()

    def poner_emparejado(self, valor):
        self.emparejado = valor
        self.refrescar_pantalla()

    def refrescar_pantalla(self):
        listo = self.conectado_ble and self.emparejado
        if not listo and self.en_config:     # salir del modo configuración
            self.en_config = False
            self.aplicar_modo(enviar=False)
        if self.conectado_ble and not self.emparejado:
            self.msg.setText("Dispositivo encontrado,\nfalta emparejarlo en el\nBluetooth de Windows")
        else:
            self.msg.setText("Bienvenido,\npor favor conectar\nel Joy-Free Cursor")
        self.pila.setCurrentIndex(1 if listo else 0)

    def actualizar_angulo(self, grados):
        self.medidor.set_valor(grados)
        self.lbl_angulo.setText(f"{grados:+.1f}°")

    def poner_valores(self, zona_decimas, sens_pct):
        """Muestra en los sliders lo que tiene el ESP32 (sin volver a enviarlo)."""
        for sl, lbl, v in ((self.sl_zona, self.lbl_zona, zona_decimas),
                           (self.sl_sens, self.lbl_sens, sens_pct)):
            sl.blockSignals(True)
            sl.setValue(v)
            sl.blockSignals(False)
            lbl.setText(sl._formato(v))
        self.medidor.set_zona(zona_decimas / 10)

    # ---------- ajustes ----------
    def zona_cambio(self, v):
        self.lbl_zona.setText(self.sl_zona._formato(v))
        self.medidor.set_zona(v / 10)
        self.t_zona.start()

    def sens_cambio(self, v):
        self.lbl_sens.setText(self.sl_sens._formato(v))
        self.t_sens.start()

    def restablecer(self):
        self.t_zona.stop()
        self.t_sens.stop()
        self.poner_valores(DEF_ZONA, DEF_SENS)
        self.enviar(UUID_ZONA, DEF_ZONA)
        self.enviar(UUID_SENS, DEF_SENS)

    def alternar_config(self):
        self.en_config = not self.en_config
        self.aplicar_modo(enviar=True)

    def aplicar_modo(self, enviar):
        on = self.en_config
        self.sl_zona.setEnabled(on)
        self.sl_sens.setEnabled(on)
        self.btn_reset.setEnabled(on)
        self.lbl_ayuda.setVisible(not on)
        if on:
            self.btn_config.setText("Salir del modo configuración")
            self.btn_config.setStyleSheet("background: #F59E0B;")
            self.chip.setText("● Configurando")
            self.chip.setStyleSheet("background: #FFF1D6; color: #B45309;")
            self.latido.start()
        else:
            self.btn_config.setText("Entrar en modo configuración")
            self.btn_config.setStyleSheet("")
            self.chip.setText("● Conectado")
            self.chip.setStyleSheet("")
            self.latido.stop()
        if enviar:
            self.enviar(UUID_MODO, 1 if on else 0, "<B")

    def enviar_latido(self):
        if self.en_config:
            self.enviar(UUID_MODO, 1, "<B")

    # ---------- escritura BLE ----------
    def enviar(self, uuid, valor, fmt="<H"):
        if self.cliente is None:
            return
        t = asyncio.ensure_future(self._escribir(uuid, struct.pack(fmt, valor)))
        self._tareas.add(t)
        t.add_done_callback(self._tareas.discard)

    async def _escribir(self, uuid, datos):
        try:
            if self.cliente is not None:
                await self.cliente.write_gatt_char(uuid, datos, response=True)
        except Exception as e:
            print("BLE escribir:", e)


async def ciclo_ble(ventana):
    """Se conecta, escucha el ángulo y reintenta si se desconecta."""
    while True:
        try:
            loop = asyncio.get_running_loop()
            desconectado = asyncio.Event()

            def al_desconectar(_):
                loop.call_soon_threadsafe(desconectado.set)

            def al_recibir(_, datos):
                ventana.actualizar_angulo(struct.unpack("<h", datos)[0] / 100)

            async with BleakClient(DIRECCION, disconnected_callback=al_desconectar) as c:
                zona = struct.unpack("<H", await c.read_gatt_char(UUID_ZONA))[0]
                sens = struct.unpack("<H", await c.read_gatt_char(UUID_SENS))[0]
                ventana.poner_valores(zona, sens)
                ventana.cliente = c
                estado = (await c.read_gatt_char(UUID_ESTADO))[0] == 1
                ventana.poner_emparejado(estado)
                ventana.mostrar(True)
                await c.start_notify(UUID_ESTADO, lambda _, d: ventana.poner_emparejado(d[0] == 1))
                await c.start_notify(UUID_ANGULO, al_recibir)
                await desconectado.wait()
        except Exception as e:
            print("BLE:", e)
        ventana.mostrar(False)
        await asyncio.sleep(2)


def main():
    if sys.platform == "win32":      # para que la barra de tareas use el logo y no el de Python
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tec.joyfreecursor.app")
    app = QApplication(sys.argv)
    if LOGO.exists():
        app.setWindowIcon(QIcon(str(LOGO)))
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    cierre = asyncio.Event()
    app.aboutToQuit.connect(cierre.set)

    ventana = Ventana()
    ventana.show()
    with loop:
        tarea = loop.create_task(ciclo_ble(ventana))
        loop.run_until_complete(cierre.wait())
        tarea.cancel()


if __name__ == "__main__":
    main()