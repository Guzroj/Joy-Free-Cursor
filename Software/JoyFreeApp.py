import asyncio
import math
import struct
import sys

import qasync
from bleak import BleakClient
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QStackedWidget,
                               QVBoxLayout, QWidget)

DIRECCION = "00:70:07:e7:98:56"
UUID_ANGULO = "8f3c0002-5b7a-4e2d-9c1a-0d4f6a2b7e10"
UUID_ZONA = "8f3c0003-5b7a-4e2d-9c1a-0d4f6a2b7e10"
ANGULO_MAX = 25.0

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
"""


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
        self.resize(1000, 600)
        self.setMinimumSize(860, 520)
        self.setStyleSheet(ESTILO)
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
        msg = QLabel("Bienvenido,\npor favor conectar\nel Joy-Free Cursor")
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
        chip = QLabel("● Conectado")
        chip.setObjectName("chip")
        cab.addWidget(titulo)
        cab.addStretch()
        cab.addWidget(chip)
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

        # ajustes (deshabilitados por ahora)
        t2 = tarjeta()
        al = QVBoxLayout(t2)
        al.setContentsMargins(16, 14, 16, 14)
        et2 = QLabel("AJUSTES  (próximamente)")
        et2.setObjectName("etiqueta")
        al.addWidget(et2)
        al.addLayout(self.fila_slider("Zona muerta", 10, 200, 50))
        al.addLayout(self.fila_slider("Sensibilidad", 20, 300, 100))
        btn = QPushButton("Recentrar")
        btn.setEnabled(False)
        al.addWidget(btn)
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

    def fila_slider(self, nombre, minimo, maximo, inicial):
        fila = QHBoxLayout()
        lbl = QLabel(nombre)
        lbl.setMinimumWidth(100)
        s = QSlider(Qt.Horizontal)
        s.setRange(minimo, maximo)
        s.setValue(inicial)
        s.setEnabled(False)
        fila.addWidget(lbl)
        fila.addWidget(s)
        return fila

    # ---------- acciones ----------
    def animar_busqueda(self):
        self.puntos = (self.puntos + 1) % 4
        self.lbl_busca.setText("Buscando dispositivo" + "." * self.puntos)

    def mostrar(self, conectado):
        self.pila.setCurrentIndex(1 if conectado else 0)

    def actualizar_angulo(self, grados):
        self.medidor.set_valor(grados)
        self.lbl_angulo.setText(f"{grados:+.1f}°")

    def poner_zona(self, grados):
        self.medidor.set_zona(grados)


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
                zona = struct.unpack("<H", await c.read_gatt_char(UUID_ZONA))[0] / 10
                ventana.poner_zona(zona)
                ventana.mostrar(True)
                await c.start_notify(UUID_ANGULO, al_recibir)
                await desconectado.wait()
        except Exception as e:
            print("BLE:", e)
        ventana.mostrar(False)
        await asyncio.sleep(2)


def main():
    app = QApplication(sys.argv)
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