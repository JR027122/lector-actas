import sys
import os
import threading
import time
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QProgressBar,
    QDialog, QLineEdit, QDialogButtonBox, QMessageBox,
    QFrame, QButtonGroup, QRadioButton, QSizePolicy, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QDesktopServices

from src.core.document_processor import ProcessControl, process_document, process_folder
from src.core.openrouter_processor import MODELO_POR_DEFECTO, MODELOS_DISPONIBLES
from src.core.processing_modes import MODE_OPTIONS, OCR_AND_RENAME, exporta_excel, renombra_archivo
from src.utils.excel_export import limpiar_registro, ordenar_dataframe
from src.utils.niu_lookup import cargar_base_usuarios
from src.utils.secure_api_key import resolve_api_key, save_api_key
from src.utils.progress_tracker import ProgressTracker

# ── Estilos ──────────────────────────────────────────────────────────────────
STYLESHEET = """
QMainWindow, QWidget#central { background-color: #f1f5f9; }
QFrame#header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1e3a8a, stop:0.5 #2563eb, stop:1 #0ea5e9);
    border-radius: 12px;
}
QLabel#headerTitle { color: white; font-size: 22px; font-weight: 700; }
QLabel#headerSub { color: rgba(255,255,255,0.85); font-size: 13px; }
QFrame#card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QLabel#cardTitle {
    color: #0f172a;
    font-size: 14px;
    font-weight: 600;
}
QRadioButton {
    color: #334155;
    font-size: 13px;
    spacing: 8px;
    padding: 6px 4px;
}
QRadioButton::indicator { width: 16px; height: 16px; }
QRadioButton:checked { color: #2563eb; font-weight: 600; }
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #0ea5e9);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    padding: 12px;
}
QPushButton#primaryBtn:hover { background: #1d4ed8; }
QPushButton#primaryBtn:disabled { background: #94a3b8; }
QPushButton#secondaryBtn {
    background: white;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 13px;
    padding: 10px 16px;
}
QPushButton#secondaryBtn:hover { background: #f8fafc; border-color: #2563eb; color: #2563eb; }
QPushButton#secondaryBtn:disabled { color: #94a3b8; border-color: #e2e8f0; background: #f8fafc; }
QPushButton#dangerBtn {
    background: white;
    color: #dc2626;
    border: 1px solid #fca5a5;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    padding: 10px 16px;
}
QPushButton#dangerBtn:hover { background: #fef2f2; border-color: #dc2626; }
QPushButton#dangerBtn:disabled { color: #94a3b8; border-color: #e2e8f0; background: #f8fafc; }
QProgressBar {
    border: none;
    border-radius: 6px;
    background: #e2e8f0;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #0ea5e9);
    border-radius: 6px;
}
QLabel#statusOk { color: #059669; font-weight: 600; }
QLabel#statusErr { color: #dc2626; font-weight: 600; }
QLabel#statusInfo { color: #2563eb; }
QLabel#pathLabel { color: #64748b; font-size: 12px; }
QLabel#apiKeyLink { font-size: 12px; }
QLabel#apiKeyLink a { color: #2563eb; text-decoration: none; }
QLabel#apiKeyLink a:hover { text-decoration: underline; }
"""

OPENROUTER_API_KEY_URL = "https://openrouter.ai/keys"

# Cómo describir en la UI de dónde vino el NIU recuperado
_NIU_ORIGEN_TXT = {
    "cedula": "cédula (base de usuarios)",
    "nombre": "nombre (base de usuarios)",
    "nombre_archivo": "nombre del archivo original",
}


def abrir_pagina_api_key():
    QDesktopServices.openUrl(QUrl(OPENROUTER_API_KEY_URL))


def _crear_enlace_api_key() -> QLabel:
    enlace = QLabel(
        f'<a href="{OPENROUTER_API_KEY_URL}">Obtener API key en OpenRouter</a>'
    )
    enlace.setObjectName("apiKeyLink")
    enlace.setOpenExternalLinks(True)
    enlace.setTextFormat(Qt.TextFormat.RichText)
    enlace.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return enlace


def preguntar_reanudacion(parent=None, carpeta="") -> bool:
    """Pregunta al usuario si desea reanudar un procesamiento anterior.

    Retorna True si quiere continuar, False si quiere empezar de nuevo.
    """
    dlg = QMessageBox(parent)
    dlg.setWindowTitle("Procesamiento anterior detectado")
    dlg.setText(
        f"Se detectó un procesamiento anterior en:\n\n{carpeta}\n\n"
        "¿Deseas continuar desde donde se quedó o empezar de nuevo?"
    )
    dlg.setIcon(QMessageBox.Icon.Question)
    btn_continuar = dlg.addButton("Continuar", QMessageBox.ButtonRole.AcceptRole)
    btn_nuevo = dlg.addButton("Empezar de nuevo", QMessageBox.ButtonRole.RejectRole)
    dlg.setDefaultButton(btn_continuar)
    dlg.exec()
    return dlg.clickedButton() == btn_continuar


def solicitar_y_guardar_api_key(parent=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle("API key de OpenRouter")
    dlg.setMinimumWidth(480)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel(
        "Introduce tu API key de OpenRouter.\n"
        "Se guardará de forma segura en el Administrador de credenciales de Windows."
    ))
    layout.addWidget(_crear_enlace_api_key())
    btn_obtener = QPushButton("Abrir OpenRouter")
    btn_obtener.setObjectName("secondaryBtn")
    btn_obtener.clicked.connect(abrir_pagina_api_key)
    layout.addWidget(btn_obtener)
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setPlaceholderText("Pega aquí tu API key")
    layout.addWidget(edit)
    botones = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    botones.accepted.connect(dlg.accept)
    botones.rejected.connect(dlg.reject)
    layout.addWidget(botones)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    clave = edit.text().strip()
    if not clave:
        QMessageBox.warning(parent, "API key", "Debes introducir una clave no vacía.")
        return False
    save_api_key(clave)
    os.environ["OPENROUTER_API_KEY"] = clave
    return True


def ensure_api_key_or_exit(parent=None):
    if resolve_api_key():
        return True
    return solicitar_y_guardar_api_key(parent)


class WorkerThread(QThread):
    progress_update = pyqtSignal(int, int, str)
    finished_success = pyqtSignal(list)
    finished_error = pyqtSignal(str)
    cuota_agotada = pyqtSignal()

    def __init__(self, folder_path, mode, user_db=None, modelo=None, progress_tracker=None, excel_callback=None):
        super().__init__()
        self.folder_path = folder_path
        self.mode = mode
        self.user_db = user_db
        self.modelo = modelo
        self.progress_tracker = progress_tracker
        self.excel_callback = excel_callback
        self.control = ProcessControl()
        self._evento_respuesta = threading.Event()
        self._nueva_api_key = None

    def pausar(self):
        self.control.pausar()

    def reanudar(self):
        self.control.reanudar()

    def detener(self):
        self.control.detener()
        # Si estaba pausado esperando por falta de créditos, desbloquear también.
        self._nueva_api_key = None
        self._evento_respuesta.set()

    def responder_cuota(self, nueva_api_key):
        """Llamado desde la UI con la nueva key (o None para detener)."""
        self._nueva_api_key = nueva_api_key
        self._evento_respuesta.set()

    def _quota_callback(self):
        """Pausa el hilo hasta que el usuario decida en la UI."""
        self._nueva_api_key = None
        self._evento_respuesta.clear()
        self.cuota_agotada.emit()
        self._evento_respuesta.wait()
        return self._nueva_api_key

    def run(self):
        try:
            def callback(actual, total, filename):
                self.progress_update.emit(actual, total, filename)

            resultados = process_folder(
                self.folder_path, mode=self.mode, progress_callback=callback,
                user_db=self.user_db, quota_callback=self._quota_callback,
                modelo=self.modelo, progress_tracker=self.progress_tracker,
                excel_callback=self.excel_callback, control=self.control,
            )
            self.finished_success.emit(resultados)
        except Exception as e:
            self.finished_error.emit(str(e))


class WorkerIndividual(QThread):
    finished_success = pyqtSignal(dict)
    finished_error = pyqtSignal(str)
    cuota_agotada = pyqtSignal()

    def __init__(self, file_path, mode, user_db=None, modelo=None):
        super().__init__()
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.mode = mode
        self.user_db = user_db
        self.modelo = modelo

    def run(self):
        try:
            data = process_document(
                self.file_path, self.filename, self.mode,
                user_db=self.user_db, modelo=self.modelo,
            )
            if "Error" in data:
                if data.get("__sin_creditos__"):
                    self.cuota_agotada.emit()
                else:
                    self.finished_error.emit(data["Error"])
            else:
                nueva_ruta = data.get("__ruta_actualizada__")
                if nueva_ruta:
                    self.file_path = nueva_ruta
                self.finished_success.emit(data)
        except Exception as e:
            self.finished_error.emit(str(e))


class AppOCR(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ruta_actual = ""
        self.tipo_procesamiento = ""
        self.user_db = None
        self.ruta_base_usuarios = ""
        self.progress_tracker = None
        self.excel_path = ""
        self._build_ui()

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        layout.addWidget(lbl)
        return frame, layout

    def _build_ui(self):
        self.setWindowTitle("Lector de Actas — OCR Inteligente")
        self.resize(820, 640)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(90)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 16)
        t = QLabel("Lector de Actas")
        t.setObjectName("headerTitle")
        s = QLabel("Digitalización inteligente de actas de mantenimiento con IA (OpenRouter)")
        s.setObjectName("headerSub")
        hl.addWidget(t)
        hl.addWidget(s)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(16)

        # Modo
        mode_card, mode_layout = self._card("Modo de operación")
        self.mode_group = QButtonGroup(self)
        for i, (key, info) in enumerate(MODE_OPTIONS.items()):
            rb = QRadioButton(f"{info['icon']}  {info['label']}")
            rb.setToolTip(info["description"])
            if key == OCR_AND_RENAME:
                rb.setChecked(True)
            self.mode_group.addButton(rb, i)
            mode_layout.addWidget(rb)
            desc = QLabel(info["description"])
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #64748b; font-size: 11px; margin-left: 24px; margin-bottom: 8px;")
            mode_layout.addWidget(desc)

        mode_layout.addSpacing(8)
        lbl_modelo = QLabel("Modelo de IA")
        lbl_modelo.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 600;")
        mode_layout.addWidget(lbl_modelo)
        self.combo_modelo = QComboBox()
        indice_defecto = 0
        for i, (slug, etiqueta) in enumerate(MODELOS_DISPONIBLES.items()):
            self.combo_modelo.addItem(etiqueta, userData=slug)
            if slug == MODELO_POR_DEFECTO:
                indice_defecto = i
        self.combo_modelo.setCurrentIndex(indice_defecto)
        mode_layout.addWidget(self.combo_modelo)
        desc_modelo = QLabel(
            "Flash es más preciso; Flash Lite es más económico pero puede cometer "
            "más errores (se corrigen automáticamente cuando es posible; ver "
            "Revisar_Manual)."
        )
        desc_modelo.setWordWrap(True)
        desc_modelo.setStyleSheet("color: #64748b; font-size: 11px;")
        mode_layout.addWidget(desc_modelo)

        body.addWidget(mode_card, stretch=1)

        # Acciones
        action_card, action_layout = self._card("Documentos")
        btn_row = QHBoxLayout()
        self.btn_carpeta = QPushButton("Buscar carpeta")
        self.btn_carpeta.setObjectName("secondaryBtn")
        self.btn_carpeta.clicked.connect(self.seleccionar_carpeta)
        self.btn_archivo = QPushButton("Buscar un acta")
        self.btn_archivo.setObjectName("secondaryBtn")
        self.btn_archivo.clicked.connect(self.seleccionar_archivo)
        self.btn_api = QPushButton("API key")
        self.btn_api.setObjectName("secondaryBtn")
        self.btn_api.setToolTip("Configurar clave de OpenRouter o usar el enlace de abajo para obtener una")
        self.btn_api.clicked.connect(self.configurar_api_key)
        btn_row.addWidget(self.btn_carpeta)
        btn_row.addWidget(self.btn_archivo)
        btn_row.addWidget(self.btn_api)
        action_layout.addLayout(btn_row)
        action_layout.addWidget(_crear_enlace_api_key())

        self.lbl_ruta = QLabel("Ningún archivo o carpeta seleccionado")
        self.lbl_ruta.setObjectName("pathLabel")
        self.lbl_ruta.setWordWrap(True)
        action_layout.addWidget(self.lbl_ruta)

        # Base de usuarios opcional (NIU por cédula o nombre)
        db_row = QHBoxLayout()
        self.btn_base_usuarios = QPushButton("Base de usuarios (opcional)")
        self.btn_base_usuarios.setObjectName("secondaryBtn")
        self.btn_base_usuarios.setToolTip(
            "Excel/CSV con columnas NIU, Cédula y/o Nombre.\n"
            "Si un acta no tiene NIU visible, se busca por cédula, nombre o el "
            "nombre del archivo original, validando siempre contra esta base."
        )
        self.btn_base_usuarios.clicked.connect(self.seleccionar_base_usuarios)
        self.btn_quitar_base = QPushButton("Quitar")
        self.btn_quitar_base.setObjectName("secondaryBtn")
        self.btn_quitar_base.setEnabled(False)
        self.btn_quitar_base.clicked.connect(self.quitar_base_usuarios)
        db_row.addWidget(self.btn_base_usuarios)
        db_row.addWidget(self.btn_quitar_base)
        action_layout.addLayout(db_row)

        self.lbl_base = QLabel("Sin base de usuarios cargada")
        self.lbl_base.setObjectName("pathLabel")
        self.lbl_base.setWordWrap(True)
        action_layout.addWidget(self.lbl_base)

        self.btn_procesar = QPushButton("Iniciar procesamiento")
        self.btn_procesar.setObjectName("primaryBtn")
        self.btn_procesar.setEnabled(False)
        self.btn_procesar.setMinimumHeight(48)
        self.btn_procesar.clicked.connect(self.iniciar_procesamiento)
        action_layout.addWidget(self.btn_procesar)
        body.addWidget(action_card, stretch=2)

        root.addLayout(body)

        # Progreso
        prog_card, prog_layout = self._card("Estado")
        self.progressbar = QProgressBar()
        self.progressbar.setValue(0)
        self.progressbar.setTextVisible(False)
        prog_layout.addWidget(self.progressbar)
        self.lbl_estado = QLabel("Esperando instrucciones...")
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_estado.setWordWrap(True)
        prog_layout.addWidget(self.lbl_estado)

        # Controles de pausa/detención (solo visibles durante el lote de carpeta)
        control_row = QHBoxLayout()
        control_row.addStretch()
        self.btn_pausar = QPushButton("Pausar")
        self.btn_pausar.setObjectName("secondaryBtn")
        self.btn_pausar.clicked.connect(self.alternar_pausa)
        self.btn_detener = QPushButton("Detener")
        self.btn_detener.setObjectName("dangerBtn")
        self.btn_detener.clicked.connect(self.detener_procesamiento)
        self.btn_pausar.hide()
        self.btn_detener.hide()
        control_row.addWidget(self.btn_pausar)
        control_row.addWidget(self.btn_detener)
        control_row.addStretch()
        prog_layout.addLayout(control_row)

        root.addWidget(prog_card)

    def _modo_actual(self) -> str:
        idx = self.mode_group.checkedId()
        return list(MODE_OPTIONS.keys())[idx]

    def _modelo_actual(self) -> str:
        return self.combo_modelo.currentData() or MODELO_POR_DEFECTO

    def _set_busy(self, busy: bool):
        self.btn_carpeta.setEnabled(not busy)
        self.btn_archivo.setEnabled(not busy)
        self.btn_procesar.setEnabled(not busy)
        self.combo_modelo.setEnabled(not busy)
        for btn in self.mode_group.buttons():
            btn.setEnabled(not busy)

    def _actualizar_excel_incremental(self, registros_limpios, carpeta):
        """Actualiza el Excel resultado_consolidado.xlsx de forma incremental.

        Carga datos anteriores si existen y los combina con los nuevos.
        """
        try:
            ruta_excel = os.path.join(carpeta, "resultado_consolidado.xlsx")

            # Cargar datos anteriores si el archivo existe
            datos_anteriores = []
            if os.path.exists(ruta_excel):
                try:
                    df_anterior = pd.read_excel(ruta_excel)
                    datos_anteriores = df_anterior.to_dict("records")
                except Exception:
                    pass

            # Combinar datos anteriores con nuevos (evitando duplicados por nombre de archivo)
            archivos_nuevos = {r.get("Archivo") for r in registros_limpios}
            datos_anteriores_filtrados = [
                r for r in datos_anteriores
                if r.get("Archivo") not in archivos_nuevos
            ]

            # Escribir combinados
            todos_datos = datos_anteriores_filtrados + registros_limpios
            df = ordenar_dataframe(pd.DataFrame(todos_datos))
            df.to_excel(ruta_excel, index=False, engine="openpyxl")
        except Exception as e:
            print(f"Error al actualizar Excel incrementalmente: {e}")

    def seleccionar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta con las actas")
        if carpeta:
            self.tipo_procesamiento = "carpeta"
            self.ruta_actual = carpeta
            self.progress_tracker = ProgressTracker(carpeta)
            self.excel_path = os.path.join(carpeta, "resultado_consolidado.xlsx")

            # Detectar si hay un procesamiento anterior incompleto
            if self.progress_tracker.has_previous_progress():
                if preguntar_reanudacion(self, carpeta):
                    self.lbl_ruta.setText(f"Carpeta: {carpeta} (reanudando...)")
                    self.lbl_ruta.setStyleSheet("color: #059669; font-size: 12px;")
                else:
                    # Usuario quiere empezar de nuevo: limpiar checkpoint
                    self.progress_tracker.delete()
                    self.lbl_ruta.setText(f"Carpeta: {carpeta}")
                    self.lbl_ruta.setStyleSheet("color: #0f172a; font-size: 12px;")
            else:
                self.lbl_ruta.setText(f"Carpeta: {carpeta}")
                self.lbl_ruta.setStyleSheet("color: #0f172a; font-size: 12px;")

            self.btn_procesar.setEnabled(True)

    def seleccionar_archivo(self):
        archivo, _ = QFileDialog.getOpenFileName(
            self, "Selecciona un acta", "",
            "Imágenes y PDFs (*.pdf *.png *.jpg *.jpeg)"
        )
        if archivo:
            self.tipo_procesamiento = "archivo"
            self.ruta_actual = archivo
            self.lbl_ruta.setText(f"Archivo: {archivo}")
            self.lbl_ruta.setStyleSheet("color: #0f172a; font-size: 12px;")
            self.btn_procesar.setEnabled(True)

    def seleccionar_base_usuarios(self):
        archivo, _ = QFileDialog.getOpenFileName(
            self, "Selecciona la base de usuarios", "",
            "Excel y CSV (*.xlsx *.xls *.csv)"
        )
        if not archivo:
            return
        try:
            self.user_db = cargar_base_usuarios(archivo)
            self.ruta_base_usuarios = archivo
            self.lbl_base.setText(
                f"Base cargada: {os.path.basename(archivo)} "
                f"({self.user_db.total} usuarios)"
            )
            self.lbl_base.setStyleSheet("color: #059669; font-size: 12px;")
            self.btn_quitar_base.setEnabled(True)
        except Exception as e:
            self.user_db = None
            self.ruta_base_usuarios = ""
            QMessageBox.warning(self, "Base de usuarios", f"No se pudo cargar:\n{e}")

    def quitar_base_usuarios(self):
        self.user_db = None
        self.ruta_base_usuarios = ""
        self.lbl_base.setText("Sin base de usuarios cargada")
        self.lbl_base.setStyleSheet("")
        self.btn_quitar_base.setEnabled(False)

    def iniciar_procesamiento(self):
        self._set_busy(True)
        self.progressbar.setValue(0)
        self.lbl_estado.setText("Iniciando motor de IA...")
        self.lbl_estado.setObjectName("statusInfo")
        self.lbl_estado.setStyleSheet("color: #2563eb;")
        self.tiempo_inicio = time.time()
        modo = self._modo_actual()
        modelo = self._modelo_actual()

        if self.tipo_procesamiento == "carpeta":
            self.worker = WorkerThread(
                self.ruta_actual, modo, user_db=self.user_db, modelo=modelo,
                progress_tracker=self.progress_tracker,
                excel_callback=self._actualizar_excel_incremental,
            )
            self.worker.progress_update.connect(self.actualizar_interfaz)
            self.worker.finished_success.connect(self.procesamiento_completado)
            self.worker.finished_error.connect(self.procesamiento_error)
            self.worker.cuota_agotada.connect(self.manejar_cuota_agotada)
            self.worker.start()
            self._mostrar_controles_lote(True)
        elif self.tipo_procesamiento == "archivo":
            self.worker_ind = WorkerIndividual(self.ruta_actual, modo, user_db=self.user_db, modelo=modelo)
            self.worker_ind.finished_success.connect(self.procesamiento_individual_completado)
            self.worker_ind.finished_error.connect(self.procesamiento_error)
            self.worker_ind.cuota_agotada.connect(self.manejar_cuota_individual)
            self.worker_ind.start()
            self.progressbar.setValue(50)

    def actualizar_interfaz(self, actual, total, filename):
        self.progressbar.setValue(int((actual / total) * 100))
        # Si se pausó justo después de terminar un archivo, no pisar el aviso de pausa.
        worker = getattr(self, "worker", None)
        if worker is not None and worker.control.pausado:
            return
        self.lbl_estado.setText(f"Procesando: {filename} ({actual} de {total})")

    def _mostrar_controles_lote(self, mostrar: bool):
        """Muestra u oculta los botones de Pausar/Detener del lote de carpeta."""
        if mostrar:
            self.btn_pausar.setText("Pausar")
            self.btn_pausar.setEnabled(True)
            self.btn_pausar.show()
            self.btn_detener.setEnabled(True)
            self.btn_detener.show()
        else:
            self.btn_pausar.hide()
            self.btn_detener.hide()

    def alternar_pausa(self):
        """Pausa o reanuda el lote en curso."""
        worker = getattr(self, "worker", None)
        if worker is None or not worker.isRunning():
            return
        if worker.control.pausado:
            worker.reanudar()
            self.btn_pausar.setText("Pausar")
            self.lbl_estado.setText("Reanudando procesamiento...")
            self.lbl_estado.setStyleSheet("color: #2563eb;")
        else:
            worker.pausar()
            self.btn_pausar.setText("Reanudar")
            self.lbl_estado.setText(
                "En pausa (se completa el archivo en curso).\n"
                "Pulsa 'Reanudar' para continuar."
            )
            self.lbl_estado.setStyleSheet("color: #d97706; font-weight: 600;")

    def detener_procesamiento(self):
        """Detiene el lote conservando lo ya procesado (se puede reanudar)."""
        worker = getattr(self, "worker", None)
        if worker is None or not worker.isRunning():
            return
        respuesta = QMessageBox.question(
            self,
            "Detener procesamiento",
            "¿Seguro que quieres detener el procesamiento?\n\n"
            "Se conservará todo lo procesado hasta ahora y podrás reanudar "
            "esta carpeta más tarde desde donde se quedó.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        worker.detener()
        self.btn_pausar.setEnabled(False)
        self.btn_detener.setEnabled(False)
        self.lbl_estado.setText("Deteniendo... (se completa el archivo en curso)")
        self.lbl_estado.setStyleSheet("color: #d97706; font-weight: 600;")

    def _reactivar(self):
        self._set_busy(False)
        self.btn_procesar.setEnabled(bool(self.ruta_actual))
        self._mostrar_controles_lote(False)

    def procesamiento_individual_completado(self, data):
        self._reactivar()
        self.progressbar.setValue(100)
        modo = self._modo_actual()

        nueva_ruta = data.pop("__ruta_actualizada__", None)
        renombrado = data.pop("__renombrado__", False)
        niu_origen = data.pop("__niu_origen__", None)
        data.pop("__incluir_excel__", None)
        data.pop("__nombre_sugerido__", None)
        revisar_manual = data.get("Revisar_Manual") == "Sí"
        motivo_revision = data.get("Motivo_Revision")

        if nueva_ruta:
            self.ruta_actual = nueva_ruta
            self.lbl_ruta.setText(f"Archivo: {nueva_ruta}")

        partes = []

        if exporta_excel(modo):
            directorio = os.path.dirname(self.ruta_actual)
            nombre_base = os.path.splitext(os.path.basename(self.ruta_actual))[0]
            ruta_excel = os.path.join(directorio, f"resultado_{nombre_base}.xlsx")
            df = ordenar_dataframe(pd.DataFrame([limpiar_registro(data)]))
            df.to_excel(ruta_excel, index=False, engine="openpyxl")
            partes.append(f"Excel guardado en:\n{ruta_excel}")

        if niu_origen:
            origen_txt = _NIU_ORIGEN_TXT.get(niu_origen, niu_origen)
            partes.append(f"NIU recuperado por: {origen_txt}.")

        if renombra_archivo(modo) and renombrado:
            partes.append(f"Archivo renombrado a:\n{os.path.basename(nueva_ruta or self.ruta_actual)}")
        elif renombra_archivo(modo) and not renombrado:
            partes.append("El archivo ya tenía el nombre correcto o no se pudo renombrar.")

        if not partes:
            partes.append("Procesamiento completado (solo renombrado, sin Excel).")

        if revisar_manual:
            partes.append(f"⚠ Revisar a mano: {motivo_revision or 'dato dudoso detectado'}")

        self.lbl_estado.setText("Completado\n\n" + "\n\n".join(partes))
        if revisar_manual:
            self.lbl_estado.setStyleSheet("color: #d97706; font-weight: 600;")
        else:
            self.lbl_estado.setStyleSheet("color: #059669; font-weight: 600;")

    def procesamiento_completado(self, resultados):
        worker = getattr(self, "worker", None)
        detenido = worker is not None and worker.control.detenido
        self._reactivar()
        modo = self._modo_actual()
        segundos = int(time.time() - self.tiempo_inicio)
        texto_tiempo = f"{segundos // 60} min y {segundos % 60} seg" if segundos >= 60 else f"{segundos} s"

        if not resultados:
            if detenido:
                self.lbl_estado.setText(
                    "⏹ Procesamiento detenido. No se alcanzó a procesar ningún archivo.\n"
                    "Puedes reanudar esta carpeta más tarde."
                )
            else:
                self.lbl_estado.setText("No se encontraron documentos válidos.")
            self.lbl_estado.setStyleSheet("color: #d97706;")
            return

        ok = [r for r in resultados if "Error" not in r]
        err = [r for r in resultados if "Error" in r]
        renombrados = sum(1 for r in ok if r.get("__renombrado__"))
        niu_recuperados = sum(1 for r in ok if r.get("__niu_origen__"))
        revisar = [r for r in ok if r.get("Revisar_Manual") == "Sí"]

        encabezado = "⏹ Procesamiento detenido (se guardó lo procesado)" if detenido else None
        partes = [p for p in (encabezado,) if p]
        partes += [f"Tiempo: {texto_tiempo}", f"Procesados: {len(ok)} | Errores: {len(err)}"]
        if niu_recuperados:
            partes.append(f"NIU recuperados (archivo/base de usuarios): {niu_recuperados}")
        if revisar:
            partes.append(f"⚠ Para revisar a mano: {len(revisar)}")

        if exporta_excel(modo) and ok:
            # Cargar datos anteriores si existen (en caso de reanudación)
            ruta_excel = os.path.join(self.ruta_actual, "resultado_consolidado.xlsx")
            datos_anteriores = []
            if os.path.exists(ruta_excel):
                try:
                    df_anterior = pd.read_excel(ruta_excel)
                    datos_anteriores = df_anterior.to_dict("records")
                except Exception:
                    pass

            # Evitar duplicados: solo los nuevos archivos procesados
            registros_nuevos = [limpiar_registro(r) for r in ok]
            archivos_nuevos = {r.get("Archivo") for r in registros_nuevos}
            datos_anteriores_filtrados = [
                r for r in datos_anteriores
                if r.get("Archivo") not in archivos_nuevos
            ]

            # Combinar y escribir
            todos_datos = datos_anteriores_filtrados + registros_nuevos
            df = ordenar_dataframe(pd.DataFrame(todos_datos))
            df.to_excel(ruta_excel, index=False, engine="openpyxl")
            partes.append(f"Excel:\n{ruta_excel}")

        if renombra_archivo(modo):
            partes.append(f"Archivos renombrados: {renombrados}")

        if not detenido:
            self.progressbar.setValue(100)
        self.lbl_estado.setText("\n\n".join(partes))
        if revisar or detenido:
            self.lbl_estado.setStyleSheet("color: #d97706; font-weight: 600;")
        else:
            self.lbl_estado.setStyleSheet("color: #059669; font-weight: 600;")

    def procesamiento_error(self, error_msg):
        self._reactivar()
        self.lbl_estado.setText(f"Error: {error_msg}")
        self.lbl_estado.setStyleSheet("color: #dc2626; font-weight: 600;")

    def _preguntar_cambio_api_key(self) -> str | None:
        """Pregunta si quiere otra API key. Devuelve la nueva key o None."""
        respuesta = QMessageBox.question(
            self,
            "Sin créditos en OpenRouter",
            "La API key de OpenRouter se quedó sin créditos\n"
            "y no es posible continuar con la clave actual.\n\n"
            "¿Quieres ingresar otra API key para continuar?\n\n"
            "Si eliges 'No', el proceso se detiene y se conserva\n"
            "todo lo procesado hasta el momento.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            if solicitar_y_guardar_api_key(self):
                return resolve_api_key()
        return None

    def manejar_cuota_agotada(self):
        """El lote queda en pausa hasta que el usuario decida."""
        self.lbl_estado.setText("Proceso en pausa: sin créditos en OpenRouter.")
        self.lbl_estado.setStyleSheet("color: #d97706; font-weight: 600;")

        nueva_key = self._preguntar_cambio_api_key()
        if nueva_key:
            self.lbl_estado.setText("API key actualizada. Reanudando procesamiento...")
            self.lbl_estado.setStyleSheet("color: #2563eb;")
        else:
            self.lbl_estado.setText("Deteniendo y guardando lo procesado...")
            self.lbl_estado.setStyleSheet("color: #d97706; font-weight: 600;")
        self.worker.responder_cuota(nueva_key)

    def manejar_cuota_individual(self):
        """Sin créditos procesando un archivo individual."""
        self._reactivar()
        self.progressbar.setValue(0)
        self.lbl_estado.setText("Sin créditos en OpenRouter. El archivo no se procesó.")
        self.lbl_estado.setStyleSheet("color: #d97706; font-weight: 600;")

        nueva_key = self._preguntar_cambio_api_key()
        if nueva_key:
            self.iniciar_procesamiento()

    def configurar_api_key(self):
        if solicitar_y_guardar_api_key(self):
            QMessageBox.information(
                self, "API key",
                "Clave guardada en el Administrador de credenciales de Windows.",
            )

    def closeEvent(self, event):
        """Detiene el hilo del lote antes de cerrar (por si está en pausa)."""
        worker = getattr(self, "worker", None)
        if worker is not None and worker.isRunning():
            worker.detener()
            worker.wait(3000)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if not ensure_api_key_or_exit(None):
        sys.exit(0)
    ventana = AppOCR()
    ventana.show()
    sys.exit(app.exec())
