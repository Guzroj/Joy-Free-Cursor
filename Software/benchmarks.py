"""Benchmarks de Joy-Free Cursor: seguir puntos y camara tipo juego.

Los resultados de cada intento se guardan en resultados_benchmarks.json (junto a este archivo).
Como el dispositivo no hace clic, un objetivo se logra manteniendo el cursor (o la mira) encima
durante un tiempo de permanencia.
"""
import json
import math
import os
import random
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

RUTA_JSON = Path(__file__).parent / "resultados_benchmarks.json"
SEMILLA = 2026                    # misma secuencia de objetivos en cada intento (para poder comparar)
TIEMPO_MAX_OBJETIVO_S = 20.0      # si un objetivo no se logra en este tiempo, cuenta como fallo
DISPOSITIVOS = ["Joy-Free Cursor", "Mouse normal"]
MORADO = "#7C3AED"

ESPERA, PRUEBA, FIN = 0, 1, 2


def promedio(valores, decimales=3):
    v = [x for x in valores if x is not None]
    return round(sum(v) / len(v), decimales) if v else None


# ----------------------------------------------------------------------------
# Almacen de resultados (JSON)
# ----------------------------------------------------------------------------
class Almacen:
    def __init__(self, ruta=RUTA_JSON):
        self.ruta = Path(ruta)

    def _leer(self):
        if not self.ruta.exists():
            return {"version": 1, "corridas": []}
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            if isinstance(datos, dict) and isinstance(datos.get("corridas"), list):
                return datos
        except (OSError, ValueError):
            pass
        try:                                   # archivo danado: se conserva aparte y se empieza otro
            os.replace(self.ruta, self.ruta.with_suffix(".corrupto.json"))
        except OSError:
            pass
        return {"version": 1, "corridas": []}

    @staticmethod
    def _coincide(c, benchmark, usuario, dispositivo):
        return (c.get("benchmark") == benchmark and c.get("usuario") == usuario
                and c.get("dispositivo") == dispositivo)

    def contar(self, benchmark, usuario, dispositivo):
        return sum(1 for c in self._leer()["corridas"] if self._coincide(c, benchmark, usuario, dispositivo))

    def guardar(self, corrida):
        """Agrega una corrida. Devuelve (id, numero de intento de ese usuario con ese dispositivo)."""
        datos = self._leer()
        corridas = datos["corridas"]
        intento = 1 + sum(1 for c in corridas
                          if self._coincide(c, corrida["benchmark"], corrida["usuario"], corrida["dispositivo"]))
        nueva = {
            "id": max([c.get("id", 0) for c in corridas], default=0) + 1,
            "benchmark": corrida["benchmark"],
            "usuario": corrida["usuario"],
            "dispositivo": corrida["dispositivo"],
            "intento": intento,
            "fecha_hora": corrida["fecha_hora"],
        }
        nueva.update({k: v for k, v in corrida.items() if k not in nueva})
        corridas.append(nueva)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.ruta)
        return nueva["id"], intento


# ----------------------------------------------------------------------------
# Logica del benchmark 1: seguir puntos (sin interfaz, para poder probarla)
# ----------------------------------------------------------------------------
class LogicaPuntos:
    def __init__(self, n_puntos, permanencia_s, ancho, alto, semilla=SEMILLA,
                 tiempo_max_s=TIEMPO_MAX_OBJETIVO_S):
        self.n = n_puntos
        self.permanencia = permanencia_s
        self.ancho, self.alto = ancho, alto
        self.radio = max(28.0, 0.045 * min(ancho, alto))
        self.tiempo_max = tiempo_max_s
        self.semilla = semilla
        self.destinos = self._generar_destinos()      # coordenadas normalizadas (0 a 1)
        self.estado = ESPERA
        self.indice = -1                               # -1 = circulo de inicio
        self.objetivos = []
        self.resumen = None
        self.t_inicio = None
        self.t_fin = None
        self.ult_pos = None
        self._reiniciar_objetivo(0.0)

    def _generar_destinos(self):
        rnd = random.Random(self.semilla)
        dest, prev = [], (0.5, 0.5)
        minimo = 0.3 * min(self.ancho, self.alto)
        while len(dest) < self.n:
            p = (rnd.uniform(0.08, 0.92), rnd.uniform(0.12, 0.88))
            if math.hypot((p[0] - prev[0]) * self.ancho, (p[1] - prev[1]) * self.alto) >= minimo:
                dest.append(p)
                prev = p
        return dest

    def centro_objetivo(self):
        if self.indice < 0:
            return self.ancho / 2, self.alto / 2
        nx, ny = self.destinos[self.indice]
        return nx * self.ancho, ny * self.alto

    def progreso(self, t):
        if self.dentro_desde is None:
            return 0.0
        return min(1.0, (t - self.dentro_desde) / self.permanencia)

    def _reiniciar_objetivo(self, t):
        self.t_obj = t
        self.pos0 = self.ult_pos if self.ult_pos is not None else (0.0, 0.0)
        self.dentro_desde = None
        self.primera_entrada = None
        self.camino = 0.0
        self.camino_llegada = None
        self.salidas = 0

    def update(self, t, x, y):
        if self.estado == FIN:
            return
        if self.ult_pos is not None and self.estado == PRUEBA:
            self.camino += math.hypot(x - self.ult_pos[0], y - self.ult_pos[1])
        self.ult_pos = (x, y)
        cx, cy = self.centro_objetivo()
        if math.hypot(x - cx, y - cy) <= self.radio:
            if self.dentro_desde is None:
                self.dentro_desde = t
            if self.primera_entrada is None:
                self.primera_entrada = t
                self.camino_llegada = self.camino
            if t - self.dentro_desde >= self.permanencia:
                self._completar(t, True)
                return
        else:
            if self.dentro_desde is not None and self.estado == PRUEBA:
                self.salidas += 1
            self.dentro_desde = None
        if self.estado == PRUEBA and t - self.t_obj >= self.tiempo_max:
            self._completar(t, False)

    def _completar(self, t, ok):
        if self.estado == ESPERA:                      # se logro el circulo de inicio: empieza la prueba
            self.estado = PRUEBA
            self.t_inicio = t
            self.indice = 0
            self._reiniciar_objetivo(t)
            return
        cx, cy = self.centro_objetivo()
        recta = math.hypot(cx - self.pos0[0], cy - self.pos0[1])
        llegada = (self.primera_entrada - self.t_obj) if self.primera_entrada is not None else None
        cam = self.camino_llegada
        self.objetivos.append({
            "indice": self.indice + 1,
            "destino_px": [round(cx, 1), round(cy, 1)],
            "completado": ok,
            "tiempo_total_s": round(t - self.t_obj, 3),
            "tiempo_llegada_s": round(llegada, 3) if llegada is not None else None,
            "salidas": self.salidas,
            "distancia_recta_px": round(recta, 1),
            "recorrido_hasta_llegar_px": round(cam, 1) if cam is not None else None,
            "velocidad_media_px_s": round(cam / llegada, 1) if cam and llegada else None,
            "eficiencia_trayectoria": round(min(1.0, recta / cam), 3) if cam and cam > 1 else None,
        })
        self.indice += 1
        if self.indice >= self.n:
            self.estado = FIN
            self.t_fin = t
            self.resumen = self._resumir()
            return
        self._reiniciar_objetivo(t)

    def _resumir(self):
        ok = [o for o in self.objetivos if o["completado"]]
        cam = sum(o["recorrido_hasta_llegar_px"] for o in self.objetivos if o["velocidad_media_px_s"])
        tie = sum(o["tiempo_llegada_s"] for o in self.objetivos if o["velocidad_media_px_s"])
        return {
            "duracion_total_s": round(self.t_fin - self.t_inicio, 3),
            "aciertos": len(ok),
            "fallos": self.n - len(ok),
            "tiempo_medio_por_punto_s": promedio([o["tiempo_total_s"] for o in ok]),
            "tiempo_medio_llegada_s": promedio([o["tiempo_llegada_s"] for o in ok]),
            "velocidad_media_px_s": round(cam / tie, 1) if tie > 0 else None,
            "eficiencia_media": promedio([o["eficiencia_trayectoria"] for o in ok]),
            "salidas_totales": sum(o["salidas"] for o in self.objetivos),
        }

    def parametros(self):
        return {"n_puntos": self.n, "permanencia_s": self.permanencia, "radio_px": round(self.radio, 1),
                "tiempo_max_objetivo_s": self.tiempo_max, "semilla": self.semilla,
                "resolucion": [self.ancho, self.alto]}


# ----------------------------------------------------------------------------
# Logica del benchmark 2: camara tipo juego (sin interfaz)
# ----------------------------------------------------------------------------
def direccion(yaw, pitch):
    y, p = math.radians(yaw), math.radians(pitch)
    return (math.cos(p) * math.sin(y), math.sin(p), math.cos(p) * math.cos(y))


def angulo_entre(a, b):
    dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))
    return math.degrees(math.acos(dot))


class LogicaCamara:
    YAW_MAX = 60.0       # los objetivos aparecen al frente: +-60 grados a los lados
    PITCH_MAX = 25.0     # y +-25 grados arriba/abajo

    def __init__(self, n_objetivos, permanencia_s, sensibilidad, tolerancia_deg=3.0, semilla=SEMILLA,
                 tiempo_max_s=TIEMPO_MAX_OBJETIVO_S):
        self.n = n_objetivos
        self.permanencia = permanencia_s
        self.sens = sensibilidad                       # grados de giro por pixel de mouse
        self.tol = tolerancia_deg
        self.tiempo_max = tiempo_max_s
        self.semilla = semilla
        self.yaw, self.pitch = 0.0, 0.0
        self.destinos = self._generar_destinos()       # (yaw, pitch) en grados
        self.estado = ESPERA
        self.indice = -1
        self.objetivos = []
        self.resumen = None
        self.t_inicio = None
        self.t_fin = None
        self._reiniciar_objetivo(0.0)

    def _generar_destinos(self):
        rnd = random.Random(self.semilla)
        dest, prev = [], (0.0, 0.0)
        while len(dest) < self.n:
            c = (rnd.uniform(-self.YAW_MAX, self.YAW_MAX), rnd.uniform(-self.PITCH_MAX, self.PITCH_MAX))
            if angulo_entre(direccion(*c), direccion(*prev)) >= 30.0:
                dest.append(c)
                prev = c
        return dest

    def objetivo_actual(self):
        return (0.0, 0.0) if self.indice < 0 else self.destinos[self.indice]

    def error_actual(self):
        return angulo_entre(direccion(self.yaw, self.pitch), direccion(*self.objetivo_actual()))

    def progreso(self, t):
        if self.dentro_desde is None:
            return 0.0
        return min(1.0, (t - self.dentro_desde) / self.permanencia)

    def _reiniciar_objetivo(self, t):
        self.t_obj = t
        self.error0 = self.error_actual()
        self.dentro_desde = None
        self.primera_entrada = None
        self.camino = 0.0
        self.camino_llegada = None
        self.salidas = 0
        self.errores_perm = []

    def update(self, t, dx_px, dy_px):
        """dx_px, dy_px: lo que se movio el mouse desde la ultima lectura (pixeles)."""
        if self.estado == FIN:
            return
        dyaw = dx_px * self.sens
        dpitch = -dy_px * self.sens
        self.yaw += dyaw
        self.yaw = (self.yaw + 180.0) % 360.0 - 180.0
        self.pitch = max(-85.0, min(85.0, self.pitch + dpitch))
        if self.estado == PRUEBA:
            self.camino += math.hypot(dyaw * math.cos(math.radians(self.pitch)), dpitch)
        err = self.error_actual()
        if err <= self.tol:
            if self.dentro_desde is None:
                self.dentro_desde = t
                self.errores_perm = []
            self.errores_perm.append(err)
            if self.primera_entrada is None:
                self.primera_entrada = t
                self.camino_llegada = self.camino
            if t - self.dentro_desde >= self.permanencia:
                self._completar(t, True)
                return
        else:
            if self.dentro_desde is not None and self.estado == PRUEBA:
                self.salidas += 1
            self.dentro_desde = None
        if self.estado == PRUEBA and t - self.t_obj >= self.tiempo_max:
            self._completar(t, False)

    def _completar(self, t, ok):
        if self.estado == ESPERA:
            self.estado = PRUEBA
            self.t_inicio = t
            self.indice = 0
            self._reiniciar_objetivo(t)
            return
        yaw_t, pitch_t = self.objetivo_actual()
        llegada = (self.primera_entrada - self.t_obj) if self.primera_entrada is not None else None
        cam = self.camino_llegada
        self.objetivos.append({
            "indice": self.indice + 1,
            "destino_grados": [round(yaw_t, 1), round(pitch_t, 1)],
            "completado": ok,
            "tiempo_total_s": round(t - self.t_obj, 3),
            "tiempo_llegada_s": round(llegada, 3) if llegada is not None else None,
            "salidas": self.salidas,
            "distancia_inicial_grados": round(self.error0, 1),
            "recorrido_hasta_llegar_grados": round(cam, 1) if cam is not None else None,
            "velocidad_media_grados_s": round(cam / llegada, 1) if cam and llegada else None,
            "eficiencia_trayectoria": round(min(1.0, self.error0 / cam), 3) if cam and cam > 0.5 else None,
            "error_medio_en_permanencia_grados": promedio(self.errores_perm, 2) if ok else None,
        })
        self.indice += 1
        if self.indice >= self.n:
            self.estado = FIN
            self.t_fin = t
            self.resumen = self._resumir()
            return
        self._reiniciar_objetivo(t)

    def _resumir(self):
        ok = [o for o in self.objetivos if o["completado"]]
        cam = sum(o["recorrido_hasta_llegar_grados"] for o in self.objetivos if o["velocidad_media_grados_s"])
        tie = sum(o["tiempo_llegada_s"] for o in self.objetivos if o["velocidad_media_grados_s"])
        return {
            "duracion_total_s": round(self.t_fin - self.t_inicio, 3),
            "aciertos": len(ok),
            "fallos": self.n - len(ok),
            "tiempo_medio_por_objetivo_s": promedio([o["tiempo_total_s"] for o in ok]),
            "tiempo_medio_llegada_s": promedio([o["tiempo_llegada_s"] for o in ok]),
            "velocidad_media_grados_s": round(cam / tie, 1) if tie > 0 else None,
            "eficiencia_media": promedio([o["eficiencia_trayectoria"] for o in ok]),
            "error_medio_en_permanencia_grados": promedio([o["error_medio_en_permanencia_grados"] for o in ok], 2),
            "salidas_totales": sum(o["salidas"] for o in self.objetivos),
        }

    def parametros(self):
        return {"n_objetivos": self.n, "permanencia_s": self.permanencia,
                "sensibilidad_grados_por_px": self.sens, "tolerancia_grados": self.tol,
                "tiempo_max_objetivo_s": self.tiempo_max, "semilla": self.semilla,
                "campo_yaw_grados": self.YAW_MAX, "campo_pitch_grados": self.PITCH_MAX}


# ----------------------------------------------------------------------------
# Ventanas de prueba (pantalla completa)
# ----------------------------------------------------------------------------
def _num(v, sufijo="", decimales=1):
    return "-" if v is None else f"{v:.{decimales}f}{sufijo}"


class PruebaBase(QWidget):
    cerrada = Signal()

    def __init__(self, usuario, dispositivo, almacen):
        super().__init__()
        self.usuario, self.dispositivo, self.almacen = usuario, dispositivo, almacen
        self.logica = None
        self.guardado = None            # (id, intento) o un texto de error
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("Joy-Free Cursor - Benchmark")
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # lo definen las pruebas
    def _tick(self):
        raise NotImplementedError

    def reiniciar(self):
        raise NotImplementedError

    def corrida(self):
        raise NotImplementedError

    def lineas_resumen(self):
        raise NotImplementedError

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.logica is not None and self.logica.estado == FIN:
            self.reiniciar()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self.timer.stop()
        self.unsetCursor()
        self.cerrada.emit()
        super().closeEvent(e)

    def _revisar_fin(self):
        if self.logica.estado == FIN and self.guardado is None:
            try:
                self.guardado = self.almacen.guardar(self.corrida())
            except Exception as e:
                self.guardado = f"No se pudo guardar: {e}"
            self.unsetCursor()

    def _dibujar_resumen(self, p):
        lineas = self.lineas_resumen()
        if isinstance(self.guardado, tuple):
            lineas.append(f"Guardado como intento {self.guardado[1]} en {self.almacen.ruta.name}")
        elif isinstance(self.guardado, str):
            lineas.append(self.guardado)
        lineas.append("Enter = repetir        Esc = cerrar")
        w, h = self.width(), self.height()
        alto_linea = 34
        panel = QRectF(w * 0.2, h / 2 - alto_linea * (len(lineas) + 1) / 2, w * 0.6, alto_linea * (len(lineas) + 1))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1E293B"))
        p.drawRoundedRect(panel, 18, 18)
        for i, texto in enumerate(lineas):
            f = QFont("Segoe UI", 22 if i == 0 else 15)
            f.setBold(i == 0)
            p.setFont(f)
            p.setPen(QColor("#FFFFFF" if i == 0 else "#CBD5E1"))
            p.drawText(QRectF(panel.left(), panel.top() + alto_linea * (i + 0.5), panel.width(), alto_linea),
                       Qt.AlignCenter, texto)

    def _dibujar_hud(self, p, texto):
        p.setPen(QColor("#94A3B8"))
        p.setFont(QFont("Segoe UI", 14))
        p.drawText(QRectF(24, 16, self.width() - 48, 30), Qt.AlignLeft | Qt.AlignVCenter, texto)
        p.drawText(QRectF(24, self.height() - 46, self.width() - 48, 30), Qt.AlignLeft | Qt.AlignVCenter,
                   "Esc: salir")


class PruebaPuntos(PruebaBase):
    def __init__(self, usuario, dispositivo, almacen, n_puntos, permanencia_s):
        super().__init__(usuario, dispositivo, almacen)
        self.n_puntos, self.permanencia = n_puntos, permanencia_s

    def _nueva_logica(self):
        return LogicaPuntos(self.n_puntos, self.permanencia, max(self.width(), 1), max(self.height(), 1))

    def resizeEvent(self, e):
        if self.logica is None or self.logica.estado == ESPERA:
            self.logica = self._nueva_logica()
        super().resizeEvent(e)

    def reiniciar(self):
        self.guardado = None
        self.logica = self._nueva_logica()
        self.update()

    def _tick(self):
        if self.logica is None:
            return
        pos = self.mapFromGlobal(QCursor.pos())
        self.logica.update(time.monotonic(), pos.x(), pos.y())
        self._revisar_fin()
        self.update()

    def corrida(self):
        return {"benchmark": "puntos", "usuario": self.usuario, "dispositivo": self.dispositivo,
                "fecha_hora": datetime.now().isoformat(timespec="seconds"),
                "parametros": self.logica.parametros(), "resumen": self.logica.resumen,
                "objetivos": self.logica.objetivos}

    def lineas_resumen(self):
        r, L = self.logica.resumen, self.logica
        return ["Prueba terminada",
                f"{self.usuario}  |  {self.dispositivo}",
                f"Duración total: {_num(r['duracion_total_s'], ' s')}     Aciertos: {r['aciertos']} de {L.n}",
                f"Tiempo medio por punto: {_num(r['tiempo_medio_por_punto_s'], ' s', 2)}     "
                f"hasta llegar: {_num(r['tiempo_medio_llegada_s'], ' s', 2)}",
                f"Velocidad media: {_num(r['velocidad_media_px_s'], ' px/s', 0)}     "
                f"Eficiencia de trayectoria: {_num(None if r['eficiencia_media'] is None else r['eficiencia_media'] * 100, ' %', 0)}",
                f"Veces que se pasó del punto: {r['salidas_totales']}"]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0F172A"))
        L = self.logica
        if L is None:
            return
        if L.estado == FIN:
            self._dibujar_resumen(p)
            return
        cx, cy = L.centro_objetivo()
        r = L.radio
        p.setPen(QPen(QColor("#334155"), 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r + 10, r + 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2F6BFF" if L.estado == PRUEBA else "#14804A"))
        p.drawEllipse(QPointF(cx, cy), r, r)
        frac = L.progreso(time.monotonic())
        if frac > 0:
            p.setPen(QPen(QColor("#FBBF24"), 7))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(cx - r - 10, cy - r - 10, 2 * (r + 10), 2 * (r + 10)), 90 * 16, int(-frac * 360 * 16))
        f = QFont("Segoe UI", 16 if L.estado == ESPERA else 20)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(cx - r, cy - r, 2 * r, 2 * r), Qt.AlignCenter, "INICIO" if L.estado == ESPERA else str(L.indice + 1))
        if L.estado == ESPERA:
            self._dibujar_hud(p, "Lleva el cursor al círculo verde y mantenlo encima para empezar")
        else:
            self._dibujar_hud(p, f"Punto {L.indice + 1} de {L.n}     Tiempo {time.monotonic() - L.t_inicio:.1f} s")


class PruebaCamara(PruebaBase):
    FOV_H = 90.0

    def __init__(self, usuario, dispositivo, almacen, n_objetivos, permanencia_s, sensibilidad):
        super().__init__(usuario, dispositivo, almacen)
        self.n_objetivos, self.permanencia, self.sens = n_objetivos, permanencia_s, sensibilidad
        self.logica = LogicaCamara(n_objetivos, permanencia_s, sensibilidad)
        self._centrado = False
        self.setCursor(Qt.BlankCursor)
        self._malla = self._crear_malla()

    @staticmethod
    def _crear_malla():
        lineas = []
        for yaw in range(-180, 180, 15):                       # meridianos
            lineas.append(([direccion(yaw, pitch) for pitch in range(-80, 85, 5)], yaw == 0))
        for pitch in range(-75, 90, 15):                       # paralelos
            lineas.append(([direccion(yaw, pitch) for yaw in range(-180, 185, 5)], pitch == 0))
        return lineas

    def reiniciar(self):
        self.guardado = None
        yaw, pitch = self.logica.yaw, self.logica.pitch
        self.logica = LogicaCamara(self.n_objetivos, self.permanencia, self.sens)
        self.logica.yaw, self.logica.pitch = yaw, pitch
        self._centrado = False
        self.setCursor(Qt.BlankCursor)
        self.update()

    def _centro_global(self):
        return self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))

    def _tick(self):
        L = self.logica
        if L.estado != FIN:
            c = self._centro_global()
            if not self._centrado:
                QCursor.setPos(c)
                self._centrado = True
            else:
                pos = QCursor.pos()
                dx, dy = pos.x() - c.x(), pos.y() - c.y()
                if dx or dy:
                    QCursor.setPos(c)                          # el mouse se "captura": siempre vuelve al centro
                L.update(time.monotonic(), dx, dy)
        self._revisar_fin()
        self.update()

    def corrida(self):
        return {"benchmark": "camara", "usuario": self.usuario, "dispositivo": self.dispositivo,
                "fecha_hora": datetime.now().isoformat(timespec="seconds"),
                "parametros": self.logica.parametros(), "resumen": self.logica.resumen,
                "objetivos": self.logica.objetivos}

    def lineas_resumen(self):
        r, L = self.logica.resumen, self.logica
        return ["Prueba terminada",
                f"{self.usuario}  |  {self.dispositivo}",
                f"Duración total: {_num(r['duracion_total_s'], ' s')}     Aciertos: {r['aciertos']} de {L.n}",
                f"Tiempo medio por objetivo: {_num(r['tiempo_medio_por_objetivo_s'], ' s', 2)}     "
                f"hasta apuntar: {_num(r['tiempo_medio_llegada_s'], ' s', 2)}",
                f"Velocidad de giro: {_num(r['velocidad_media_grados_s'], ' °/s', 0)}     "
                f"Eficiencia de trayectoria: {_num(None if r['eficiencia_media'] is None else r['eficiencia_media'] * 100, ' %', 0)}",
                f"Error medio de la mira al mantener: {_num(r['error_medio_en_permanencia_grados'], '°', 2)}     "
                f"Veces que se pasó: {r['salidas_totales']}"]

    # ---- dibujo de la escena ----
    def _base_camara(self):
        y, p = math.radians(self.logica.yaw), math.radians(self.logica.pitch)
        F = (math.cos(p) * math.sin(y), math.sin(p), math.cos(p) * math.cos(y))
        R = (math.cos(y), 0.0, -math.sin(y))
        U = (-math.sin(p) * math.sin(y), math.cos(p), -math.sin(p) * math.cos(y))
        return F, R, U

    def _proyectar(self, d, base, f, cx, cy):
        F, R, U = base
        zc = d[0] * F[0] + d[1] * F[1] + d[2] * F[2]
        xc = d[0] * R[0] + d[1] * R[1] + d[2] * R[2]
        yc = d[0] * U[0] + d[1] * U[1] + d[2] * U[2]
        if zc <= 0.05:
            return None, xc, yc
        return (cx + f * xc / zc, cy - f * yc / zc), xc, yc

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        f = (w / 2) / math.tan(math.radians(self.FOV_H / 2))
        p.fillRect(self.rect(), QColor("#0B1220"))
        L = self.logica
        base = self._base_camara()

        for puntos, destacada in self._malla:
            pen = QPen(QColor("#3B5B8C" if destacada else "#1F2D47"), 2 if destacada else 1)
            p.setPen(pen)
            anterior = None
            for d in puntos:
                q, _, _ = self._proyectar(d, base, f, cx, cy)
                if q is not None and anterior is not None:
                    p.drawLine(QPointF(*anterior), QPointF(*q))
                anterior = q

        if L.estado != FIN:
            objetivo = direccion(*L.objetivo_actual())
            q, xc, yc = self._proyectar(objetivo, base, f, cx, cy)
            r = f * math.tan(math.radians(L.tol))
            color = QColor("#14804A" if L.estado == ESPERA else "#F59E0B")
            en_pantalla = q is not None and -r < q[0] < w + r and -r < q[1] < h + r
            if en_pantalla:
                c = QColor(color)
                c.setAlpha(110)
                p.setPen(QPen(color, 4))
                p.setBrush(c)
                p.drawEllipse(QPointF(*q), r, r)
                frac = L.progreso(time.monotonic())
                if frac > 0:
                    p.setPen(QPen(QColor("#FBBF24"), 7))
                    p.setBrush(Qt.NoBrush)
                    p.drawArc(QRectF(q[0] - r - 8, q[1] - r - 8, 2 * (r + 8), 2 * (r + 8)), 90 * 16, int(-frac * 360 * 16))
                p.setPen(QColor("#FFFFFF"))
                p.setFont(QFont("Segoe UI", 14, QFont.Bold))
                p.drawText(QRectF(q[0] - r, q[1] - r, 2 * r, 2 * r), Qt.AlignCenter,
                           "INICIO" if L.estado == ESPERA else str(L.indice + 1))
            else:                                              # flecha hacia donde esta el objetivo
                ang = math.atan2(-yc, xc)
                ax, ay = cx + math.cos(ang) * min(w, h) * 0.42, cy + math.sin(ang) * min(w, h) * 0.42
                punta = QPointF(ax + math.cos(ang) * 22, ay + math.sin(ang) * 22)
                lado = 14
                tri = QPolygonF([punta,
                                 QPointF(ax + math.cos(ang + 2.5) * lado, ay + math.sin(ang + 2.5) * lado),
                                 QPointF(ax + math.cos(ang - 2.5) * lado, ay + math.sin(ang - 2.5) * lado)])
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawPolygon(tri)

        # mira
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.drawLine(QPointF(cx - 14, cy), QPointF(cx - 4, cy))
        p.drawLine(QPointF(cx + 4, cy), QPointF(cx + 14, cy))
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy - 4))
        p.drawLine(QPointF(cx, cy + 4), QPointF(cx, cy + 14))

        if L.estado == FIN:
            self._dibujar_resumen(p)
        elif L.estado == ESPERA:
            self._dibujar_hud(p, "Gira la vista hasta poner la mira dentro del círculo verde y mantenla ahí para empezar")
        else:
            self._dibujar_hud(p, f"Objetivo {L.indice + 1} de {L.n}     Tiempo {time.monotonic() - L.t_inicio:.1f} s")


# ----------------------------------------------------------------------------
# Menu de seleccion
# ----------------------------------------------------------------------------
class MenuBenchmarks(QDialog):
    def __init__(self, padre=None, almacen=None):
        super().__init__(padre)
        self.almacen = almacen or Almacen()
        self._prueba = None
        self.setWindowTitle("Benchmarks - Joy-Free Cursor")
        self.setMinimumWidth(560)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(22, 20, 22, 20)
        raiz.setSpacing(12)

        titulo = QLabel("Benchmarks")
        titulo.setStyleSheet("font-size: 22px; font-weight: 700;")
        raiz.addWidget(titulo)
        sub = QLabel("Elige una prueba. Cada intento terminado se guarda en un archivo JSON.")
        sub.setStyleSheet("color: #6B7280;")
        raiz.addWidget(sub)

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Usuario"))
        self.txt_usuario = QLineEdit("Usuario")
        self.txt_usuario.setMinimumWidth(150)
        fila.addWidget(self.txt_usuario)
        fila.addSpacing(12)
        fila.addWidget(QLabel("Dispositivo"))
        self.cmb_disp = QComboBox()
        self.cmb_disp.addItems(DISPOSITIVOS)
        fila.addWidget(self.cmb_disp)
        fila.addStretch()
        raiz.addLayout(fila)

        self.lbl_intentos = QLabel("")
        self.lbl_intentos.setStyleSheet("color: #6B7280;")
        self.lbl_intentos.setWordWrap(True)
        raiz.addWidget(self.lbl_intentos)

        # --- seguir puntos ---
        t1 = self._tarjeta("Seguir puntos",
                           "Aparecen puntos uno por uno. Lleva el cursor a cada uno y mantenlo encima. "
                           "Mide tiempo, velocidad y precisión.")
        self.sp_puntos = QSpinBox()
        self.sp_puntos.setRange(3, 30)
        self.sp_puntos.setValue(10)
        self.sp_perm1 = QDoubleSpinBox()
        self.sp_perm1.setRange(0.3, 3.0)
        self.sp_perm1.setSingleStep(0.1)
        self.sp_perm1.setValue(1.0)
        self.sp_perm1.setSuffix(" s")
        self._fila_param(t1, "Puntos", self.sp_puntos, "Permanencia", self.sp_perm1)
        b1 = QPushButton("Iniciar seguir puntos")
        b1.setStyleSheet(f"background: {MORADO}; color: white;")
        b1.clicked.connect(self._lanzar_puntos)
        t1.layout().addWidget(b1)
        raiz.addWidget(t1)

        # --- camara ---
        t2 = self._tarjeta("Cámara tipo juego",
                           "Una vista en primera persona: el cuello gira a los lados y el hombro arriba y abajo. "
                           "Centra la mira en cada objetivo y mantenla.")
        self.sp_obj = QSpinBox()
        self.sp_obj.setRange(3, 30)
        self.sp_obj.setValue(10)
        self.sp_perm2 = QDoubleSpinBox()
        self.sp_perm2.setRange(0.3, 3.0)
        self.sp_perm2.setSingleStep(0.1)
        self.sp_perm2.setValue(1.0)
        self.sp_perm2.setSuffix(" s")
        self.sp_sens = QDoubleSpinBox()
        self.sp_sens.setRange(0.02, 1.0)
        self.sp_sens.setSingleStep(0.01)
        self.sp_sens.setDecimals(2)
        self.sp_sens.setValue(0.15)
        self.sp_sens.setSuffix(" °/px")
        self._fila_param(t2, "Objetivos", self.sp_obj, "Permanencia", self.sp_perm2)
        self._fila_param(t2, "Sensibilidad de cámara", self.sp_sens)
        b2 = QPushButton("Iniciar cámara")
        b2.setStyleSheet(f"background: {MORADO}; color: white;")
        b2.clicked.connect(self._lanzar_camara)
        t2.layout().addWidget(b2)
        raiz.addWidget(t2)

        self.lbl_ruta = QLabel(f"Resultados: {self.almacen.ruta}")
        self.lbl_ruta.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.lbl_ruta.setWordWrap(True)
        raiz.addWidget(self.lbl_ruta)
        nota = QLabel("Para salir de una prueba, presiona Esc.")
        nota.setStyleSheet("color: #6B7280; font-size: 12px;")
        raiz.addWidget(nota)

        self.txt_usuario.textChanged.connect(self.actualizar_intentos)
        self.cmb_disp.currentTextChanged.connect(self.actualizar_intentos)
        self.actualizar_intentos()

    @staticmethod
    def _tarjeta(titulo, descripcion):
        t = QFrame()
        t.setObjectName("tarjeta")
        lay = QVBoxLayout(t)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        a = QLabel(titulo)
        a.setStyleSheet("font-size: 17px; font-weight: 700;")
        b = QLabel(descripcion)
        b.setWordWrap(True)
        b.setStyleSheet("color: #6B7280;")
        lay.addWidget(a)
        lay.addWidget(b)
        return t

    @staticmethod
    def _fila_param(tarjeta, nombre1, w1, nombre2=None, w2=None):
        fila = QHBoxLayout()
        fila.addWidget(QLabel(nombre1))
        fila.addWidget(w1)
        if w2 is not None:
            fila.addSpacing(12)
            fila.addWidget(QLabel(nombre2))
            fila.addWidget(w2)
        fila.addStretch()
        tarjeta.layout().addLayout(fila)

    def _usuario(self):
        return self.txt_usuario.text().strip() or "Usuario"

    def actualizar_intentos(self, *_):
        u, d = self._usuario(), self.cmb_disp.currentText()
        np_ = self.almacen.contar("puntos", u, d)
        nc = self.almacen.contar("camara", u, d)
        self.lbl_intentos.setText(f"Intentos guardados de {u} con {d}:  seguir puntos {np_},  cámara {nc}. "
                                  f"Próximos intentos: {np_ + 1} y {nc + 1}.")

    def _lanzar(self, ventana):
        self._prueba = ventana
        ventana.cerrada.connect(self._al_cerrar_prueba)
        self.hide()
        ventana.showFullScreen()
        ventana.activateWindow()
        ventana.setFocus()

    def _lanzar_puntos(self):
        self._lanzar(PruebaPuntos(self._usuario(), self.cmb_disp.currentText(), self.almacen,
                                  self.sp_puntos.value(), self.sp_perm1.value()))

    def _lanzar_camara(self):
        self._lanzar(PruebaCamara(self._usuario(), self.cmb_disp.currentText(), self.almacen,
                                  self.sp_obj.value(), self.sp_perm2.value(), self.sp_sens.value()))

    def _al_cerrar_prueba(self):
        self._prueba = None
        self.actualizar_intentos()
        self.show()
        self.raise_()
        self.activateWindow()