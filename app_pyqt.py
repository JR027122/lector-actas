import sys
import os
import time
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QProgressBar,
    QDialog, QLineEdit, QDialogButtonBox, QMessageBox,
    QFrame, QButtonGroup, QRadioButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from src.core.document_processor import process_document, process_folder
from src.core.processing_modes import MODE_OPTIONS, OCR_AND_RENAME, exporta_excel, renombra_archivo
from src.utils.excel_export import limpiar_registro, ordenar_dataframe
from src.utils.secure_api_key import resolve_api_key, save_api_key

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
"""


def solicitar_y_guardar_api_key(parent=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle("API key de Google Gemini")
    dlg.setMinimumWidth(480)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel(
        "Introduce tu API key de Google AI Studio.\n"
        "Se guardará de forma segura en el Administrador de credenciales de Windows.\n"
        "Clave gratuita: https://aistudio.google.com/apikey"
    ))
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
    os.environ["GEMINI_API_KEY"] = clave
    return True


def ensure_api_key_or_exit(parent=None):
    if resolve_api_key():
        return True
    return solicitar_y_guardar_api_key(parent)


class WorkerThread(QThread):
    progress_update = pyqtSignal(int, int, str)
    finished_success = pyqtSignal(list)
    finished_error = pyqtSignal(str)

    def __init__(self, folder_path, mode):
        super().__init__()
        self.folder_path = folder_path
        self.mode = mode

    def run(self):
        try:
            def callback(actual, total, filename):
                self.progress_update.emit(actual, total, filename)

            resultados = process_folder(
                self.folder_path, mode=self.mode, progress_callback=callback
            )
            self.finished_success.emit(resultados)
        except Exception as e:
            self.finished_error.emit(str(e))


class WorkerIndividual(QThread):
    finished_success = pyqtSignal(dict)
    finished_error = pyqtSignal(str)

    def __init__(self, file_path, mode):
        super().__init__()
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.mode = mode

    def run(self):
        try:
            data = process_document(self.file_path, self.filename, self.mode)
            if "Error" in data:
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
        self.resize(820, 580)
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
        s = QLabel("Digitalización inteligente de actas de mantenimiento con Google Gemini")
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
        self.btn_api.setToolTip("Configurar clave de Gemini")
        self.btn_api.clicked.connect(self.configurar_api_key)
        btn_row.addWidget(self.btn_carpeta)
        btn_row.addWidget(self.btn_archivo)
        btn_row.addWidget(self.btn_api)
        action_layout.addLayout(btn_row)

        self.lbl_ruta = QLabel("Ningún archivo o carpeta seleccionado")
        self.lbl_ruta.setObjectName("pathLabel")
        self.lbl_ruta.setWordWrap(True)
        action_layout.addWidget(self.lbl_ruta)

        self.btn_procesar = QPushButton("Iniciar procesamiento")
        self.btn_procesar.setObjectName("primaryBtn")
        self.btn_procesar.setEnabled(False)
        self.btn_procesar.setMinimumHeight(48)
        self.btn_procesar.clicked.connect(self.iniciar_procesamiento)
        action_layout.addWidget(self.btn_procesar)
        body.addWidget(action_card, stretch=1.2)

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
        root.addWidget(prog_card)

    def _modo_actual(self) -> str:
        idx = self.mode_group.checkedId()
        return list(MODE_OPTIONS.keys())[idx]

    def _set_busy(self, busy: bool):
        self.btn_carpeta.setEnabled(not busy)
        self.btn_archivo.setEnabled(not busy)
        self.btn_procesar.setEnabled(not busy)
        for btn in self.mode_group.buttons():
            btn.setEnabled(not busy)

    def seleccionar_carpeta(self):
        carpeta = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta con las actas")
        if carpeta:
            self.tipo_procesamiento = "carpeta"
            self.ruta_actual = carpeta
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

    def iniciar_procesamiento(self):
        self._set_busy(True)
        self.progressbar.setValue(0)
        self.lbl_estado.setText("Iniciando motor de IA...")
        self.lbl_estado.setObjectName("statusInfo")
        self.lbl_estado.setStyleSheet("color: #2563eb;")
        self.tiempo_inicio = time.time()
        modo = self._modo_actual()

        if self.tipo_procesamiento == "carpeta":
            self.worker = WorkerThread(self.ruta_actual, modo)
            self.worker.progress_update.connect(self.actualizar_interfaz)
            self.worker.finished_success.connect(self.procesamiento_completado)
            self.worker.finished_error.connect(self.procesamiento_error)
            self.worker.start()
        elif self.tipo_procesamiento == "archivo":
            self.worker_ind = WorkerIndividual(self.ruta_actual, modo)
            self.worker_ind.finished_success.connect(self.procesamiento_individual_completado)
            self.worker_ind.finished_error.connect(self.procesamiento_error)
            self.worker_ind.start()
            self.progressbar.setValue(50)

    def actualizar_interfaz(self, actual, total, filename):
        self.progressbar.setValue(int((actual / total) * 100))
        self.lbl_estado.setText(f"Procesando: {filename} ({actual} de {total})")

    def _reactivar(self):
        self._set_busy(False)
        self.btn_procesar.setEnabled(bool(self.ruta_actual))

    def procesamiento_individual_completado(self, data):
        self._reactivar()
        self.progressbar.setValue(100)
        modo = self._modo_actual()

        nueva_ruta = data.pop("__ruta_actualizada__", None)
        renombrado = data.pop("__renombrado__", False)
        data.pop("__incluir_excel__", None)
        data.pop("__nombre_sugerido__", None)

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

        if renombra_archivo(modo) and renombrado:
            partes.append(f"Archivo renombrado a:\n{os.path.basename(nueva_ruta or self.ruta_actual)}")
        elif renombra_archivo(modo) and not renombrado:
            partes.append("El archivo ya tenía el nombre correcto o no se pudo renombrar.")

        if not partes:
            partes.append("Procesamiento completado (solo renombrado, sin Excel).")

        self.lbl_estado.setText("Completado\n\n" + "\n\n".join(partes))
        self.lbl_estado.setStyleSheet("color: #059669; font-weight: 600;")

    def procesamiento_completado(self, resultados):
        self._reactivar()
        modo = self._modo_actual()
        segundos = int(time.time() - self.tiempo_inicio)
        texto_tiempo = f"{segundos // 60} min y {segundos % 60} seg" if segundos >= 60 else f"{segundos} s"

        if not resultados:
            self.lbl_estado.setText("No se encontraron documentos válidos.")
            self.lbl_estado.setStyleSheet("color: #d97706;")
            return

        ok = [r for r in resultados if "Error" not in r]
        err = [r for r in resultados if "Error" in r]
        renombrados = sum(1 for r in ok if r.get("__renombrado__"))

        partes = [f"Tiempo: {texto_tiempo}", f"Procesados: {len(ok)} | Errores: {len(err)}"]

        if exporta_excel(modo) and ok:
            df = ordenar_dataframe(pd.DataFrame([limpiar_registro(r) for r in ok]))
            ruta_excel = os.path.join(self.ruta_actual, "resultado_consolidado.xlsx")
            df.to_excel(ruta_excel, index=False, engine="openpyxl")
            partes.append(f"Excel:\n{ruta_excel}")

        if renombra_archivo(modo):
            partes.append(f"Archivos renombrados: {renombrados}")

        self.progressbar.setValue(100)
        self.lbl_estado.setText("\n\n".join(partes))
        self.lbl_estado.setStyleSheet("color: #059669; font-weight: 600;")

    def procesamiento_error(self, error_msg):
        self._reactivar()
        self.lbl_estado.setText(f"Error: {error_msg}")
        self.lbl_estado.setStyleSheet("color: #dc2626; font-weight: 600;")

    def configurar_api_key(self):
        if solicitar_y_guardar_api_key(self):
            QMessageBox.information(
                self, "API key",
                "Clave guardada en el Administrador de credenciales de Windows.",
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if not ensure_api_key_or_exit(None):
        sys.exit(0)
    ventana = AppOCR()
    ventana.show()
    sys.exit(app.exec())
