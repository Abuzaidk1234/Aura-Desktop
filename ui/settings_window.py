from ui.components import enable_native_mica
import json
import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
    QSpinBox, QDoubleSpinBox, QFormLayout, QScrollArea,
    QCheckBox, QApplication, QLabel, QTabWidget
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer
import winreg
import subprocess
from config import CONFIG, save_config, DEFAULT_CONFIG
import socket

class SettingsWindow(QWidget):
    def __init__(self, is_standalone=False):
        super().__init__()
        self.is_standalone = is_standalone
        self.setWindowTitle("AURA Settings")
        self.setMinimumSize(450, 500)
        self.resize(550, 650)
        self.winId()
        enable_native_mica(self.winId(), acrylic=False)
        self.setObjectName("MainWindow")

        icon_path = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "aura_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            # Force Windows taskbar to use this icon instead of python.exe
            import ctypes
            try:
                hwnd = int(self.winId())
                hicon = ctypes.windll.user32.LoadImageW(0, icon_path, 1, 0, 0, 0x0010)
                if hicon:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon) # ICON_BIG
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon) # ICON_SMALL
            except Exception:
                pass
        
        # AURA Aesthetic Styling - True Frosted Glass
        self.setStyleSheet("""
            QWidget#MainWindow {
                background: transparent;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                background-color: transparent;
            }
            QWidget#HeaderWidget {
                background-color: rgba(0, 0, 0, 80);
                border-bottom: 1px solid rgba(255, 255, 255, 20);
            }
            QLabel {
                font-weight: bold;
                color: #ffffff;
                background-color: transparent;
            }
            QLabel#HeaderText {
                font-size: 20px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 6px;
                padding: 5px;
                color: #ffffff;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #3b82f6;
                background-color: rgba(255, 255, 255, 30);
            }
            QPushButton#SaveBtn {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton#SaveBtn:hover {
                background-color: #2563eb;
            }
            QPushButton#ResetBtn {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 20);
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton#ResetBtn:hover {
                background-color: rgba(255, 255, 255, 20);
            }
            QPushButton#LaunchBtn {
                background-color: rgba(30, 160, 90, 200);
                border: 1px solid rgba(50, 180, 110, 220);
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton#LaunchBtn:hover {
                background-color: rgba(30, 180, 100, 255);
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 20);
                background: rgba(0, 0, 0, 40);
                border-radius: 6px;
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 10);
                color: #ffffff;
                padding: 8px 15px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: rgba(59, 130, 246, 180);
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background: rgba(255, 255, 255, 20);
            }

        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.network_label = QLabel("Checking Voice Engine Status...")
        self.network_label.setObjectName("NetworkStatus")
        self.network_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.network_label)
        
        self.net_timer = QTimer(self)
        self.net_timer.timeout.connect(self.update_network_status)
        self.net_timer.start(3000)
        self.update_network_status()

        # Startup Option (Top Level)
        self.startup_checkbox = QCheckBox("Start AURA silently on Windows Startup")
        self.startup_checkbox.setChecked(self.check_startup())
        self.startup_checkbox.setStyleSheet("margin-left: 20px; margin-top: 10px; margin-bottom: 5px; font-weight: bold; color: #60a5fa;")
        layout.addWidget(self.startup_checkbox)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setContentsMargins(20, 10, 20, 10)
        layout.addWidget(self.tabs)

        # --- TAB 1: Voice & Audio ---
        tab_voice = QWidget()
        voice_layout = QFormLayout(tab_voice)
        voice_layout.setContentsMargins(20, 20, 20, 20)
        voice_layout.setSpacing(15)

        self.wake_words_input = QLineEdit()
        voice_layout.addRow("Wake Words (comma separated):", self.wake_words_input)

        self.tts_voice_input = QLineEdit()
        voice_layout.addRow("TTS Voice:", self.tts_voice_input)

        self.tts_rate_input = QLineEdit()
        voice_layout.addRow("Speech Rate:", self.tts_rate_input)

        self.energy_spin = QSpinBox()
        self.energy_spin.setRange(50, 4000)
        voice_layout.addRow("Mic Sensitivity:", self.energy_spin)

        self.pause_spin = QDoubleSpinBox()
        self.pause_spin.setRange(0.5, 5.0)
        self.pause_spin.setSingleStep(0.1)
        voice_layout.addRow("Mic Pause Timeout:", self.pause_spin)
        
        self.tabs.addTab(tab_voice, "Voice & Audio")

        # --- TAB 2: Positioning ---
        tab_pos = QWidget()
        pos_layout = QFormLayout(tab_pos)
        pos_layout.setContentsMargins(20, 20, 20, 20)
        pos_layout.setSpacing(15)

        self.avatar_left_margin = QSpinBox()
        self.avatar_left_margin.setRange(0, 1000)
        pos_layout.addRow("Avatar Left Margin:", self.avatar_left_margin)

        self.avatar_right_margin = QSpinBox()
        self.avatar_right_margin.setRange(0, 1000)
        pos_layout.addRow("Avatar Right Margin:", self.avatar_right_margin)

        self.avatar_bottom_margin = QSpinBox()
        self.avatar_bottom_margin.setRange(0, 1000)
        pos_layout.addRow("Avatar Bottom Margin:", self.avatar_bottom_margin)
        
        self.tabs.addTab(tab_pos, "Positioning")

        # --- TAB 3: Behavior ---
        tab_beh = QWidget()
        beh_layout = QFormLayout(tab_beh)
        beh_layout.setContentsMargins(20, 20, 20, 20)
        beh_layout.setSpacing(15)

        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.0, 10.0)
        self.cooldown_spin.setSingleStep(0.5)
        beh_layout.addRow("Command Cooldown:", self.cooldown_spin)
        
        self.idle_timeout_spin = QSpinBox()
        self.idle_timeout_spin.setRange(1, 60)
        beh_layout.addRow("Idle Timeout (min):", self.idle_timeout_spin)
        
        self.tabs.addTab(tab_beh, "Behavior")

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(20, 10, 20, 20)
        
        reset_btn = QPushButton("Restore Defaults")
        reset_btn.setObjectName("ResetBtn")
        reset_btn.clicked.connect(self.restore_defaults)
        
        save_btn = QPushButton("Save && Apply")
        save_btn.setObjectName("SaveBtn")
        save_btn.clicked.connect(self.save_settings)
        
        btn_layout.addWidget(reset_btn)
        btn_layout.addWidget(save_btn)
        
        if self.is_standalone:
            launch_btn = QPushButton("Launch AURA")
            launch_btn.setObjectName("LaunchBtn")
            launch_btn.clicked.connect(self.launch_aura)
            btn_layout.addWidget(launch_btn)

        layout.addLayout(btn_layout)

        self.load_values(CONFIG)

    def update_network_status(self):
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=1.0)
            self.network_label.setText("🟢 CLOUD VOICE ENGINE ACTIVE (Online)")
            self.network_label.setStyleSheet("padding: 10px; font-weight: bold; font-size: 13px; color: #4ade80; background: rgba(20, 40, 20, 150); border: 1px solid #22c55e; border-radius: 6px; margin: 15px 20px 0px 20px;")
        except OSError:
            self.network_label.setText("🔴 LOCAL VOICE ENGINE ACTIVE (Offline Fallback)")
            self.network_label.setStyleSheet("padding: 10px; font-weight: bold; font-size: 13px; color: #f87171; background: rgba(60, 20, 20, 150); border: 1px solid #ef4444; border-radius: 6px; margin: 15px 20px 0px 20px;")

    def load_values(self, conf):
        self.wake_words_input.setText(", ".join(conf.get("wake_words", ["aura"])))
        self.tts_voice_input.setText(conf.get("tts_voice", "en-US-ChristopherNeural"))
        self.tts_rate_input.setText(conf.get("tts_rate", "+15%"))
        self.energy_spin.setValue(conf.get("energy_threshold", 300))
        self.pause_spin.setValue(conf.get("mic_pause_threshold", 1.5))
        self.cooldown_spin.setValue(conf.get("debounce_cooldown_seconds", 2.0))
        self.idle_timeout_spin.setValue(conf.get("idle_timeout_minutes", 5))
        self.avatar_left_margin.setValue(conf.get("avatar_left_margin", 20))
        self.avatar_right_margin.setValue(conf.get("avatar_tray_safe_right_margin", 270))
        self.avatar_bottom_margin.setValue(conf.get("avatar_bottom_margin", 20))

    def restore_defaults(self):
        self.load_values(DEFAULT_CONFIG)

    def save_settings(self):
        wake_words_raw = self.wake_words_input.text()
        wake_words = [w.strip() for w in wake_words_raw.split(",") if w.strip()]
        if "aura" not in wake_words:
            wake_words.insert(0, "aura")

        new_config = {
            "wake_words": wake_words,
            "tts_voice": self.tts_voice_input.text().strip(),
            "tts_rate": self.tts_rate_input.text().strip(),
            "energy_threshold": self.energy_spin.value(),
            "mic_pause_threshold": self.pause_spin.value(),
            "debounce_cooldown_seconds": self.cooldown_spin.value(),
            "idle_timeout_minutes": self.idle_timeout_spin.value(),
            "avatar_left_margin": self.avatar_left_margin.value(),
            "avatar_tray_safe_right_margin": self.avatar_right_margin.value(),
            "avatar_bottom_margin": self.avatar_bottom_margin.value()
        }

        save_config(new_config)
        self.set_startup(self.startup_checkbox.isChecked())

    def check_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "AURA")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False

    def set_startup(self, enable):
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        
        if getattr(sys, 'frozen', False):
            exe_path = f'"{sys.executable}" --hidden'
        else:
            pythonw = sys.executable.replace("python.exe", "pythonw.exe")
            script_path = os.path.abspath(sys.argv[0])
            exe_path = f'"{pythonw}" "{script_path}" --hidden'

        if enable:
            winreg.SetValueEx(key, "AURA", 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, "AURA")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)

    def launch_aura(self):
        self.save_settings()
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "--hidden"])
        else:
            subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0]), "--hidden"])
        self.close()
        QApplication.quit()
