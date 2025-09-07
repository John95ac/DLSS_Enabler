import sys
import json
import os
import re
import glob
import random
import configparser
import time
import sys
import ctypes
from datetime import datetime  
import subprocess 
import difflib
import shutil

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox,
    QHBoxLayout, QLineEdit, QTabWidget, QGroupBox, QScrollArea,
    QInputDialog, QFileDialog, QMenuBar, QAction, QDialog,
    QFormLayout, QMenu, QAbstractItemView, QSplitter, QTextEdit,
    QSizePolicy, QToolTip, QFrame, QStatusBar, QStyle, QStyleOptionTitleBar,
    QComboBox, QDialogButtonBox, QGridLayout, QCheckBox, QStyledItemDelegate # Import QGridLayout, QCheckBox, and QStyledItemDelegate
)
from PyQt5.QtCore import Qt, QSettings, QPoint, QTimer, QSize, QUrl, QObject, QThread, pyqtSignal, pyqtSlot, QProcess, QFileSystemWatcher  # Added: threading primitives + FS watcher
from PyQt5.QtGui import (
    QPalette, QColor, QCursor, QClipboard, QFont,
    QTextCharFormat, QTextCursor, QSyntaxHighlighter,
    QPainter, QPen, QBrush, QMouseEvent, QRegion, QIcon, QPixmap, QLinearGradient,
    QDesktopServices, QMovie
)
from PyQt5.QtMultimedia import QSoundEffect, QMediaPlayer, QMediaContent
import platform
try:
    import winsound
except Exception:
    winsound = None

# --- JSON Syntax Highlighter ---
class JsonHighlighter(QSyntaxHighlighter):
    """Simple syntax highlighter for JSON."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        # Define color formats
        # Keys
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#FF79C6"))  # Pink
        self.highlighting_rules.append((r'"[^"]*"(?=\s*:)', key_format))
        # Strings (values)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#F1FA8C"))  # Yellow
        self.highlighting_rules.append((r'"[^"]*"(?!\s*:)', string_format))
        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#BD93F9"))  # Purple
        self.highlighting_rules.append((r'\b-?\d+(?:\.\d+)?\b', number_format))
        # Booleans
        bool_format = QTextCharFormat()
        bool_format.setForeground(QColor("#BD93F9"))  # Purple
        self.highlighting_rules.append((r'\b(true|false)\b', bool_format))
        # Null
        null_format = QTextCharFormat()
        null_format.setForeground(QColor("#BD93F9"))  # Purple
        self.highlighting_rules.append((r'\bnull\b', null_format))
        # Braces and brackets
        brace_format = QTextCharFormat()
        brace_format.setForeground(QColor("#FFFFFF"))  # White
        self.highlighting_rules.append((r'[{}[\]]', brace_format))
        # Colons
        colon_format = QTextCharFormat()
        colon_format.setForeground(QColor("#50FA7B"))  # Green
        self.highlighting_rules.append((r':', colon_format))
        # Commas
        comma_format = QTextCharFormat()
        comma_format.setForeground(QColor("#FFFFFF"))  # White
        self.highlighting_rules.append((r',', comma_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            expression = re.compile(pattern)
            for match in expression.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, format)
# --- END Highlighter ---

# --- NEW: Enhanced Gradient Background Widget ---
class GradientWidget(QWidget):
    """Widget that paints a horizontal enhanced gradient background."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Hacer que este widget se expanda para llenar el espacio disponible
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Definir colores MAS DISTINTOS para un degradado mas pronunciado
        # Degradado con tinte azul para mayor profundidad visual
        self.start_color = QColor(35, 35, 45)   # Gris azulado muy oscuro
        self.end_color = QColor(75, 75, 85)     # Gris azulado mas claro

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Crear un gradiente lineal horizontal
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, self.start_color)  # Izquierda - oscuro
        gradient.setColorAt(1, self.end_color)    # Derecha - claro

        # Rellenar todo el rectángulo del widget con el degradado
        painter.fillRect(self.rect(), QBrush(gradient))

    def sizeHint(self):
        # Sugerir un tamaño por defecto, aunque el layout lo ajustará
        return QSize(400, 300)

class FolderScanWorker(QObject):
    """Worker de segundo plano para calcular tamaños de subcarpetas sin bloquear la UI.

    Señales:
      - progress(int): índice actual (1..total) para actualizar la barra de progreso.
      - item(str, str, int): (nombre_relativo, ruta_absoluta, bytes) para resultados parciales.
      - finished(float): segundos transcurridos al finalizar.
    """
    progress = pyqtSignal(int)
    item = pyqtSignal(str, str, int)
    finished = pyqtSignal(float)

    def __init__(self, root_path, dirs):
        super().__init__()
        self.root_path = root_path
        self.dirs = list(dirs) if dirs else []
        self._stop = False

    @pyqtSlot()
    def run(self):
        start_t = time.time()
        try:
            for idx, dpath in enumerate(self.dirs, start=1):
                if self._stop:
                    break
                size = self._dir_size(dpath)
                rel_name = os.path.basename(dpath)
                self.item.emit(rel_name, dpath, int(size))
                self.progress.emit(int(idx))
        finally:
            elapsed = time.time() - start_t
            self.finished.emit(float(elapsed))

    def request_stop(self):
        """Pide una detención suave del recorrido (se verifica entre iteraciones)."""
        self._stop = True

    def _dir_size(self, path):
        total = 0
        for root, dirs, files in os.walk(path, topdown=True):
            # Puede personalizarse para ignorar enlaces simbólicos o carpetas específicas
            dirs[:] = [d for d in dirs]
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
                except Exception:
                    # Ignorar archivos inaccesibles sin interrumpir el proceso
                    pass
        return int(total)

class CustomTitleBar(QWidget):
    """Custom title bar with buttons and icon."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(40) # Altura ligeramente aumentada
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                border: none;
            }
        """)
        self.layout = QHBoxLayout(self)
        # Márgenes izquierdo y derecho reducidos
        self.layout.setContentsMargins(8, 0, 8, 0)
        # Espacio reducido entre elementos
        self.layout.setSpacing(8)

        # --- NUEVO: Etiqueta para el ícono ---
        self.icon_label = QLabel()
        # Cargar el ícono desde el archivo log.ico
        icon_path = os.path.join('Data', 'ICON', 'log.ico')
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            # Escalar el pixmap manteniendo la relación de aspecto, ajustado al tamaño de la barra
            scaled_pixmap = pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation) # Ligeramente más grande
            self.icon_label.setPixmap(scaled_pixmap)
        else:
            # Si no se encuentra el ícono, simplemente no mostrar nada
            pass
        self.layout.addWidget(self.icon_label)
        # --- FIN NUEVO: Etiqueta para el ícono ---

        # --- MENÚS ---
        # Botón de menú Archivo
        self.file_menu_button = QPushButton("File")
        # Tamaño ajustado para texto más grande
        self.file_menu_button.setFixedSize(70, 30)
        self.file_menu_button.setStyleSheet(self.get_menu_button_style())
        self.file_menu_button.clicked.connect(self.show_file_menu)
        self.layout.addWidget(self.file_menu_button)

        # Botón de menú Ayuda
        self.help_menu_button = QPushButton("Help")
        # Tamaño ajustado para texto más grande
        self.help_menu_button.setFixedSize(70, 30)
        self.help_menu_button.setStyleSheet(self.get_menu_button_style())
        self.help_menu_button.clicked.connect(self.show_help_menu)
        self.layout.addWidget(self.help_menu_button)

        # Espacio flexible para empujar el título a la derecha
        self.layout.addStretch(1)

        # --- TÍTULO ---
        self.title_label = QLabel("NVIDIA DLSS Enabler Helper App")
        # Fuente ligeramente más grande
        self.title_label.setStyleSheet("color: white; font-size: 15px; font-weight: bold;")
        self.layout.addWidget(self.title_label)

        # --- SEPARADOR ---
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #454545;") # Color del separador
        self.layout.addWidget(separator)

        # --- BOTONES DE VENTANA ---
        # Botón Minimizar
        self.minimize_button = QPushButton("-")
        # Tamaño ajustado
        self.minimize_button.setFixedSize(35, 35)
        self.minimize_button.setStyleSheet(self.get_window_button_style())
        self.minimize_button.setToolTip("Minimize window")
        self.minimize_button.clicked.connect(self.parent.showMinimized)
        self.layout.addWidget(self.minimize_button)

        # Botón Maximizar/Restaurar
        self.maximize_button = QPushButton("□")
        # Tamaño ajustado
        self.maximize_button.setFixedSize(35, 35)
        self.maximize_button.setStyleSheet(self.get_window_button_style())
        self.maximize_button.setToolTip("Maximize/Restore window")
        self.maximize_button.clicked.connect(self.toggle_maximize_restore)
        self.layout.addWidget(self.maximize_button)

        # Botón Cerrar
        self.close_button = QPushButton("×")
        # Tamaño ajustado
        self.close_button.setFixedSize(35, 35)
        self.close_button.setStyleSheet(self.get_window_button_style("close"))
        self.close_button.setToolTip("Close window")
        self.close_button.clicked.connect(self.parent.close)
        self.layout.addWidget(self.close_button)

        self.pressing = False
        self.offset = QPoint(0, 0)

        # --- MENÚS CONTEXTUALES ---
        self.file_menu = QMenu(self)
        self.file_menu.setStyleSheet(self.get_menu_style())
        # Refresh Restore List action (for JSON Restore tab)
        refresh_restore_action = QAction("Refresh Restore List", self)
        refresh_restore_action.setToolTip("Refresh the backups list in the JSON Restore tab")
        try:
            refresh_restore_action.triggered.connect(lambda: getattr(self.parent, 'tab_restore', None) and self.parent.tab_restore.refresh_list())
        except Exception:
            pass

        # Explicitly set the button state to match the file attribute (avoid emitting signals during init)
        try:
            self.read_only_btn.blockSignals(True)
            self.read_only_btn.setChecked(is_ro)
            self.read_only_btn.blockSignals(False)
        except Exception:
            pass

        # Enable/disable related controls based on RO state
        for widget in [getattr(self, 'disable_fg_checkbox', None),
                       getattr(self, 'disable_rr_checkbox', None),
                       getattr(self, 'disable_sr_checkbox', None),
                       getattr(self, 'disable_rr_model_checkbox', None),
                       getattr(self, 'disable_sr_model_checkbox', None)]:
            try:
                if widget is not None:
                    widget.setEnabled(not is_ro)
            except Exception:
                pass
        self.file_menu.addAction(refresh_restore_action)
        # Open Backup Folder action
        open_backup_action = QAction("Open Backup Folder", self)
        open_backup_action.setToolTip("Open the Data/backup folder in Explorer")
        def _open_backup():
            try:
                # Prefer script directory Data/backup
                script_dir = os.path.dirname(os.path.abspath(__file__))
                backup_dir = os.path.join(script_dir, 'Data', 'backup')
                if not os.path.isdir(backup_dir):
                    # Fallback: current working directory
                    backup_dir = os.path.join(os.getcwd(), 'Data', 'backup')
                if os.path.isdir(backup_dir):
                    os.startfile(backup_dir)
                else:
                    QMessageBox.warning(self, "Warning", f"Backup folder not found:\n{backup_dir}")
            except Exception as e:
                try:
                    QMessageBox.critical(self, "Error", f"Failed to open backup folder:\n{e}")
                except Exception:
                    pass
        try:
            open_backup_action.triggered.connect(_open_backup)
        except Exception:
            pass
        self.file_menu.addAction(open_backup_action)
        # Open Master Folder (NvBackend) action
        open_master_action = QAction("Open Master Folder", self)
        open_master_action.setToolTip("Open the Nvidia NvBackend folder that contains the master JSON")
        def _open_master_folder():
            try:
                home = os.path.expanduser("~")
                nvbackend = os.path.join(home, "AppData", "Local", "NVIDIA Corporation", "NVIDIA App", "NvBackend")
                if os.path.isdir(nvbackend):
                    os.startfile(nvbackend)
                else:
                    QMessageBox.warning(self, "Warning", f"NvBackend folder not found:\n{nvbackend}")
            except Exception as e:
                try:
                    QMessageBox.critical(self, "Error", f"Failed to open NvBackend folder:\n{e}")
                except Exception:
                    pass
        try:
            open_master_action.triggered.connect(_open_master_folder)
        except Exception:
            pass
        self.file_menu.addAction(open_master_action)
        # Add Restart action
        restart_action = QAction("Restart", self)
        try:
            restart_action.setShortcut("Ctrl+R")
        except Exception:
            pass
        try:
            restart_action.triggered.connect(self.parent.restart_app)
        except Exception:
            pass
        self.file_menu.addAction(restart_action)
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.parent.close)
        exit_action.setToolTip("Close the application.")
        self.file_menu.addAction(exit_action)

        self.help_menu = QMenu(self)
        self.help_menu.setStyleSheet(self.get_menu_style())
        about_action = QAction("About", self)
        about_action.setToolTip("Show information.")
        # Conectar la acción "About" a la nueva función show_about_dialog
        about_action.triggered.connect(self.parent.show_about_dialog)
        self.help_menu.addAction(about_action)

    def get_menu_button_style(self):
        """Estilo para los botones del menú en la barra de título."""
        return """
            QPushButton {
                background-color: #1a1a1a; /* Mismo color que la barra */
                color: white;
                border: 1px solid #454545; /* Borde sutil */
                border-radius: 4px; /* Bordes ligeramente redondeados */
                padding: 4px 6px;
                font-size: 14px; /* Fuente más grande */
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #454545;
            }
            QPushButton:pressed {
                background-color: #555555;
            }
        """

    def get_window_button_style(self, button_type="default"):
        """Estilo para los botones de ventana (minimizar, maximizar, cerrar)."""
        base_style = """
            QPushButton {
                background-color: #1a1a1a;
                color: white;
                border: none;
                font-size: 18px; /* Fuente más grande */
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #454545;
            }
        """
        if button_type == "close":
            # Use the same style as other window buttons (no special gray override)
            pass
        return base_style

    def get_menu_style(self):
        """Estilo para los menús desplegables."""
        return """
            QMenu {
                background-color: #353535;
                color: white;
                border: 1px solid #454545;
                font-size: 14px; /* Fuente más grande */
            }
            QMenu::item {
                padding: 6px 22px;
            }
            QMenu::item:selected {
                background-color: #454545;
            }
        """

    def show_file_menu(self):
        """Muestra el menú Archivo debajo del botón."""
        # Posicionar el menú debajo del botón
        button_pos = self.file_menu_button.mapToGlobal(QPoint(0, self.file_menu_button.height()))
        self.file_menu.exec_(button_pos)

    def show_help_menu(self):
        """Muestra el menú Ayuda debajo del botón."""
        # Posicionar el menú debajo del botón
        button_pos = self.help_menu_button.mapToGlobal(QPoint(0, self.help_menu_button.height()))
        self.help_menu.exec_(button_pos)

    def toggle_maximize_restore(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        self.offset = event.pos()
        self.pressing = True

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.pressing and not self.parent.isMaximized():
            self.parent.move(event.globalPos() - self.offset)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.pressing = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1a1a1a"))
        painter.drawRect(self.rect())

# --- Custom Delegate for List Item Background ---
class BackgroundRectDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Get the application data
        item = index.data(Qt.UserRole)
        
        # Default color (gray) - will be overridden if conditions are met
        color = QColor(85, 85, 85, 128)  # 50% transparent gray
        
        if item and isinstance(item, dict) and 'Application' in item:
            app_data = item['Application']
            # Check if any of the override settings are False
            overrides = [
                app_data.get("Disable_FG_Override", True),
                app_data.get("Disable_RR_Override", True),
                app_data.get("Disable_SR_Override", True),
                app_data.get("Disable_RR_Model_Override", True),
                app_data.get("Disable_SR_Model_Override", True)
            ]
            
            # If any override is False, use green (enabled), otherwise use red (all disabled)
            if any(not ovr for ovr in overrides):
                color = QColor(0, 119, 0, 128)  # 50% transparent green (enabled)
            else:
                color = QColor(119, 0, 0, 128)  # 50% transparent red (all disabled)
        
        # Draw the background rectangle with the determined color
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(option.rect.adjusted(1, 1, -1, -1), 2, 2)
        painter.restore()

        # Call the base class to draw the text
        super().paint(painter, option, index)

# --- NUEVA CLASE: AboutDialog ---
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About This Program")
        # ELIMINAR self.setFixedSize() para permitir que la ventana se ajuste al contenido
        # self.setFixedSize(550, 500) # Eliminado

        self.setStyleSheet("""
            QDialog {
                background-color: #353535;
                color: white;
                border: 1px solid #454545;
                border-radius: 5px;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QPushButton {
                background-color: #454545;
                color: white;
                border: 1px solid ;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
        """)
        self.init_ui()

    # Restart the current application: relaunch the same script and close this instance.
    def restart_app(self):
        try:
            python = sys.executable
            # Prefer the original invocation path
            script = os.path.abspath(sys.argv[0])
            args = sys.argv[1:]
            # Start a detached new process and quit this app
            QProcess.startDetached(python, [script] + args)
            QApplication.quit()
        except Exception as e:
            try:
                QMessageBox.critical(self, "Restart failed", f"Could not restart the app.\n{e}")
            except Exception:
                pass

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title_label = QLabel("<b>Dark Style PyQt5 Window</b>")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; color: #50FA7B;") # Bright Green
        layout.addWidget(title_label)

        description_text = """
        <p>Hello! 👋 This app helps you adjust NVIDIA DLSS features for your games by editing the master file <b>ApplicationStorage.json</b> used by <b>NVIDIA App</b>. 🎮⚙️</p>
        <p>Requirements: install the <a href='https://www.nvidia.com/es-la/software/nvidia-app/'>NVIDIA App</a> first and open it once to initialize your configuration. Then return here and use the tools. 🚀</p>
        <p>I created this program inspired by the Reddit discussion: 
        <a href='https://www.reddit.com/r/nvidia/comments/1ie7l1u/psa_how_to_enable_dlss_overrides_in_nvidia_app_on/?share_id=YcBEn_3x6IQM5MxTVu6Ja'>How to enable DLSS overrides in NVIDIA App</a>. 🔗
        I applied it to my game on an <b>RTX 3060</b> and being able to use more resources felt great. 🙌
        I’m sharing this tool so you can try it too, the app keeps things simple and includes restore options if you don’t like a change. 
        Please don’t over-stress your GPUs, drink water, and see you soon with more apps and mods! 💧😄</p>
        """
        description_label = QLabel(description_text)
        description_label.setWordWrap(True)
        description_label.setOpenExternalLinks(True)
        description_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(description_label)

        # Contact and Support Section
        contact_label = QLabel("<b>Contact and Support:</b>")
        contact_label.setStyleSheet("font-size: 15px; color: #BD93F9;") # Purple
        layout.addWidget(contact_label)

        # Layout for link buttons
        links_layout = QGridLayout()
        links_layout.setSpacing(10)

        # Nexus Mods
        nexus_button = QPushButton("Nexus Mods 🎮")
        nexus_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://next.nexusmods.com/profile/John1995ac")))
        links_layout.addWidget(nexus_button, 0, 0)

        # GitHub
        github_button = QPushButton("GitHub 💻")
        github_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/John95ac")))
        links_layout.addWidget(github_button, 0, 1)

        # Ko-fi
        kofi_button = QPushButton("Ko-fi ☕")
        kofi_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/john95ac")))
        links_layout.addWidget(kofi_button, 1, 0)

        # Patreon
        patreon_button = QPushButton("Patreon ❤️")
        patreon_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.patreon.com/c/John95ac")))
        links_layout.addWidget(patreon_button, 1, 1)

        layout.addLayout(links_layout)

        # Web documents button (same action as in Tips tab)
        try:
            web_docs_button = QPushButton("Web Documents John95AC WIP")
            web_docs_button.setCursor(Qt.PointingHandCursor)
            web_docs_button.setFixedHeight(28)
            web_docs_button.setToolTip("Web page that gathers documents, advancements, and more about these programs and mods")
            web_docs_button.setStyleSheet(
                "QPushButton { background: rgba(139, 0, 0, 0.8); color: white; border: 1px solid rgba(170, 0, 0, 0.8); border-radius: 4px; padding: 4px 8px;}"
                "QPushButton:hover { background: rgba(170, 0, 0, 0.9); }"
            )
            try:
                web_docs_button.clicked.connect(self.parent.open_web_interface)
            except Exception:
                # Fallback: open directly from AboutDialog if parent handler is unavailable
                web_docs_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://john95ac.github.io/website-documents-John95AC/index.html")))
            layout.addWidget(web_docs_button)
        except Exception:
            pass

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.close) # Conectar a self.close para asegurar que solo se cierre el diálogo.
        layout.addWidget(button_box)


class OutfitManagerTab(QWidget):
    """tab with buttons and lists."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.json_path = self.get_json_path()
        self.applications = []
        # Inform user if master JSON is missing; continue running
        try:
            if not os.path.exists(self.json_path):
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Master JSON Not Found")
                msg.setTextFormat(Qt.RichText)
                msg.setText(
                    "The master file 'ApplicationStorage.json' was not found.\n\n"
                    "Possible causes:\n"
                    "- You do not have an NVIDIA GPU, or\n"
                    "- NVIDIA App is not installed yet.\n\n"
                    "Recommendation: Install the <a href='https://www.nvidia.com/es-la/software/nvidia-app/'>NVIDIA App</a>, "
                    "open it once to initialize your configuration, then return here."
                )
                msg.addButton("OK", QMessageBox.AcceptRole)
                msg.exec_()
        except Exception:
            pass
        self.load_json()
        self.setup_ui()
        
        # Conectar señales de los botones
        self.safe_changes_btn.clicked.connect(self.save_changes)
        self.read_only_btn.toggled.connect(self.toggle_read_only)
        try:
            self.restore_btn.clicked.connect(self.open_restore_tab)
        except Exception:
            pass
        try:
            self.export_json_btn.clicked.connect(self.export_master_json)
        except Exception:
            pass
        
        # Crear directorio de respaldo si no existe
        self.backup_dir = os.path.join('Data', 'backup')
        os.makedirs(self.backup_dir, exist_ok=True)

        # Initialize sound resources preferring WAV via QSoundEffect (more reliable for PyInstaller)
        def _resource_path(*parts):
            # 1) PyInstaller temp directory
            try:
                base = getattr(sys, '_MEIPASS', None)
                if base and os.path.isdir(base):
                    return os.path.join(base, *parts)
            except Exception:
                pass
            # 2) Frozen executable directory (cx_Freeze / Nuitka)
            try:
                exe_dir = os.path.dirname(sys.executable)
                if exe_dir and os.path.isdir(exe_dir):
                    candidate = os.path.join(exe_dir, *parts)
                    if os.path.exists(candidate):
                        return candidate
            except Exception:
                pass
            # 3) Module directory (development / unfrozen)
            try:
                mod_dir = os.path.dirname(os.path.abspath(__file__))
                candidate = os.path.join(mod_dir, *parts)
                if os.path.exists(candidate):
                    return candidate
                return candidate
            except Exception:
                return os.path.join(*parts)

        self._wav_path = _resource_path('Data', 'Sounds', 'switch-sound.wav')
        self._mp3_path = _resource_path('Data', 'Sounds', 'switch-sound.mp3')

        # Prefer QSoundEffect (WAV). If WAV not available, we'll fall back to winsound.
        self._switch_effect = None
        try:
            if os.path.exists(self._wav_path):
                eff = QSoundEffect(self)
                eff.setSource(QUrl.fromLocalFile(self._wav_path))
                eff.setLoopCount(1)
                eff.setVolume(0.25)  # 0.0 - 1.0
                self._switch_effect = eff
        except Exception:
            self._switch_effect = None
        # Keep legacy MP3 player as a last resort for environments that support it
        self._switch_player = None
        try:
            self._switch_player = QMediaPlayer(self)
            self._switch_player.setMedia(QMediaContent(QUrl.fromLocalFile(self._mp3_path)))
            self._switch_player.setVolume(20)
        except Exception:
            self._switch_player = None

    def _play_switch(self):
        """Play the UI switch sound in a way that works reliably in a packaged .exe.
        Order: winsound.PlaySound (WAV, async) -> QSoundEffect (WAV) -> QMediaPlayer (MP3) -> winsound.Beep.
        Ensures rapid clicks retrigger by purging before play when applicable.
        """
        # Primary: winsound.PlaySound with WAV (built-in, zero external plugins)
        try:
            if winsound and platform.system().lower().startswith('win') and os.path.exists(self._wav_path):
                try:
                    # Stop any currently playing sound from this process
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:
                    pass
                flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
                winsound.PlaySound(self._wav_path, flags)
                return
        except Exception:
            pass

        # Secondary: QSoundEffect with WAV (requires QtMultimedia backend available)
        try:
            if self._switch_effect is not None:
                try:
                    self._switch_effect.stop()
                except Exception:
                    pass
                self._switch_effect.setLoopCount(1)
                self._switch_effect.play()
                return
        except Exception:
            pass

        # Tertiary: QMediaPlayer with MP3 (often needs Qt plugins when packaged)
        try:
            if self._switch_player is not None:
                self._switch_player.stop()
                self._switch_player.setPosition(0)
                self._switch_player.play()
                return
        except Exception:
            pass

        # Final fallback: simple Beep
        try:
            if winsound and platform.system().lower().startswith('win'):
                winsound.Beep(1000, 100)
        except Exception:
            pass

        # Sincronizar el botón Read Only con el estado REAL del archivo al iniciar
        try:
            self.sync_read_only_button_from_file()
        except Exception:
            pass
        # Hacer una sincronización diferida para asegurar el estado tras cargar toda la UI
        try:
            QTimer.singleShot(0, self.sync_read_only_button_from_file)
        except Exception:
            pass

        # Start a lightweight polling timer to continuously monitor RO attribute
        try:
            self._last_ro_state = None
            try:
                attrs = ctypes.windll.kernel32.GetFileAttributesW(self.json_path)
                self._last_ro_state = bool(attrs & 0x1) if attrs != -1 else None
            except Exception:
                self._last_ro_state = None
            self._ro_watch_timer = QTimer(self)
            self._ro_watch_timer.setInterval(1000)  # 1s
            self._ro_watch_timer.timeout.connect(self._poll_read_only_status)
            self._ro_watch_timer.start()
        except Exception:
            pass

    def get_json_path(self):
        # Dynamically get the user's home directory and build the JSON file path
        home_dir = os.path.expanduser("~")
        json_path = os.path.join(home_dir, "AppData", "Local", "NVIDIA Corporation", "NVIDIA App", "NvBackend", "ApplicationStorage.json")
        return json_path

    def load_json(self):
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.applications = data.get("Applications", [])
            # Sort applications alphabetically by DisplayName
            self.applications.sort(key=lambda app: app.get("Application", {}).get("DisplayName", "Unknown").lower())
        except Exception as e:
            print(f"Failed to load JSON file: {e}")
            self.applications = []

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        # Fuente base aumentada
        self.setStyleSheet("font-size: 14px;")
        main_h_layout = QHBoxLayout()
        main_h_layout.setSpacing(6)
        
        # --- NUEVA COLUMNA IZQUIERDA ---
        left_buttons_group = QGroupBox()
        left_buttons_group.setStyleSheet(self.get_groupbox_style())
        left_buttons_layout = QVBoxLayout()
        left_buttons_layout.setSpacing(10)
        left_buttons_layout.setContentsMargins(10, 20, 10, 10)
        
        # Botón Safe Changes
        self.safe_changes_btn = QPushButton()
        self.safe_changes_btn.setIcon(QIcon(os.path.join('Data', 'ICON', '011.png')))
        self.safe_changes_btn.setText("Safe Changes")
        self.safe_changes_btn.setIconSize(QSize(32, 32))
        self.safe_changes_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px;
                border: 1px solid rgba(21, 87, 36, 0.9);
                border-radius: 4px;
                background-color: rgba(21, 87, 36, 0.55); /* translucent green #155724 */
                color: white;
            }
            QPushButton:hover {
                background-color: rgba(21, 87, 36, 0.70);
            }
        """)
        self.safe_changes_btn.setToolTip("Save changes to the master JSON. Creates a backup and replaces the file atomically.")
        left_buttons_layout.addWidget(self.safe_changes_btn)
        
        # Botón Restore
        self.restore_btn = QPushButton()
        self.restore_btn.setIcon(QIcon(os.path.join('Data', 'ICON', '012.png')))
        self.restore_btn.setText("Restore")
        self.restore_btn.setIconSize(QSize(32, 32))
        self.restore_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px;
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #2d2d2d;
                color: white;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
        """)
        self.restore_btn.setToolTip("Open the JSON Restore tab to view and restore backups.")
        left_buttons_layout.addWidget(self.restore_btn)
        
        # Botón Export JSON
        self.export_json_btn = QPushButton()
        self.export_json_btn.setIcon(QIcon(os.path.join('Data', 'ICON', '013.png')))
        self.export_json_btn.setText("Export JSON")
        self.export_json_btn.setIconSize(QSize(32, 32))
        self.export_json_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px;
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #2d2d2d;
                color: white;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
        """)
        self.export_json_btn.setToolTip("Export the master JSON to your Downloads folder and open it.")
        left_buttons_layout.addWidget(self.export_json_btn)
        
        # Botón Read Only
        self.read_only_btn = QPushButton()
        self.read_only_btn.setIcon(QIcon(os.path.join('Data', 'ICON', '026.png')))
        self.read_only_btn.setText("Read Only")
        self.read_only_btn.setCheckable(True)  # Hacer el botón checkeable
        self.read_only_btn.setChecked(False)   # Por defecto no está activado
        self.read_only_btn.setIconSize(QSize(32, 32))
        self.read_only_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px;
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #2d2d2d;
                color: white;
            }
            QPushButton:checked {
                background-color: #3d5a80;
                border: 1px solid #4cc9f0;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
        """)
        self.read_only_btn.setToolTip("Toggle the Read-Only attribute on the master JSON file.")
        left_buttons_layout.addWidget(self.read_only_btn)
        
        # Espaciador para empujar los botones hacia arriba
        left_buttons_layout.addStretch(1)
        left_buttons_group.setLayout(left_buttons_layout)
        main_h_layout.addWidget(left_buttons_group, stretch=1)
        # --- FIN NUEVA COLUMNA IZQUIERDA ---
        
        # Columna central (lista de aplicaciones)
        outfit_list_group = QGroupBox("Application")
        outfit_list_group.setStyleSheet(self.get_groupbox_style())
        outfit_list_layout = QVBoxLayout()
        outfit_list_layout.setSpacing(6)
        self.outfit_listbox = QListWidget()
        self.outfit_listbox.setStyleSheet(self.get_list_style())
        for app in self.applications:
            display_name = app.get("Application", {}).get("DisplayName", "Unknown")
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, app)
            # Tooltip: Double-click behavior to toggle DLSS overrides
            item.setToolTip("Double-click to toggle all overrides (DLSS on/off).")
            self.outfit_listbox.addItem(item)
        self.outfit_listbox.currentItemChanged.connect(self.on_item_selected)
        try:
            self.outfit_listbox.itemDoubleClicked.connect(self.on_item_double_clicked)
        except Exception:
            pass
        outfit_list_layout.addWidget(self.outfit_listbox)
        outfit_list_group.setLayout(outfit_list_layout)
        main_h_layout.addWidget(outfit_list_group, stretch=3)

        # Apply custom delegate for background rectangle on list items
        self.outfit_listbox.setItemDelegate(BackgroundRectDelegate(self.outfit_listbox))
        outfit_details_group = QGroupBox("Application Details")
        outfit_details_group.setStyleSheet(self.get_groupbox_style())
        outfit_details_layout = QGridLayout()
        outfit_details_layout.setSpacing(6)

        def make_row(row, label_text):
            name_lbl = QLabel(label_text)
            name_lbl.setStyleSheet("color: white;")
            val_lbl = QLabel("-")
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("color: #cccccc;")
            outfit_details_layout.addWidget(name_lbl, row, 0)
            outfit_details_layout.addWidget(val_lbl, row, 1)
            return name_lbl, val_lbl

        self.override_labels = {}
        _, self.lbl_fg_value = make_row(0, "Disable_FG_Override")
        _, self.lbl_rr_value = make_row(1, "Disable_RR_Override")
        _, self.lbl_sr_value = make_row(2, "Disable_SR_Override")
        _, self.lbl_rrm_value = make_row(3, "Disable_RR_Model_Override")
        _, self.lbl_srm_value = make_row(4, "Disable_SR_Model_Override")

        # Map to old attribute names to keep other code paths safe (enable/disable no-ops on labels)
        self.disable_fg_checkbox = self.lbl_fg_value
        self.disable_rr_checkbox = self.lbl_rr_value
        self.disable_sr_checkbox = self.lbl_sr_value
        self.disable_rr_model_checkbox = self.lbl_rrm_value
        self.disable_sr_model_checkbox = self.lbl_srm_value

        outfit_details_group.setLayout(outfit_details_layout)
        main_h_layout.addWidget(outfit_details_group, stretch=2)
        layout.addLayout(main_h_layout)
        self.setLayout(layout)

    def get_groupbox_style(self):
        # Hacer el fondo del groupbox semi-transparente para que se vea el degradado
        return """
            QGroupBox {
                color: white;
                background-color: rgba(53, 53, 53, 180); /* Con transparencia */
                border: 1px solid #454545;
                border-radius: 5px;
                margin-top: 10px;
                font-size: 14px; /* Fuente más grande */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
                color: white;
                font-size: 14px; /* Fuente más grande */
            }
        """

    def get_list_style(self):
        # Hacer el fondo de la lista semi-transparente
        return """
            QListWidget {
                background-color: rgba(53, 53, 53, 180); /* Con transparencia */
                color: white;
                border: 1px solid #454545;
                padding: 6px;
                border-radius: 4px;
                font-size: 14px; /* Fuente más grande */
            }
            QListWidget::item {
                background-color: rgba(69, 69, 69, 150); /* Fondo más oscuro semi-transparente para el texto */
                padding: 6px;
                border-radius: 2px;
                margin: 1px;
            }
            QListWidget::item:selected {
                background-color: #454545;
                color: white;
            }
        """

    def get_button_style(self, color="default"):
        styles = {
            "default": """
                QPushButton {
                    background-color: rgba(53, 53, 53, 200); /* Fondo con algo de transparencia */
                    color: white;
                    border: 1px solid #454545;
                    padding: 9px;
                    border-radius: 4px;
                    font-size: 14px; /* Fuente más grande */
                }
                QPushButton:hover {
                    background-color: rgba(69, 69, 69, 220); /* Hover con transparencia */
                }
            """,
            "green": """
                QPushButton {
                    background-color: rgba(0, 102, 0, 150); /* Verde con mayor transparencia */
                    color: white;
                    border: 1px solid #007700;
                    padding: 9px;
                    border-radius: 4px;
                    font-size: 14px; /* Fuente más grande */
                }
                QPushButton:hover {
                    background-color: rgba(0, 119, 0, 180); /* Hover con transparencia */
                }
            """,
            "red": """
                QPushButton {
                    background-color: rgba(102, 0, 0, 150); /* Rojo con mayor transparencia */
                    color: white;
                    border: 1px solid #770000;
                    padding: 9px;
                    border-radius: 4px;
                    font-size: 14px; /* Fuente más grande */
                }
                QPushButton:hover {
                    background-color: rgba(119, 0, 0, 180); /* Hover con transparencia */
                }
            """
        }
        return styles.get(color, styles["default"])

    def on_item_selected(self, current, previous):
        if current:
            app = current.data(Qt.UserRole) or {}
            application = app.get("Application", {})
            self.set_override_labels_from_application(application)

    def set_override_labels_from_application(self, application: dict):
        """Update the read-only True/False labels based on the given application dict."""
        def set_val(lbl, val: bool):
            lbl.setText("True" if bool(val) else "False")
            # Inverted colors per request: True = red, False = green
            lbl.setStyleSheet("color: #cc3333;" if val else "color: #00aa00;")
        try:
            set_val(self.lbl_fg_value, application.get("Disable_FG_Override", False))
            set_val(self.lbl_rr_value, application.get("Disable_RR_Override", False))
            set_val(self.lbl_sr_value, application.get("Disable_SR_Override", False))
            set_val(self.lbl_rrm_value, application.get("Disable_RR_Model_Override", False))
            set_val(self.lbl_srm_value, application.get("Disable_SR_Model_Override", False))
        except Exception:
            pass

    def on_item_double_clicked(self, item):
        """Toggle all overrides to all True or all False on double-click of application name."""
        try:
            app = item.data(Qt.UserRole) or {}
            application = app.setdefault("Application", {})
            keys = [
                "Disable_FG_Override",
                "Disable_RR_Override",
                "Disable_SR_Override",
                "Disable_RR_Model_Override",
                "Disable_SR_Model_Override",
            ]
            states = [bool(application.get(k, False)) for k in keys]
            all_true = all(states)
            new_val = not all_true  # if all True -> set all False, else set all True
            for k in keys:
                application[k] = bool(new_val)
            # Reflect in labels
            self.set_override_labels_from_application(application)
            # Update back into the list item and data source
            item.setData(Qt.UserRole, app)
            try:
                row = self.outfit_listbox.row(item)
                if 0 <= row < len(self.applications):
                    self.applications[row] = app
            except Exception:
                pass
            # Force repaint to update background color delegate
            self.outfit_listbox.viewport().update()
            # Play click sound
            self._play_switch()
        except Exception:
            pass

    def create_backup(self):
        """Create a backup of the current JSON file"""
        try:
            # Check if the JSON path is valid
            if not self.json_path or not os.path.exists(self.json_path):
                QMessageBox.critical(
                    self,
                    "Error",
                    "Could not find the original configuration file."
                )
                return False
                
            # Ensure the backup directory exists
            try:
                os.makedirs(self.backup_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to create backup directory:\n{self.backup_dir}\n\n{str(e)}"
                )
                return False
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"ApplicationStorage_{timestamp}.json")
            
            try:
                # Leer el contenido primero
                with open(self.json_path, 'r', encoding='utf-8') as src:
                    content = src.read()
                    
                # Verificar si el contenido es válido JSON
                try:
                    json.loads(content)  # Validar que es JSON válido
                except json.JSONDecodeError:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "The configuration file is not valid JSON. A backup will be created anyway."
                    )
                
                # Escribir el archivo de respaldo
                with open(backup_path, 'w', encoding='utf-8') as dst:
                    dst.write(content)
                    
                return True
                
            except PermissionError:
                QMessageBox.critical(
                    self,
                    "Permission Error",
                    f"Permission denied. Ensure the app can write to:\n{self.backup_dir}\n\n"
                    "Try running this program as Administrator."
                )
                return False
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Backup Error",
                    f"Failed to create backup:\n{str(e)}\n\n"
                    f"Backup path: {backup_path}"
                )
                return False
                
        except Exception as e:
            QMessageBox.critical(
                self,
                "Unexpected Error",
                f"An unexpected error occurred while creating the backup:\n{str(e)}"
            )
            return False
            
    def toggle_read_only(self, checked):
        """Enable/disable filesystem Read-Only attribute on the master JSON file."""
        try:
            # If user is turning OFF Read-Only, ask for confirmation first
            if checked is False:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Confirm Read-Only Removal")
                msg.setTextFormat(Qt.RichText)
                msg.setText(
                    "Are you sure you want to remove read-only mode?<br>"
                    "<span style='color:#999'>This may cause changes to not take effect on the next PC restart.</span><br><br>"
                    "<span style='color:#7bd88f'>You can temporarily remove read-only to add more programs to NVIDIA App, "
                    "but don't forget to enable read-only again, or your changes may have no effect.</span>"
                )
                yes_btn = msg.addButton("Accept", QMessageBox.YesRole)
                no_btn = msg.addButton("Cancel", QMessageBox.NoRole)
                # Style buttons: Accept (grey), Cancel (amber-red)
                try:
                    yes_btn.setStyleSheet(
                        "QPushButton {"
                        " background-color: #6c757d; color: white;"
                        " border: 1px solid #545b62; border-radius: 4px; padding: 6px 12px;"
                        "}"
                        "QPushButton:hover { background-color: #5a6268; }"
                    )
                    no_btn.setStyleSheet(
                        "QPushButton {"
                        " background-color: #d35400; color: white;"
                        " border: 1px solid #a84300; border-radius: 4px; padding: 6px 12px;"
                        "}"
                        "QPushButton:hover { background-color: #e67e22; }"
                    )
                except Exception:
                    pass
                msg.exec_()
                if msg.clickedButton() is not yes_btn:
                    # Revert toggle and abort
                    self.read_only_btn.blockSignals(True)
                    self.read_only_btn.setChecked(True)
                    self.read_only_btn.blockSignals(False)
                    return

            if not hasattr(self, 'json_path') or not self.json_path:
                QMessageBox.warning(self, "Warning", "No JSON file has been loaded")
                self.read_only_btn.setChecked(not checked)  # Revert change in UI
                return
                
            # Update file attribute using helper (with verification)
            if os.path.exists(self.json_path):
                ok = self.set_file_readonly(self.json_path, checked)
                if not ok:
                    QMessageBox.warning(self, "Warning", "Could not change the file read-only attribute.")
                    self.read_only_btn.setChecked(not checked)
                    return
            
            # Update UI controls state
            self.disable_fg_checkbox.setEnabled(not checked)
            self.disable_rr_checkbox.setEnabled(not checked)
            self.disable_sr_checkbox.setEnabled(not checked)
            self.disable_rr_model_checkbox.setEnabled(not checked)
            self.disable_sr_model_checkbox.setEnabled(not checked)
            
            # Update button style
            self.read_only_btn.setStyleSheet("""
                QPushButton {
                    background-color: %s;
                    color: white;
                    border: 1px solid #2d2d2d;
                    border-radius: 4px;
                    padding: 5px 10px;
                    text-align: left;
                    padding-left: 10px;
                }
                QPushButton:checked {
                    background-color: #3d5a80;
                    border: 1px solid #4cc9f0;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                }
            """ % ("#3d5a80" if checked else "#2d2d2d"))
            
            # Mostrar mensaje de estado
            estado = "enabled" if checked else "disabled"
            QMessageBox.information(self, "Read-Only Mode", f"Read-Only mode {estado} successfully")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not change Read-Only mode:\n{str(e)}")
            self.read_only_btn.setChecked(not checked)  # Revert change on error

    def set_file_writable(self, filepath):
        """Ensure file is writable by removing the Read-Only attribute if present."""
        try:
            if os.path.exists(filepath):
                # Get current attributes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                if attrs & 0x1:  # 0x1 is Read-Only attribute
                    # Remove Read-Only
                    ctypes.windll.kernel32.SetFileAttributesW(filepath, attrs & ~0x1)
                    return True
            return True
        except Exception as e:
            print(f"Error al hacer el archivo escribible: {e}")
            return False

    def set_file_readonly(self, filepath, enable):
        """Set or unset the Read-Only attribute with retries. Returns True if final state matches 'enable'."""
        try:
            if not os.path.exists(filepath):
                return False
            import time, gc
            gc.collect()
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                    if attrs == -1:
                        time.sleep(0.1)
                        continue
                    if enable:
                        # Clear RO then set again to refresh reliably
                        if attrs & 0x1:
                            ctypes.windll.kernel32.SetFileAttributesW(filepath, attrs & ~0x1)
                            time.sleep(0.05)
                            attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                        ctypes.windll.kernel32.SetFileAttributesW(filepath, attrs | 0x1)
                    else:
                        if attrs & 0x1:
                            ctypes.windll.kernel32.SetFileAttributesW(filepath, attrs & ~0x1)
                    # Verify
                    res = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                    is_ro = bool(res & 0x1)
                    if is_ro == bool(enable):
                        return True
                except Exception:
                    pass
                time.sleep(0.2)
            return False
        except Exception as e:
            print(f"set_file_readonly error: {e}")
            return False

    def is_file_readonly_effective(self, filepath):
        """Return True if file is effectively read-only (DOS attribute or not writable by open)."""
        try:
            if not os.path.exists(filepath):
                return False
            # DOS attribute check (FILE_ATTRIBUTE_READONLY = 0x1)
            try:
                GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
                GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
                GetFileAttributesW.restype = ctypes.c_uint32
                attrs = GetFileAttributesW(ctypes.c_wchar_p(filepath))
                dos_ro = bool(attrs & 0x1) if attrs != 0xFFFFFFFF else False
            except Exception:
                dos_ro = False
            # Quick writability probe: try opening in r+ (no write performed, but requires write access)
            can_write = True
            try:
                f = open(filepath, 'r+')
                f.close()
            except Exception:
                can_write = False
            return bool(dos_ro or (not can_write))
        except Exception:
            return False

    def sync_read_only_button_from_file(self):
        """Read file Read-Only attribute and reflect the state on the toggle button and UI."""
        if not hasattr(self, 'json_path') or not self.json_path:
            return
        if not os.path.exists(self.json_path):
            return
        is_ro = self.is_file_readonly_effective(self.json_path)

        # Update button without emitting toggled signal
        try:
            self.read_only_btn.blockSignals(True)
            self.read_only_btn.setChecked(is_ro)
            self.read_only_btn.blockSignals(False)
        except Exception:
            pass

        # Update editing controls according to state
        for widget in [self.disable_fg_checkbox, self.disable_rr_checkbox,
                       self.disable_sr_checkbox, self.disable_rr_model_checkbox,
                       self.disable_sr_model_checkbox]:
            try:
                widget.setEnabled(not is_ro)
            except Exception:
                pass

        # Update button style
        try:
            self.read_only_btn.setStyleSheet("""
                QPushButton {
                    background-color: %s;
                    color: white;
                    border: 1px solid #2d2d2d;
                    border-radius: 4px;
                    padding: 5px 10px;
                    text-align: left;
                    padding-left: 10px;
                }
                QPushButton:checked {
                    background-color: #3d5a80;
                    border: 1px solid #4cc9f0;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                }
            """ % ("#3d5a80" if is_ro else "#2d2d2d"))
        except Exception:
            pass

        # Cache current RO state
        try:
            self._last_ro_state = bool(is_ro)
        except Exception:
            pass

    def _poll_read_only_status(self):
        """Periodic poll to detect external RO attribute changes and resync UI without popups."""
        try:
            if not hasattr(self, 'json_path') or not self.json_path:
                return
            if not os.path.exists(self.json_path):
                return
            is_ro = self.is_file_readonly_effective(self.json_path)
            if self._last_ro_state is None or is_ro != self._last_ro_state:
                # State changed externally; resync button and UI silently
                self.read_only_btn.blockSignals(True)
                self.read_only_btn.setChecked(is_ro)
                self.read_only_btn.blockSignals(False)
                # Update controls enablement
                for widget in [self.disable_fg_checkbox, self.disable_rr_checkbox,
                               self.disable_sr_checkbox, self.disable_rr_model_checkbox,
                               self.disable_sr_model_checkbox]:
                    try:
                        widget.setEnabled(not is_ro)
                    except Exception:
                        pass
                # Update style
                try:
                    self.read_only_btn.setStyleSheet("""
                        QPushButton {
                            background-color: %s;
                            color: white;
                            border: 1px solid #2d2d2d;
                            border-radius: 4px;
                            padding: 5px 10px;
                            text-align: left;
                            padding-left: 10px;
                        }
                        QPushButton:checked {
                            background-color: #3d5a80;
                            border: 1px solid #4cc9f0;
                        }
                        QPushButton:hover {
                            background-color: #3d3d3d;
                        }
                    """ % ("#3d5a80" if is_ro else "#2d2d2d"))
                except Exception:
                    pass
                self._last_ro_state = is_ro
        except Exception:
            # Never raise from polling
            pass

    def save_changes(self):
        try:
            # 1) Validate JSON path
            if not self.json_path or not os.path.exists(self.json_path):
                QMessageBox.critical(self, "Error", "Configuration file not found.")
                return

            # 2) Load original JSON structure
            with open(self.json_path, 'r', encoding='utf-8') as f:
                original_data = json.load(f)

            # 2.1) ALWAYS remove Read-Only before saving
            ro_off_ok = self.set_file_readonly(self.json_path, False)
            if not ro_off_ok:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "Could not remove read-only attribute before saving.\n"
                    "Close NVIDIA App and run this program as Administrator."
                )

            # 3) Update only Applications, keep the rest of the structure
            if isinstance(original_data, dict):
                original_data['Applications'] = self.applications
            else:
                original_data = {'Applications': self.applications}

            # 4) RO removal already handled in 2.1

            # 5) Create backup
            backup_ok = self.create_backup()
            if not backup_ok:
                reply = QMessageBox.warning(
                    self, 
                    "Warning", 
                    "Could not create backup. Do you want to continue anyway?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

            # 6) Save changes
            temp_path = self.json_path + ".tmp"
            try:
                # Write to temp file (single line)
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(original_data, f, ensure_ascii=False, separators=(',', ':'))
                
                # Replace original
                if os.path.exists(self.json_path):
                    os.replace(temp_path, self.json_path)
                else:
                    os.rename(temp_path, self.json_path)
                
                # ALWAYS set Read-Only at the end
                ok = self.set_file_readonly(self.json_path, True)
                if not ok:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "The file was saved, but it did NOT remain read-only.\n"
                        "Close NVIDIA App and run this program as Administrator."
                    )
                    try:
                        self.read_only_btn.setChecked(False)
                    except Exception:
                        pass
                else:
                    # Update UI
                    for widget in [self.disable_fg_checkbox, self.disable_rr_checkbox,
                                   self.disable_sr_checkbox, self.disable_rr_model_checkbox,
                                   self.disable_sr_model_checkbox]:
                        widget.setEnabled(False)
                    self.read_only_btn.setChecked(True)
                
                # Success message with final RO state verification and green advisory
                try:
                    _fa = ctypes.windll.kernel32.GetFileAttributesW(self.json_path)
                    final_ro = bool(_fa & 0x1) if _fa != -1 else False
                    estado = "Yes" if final_ro else "No"
                except Exception:
                    final_ro = None
                    estado = None
                try:
                    msg = QMessageBox(self)
                    msg.setIcon(QMessageBox.Information)
                    msg.setWindowTitle("Success")
                    msg.setTextFormat(Qt.RichText)
                    base = "Changes have been saved successfully!"
                    ro_line = f"<br><br>Read-only final: {estado}" if estado is not None else ""
                    advisory = "<br><br><span style='color:#00aa00'>To make changes effective, reboot your PC and open NVIDIA App to verify.</span>"
                    msg.setText(base + ro_line + advisory)
                    msg.addButton("OK", QMessageBox.AcceptRole)
                    msg.exec_()
                except Exception:
                    try:
                        QMessageBox.information(self, "Success", "Changes have been saved successfully!\nTo make changes effective, reboot your PC and open NVIDIA App to verify.")
                    except Exception:
                        pass
                
            except Exception as e:
                if os.path.exists(temp_path):
                    try: 
                        os.remove(temp_path)
                    except: 
                        pass
                raise e
                
        except PermissionError as e:
            QMessageBox.critical(
                self,
                "Permission Error",
                f"Could not save the file.\nError: {str(e)}\n\n"
                "1. Close NVIDIA App\n"
                "2. Run as Administrator\n"
                "3. Check write permissions"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save changes:\n{str(e)}"
            )

    def set_all_true(self):
        """Set all overrides to True for the currently selected application and refresh labels."""
        current = self.outfit_listbox.currentItem()
        if not current:
            return
        try:
            app = current.data(Qt.UserRole) or {}
            application = app.setdefault("Application", {})
            for k in [
                "Disable_FG_Override",
                "Disable_RR_Override",
                "Disable_SR_Override",
                "Disable_RR_Model_Override",
                "Disable_SR_Model_Override",
            ]:
                application[k] = True
            self.set_override_labels_from_application(application)
            current.setData(Qt.UserRole, app)
            try:
                row = self.outfit_listbox.currentRow()
                if 0 <= row < len(self.applications):
                    self.applications[row] = app
            except Exception:
                pass
            self.outfit_listbox.viewport().update()
        except Exception:
            pass

    def set_all_false(self):
        """Set all overrides to False for the currently selected application and refresh labels."""
        current = self.outfit_listbox.currentItem()
        if not current:
            return
        try:
            app = current.data(Qt.UserRole) or {}
            application = app.setdefault("Application", {})
            for k in [
                "Disable_FG_Override",
                "Disable_RR_Override",
                "Disable_SR_Override",
                "Disable_RR_Model_Override",
                "Disable_SR_Model_Override",
            ]:
                application[k] = False
            self.set_override_labels_from_application(application)
            current.setData(Qt.UserRole, app)
            self.outfit_listbox.viewport().update()
        except Exception:
            pass

    def open_restore_tab(self):
        """Switch to the JSON Restore tab in the main window."""
        try:
            if hasattr(self.parent, 'tabs') and hasattr(self.parent, 'tab_restore'):
                idx = self.parent.tabs.indexOf(self.parent.tab_restore)
                if idx != -1:
                    self.parent.tabs.setCurrentIndex(idx)
                else:
                    QMessageBox.warning(self, "Warning", "JSON Restore tab not found.")
            else:
                QMessageBox.warning(self, "Warning", "Main window tabs are not available.")
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not open JSON Restore tab.\n{e}")

    def export_master_json(self):
        """Copy master JSON to user's Downloads folder with timestamp."""
        try:
            if not self.json_path or not os.path.exists(self.json_path):
                QMessageBox.warning(self, "Warning", "Master JSON file not found.")
                return
            home = os.path.expanduser("~")
            downloads = os.path.join(home, 'Downloads')
            try:
                os.makedirs(downloads, exist_ok=True)
            except Exception:
                pass
            # Use original filename in Downloads
            dest = os.path.join(downloads, "ApplicationStorage.json")
            # If destination exists and is read-only, remove RO to allow overwrite
            try:
                if os.path.exists(dest):
                    # Try to ensure writable
                    try:
                        self.set_file_readonly(dest, False)
                    except Exception:
                        pass
                    try:
                        os.chmod(dest, 0o666)
                    except Exception:
                        pass
            except Exception:
                pass
            # Try copy with fallback strategies to guarantee overwrite
            copied = False
            try:
                shutil.copy2(self.json_path, dest)
                copied = True
            except Exception:
                try:
                    # Fallback: copy to temp then atomic replace
                    temp_dest = dest + ".tmp"
                    shutil.copyfile(self.json_path, temp_dest)
                    try:
                        if os.path.exists(dest):
                            os.replace(temp_dest, dest)
                        else:
                            os.rename(temp_dest, dest)
                        copied = True
                    finally:
                        try:
                            if os.path.exists(temp_dest):
                                os.remove(temp_dest)
                        except Exception:
                            pass
                except Exception:
                    try:
                        # Last resort: remove and copy
                        if os.path.exists(dest):
                            os.remove(dest)
                        shutil.copy2(self.json_path, dest)
                        copied = True
                    except Exception as e_copy:
                        raise e_copy
            # Open the Downloads folder for the user
            try:
                os.startfile(downloads)  # Windows only
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export JSON:\n{e}")

    def create_example_widget(self, text, index):
        example_frame = QWidget()
        # Hacer el fondo del frame semi-transparente
        example_frame.setStyleSheet("""
            QWidget {
                background-color: rgba(53, 53, 53, 180); /* Con transparencia */
                border: 1px solid #454545;
                border-radius: 4px;
                margin: 2px;
            }
            QWidget:hover {
                background-color: rgba(69, 69, 69, 200); /* Hover con transparencia */
            }
        """)
        example_layout = QHBoxLayout(example_frame)
        example_layout.setContentsMargins(6, 6, 6, 6)
        example_label = QLabel(text)
        # Fuente más grande
        example_label.setStyleSheet("QLabel { color: white; font-size: 14px; }")
        example_label.setCursor(QCursor(Qt.PointingHandCursor))
        example_label.setToolTip(f"Tooltip for {text} (Example)")
        example_layout.addWidget(example_label)
        self.scroll_layout.addWidget(example_frame)

# --- Tab: JSON Restore ---
class JsonRestoreTab(QWidget):
    """Tab to browse backups, compare with master, and restore safely."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.json_path = self.get_json_path()
        self.backup_dir = os.path.join('Data', 'backup')
        os.makedirs(self.backup_dir, exist_ok=True)
        # Build UI FIRST to guarantee the tab has visible content
        self.setup_ui()
        # Initialize sound resources for restore actions (optional)
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self._mp3_path = os.path.join(script_dir, 'Data', 'Sounds', 'switch-sound.mp3')
            self._wav_path = os.path.join(script_dir, 'Data', 'Sounds', 'switch-sound.wav')
            self._switch_player = None
            try:
                self._switch_player = QMediaPlayer(self)
                self._switch_player.setMedia(QMediaContent(QUrl.fromLocalFile(self._mp3_path)))
                self._switch_player.setVolume(15)
            except Exception:
                self._switch_player = None
            self._switch_effect = None
            try:
                if os.path.exists(self._wav_path):
                    self._switch_effect = QSoundEffect(self)
                    self._switch_effect.setSource(QUrl.fromLocalFile(self._wav_path))
                    self._switch_effect.setVolume(0.15)
            except Exception:
                self._switch_effect = None
        except Exception:
            self._switch_player = None
            self._switch_effect = None
        # FS watcher and debounce timer (optional)
        try:
            self._watcher = QFileSystemWatcher(self)
            try:
                self._watcher.addPath(self.backup_dir)
            except Exception:
                pass
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.setInterval(600)  # debounce
            self._refresh_timer.timeout.connect(self.refresh_list)
            try:
                self._watcher.directoryChanged.connect(self._on_backups_dir_changed)
            except Exception:
                pass
        except Exception:
            pass
        # Populate lists and viewers
        try:
            self.refresh_list()
        except Exception:
            pass
        try:
            self.load_master_text()
        except Exception:
            pass

    def _play_switch(self):
        try:
            if self._switch_player:
                self._switch_player.stop()
                self._switch_player.setPosition(0)
                self._switch_player.play()
                return
        except Exception:
            pass
        try:
            if self._switch_effect:
                self._switch_effect.stop()
                self._switch_effect.play()
                return
        except Exception:
            pass
        try:
            if winsound and platform.system().lower().startswith('win'):
                winsound.Beep(900, 120)
        except Exception:
            pass
        # FS watcher and debounce timer
        self._watcher = QFileSystemWatcher(self)
        try:
            self._watcher.addPath(self.backup_dir)
        except Exception:
            pass
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(600)  # debounce
        self._refresh_timer.timeout.connect(self.refresh_list)
        try:
            self._watcher.directoryChanged.connect(self._on_backups_dir_changed)
        except Exception:
            pass
        self.setup_ui()
        try:
            self.refresh_list()
        except Exception:
            pass

    def _on_backups_dir_changed(self, path):
        try:
            # Debounce frequent events
            self._refresh_timer.start()
        except Exception:
            pass

    def get_json_path(self):
        home_dir = os.path.expanduser("~")
        return os.path.join(home_dir, "AppData", "Local", "NVIDIA Corporation", "NVIDIA App", "NvBackend", "ApplicationStorage.json")

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        self.setStyleSheet("font-size: 14px;")

        # Backups list
        group = QGroupBox("Available Backups")
        group.setStyleSheet(self.get_groupbox_style())
        gl = QVBoxLayout()
        gl.setSpacing(6)
        self.backup_list = QListWidget()
        self.backup_list.setStyleSheet(self.get_list_style())
        self.backup_list.setFixedHeight(140)
        self.backup_list.itemSelectionChanged.connect(self.on_select_backup)
        gl.addWidget(self.backup_list)
        group.setLayout(gl)
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(group)

        # Splitter with two viewers
        splitter = QSplitter(Qt.Horizontal)

        # Left: Selected backup
        left_group = QGroupBox("Selected Backup")
        left_group.setStyleSheet(self.get_groupbox_style())
        left_lay = QVBoxLayout()
        left_lay.setSpacing(6)
        self.txt_backup = QTextEdit()
        self.txt_backup.setReadOnly(True)
        self.txt_backup.setStyleSheet(self.get_textedit_style())
        self.hl_backup = JsonHighlighter(self.txt_backup.document())
        left_lay.addWidget(self.txt_backup)
        left_group.setLayout(left_lay)
        splitter.addWidget(left_group)

        # Right: Current master
        right_group = QGroupBox("Current Master")
        right_group.setStyleSheet(self.get_groupbox_style())
        right_lay = QVBoxLayout()
        right_lay.setSpacing(6)
        self.txt_master = QTextEdit()
        self.txt_master.setReadOnly(True)
        self.txt_master.setStyleSheet(self.get_textedit_style())
        self.hl_master = JsonHighlighter(self.txt_master.document())
        right_lay.addWidget(self.txt_master)
        right_group.setLayout(right_lay)
        splitter.addWidget(right_group)
        layout.addWidget(splitter)

        # Diff viewer
        # (Removed by request)

        # Restore selected backup button
        self.btn_restore = QPushButton("Restore")
        try:
            self.btn_restore.setIcon(QIcon(os.path.join('Data', 'ICON', '022.png')))
            self.btn_restore.setIconSize(QSize(24, 24))
        except Exception:
            pass
        self.btn_restore.setToolTip("Restore the selected backup over the master (keeps Read-Only ON afterwards).")
        self.btn_restore.setStyleSheet("""
            QPushButton {
                background-color: #1e7e34; /* green */
                color: white;
                border: 2px solid #155724;
                padding: 12px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #444; border-color: #333; }
        """)
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self.on_restore)
        layout.addWidget(self.btn_restore)

        # Restore to original mode (oldest backup) button
        self.btn_restore_original = QPushButton("Restore to Original Mode")
        try:
            self.btn_restore_original.setIcon(QIcon(os.path.join('Data', 'ICON', '019.png')))
            self.btn_restore_original.setIconSize(QSize(24, 24))
        except Exception:
            pass
        self.btn_restore_original.setToolTip("Restore the oldest backup as master (leaves Read-Only OFF afterwards).")

        # Helpful tooltip for the backups list
        try:
            self.backup_list.setToolTip("Select a backup to preview. Use Restore to apply it.")
        except Exception:
            pass
        self.btn_restore_original.setStyleSheet("""
            QPushButton {
                background-color: #0069d9; /* blue */
                color: white;
                border: 2px solid #005cbf;
                padding: 12px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #007bff; }
            QPushButton:disabled { background-color: #444; border-color: #333; }
        """)
        self.btn_restore_original.clicked.connect(self.on_restore_original)
        layout.addWidget(self.btn_restore_original)

        self.setLayout(layout)

    def refresh_list(self):
        try:
            if not hasattr(self, 'backup_list') or self.backup_list is None:
                return
            # Remember current selection path, if any
            sel_items = self.backup_list.selectedItems()
            sel_path = sel_items[0].data(Qt.UserRole) if sel_items else None

            self.backup_list.blockSignals(True)
            self.backup_list.clear()
            # Add master at top, highlighted green
            master_item = QListWidgetItem("[MASTER] ApplicationStorage.json")
            master_item.setData(Qt.UserRole, self.json_path)
            master_item.setForeground(QColor("#ffffff"))
            master_item.setBackground(QColor(0, 100, 0))
            self.backup_list.addItem(master_item)

            # List backups by modification time desc
            try:
                files = []
                if os.path.isdir(self.backup_dir):
                    for fn in os.listdir(self.backup_dir):
                        if fn.lower().endswith('.json'):
                            fp = os.path.join(self.backup_dir, fn)
                            try:
                                mt = os.path.getmtime(fp)
                                files.append((mt, fp))
                            except Exception:
                                pass
                files.sort(key=lambda x: x[0], reverse=True)
                for mt, fp in files:
                    ts = datetime.fromtimestamp(mt).strftime('%Y-%m-%d %H:%M:%S')
                    item = QListWidgetItem(f"{ts} - {os.path.basename(fp)}")
                    item.setData(Qt.UserRole, fp)
                    self.backup_list.addItem(item)
            except Exception:
                pass

            # Restore selection if possible; else select master
            target_row = 0
            if sel_path:
                for i in range(self.backup_list.count()):
                    it = self.backup_list.item(i)
                    if it and it.data(Qt.UserRole) == sel_path:
                        target_row = i
                        break
            self.backup_list.setCurrentRow(target_row)
        except Exception:
            pass
        finally:
            try:
                self.backup_list.blockSignals(False)
            except Exception:
                pass
        # Update master viewer (safe)
        try:
            self.load_master_text()
        except Exception:
            pass

    def load_master_text(self):
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                txt = f.read()
            self.txt_master.setPlainText(txt)
        except Exception as e:
            self.txt_master.setPlainText(f"<failed to read master>\n{e}")

    def on_select_backup(self):
        items = self.backup_list.selectedItems()
        if not items:
            self.txt_backup.clear()
            self.txt_diff.clear()
            self.btn_restore.setEnabled(False)
            return
        fp = items[0].data(Qt.UserRole)
        # Enable restore only when a backup (not master) is selected
        is_master = (fp == self.json_path)
        self.btn_restore.setEnabled(not is_master)
        # Load selected content
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                txt = f.read()
            self.txt_backup.setPlainText(txt)
        except Exception as e:
            self.txt_backup.setPlainText(f"<failed to read>\n{e}")
        # Ensure master shown
        self.load_master_text()

    def on_restore(self):
        items = self.backup_list.selectedItems()
        if not items:
            return
        src = items[0].data(Qt.UserRole)
        if src == self.json_path:
            return
        # Play sound immediately on button press
        self._play_switch()
        # Confirm
        reply = QMessageBox.question(self, "Confirmation", 
                                     "Restore this backup over the master?\nAn automatic backup will be created.",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            # Ensure RO off
            try:
                self.parent.tab_outfits.set_file_readonly(self.json_path, False)
            except Exception:
                pass
            # Create backup of current master using existing helper
            try:
                self.parent.tab_outfits.create_backup()
            except Exception:
                pass
            # Read source
            with open(src, 'r', encoding='utf-8') as f:
                content = f.read()
            # Write to temp and replace
            temp_path = self.json_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            if os.path.exists(self.json_path):
                os.replace(temp_path, self.json_path)
            else:
                os.rename(temp_path, self.json_path)
            # Set RO on
            try:
                self.parent.tab_outfits.set_file_readonly(self.json_path, True)
            except Exception:
                pass
            QMessageBox.information(self, "Success", "Restore completed.")
            # Refresh views (deferred and safe)
            try:
                QTimer.singleShot(0, self.load_master_text)
                QTimer.singleShot(0, self.on_select_backup)
                QTimer.singleShot(0, self.refresh_list)
            except Exception:
                pass
        except PermissionError as e:
            QMessageBox.critical(self, "Permission Error", f"Could not restore.\n{e}\nRun as Administrator and close NVIDIA App.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore:\n{e}")

    def on_restore_original(self):
        """Restore the oldest backup over the master. Leave master NOT read-only afterwards."""
        try:
            # Play sound immediately on button press
            self._play_switch()
            # Find oldest backup
            files = []
            for fn in os.listdir(self.backup_dir):
                if fn.lower().endswith('.json'):
                    fp = os.path.join(self.backup_dir, fn)
                    try:
                        mt = os.path.getmtime(fp)
                        files.append((mt, fp))
                    except Exception:
                        pass
            if not files:
                QMessageBox.warning(self, "Warning", "No backups available to restore.")
                return
            files.sort(key=lambda x: x[0])  # oldest first
            src = files[0][1]
            # Confirm
            reply = QMessageBox.question(
                self,
                "Confirmation",
                "Restore the oldest backup as the master?\nAn automatic backup will be created.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            # Ensure RO off
            try:
                self.parent.tab_outfits.set_file_readonly(self.json_path, False)
            except Exception:
                pass
            # Backup current master
            try:
                self.parent.tab_outfits.create_backup()
            except Exception:
                pass
            # Replace content
            with open(src, 'r', encoding='utf-8') as f:
                content = f.read()
            temp_path = self.json_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            if os.path.exists(self.json_path):
                os.replace(temp_path, self.json_path)
            else:
                os.rename(temp_path, self.json_path)
            # Leave NOT read-only
            try:
                self.parent.tab_outfits.set_file_readonly(self.json_path, False)
            except Exception:
                pass
            QMessageBox.information(self, "Success", "Restore to original mode completed (read-only disabled).")
            # Refresh views (deferred and safe)
            try:
                QTimer.singleShot(0, self.load_master_text)
                QTimer.singleShot(0, self.on_select_backup)
                QTimer.singleShot(0, self.refresh_list)
            except Exception:
                pass
        except PermissionError as e:
            QMessageBox.critical(self, "Permission Error", f"Could not restore.\n{e}\nRun as Administrator and close NVIDIA App.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore:\n{e}")

    def get_groupbox_style(self):
        return """
            QGroupBox {
                color: white;
                background-color: rgba(53, 53, 53, 180);
                border: 1px solid #454545;
                border-radius: 5px;
                margin-top: 10px;
                font-size: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
                color: white;
                font-size: 14px;
            }
        """

    def get_list_style(self):
        return """
            QListWidget {
                background-color: rgba(53, 53, 53, 180);
                color: white;
                border: 1px solid #454545;
                padding: 6px;
                border-radius: 4px;
                font-size: 14px;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:selected { background-color: #454545; color: white; }
        """

    def get_textedit_style(self):
        return """
            QTextEdit {
                background-color: rgba(53, 53, 53, 180);
                color: white;
                border: 1px solid #454545;
                padding: 6px;
                border-radius: 4px;
                font-size: 14px;
                font-family: Consolas, monospace;
            }
        """

    def get_button_style(self):
        return """
            QPushButton {
                background-color: rgba(53, 53, 53, 200);
                color: white;
                border: 1px solid #454545;
                padding: 9px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: rgba(69, 69, 69, 220); }
        """
# --- Fin Pestaña JSON Restore ---

class TipsTab(QWidget):
    """Tab that shows a random cat image at the bottom-right corner."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setStyleSheet("background-color: transparent; font-size: 14px;")
        # Keep a small history to avoid repeating the same image too frequently
        self._no_repeat_window = 7  # do not repeat an image within the last 7 selections
        self._recent_images = []    # simple FIFO list

        # Layout that lets us anchor advice top-left and image bottom-right
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(6)

        # Stretches: keep row 1 and column 1 flexible to push widgets to corners
        self._layout.setRowStretch(0, 0)   # top row minimal
        self._layout.setRowStretch(1, 1)   # bottom row expands
        self._layout.setColumnStretch(0, 0)  # left column minimal
        self._layout.setColumnStretch(1, 1)  # right column expands
        # Reserve space for the image cell so the advice cannot shrink it away
        self._layout.setRowMinimumHeight(1, 360)
        self._layout.setColumnMinimumWidth(1, 360)
        # Add web documents button
        self._layout.setColumnMinimumWidth(0, 200)

        # Top-right bar with "New tip" button only
        try:
            # New tip button
            self.btn_new = QPushButton("New tip")
            self.btn_new.setCursor(Qt.PointingHandCursor)
            self.btn_new.setFixedHeight(28)
            self.btn_new.setToolTip("Show a new random tip.")
            self.btn_new.setStyleSheet(
                "QPushButton { background: #2b2b2b; color: #e0e0e0; border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px 8px;}"
                "QPushButton:hover { background: #3a3a3a; }"
            )
            self.btn_new.clicked.connect(self.refresh)

            top_bar = QWidget()
            top_bar.setStyleSheet("background: transparent;")
            top_lay = QHBoxLayout(top_bar)
            top_lay.setContentsMargins(0, 0, 0, 0)
            top_lay.addStretch(1)
            top_lay.addWidget(self.btn_new, 0, Qt.AlignRight)
            self._layout.addWidget(top_bar, 0, 1, alignment=Qt.AlignRight | Qt.AlignTop)
        except Exception:
            pass

        # Bottom-left web interface button
        try:
            # Web Documents Button (red translucent style)
            self.btn_web = QPushButton("Web Documents John95AC WIP")
            self.btn_web.setCursor(Qt.PointingHandCursor)
            self.btn_web.setFixedHeight(28)
            self.btn_web.setToolTip("Web page that gathers documents, advancements, and more about these programs and mods")
            self.btn_web.setStyleSheet(
                "QPushButton { background: rgba(139, 0, 0, 0.8); color: white; border: 1px solid rgba(170, 0, 0, 0.8); border-radius: 4px; padding: 4px 8px;}"
                "QPushButton:hover { background: rgba(170, 0, 0, 0.9); }"
            )
            self.btn_web.clicked.connect(self.parent.open_web_interface)

            # Container for bottom-left positioning
            bottom_left_container = QWidget()
            bottom_left_container.setStyleSheet("background: transparent;")
            bottom_left_layout = QVBoxLayout(bottom_left_container)
            bottom_left_layout.setContentsMargins(0, 0, 0, 0)
            bottom_left_layout.addWidget(self.btn_web, alignment=Qt.AlignBottom | Qt.AlignLeft)
            bottom_left_layout.addStretch(1)  # Push button to bottom

            self._layout.addWidget(bottom_left_container, 1, 0, alignment=Qt.AlignBottom | Qt.AlignLeft)
        except Exception:
            pass

        # Bottom-right box containing advice (left) and cat image (right)
        self.bottom_box = QWidget()
        self.bottom_box.setStyleSheet("background: transparent;")
        h = QHBoxLayout(self.bottom_box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        self.advice_label = QLabel()
        self.advice_label.setWordWrap(True)
        # Center the text content within its own box
        self.advice_label.setAlignment(Qt.AlignCenter)
        # Remove global color so inline HTML colors (e.g., green italics) are respected; increase font size
        self.advice_label.setStyleSheet("background: transparent; font-size: 24px; font-weight: 600;")
        # Enable rich text and clickable links
        self.advice_label.setTextFormat(Qt.RichText)
        self.advice_label.setOpenExternalLinks(True)
        try:
            # Ensure the label accepts mouse for links and behaves like a browser for anchors
            self.advice_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        except Exception:
            pass
        # Confine advice to a fixed-size rectangle (slightly larger)
        self.advice_label.setFixedWidth(640)
        self.advice_label.setMinimumHeight(150)

        # Wrap in a box (overlay) to offset position slightly down and right
        self.advice_box = QWidget(self)  # overlay child of TipsTab, not managed by grid
        self.advice_box.setStyleSheet("background: transparent;")
        try:
            # ensure true transparency; allow mouse events so links are clickable
            self.advice_box.setAttribute(Qt.WA_TranslucentBackground, True)
            self.advice_box.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        except Exception:
            pass
        vbox = QVBoxLayout(self.advice_box)
        # Use zero margins in the overlay; we'll position the box explicitly
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self.advice_label, alignment=Qt.AlignCenter)
        # Initial positioning of the overlay (will be updated on show/resize)
        self._advice_offset_left = 56
        # Raise the advice a bit higher for better visual balance
        self._advice_offset_top = 190
        self.position_advice_box()

        self.image_label = QLabel()
        self.image_label.setStyleSheet("background: transparent;")
        # Reserve the visible footprint for the image so it is never cropped by layout
        self.image_label.setMinimumSize(360, 360)
        self.image_label.setMaximumSize(360, 360)
        self.image_label.setScaledContents(False)  # we will scale pixmap manually
        # Make image ignore mouse events so it never blocks link clicks beneath
        try:
            self.image_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            pass
        # Keep a reference to current GIF movie if any
        self._gif_movie = None

        # Only the image lives in the bottom box (right)
        h.addWidget(self.image_label, 0, Qt.AlignVCenter)

        # Place the bottom box at bottom-right
        self._layout.addWidget(self.bottom_box, 1, 1, alignment=Qt.AlignRight | Qt.AlignBottom)

        # Ensure z-order so image appears above advice
        self.ensure_image_on_top()

        # Initial content
        self.refresh()

    def get_cat_dir(self):
        """Return the directory where cat images are located.
        Preference: current working directory Data/CAT, fallback to script directory Data/CAT.
        """
        cwd_path = os.path.join(os.getcwd(), 'Data', 'CAT')
        if os.path.isdir(cwd_path):
            return cwd_path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, 'Data', 'CAT')
        return script_path

    def list_cat_images(self):
        base = self.get_cat_dir()
        # Support PNG and GIF images (recursive to include subfolders)
        files = []
        try:
            files.extend(sorted(glob.glob(os.path.join(base, '**', '*.png'), recursive=True)))
            files.extend(sorted(glob.glob(os.path.join(base, '**', '*.PNG'), recursive=True)))
            files.extend(sorted(glob.glob(os.path.join(base, '**', '*.gif'), recursive=True)))
            files.extend(sorted(glob.glob(os.path.join(base, '**', '*.GIF'), recursive=True)))
        except Exception:
            pass
        return files

    def show_random_cat(self):
        imgs = self.list_cat_images()
        if not imgs:
            self.image_label.setText("No cat images found in Data/CAT")
            self.image_label.setStyleSheet("color: #CCCCCC; background: transparent;")
            return

        # Prefer GIFs sometimes so they are more likely to appear when available
        gifs = [p for p in imgs if p.lower().endswith('.gif')]
        prefer_gifs = gifs and (random.random() < 0.6)

        # Build primary candidate pool (gifs or all imgs)
        primary_pool = gifs if prefer_gifs else imgs
        # Filter out recently used images
        filtered_primary = [p for p in primary_pool if p not in self._recent_images]

        # If primary is exhausted after filtering, relax to all images excluding recents
        candidates = filtered_primary if filtered_primary else [p for p in imgs if p not in self._recent_images]
        # If still empty (e.g., fewer unique images than the no-repeat window), allow any image
        if not candidates:
            candidates = primary_pool if primary_pool else imgs

        path = random.choice(candidates)

        ext = os.path.splitext(path)[1].lower()

        # Stop previous movie if switching from GIF to static or to another GIF
        if getattr(self, '_gif_movie', None) is not None:
            try:
                self._gif_movie.stop()
            except Exception:
                pass
            self._gif_movie = None
            try:
                self.image_label.setMovie(None)
            except Exception:
                pass

        if ext == '.gif':
            try:
                movie = QMovie(path)
                # Optional: set cache mode for smoother playback
                try:
                    movie.setCacheMode(QMovie.CacheAll)
                except Exception:
                    pass
                self._gif_movie = movie
                self.image_label.setMovie(movie)
                movie.start()
                # Update recent list only after successful load/start
                try:
                    self._recent_images.append(path)
                    if len(self._recent_images) > self._no_repeat_window:
                        # FIFO: drop oldest
                        self._recent_images.pop(0)
                except Exception:
                    pass
            except Exception:
                # Fallback to static load if movie fails
                pix = QPixmap(path)
                if pix.isNull():
                    self.image_label.setText("Failed to load: " + os.path.basename(path))
                    self.image_label.setStyleSheet("color: #FF8888; background: transparent;")
                    return
                max_w = self.image_label.maximumWidth()
                max_h = self.image_label.maximumHeight()
                scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled)
                # Update recent list after successful static display
                try:
                    self._recent_images.append(path)
                    if len(self._recent_images) > self._no_repeat_window:
                        self._recent_images.pop(0)
                except Exception:
                    pass
        else:
            pix = QPixmap(path)
            if pix.isNull():
                self.image_label.setText("Failed to load: " + os.path.basename(path))
                self.image_label.setStyleSheet("color: #FF8888; background: transparent;")
                return
            # Scale to fit max size while keeping aspect ratio
            max_w = self.image_label.maximumWidth()
            max_h = self.image_label.maximumHeight()
            scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)
            # Update recent list after successful static display
            try:
                self._recent_images.append(path)
                if len(self._recent_images) > self._no_repeat_window:
                    self._recent_images.pop(0)
            except Exception:
                pass

    def get_advice_ini_path(self):
        """Return preferred Advice.ini path if it exists; else fallback path (may or may not exist)."""
        cwd_path = os.path.join(os.getcwd(), 'Data', 'CAT', 'Advice.ini')
        if os.path.isfile(cwd_path):
            return cwd_path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, 'Data', 'CAT', 'Advice.ini')

    def _candidate_advice_paths(self):
        """Return candidate INI paths (both Advice.ini and Advice tips.ini) in CWD and script dir."""
        paths = []
        # CWD variants
        paths.append(os.path.join(os.getcwd(), 'Data', 'CAT', 'Advice.ini'))
        paths.append(os.path.join(os.getcwd(), 'Data', 'CAT', 'Advice tips.ini'))
        # Script dir variants
        script_dir = os.path.dirname(os.path.abspath(__file__))
        paths.append(os.path.join(script_dir, 'Data', 'CAT', 'Advice.ini'))
        paths.append(os.path.join(script_dir, 'Data', 'CAT', 'Advice tips.ini'))
        return paths

    def read_advices(self):
        advices = []
        # Aggregate from all candidate paths
        for path in self._candidate_advice_paths():
            if not os.path.isfile(path):
                continue
            current = []
            # Try parsing as INI first (robust settings)
            config = configparser.ConfigParser(strict=False)
            try:
                config.read(path, encoding='utf-8-sig')
                if config.has_section('Advice'):
                    for _, val in config.items('Advice'):
                        text = (val or '').strip()
                        if text:
                            current.append(text)
                else:
                    for section in config.sections():
                        for _, val in config.items(section):
                            text = (val or '').strip()
                            if text and not text.startswith('['):
                                current.append(text)
                    for _, val in config.defaults().items():
                        text = (val or '').strip()
                        if text:
                            current.append(text)
            except Exception:
                current = []

            # Fallback: treat file as plain text list if INI yielded nothing
            if not current:
                try:
                    with open(path, 'r', encoding='utf-8-sig') as f:
                        for line in f:
                            s = line.strip()
                            if not s:
                                continue
                            if s.startswith(';') or s.startswith('#') or s.startswith('['):
                                continue
                            if '=' in s:
                                _, rhs = s.split('=', 1)
                                rhs = rhs.strip()
                                if rhs:
                                    current.append(rhs)
                            else:
                                current.append(s)
                except Exception:
                    pass

            advices.extend(current)

        return advices

    def show_random_advice(self):
        advices = self.read_advices()
        if advices:
            txt = random.choice(advices)
            # Convert Markdown bold and italics to HTML
            try:
                # Bold: **text** -> <b>text</b>
                txt = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", txt)
                # Italic: *text* -> colored italic with configurable color (avoid matching **)
                italic_color = '#7bd88f'  # soft green
                txt = re.sub(
                    r"(?<!\*)\*([^*]+)\*(?!\*)",
                    lambda m: f"<i><span style=\"color:{italic_color}\">{m.group(1)}</span></i>",
                    txt,
                )
            except Exception:
                pass
            # Convert basic markdown links [text](url) to HTML anchors
            try:
                txt = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', txt)
            except Exception:
                pass
            # Support both literal and double-escaped newline sequences as HTML line breaks
            # 1) Normalize real Windows CRLF to LF
            txt = txt.replace("\r\n", "\n")
            # 2) Convert double-escaped CRLF ("\\r\\n") to LF
            txt = txt.replace("\\r\\n", "\n")
            # 3) Convert double-escaped "\\n" to LF
            txt = txt.replace("\\\\n", "\n")
            # 4) Convert single-escaped "\n" to LF
            txt = txt.replace("\\n", "\n")
            # 5) Finally convert LF to <br> for RichText QLabel
            txt = txt.replace("\n", "<br>")
            self.advice_label.setText(txt)
            # Recompute overlay geometry after text updates
            self.position_advice_box()
            self.ensure_image_on_top()
        else:
            paths = self._candidate_advice_paths()
            # Debug print to console for troubleshooting path issues
            try:
                print("[TipsTab] No advice found. Candidates:")
                for p in paths:
                    print(" -", p, "exists=" , os.path.isfile(p))
            except Exception:
                pass
            msg_lines = ["No advice found. Tried:"]
            for p in paths:
                exists = os.path.isfile(p)
                msg_lines.append(f"- {p} (exists: {'yes' if exists else 'no'})")
            self.advice_label.setText("<br>".join(msg_lines))

    def refresh(self):
        self.show_random_cat()
        self.show_random_advice()

    def ensure_image_on_top(self):
        """Ensure the advice overlay is on top to allow hyperlink clicks; image stays behind.
        """
        try:
            # Put the bottom image container under the advice overlay
            self.bottom_box.stackUnder(self.advice_box)
            # Raise the advice overlay
            self.advice_box.raise_()
        except Exception:
            pass

    def position_advice_box(self):
        """Position the overlay advice box at the configured top-left offset with a size
        that fits the label's content width and height, without affecting layout.
        """
        try:
            left = getattr(self, '_advice_offset_left', 56)
            top = getattr(self, '_advice_offset_top', 240)
            # Use the fixed width and content-based height
            w = self.advice_label.width() or self.advice_label.sizeHint().width() or 640
            # Ensure width equals the fixed width we set
            try:
                fixed_w = self.advice_label.maximumWidth()
                if fixed_w and fixed_w > 0:
                    w = fixed_w
                else:
                    w = 640
            except Exception:
                w = 640
            content_h = self.advice_label.sizeHint().height()
            h = max(150, content_h)
            self.advice_box.setGeometry(left, top, w, h)
        except Exception:
            pass

    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass
        self.position_advice_box()
        self.ensure_image_on_top()

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        self.position_advice_box()
        self.ensure_image_on_top()

# --- New Tab: JSON File Editor ---
class JsonFileEditorTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.json_path = self.get_json_path()
        self.setup_ui()

    def get_json_path(self):
        # Dynamically get the user's home directory and build the JSON file path
        home_dir = os.path.expanduser("~")
        json_path = os.path.join(home_dir, "AppData", "Local", "NVIDIA Corporation", "NVIDIA App", "NvBackend", "ApplicationStorage.json")
        return json_path

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.path_label = QLabel(f"JSON File Path:\n{self.json_path}")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.load_button = QPushButton("Load JSON File")
        self.load_button.clicked.connect(self.load_json)
        layout.addWidget(self.load_button)

        self.json_text_edit = QTextEdit()
        self.json_text_edit.setReadOnly(False)
        self.json_text_edit.setStyleSheet("""
            background-color: rgba(53, 53, 53, 180);
            color: white;
            border: 1px solid #454545;
            padding: 6px;
            border-radius: 4px;
            font-size: 14px;
            font-family: Consolas, monospace;
        """)
        layout.addWidget(self.json_text_edit)

        self.save_button = QPushButton("Save JSON File")
        self.save_button.clicked.connect(self.save_json)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

    def load_json(self):
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.json_text_edit.setPlainText(content)
            self.parent.statusBar.showMessage("JSON file loaded successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load JSON file:\n{e}")
            self.parent.statusBar.showMessage("Failed to load JSON file.")

    def save_json(self):
        try:
            content = self.json_text_edit.toPlainText()
            # Validate JSON before saving
            json.loads(content)
            with open(self.json_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.parent.statusBar.showMessage("JSON file saved successfully.")
        except json.JSONDecodeError as jde:
            QMessageBox.warning(self, "Invalid JSON", f"Cannot save. JSON is invalid:\n{jde}")
            self.parent.statusBar.showMessage("Save failed: Invalid JSON.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save JSON file:\n{e}")
            self.parent.statusBar.showMessage("Failed to save JSON file.")

class EjemploVentanaPyQt(QMainWindow):
    """Main window."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle("NVIDIA DLSS Enabler Helper App")
        # --- MODIFICACIÓN: Aumentar el tamaño de la ventana principal ---
        self.setGeometry(100, 100, 1100, 800)  # Dimensiones (X, Y, Ancho, Alto)
        # --- FIN MODIFICACIÓN ---
        # --- NUEVO: Establecer el ícono de la ventana ---
        self.set_window_icon(os.path.join('Data', 'ICON', 'log.ico'))
        # --- FIN NUEVO ---
        self.set_dark_theme()
        self.title_bar = CustomTitleBar(self)
        
        # --- MODIFICACIÓN: Crear el widget de degradado como widget central ---
        self.gradient_widget = GradientWidget()
        # Establecer un estilo básico sin fondo para no interferir con el pintado
        self.gradient_widget.setStyleSheet("border: none;")
        self.setCentralWidget(self.gradient_widget)

        # Crear el layout principal dentro del widget de degradado
        self.main_layout = QVBoxLayout(self.gradient_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Agregar la barra de título al layout del degradado
        self.main_layout.addWidget(self.title_bar)

        # Crear el widget que contendrá las pestañas
        self.content_container = QWidget()
        # Hacer que el contenedor de contenido tenga un fondo transparente
        self.content_container.setStyleSheet("background-color: transparent; border: none;")
        self.main_layout.addWidget(self.content_container)
        
        # El layout del contenido principal va dentro de content_container
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(1, 1, 1, 1)
        self.content_layout.setSpacing(0)
        
        # El widget de contenido real
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: transparent;")
        self.content_layout.addWidget(self.content_widget)
        # --- FIN MODIFICACIÓN ---
        
        self.init_ui()

    # --- FUNCIÓN: Establecer ícono de ventana ---
    def set_window_icon(self, icon_path):
        """Establece el ícono de la ventana si el archivo existe."""
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)
            # Actualizar también el ícono en la barra de título personalizada
            if hasattr(self, 'title_bar') and hasattr(self.title_bar, 'icon_label'):
                 pixmap = QPixmap(icon_path)
                 if not pixmap.isNull():
                     scaled_pixmap = pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation) # Tamaño ajustado
                     self.title_bar.icon_label.setPixmap(scaled_pixmap)
        else:
            print(f"Warning: Icon file '{icon_path}' not found.")

    # --- FIN FUNCIÓN ---

    def set_dark_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(37, 37, 37))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        QApplication.setPalette(dark_palette)
        QApplication.setStyle("Fusion")
        self.setStyleSheet("""
            QMainWindow {
                background-color: transparent; /* Fondo transparente para la ventana principal */
                border: 1px solid #454545;
            }
            QToolTip {
                color: white;
                background-color: #353535;
                border: 1px solid #454545;
                padding: 2px;
                font-size: 14px; /* Fuente más grande */
            }
            QMenuBar {
                background-color: #252525;
                color: white;
                font-size: 14px; /* Fuente más grande */
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 6px 12px;
            }
            QMenuBar::item:selected {
                background-color: #353535;
            }
            QMenu {
                background-color: #353535;
                color: white;
                border: 1px solid #454545;
                font-size: 14px; /* Fuente más grande */
            }
            QMenu::item {
                padding: 6px 22px;
            }
            QMenu::item:selected {
                background-color: #454545;
            }
            QStatusBar {
                background-color: rgba(37, 37, 37, 230); /* Fondo con algo de transparencia */
                color: white;
                font-size: 14px; /* Fuente más grande */
                border-top: 1px solid #454545;
            }
        """)

    def restart_app(self):
        """Restart the application by launching a new process of the same script and quitting this one."""
        try:
            python = sys.executable
            script = os.path.abspath(sys.argv[0])
            args = sys.argv[1:]
            # Try starting a detached process via QProcess
            started = QProcess.startDetached(python, [script] + args)
            if not started:
                # Fallback 1: use os.startfile for .pyw on Windows
                try:
                    os.startfile(script)  # type: ignore[attr-defined]
                    started = True
                except Exception:
                    started = False
            if not started:
                # Fallback 2: subprocess as last resort
                try:
                    import subprocess
                    subprocess.Popen([python, script] + args, close_fds=True)
                    started = True
                except Exception:
                    started = False
            if started:
                QApplication.quit()
            else:
                raise RuntimeError("Unable to launch new process")
        except Exception as e:
            try:
                QMessageBox.critical(self, "Restart failed", f"Could not restart the app.\n{e}")
            except Exception:
                pass

    def init_ui(self):
        main_layout = QVBoxLayout(self.content_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        # self.setup_menu() # Ya no se necesita el menú tradicional
        # main_layout.addWidget(self.menuBar()) # Ya no se agrega la barra de menú tradicional

        tabs_container = QWidget()
        tabs_container.setStyleSheet("background-color: transparent;")
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(6, 6, 6, 6)
        tabs_layout.setSpacing(6)
        tabs_container.setMinimumWidth(950) # Ancho mínimo aumentado
        self.tabs = QTabWidget()
        tab_bar = self.tabs.tabBar()
        tab_bar.setExpanding(False) # Clave: Evita que las pestañas se expandan
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #454545;
                background: transparent; /* Fondo transparente para el panel de pestañas */
            }
            QTabBar::tab {
                background: rgba(53, 53, 53, 200); /* Fondo con transparencia */
                color: white;
                /* padding: 10px 28px; */ /* Original - Ancho fijo incorrecto */
                padding: 8px 12px; /* Nuevo: Menos padding horizontal, se adapta mejor al texto */
                border: 1px solid #454545;
                border-bottom: none;
                font-size: 12px; /* Fuente de pestañas MAS PEQUENA */
                /* min-width y height pueden ayudar a tener un tamaño base razonable */
                min-width: 8ex; /* Ancho mínimo basado en caracteres */
                /* height: 24px; */ /* Altura fija si es necesario */
            }
            QTabBar::tab:selected {
                background: rgba(69, 69, 69, 220); /* Fondo seleccionado con transparencia */
            }
            QTabBar::tab:hover {
                background: rgba(69, 69, 69, 220); /* Hover con transparencia */
            }
        """)
        tabs_layout.addWidget(self.tabs)
        main_layout.addWidget(tabs_container)

        self.tab_outfits = OutfitManagerTab(self)
        self.tabs.addTab(self.tab_outfits, "Manager")
        self.tab_restore = JsonRestoreTab(self)
        self.tabs.addTab(self.tab_restore, "JSON Restore")


        # New Tips tab (last)
        self.tab_tips = TipsTab(self)
        self.tabs.addTab(self.tab_tips, "Tips")

        # JSON File Editor tab removed/hidden by request
        # self.tab_json_editor = JsonFileEditorTab(self)
        # self.tabs.addTab(self.tab_json_editor, "JSON File Editor")

        # Refresh cat each time Tips tab is selected
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Ensure RO button synchronizes once after tabs are constructed
        try:
            self.tab_outfits.sync_read_only_button_from_file()
            QTimer.singleShot(0, self.tab_outfits.sync_read_only_button_from_file)
        except Exception:
            pass

        self.statusBar = QStatusBar()
        # Usar fondo con transparencia para la barra de estado
        self.statusBar.setStyleSheet("background-color: rgba(37, 37, 37, 230); color: white; font-size: 14px; border-top: 1px solid #454545;")
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready - NVIDIA DLSS Enabler App")

    # --- NUEVA FUNCIÓN: show_about_dialog ---
    def show_about_dialog(self):
        """Muestra el diálogo 'About' con la información personalizada."""
        about_dialog = AboutDialog(self)
        about_dialog.exec_()
    # --- FIN NUEVA FUNCIÓN ---

    def on_tab_changed(self, index):
        """When switching tabs, refresh the cat if Tips tab is active."""
        try:
            if self.tabs.widget(index) is self.tab_tips:
                self.tab_tips.refresh()
        except Exception:
            pass

    def open_web_interface(self):
        """Open the web interface URL in the default browser."""
        # Prefer parenting dialogs to the currently active window (e.g., AboutDialog) for proper modality
        try:
            parent_win = QApplication.activeWindow() or self
        except Exception:
            parent_win = self
        try:
            # Informational note (WIP)
            QMessageBox.information(
                parent_win,
                "Website (WIP)",
                "The documentation website is under construction. Some sections may be empty or change frequently."
            )
        except Exception:
            pass
        try:
            raw_url = "https://john95ac.github.io/website-documents-John95AC/index.html"
            url = QUrl(raw_url)
            if not url.isValid():
                url = QUrl.fromUserInput(raw_url)
            if not QDesktopServices.openUrl(url):
                QMessageBox.warning(parent_win, "Error", "Could not open web browser to access the documentation.")
        except Exception as e:
            try:
                QMessageBox.warning(parent_win, "Error", f"Failed to open the documentation website.\n{e}")
            except Exception:
                pass

def main():
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        window = EjemploVentanaPyQt()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
