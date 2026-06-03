import ctypes
import os
from ctypes import POINTER, Structure, c_int, sizeof

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ACCENT_POLICY(Structure):
    _fields_ = [
        ("AccentState", c_int),
        ("AccentFlags", c_int),
        ("GradientColor", c_int),
        ("AnimationId", c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(Structure):
    _fields_ = [
        ("Attribute", c_int),
        ("Data", POINTER(ACCENT_POLICY)),
        ("SizeOfData", c_int),
    ]


def enable_native_mica(hwnd, acrylic=True):
    try:
        import ctypes

        # Force rounded corners for frameless windows
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        corner_val = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner_val),
            ctypes.sizeof(corner_val),
        )

        # Enable immersive dark mode for dark title bar text
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )

        # Set Backdrop Type to Acrylic (3) or Mica (2)
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        backdrop_val = 3 if acrylic else 2
        value2 = ctypes.c_int(backdrop_val)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(hwnd),
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(value2),
            ctypes.sizeof(value2),
        )

        # Extend frame into client area so the backdrop fills the window
        class MARGINS(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int),
            ]

        margins = MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
            int(hwnd), ctypes.byref(margins)
        )
    except Exception as e:
        print(f"Failed to enable native mica: {e}")


def enable_blur(hwnd, acrylic=False):
    try:
        accent = ACCENT_POLICY()
        if acrylic:
            accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.GradientColor = 0x01000000
        else:
            accent.AccentState = 3  # ACCENT_ENABLE_BLURBEHIND
        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19
        data.SizeOfData = sizeof(accent)
        data.Data = ctypes.pointer(accent)
        ctypes.windll.user32.SetWindowCompositionAttribute(
            int(hwnd), ctypes.pointer(data)
        )

        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            value2 = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd),
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(value2),
                ctypes.sizeof(value2),
            )
        except Exception:
            pass
    except Exception as e:
        print(f"Blur failed: {e}")


class DragFilter(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.dragPos = None

    def eventFilter(self, obj, event):
        try:
            if (
                event.type() == event.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                if not getattr(self.window, "ghost_mode", False):
                    self.dragPos = event.globalPosition().toPoint()
                    return True
            elif event.type() == event.Type.MouseMove and self.dragPos is not None:
                if not getattr(self.window, "ghost_mode", False):
                    self.window.move(
                        self.window.pos()
                        + event.globalPosition().toPoint()
                        - self.dragPos
                    )
                    self.dragPos = event.globalPosition().toPoint()
                    return True
            elif event.type() == event.Type.MouseButtonRelease:
                if not getattr(self.window, "ghost_mode", False):
                    self.dragPos = None
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


class PomodoroWindow(QWidget):
    def __init__(self, comm, main_app=None):
        super().__init__()
        self.comm = comm
        self.main_app = main_app

        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.winId()
        enable_blur(self.winId(), acrylic=True)

        # We exclusively use Qt's native translucency for perfect 16px corners without Windows DWM blur bleeding

        self.is_focus = True
        self.time_left = 25 * 60  # 25 minutes

        main_wrapper_layout = QVBoxLayout(self)
        main_wrapper_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("container")
        main_wrapper_layout.addWidget(self.container)

        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(15, 10, 15, 15)

        self.setStyleSheet("""
            QFrame#container {
                background-color: rgba(20, 20, 25, 60);
                border-radius: 0px;
                border: 1px solid rgba(255, 255, 255, 30);
                color: white;
            }
            QLabel#timerLabel {
                font-size: 32px;
                font-weight: bold;
                border: none;
                background: transparent;
            }
            QLabel#statusLabel {
                font-size: 12px;
                font-weight: bold;
                color: rgba(255, 255, 255, 0.5);
                border: none;
                background: transparent;
                letter-spacing: 2px;
            }
            QPushButton#closeBtn {
                font-size: 14px;
                font-weight: bold;
                color: rgba(255, 255, 255, 0.5);
                border: none;
                background: transparent;
            }
            QPushButton#closeBtn:hover {
                color: rgba(255, 255, 255, 1.0);
            }
        """)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("FOCUS")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.close_btn = QPushButton("X")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close_pomodoro)

        top_layout.addWidget(self.status_label)
        top_layout.addStretch()
        top_layout.addWidget(self.close_btn)

        self.timer_label = QLabel(self.format_time(self.time_left))
        self.timer_label.setObjectName("timerLabel")
        self.timer_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout.addLayout(top_layout)
        self.layout.addWidget(self.timer_label)

        self.dragPos = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.resize(180, 100)

    def format_time(self, seconds):
        m = seconds // 60
        s = seconds % 60
        return f"{m:02d}:{s:02d}"

    def tick(self):
        self.time_left -= 1
        if self.time_left <= 0:
            self.switch_state()
        else:
            self.timer_label.setText(self.format_time(self.time_left))

    def switch_state(self):
        if self.is_focus:
            self.is_focus = False
            self.time_left = 5 * 60
            self.status_label.setText("BREAK")
            msg = "Your 25 minute focus session has ended. Take a 5 minute break!"
        else:
            self.is_focus = True
            self.time_left = 25 * 60
            self.status_label.setText("FOCUS")
            msg = "Break is over! Let's get back to your 25 minute focus session."

        self.timer_label.setText(self.format_time(self.time_left))

        if self.comm:
            self.comm.change_state.emit("speaking")
            self.comm.show_subtitle.emit(msg)
        if self.main_app:
            self.main_app.speak(msg, return_to_idle=True)

    def close_pomodoro(self):
        self.timer.stop()
        if self.comm:
            self.comm.change_state.emit("speaking")
            self.comm.show_subtitle.emit("Pomodoro cancelled.")
        if self.main_app:
            self.main_app.speak("Pomodoro cancelled.", return_to_idle=True)
        self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragPos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.dragPos)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragPos = None
        event.accept()


class ShutdownOSDWindow(QWidget):
    def __init__(self, buffer_time, main_app=None, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        # Window Flags: Frameless, transparent background, always on top, centered
        # Let it be a standard window so Mica For Everyone can perfectly blur it
        self.setWindowTitle(" ")
        self.setObjectName("MainWindow")
        self.setStyleSheet("QWidget#MainWindow { background: transparent; }")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window)
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setFixedSize(600, 450)
        
        # Enable OS-level blur before showing
        self.winId()
        enable_native_mica(self.winId(), acrylic=False)

        # Center the window on the screen
        screen_geom = self.screen().geometry()
        x = (screen_geom.width() - 600) // 2
        y = (screen_geom.height() - 450) // 2
        self.move(x, y)
        self.show()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Styling (Frosted Cyberpunk Aesthetic)
        self.container = QFrame()
        self.container.setFixedSize(600, 450)
        self.container.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)

        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self.container_layout.setContentsMargins(40, 60, 40, 50)
        self.container_layout.setSpacing(30)

        # Time Label with Circle
        self.time_label = QLabel(str(buffer_time))
        self.time_label.setFixedSize(140, 140)
        self.time_label.setStyleSheet("""
            QLabel {
                color: white;
                font-family: 'Segoe UI', -apple-system;
                font-size: 38px;
                font-weight: 400;
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 150);
                border-radius: 70px;
            }
        """)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        time_layout = QHBoxLayout()
        time_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_layout.addWidget(self.time_label)
        self.container_layout.addLayout(time_layout)

        # PC SHUTTING DOWN text
        self.warning_label = QLabel("PC SHUTTING DOWN")
        self.warning_label.setStyleSheet("""
            QLabel {
                color: white;
                font-family: 'Segoe UI', -apple-system;
                font-size: 28px;
                font-weight: 400;
                letter-spacing: 1px;
                border: none;
                background: transparent;
            }
        """)
        self.warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.container_layout.addWidget(self.warning_label)

        # Push buttons down a bit
        self.container_layout.addSpacing(20)

        # Buttons Layout
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(40)
        self.btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Cancel Button
        self.cancel_btn = QPushButton("CANCEL")
        self.cancel_btn.setFixedSize(180, 55)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(130, 170, 110, 160);
                border: 1px solid rgba(150, 200, 120, 200);
                color: black;
                border-radius: 27px;
                font-family: 'Segoe UI', -apple-system;
                font-weight: 400;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: rgba(130, 170, 110, 200);
            }
        """)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.abort_shutdown)

        # OK Button -> Shut down now
        self.ok_btn = QPushButton("Shut down now")
        self.ok_btn.setFixedSize(180, 55)
        self.ok_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 170, 90, 160);
                border: 1px solid rgba(220, 190, 100, 200);
                color: black;
                border-radius: 27px;
                font-family: 'Segoe UI', -apple-system;
                font-weight: 400;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: rgba(200, 170, 90, 200);
            }
        """)
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.clicked.connect(self.accept_shutdown)

        self.btn_layout.addWidget(self.cancel_btn)
        self.btn_layout.addWidget(self.ok_btn)

        self.container_layout.addLayout(self.btn_layout)
        self.layout.addWidget(self.container)

        self.time_left = buffer_time
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def abort_shutdown(self):
        self.timer.stop()  # CRITICAL FIX: STOP THE TIMER
        import subprocess

        try:
            subprocess.run("shutdown /a", shell=True, capture_output=True)
        except Exception:
            pass

        if self.main_app:
            self.main_app.comm.show_subtitle.emit(
                "System shutdown aborted. Standing by."
            )
            self.main_app.speak(
                "System shutdown aborted. Standing by.", return_to_idle=True
            )
            self.main_app.osd = None

        self.close()

    def closeEvent(self, event):
        # If the user clicks the "X" on the title bar or presses Alt+F4, abort the shutdown!
        if self.timer.isActive():
            self.abort_shutdown()
        event.accept()

    def accept_shutdown(self):
        import subprocess

        subprocess.Popen("shutdown /s /t 0", shell=True)
        if self.main_app:
            self.main_app.osd = None
        self.close()

    def tick(self):
        self.time_left -= 1
        if self.time_left <= 0:
            self.accept_shutdown()
        else:
            self.time_label.setText(str(self.time_left))
