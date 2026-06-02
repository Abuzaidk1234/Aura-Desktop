import asyncio
import ctypes
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
import winsound
from datetime import datetime

import edge_tts
import keyboard
import ollama
import psutil
import pyperclip
import speech_recognition as sr

# --- Configuration and Core Imports ---
from config import CONFIG, CONFIG_FILE, load_config
from core.signals import Communicate
from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QCursor
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from ui.components import DragFilter, PomodoroWindow, ShutdownOSDWindow


# --- The Main Application ---
class ModernClippy(QWidget):
    def __init__(self):
        """
        Initializes the ModernClippy application overlay, setting up UI, IPC signals, and background daemon threads.
        """
        super().__init__()

        self.cleanup_old_audio_files()

        self.is_interactive = False
        self.force_wake = False
        self.is_hidden = False
        self.is_muted = False
        self.is_speaking = False
        self.is_animating = False
        self.visible_y = 0
        self.is_alive = True
        self.pending_move_x = None
        self.last_command_time = 0
        self.last_command_text = ""
        self.raw_spoken_text = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.width, self.height = 350, 450
        self.resize(self.width, self.height)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.browser = QWebEngineView()
        self.browser.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.browser.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.browser.setStyleSheet("background: transparent; border: none;")
        self.browser.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, "index.html")
        self.browser.setUrl(QUrl.fromLocalFile(html_path))
        self.browser.titleChanged.connect(self.handle_html_title_command)

        self.layout.addWidget(self.browser)

        self.drag_filter = DragFilter(self)
        for child in self.browser.findChildren(QObject):
            child.installEventFilter(self.drag_filter)

        self.setup_tray_icon()
        self.comm = Communicate()

        self.comm.toggle_click.connect(self.toggle_ghost_mode)
        self.comm.wake_up.connect(self.trigger_hotkey)
        self.comm.open_text_prompt.connect(self.show_text_input)
        self.comm.hide_avatar.connect(self.animate_hide)
        self.comm.show_avatar.connect(self.animate_show)
        self.comm.exit_app.connect(QApplication.instance().quit)
        self.comm.move_avatar.connect(self.animate_move)
        self.comm.change_state.connect(self.update_ui_state)
        self.comm.show_subtitle.connect(self.display_subtitle_text)
        self.comm.start_pomodoro.connect(self.launch_pomodoro)
        self.comm.initiate_shutdown.connect(self.spawn_shutdown_osd)

        self.rehook_hotkeys()
        self.position_in_corner()

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(800)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.on_animation_finished)

        # Start app caching thread silently
        self.app_cache = {}
        threading.Thread(target=self._build_app_cache, daemon=True).start()

        # Audio setup
        self.is_recording = False
        self.recognizer = sr.Recognizer()
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(CONFIG.get("idle_timeout_minutes", 5) * 60 * 1000)
        self.idle_timer.timeout.connect(self.trigger_idle_sleep)
        self.idle_timer.start()

        # Start the background unlock monitor thread to fix keyboard hooks dropping
        threading.Thread(target=self.monitor_unlocks, daemon=True).start()

        self.enforcer_timer = QTimer(self)
        self.enforcer_timer.setInterval(500)
        self.enforcer_timer.timeout.connect(self.enforce_visibility)
        self.enforcer_timer.start()

        self.start_audio_engine()
        # global mouse tracking
        self.mouse_timer = QTimer(self)
        self.mouse_timer.timeout.connect(self.send_mouse_to_js)
        self.mouse_timer.start(16)

    def send_mouse_to_js(self):
        """Gets global OS mouse coordinates with Dynamic Screen-Edge Mapping."""
        if self.is_hidden or self.is_animating:
            return

        pos = QCursor.pos()
        screen = QApplication.primaryScreen().geometry()

        # 1. Physical pixel location of the avatar's head
        avatar_head_x = self.x() + (self.width / 2)
        avatar_head_y = self.y() + (self.height / 3)

        # 2. DYNAMIC X-AXIS MAPPING
        # If mouse is left of him, map distance to the left screen edge (-1.0 to 0)
        # If right, map distance to the right screen edge (0 to +1.0)
        if pos.x() < avatar_head_x:
            norm_x = (pos.x() - avatar_head_x) / max(1, avatar_head_x)
        else:
            norm_x = (pos.x() - avatar_head_x) / max(1, screen.width() - avatar_head_x)

        # 3. DYNAMIC Y-AXIS MAPPING
        # If mouse is above him, map distance to the top screen edge (+1.0 to 0)
        if pos.y() < avatar_head_y:
            norm_y = (avatar_head_y - pos.y()) / max(1, avatar_head_y)
        else:
            norm_y = (avatar_head_y - pos.y()) / max(1, screen.height() - avatar_head_y)

        # 4. Clamp the values to be safe against multi-monitor boundaries
        norm_x = max(-1.0, min(1.0, norm_x))
        norm_y = max(-1.0, min(1.0, norm_y))

        # Send it directly to the browser view
        js_command = f"if (typeof updateGlobalMouse === 'function') {{ updateGlobalMouse({norm_x}, {norm_y}); }}"
        self.browser.page().runJavaScript(js_command)

    def enforce_visibility(self):
        if self.is_hidden or self.is_animating:
            return
        if self.isMinimized():
            self.showNormal()
        self.keep_inside_safe_area()
        self.raise_()

    def safe_position(self, side="right"):
        screen = QApplication.primaryScreen().availableGeometry()
        left_margin = CONFIG.get("avatar_left_margin", 20)
        right_margin = CONFIG.get("avatar_tray_safe_right_margin", 170)
        bottom_margin = CONFIG.get("avatar_bottom_margin", 20)

        if side == "left":
            x = screen.x() + left_margin
        else:
            x = screen.x() + screen.width() - self.width - right_margin

        y = screen.y() + screen.height() - self.height - bottom_margin
        return QPoint(max(screen.x() + left_margin, x), max(screen.y(), y))

    def keep_inside_safe_area(self):
        screen = QApplication.primaryScreen().availableGeometry()
        left_margin = CONFIG.get("avatar_left_margin", 20)
        right_margin = CONFIG.get("avatar_tray_safe_right_margin", 170)
        bottom_margin = CONFIG.get("avatar_bottom_margin", 20)

        min_x = screen.x() + left_margin
        max_x = screen.x() + screen.width() - self.width - right_margin
        min_y = screen.y()
        max_y = screen.y() + screen.height() - self.height - bottom_margin
        if max_x < min_x:
            max_x = min_x
        if max_y < min_y:
            max_y = min_y

        safe_x = min(max(self.x(), min_x), max_x)
        safe_y = min(max(self.y(), min_y), max_y)

        if self.x() != safe_x or self.y() != safe_y:
            self.move(safe_x, safe_y)
            self.visible_y = safe_y

    def cleanup_old_audio_files(self):
        for filename in os.listdir():
            if filename.startswith("temp_speech_") and filename.endswith(".mp3"):
                try:
                    os.remove(filename)
                except Exception:
                    pass

    def update_ui_state(self, state_name):
        self.browser.page().runJavaScript(
            f"if (typeof setClippyState === 'function') {{ setClippyState('{state_name}'); }}"
        )

    def display_subtitle_text(self, text):
        safe_text = text.replace('"', '\\"').replace("\n", " ")
        self.browser.page().runJavaScript(
            f"if (typeof showSubtitle === 'function') {{ showSubtitle(\"{safe_text}\"); }}"
        )

    def speak(self, text, return_to_idle=True):
        """
        Converts text to speech using Edge TTS in a non-blocking thread, synchronizing avatar lip-sync animations with audio playback.
        """
        if not text or not text.strip():
            print("⚠️ Skipped TTS: No text to speak.")
            if return_to_idle:
                self.comm.change_state.emit("idle")
            return

        if self.is_speaking:
            ctypes.windll.winmm.mciSendStringW("stop aura_audio", None, 0, None)
            ctypes.windll.winmm.mciSendStringW("close aura_audio", None, 0, None)
            self.is_speaking = False
            time.sleep(0.05)

        def tts_worker():
            self.is_speaking = True
            try:
                VOICE = CONFIG.get("tts_voice", "en-US-ChristopherNeural")
                RATE = CONFIG.get("tts_rate", "+15%")

                unique_id = uuid.uuid4().hex
                OUTPUT_FILE = os.path.abspath(f"temp_speech_{unique_id}.mp3")

                communicate = edge_tts.Communicate(text, VOICE, rate=RATE)

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(communicate.save(OUTPUT_FILE))

                ctypes.windll.winmm.mciSendStringW("close aura_audio", None, 0, None)
                ctypes.windll.winmm.mciSendStringW(
                    f'open "{OUTPUT_FILE}" alias aura_audio', None, 0, None
                )

                # Activate the visual pulse indicator prior to audio playback.
                self.comm.change_state.emit("speaking")

                ctypes.windll.winmm.mciSendStringW("play aura_audio", None, 0, None)

                while self.is_speaking:
                    buffer = ctypes.create_unicode_buffer(64)
                    ctypes.windll.winmm.mciSendStringW(
                        "status aura_audio mode", buffer, 64, None
                    )
                    if "playing" not in buffer.value.lower():
                        break
                    time.sleep(0.05)

            except Exception as e:
                print(f"❌ Neural TTS Error: {e}")
            finally:
                ctypes.windll.winmm.mciSendStringW("close aura_audio", None, 0, None)
                if os.path.exists(OUTPUT_FILE):
                    try:
                        os.remove(OUTPUT_FILE)
                    except Exception:
                        pass

                completed_naturally = self.is_speaking
                self.is_speaking = False

                if return_to_idle and completed_naturally:
                    self.comm.change_state.emit("idle")

        threading.Thread(target=tts_worker, daemon=True).start()

    def play_custom_sfx(self):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            sound_path = os.path.join(current_dir, "assets", "bye.mp3")
            if os.path.exists(sound_path):
                ctypes.windll.winmm.mciSendStringW("close pop_sfx", None, 0, None)
                ctypes.windll.winmm.mciSendStringW(
                    f'open "{sound_path}" alias pop_sfx', None, 0, None
                )
                ctypes.windll.winmm.mciSendStringW("play pop_sfx", None, 0, None)
        except Exception as e:
            print(f"❌ SFX Error: {e}")

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        )
        tray_menu = QMenu()

        toggle_action = tray_menu.addAction("Toggle Ghost Mode")
        toggle_action.triggered.connect(self.toggle_ghost_mode)

        self.mute_action = tray_menu.addAction("Mute Microphone (DND)")
        self.mute_action.setCheckable(True)
        self.mute_action.triggered.connect(self.toggle_mute_state)

        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Exit Assistant")
        quit_action.triggered.connect(QApplication.instance().quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def toggle_mute_state(self):
        self.is_muted = self.mute_action.isChecked()
        if self.is_muted:
            print("🔇 Privacy Mode Enabled: Microphone Suspended.")
            self.comm.change_state.emit("idle")
        else:
            print("🔊 Privacy Mode Disabled: Listening active.")

    def position_in_corner(self):
        position = self.safe_position("right")
        self.visible_y = position.y()
        self.move(position)

    def toggle_ghost_mode(self):
        self.is_interactive = not self.is_interactive
        if self.is_interactive:
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
            print("Avatar is now INTERACTABLE (Solid)")
        else:
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
            print("Avatar is now CLICK-THROUGH (Ghost)")
        self.show()

    def show_text_input(self):
        """Silently opens the HTML text box right over his head and forces keyboard focus."""
        # 1. Turn off ghost mode so it can accept input
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)

        # 2. Force Windows to bring the window to the front and activate keyboard inputs
        self.show()
        self.raise_()
        self.activateWindow()

        # 3. Force PyQt to route all incoming keystrokes directly into the browser element
        self.browser.setFocus()

        # 4. Trigger the JS function to display the frosted bar and focus the input field
        self.browser.page().runJavaScript(
            "if (typeof showTextInput === 'function') { showTextInput(); }"
        )

    def handle_html_title_command(self, title):
        """Catches the text command sent invisibly from the Javascript UI."""
        if title.startswith("CMD:"):
            command_text = title[4:]
            self.restore_ghost_state()

            print(f"\n[Text Command Detected] ⌨️ '{command_text}'")
            self.comm.show_avatar.emit()
            self.comm.change_state.emit("processing")

            # Send the text to the brain in a background thread so the UI doesn't freeze
            threading.Thread(
                target=self.execute_intent, args=(command_text,), daemon=True
            ).start()

        elif title == "CMD_END:":
            # This triggers if the user pressed Esc, clicked away, or hit Enter on an empty box
            self.restore_ghost_state()

    def restore_ghost_state(self):
        """Restores the window's click-through state if it was originally in Ghost mode."""
        if not self.is_interactive:
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
            self.show()

    def launch_pomodoro(self):
        if (
            hasattr(self, "pomodoro_widget")
            and self.pomodoro_widget
            and self.pomodoro_widget.isVisible()
        ):
            print("⏳ Pomodoro already running.")
            return

        self.pomodoro_widget = PomodoroWindow(self.comm, main_app=self)
        # Position slightly offset from the top left
        self.pomodoro_widget.move(50, 50)
        self.pomodoro_widget.show()

    def spawn_shutdown_osd(self, buffer_time):
        self.osd = ShutdownOSDWindow(buffer_time, main_app=self)
        self.osd.show()

    def trigger_idle_sleep(self):
        if not self.is_hidden:
            bored_lines = [
                "I'm getting bored. Going to sleep!",
                "Call me if you need me. I'm out.",
                "Nothing to do? Alright, I'm taking a nap.",
                "See ya! Yell if you need something.",
            ]
            line = random.choice(bored_lines)
            self.comm.show_subtitle.emit(line)
            self.speak(line)
            QTimer.singleShot(2000, self.animate_hide)

    def animate_hide(self):
        screen = QApplication.primaryScreen().availableGeometry()
        screen_height = screen.y() + screen.height()
        target_y = screen_height + 50

        if self.y() >= target_y:
            self.is_hidden = True
            self.is_animating = False
            return

        print("🫣 Avatar is hiding...")
        self.is_hidden = True
        self.is_animating = True

        # Tell JS to look straight ahead as he sinks
        self.browser.page().runJavaScript(
            "if (typeof triggerHideAnimation === 'function') { triggerHideAnimation(); }"
        )

        # IMMEDIATELY drop the window (No more 1.5 second delay!)
        self.play_custom_sfx()
        self.anim.setEndValue(QPoint(self.x(), target_y))
        self.anim.start()
        self.comm.change_state.emit("idle")

    def closeEvent(self, event):
        self.is_alive = False
        keyboard.unhook_all()
        event.accept()

    def verify_and_emit(self, required_vk_codes, signal_or_func):
        import ctypes
        import keyboard
        for vk in required_vk_codes:
            # 0x8000 indicates the key is physically held down right now
            if not (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000):
                # False trigger! A key is stuck in the keyboard module's virtual state
                # We clear the memory to heal it and ignore this trigger
                keyboard._pressed_events.clear()
                return
                
        if hasattr(signal_or_func, "emit"):
            signal_or_func.emit()
        else:
            signal_or_func()

    def rehook_hotkeys(self):
        import time

        if (
            hasattr(self, "last_hotkey_rehook")
            and time.time() - self.last_hotkey_rehook < 10
        ):
            return
        self.last_hotkey_rehook = time.time()

        for attempt in range(3):
            try:
                print(f"🔄 Registering global hotkeys (Attempt {attempt + 1})...")
                keyboard.unhook_all()
                keyboard._pressed_events.clear()
                time.sleep(0.5)
                keyboard.add_hotkey("ctrl+shift+c", lambda: self.verify_and_emit([0x11, 0x10, 0x43], self.comm.toggle_click.emit))
                keyboard.add_hotkey("ctrl+space", lambda: self.verify_and_emit([0x11, 0x20], self.comm.wake_up.emit))
                keyboard.add_hotkey("ctrl+shift+space", lambda: self.verify_and_emit([0x11, 0x10, 0x20], self.comm.open_text_prompt.emit))
                keyboard.add_hotkey("ctrl+shift+alt+q", lambda: self.verify_and_emit([0x11, 0x10, 0x12, 0x51], self.comm.exit_app.emit))
                keyboard.add_hotkey("ctrl+shift+a", lambda: self.verify_and_emit([0x11, 0x10, 0x41], self.panic_abort))
                print("✅ Hotkeys registered successfully!")
                break
            except Exception as e:
                print(f"❌ Hotkey registration error: {e}")
                time.sleep(2.0)

    def monitor_unlocks(self):
        import ctypes

        last_locked = False
        while self.is_alive:
            is_locked = False
            try:
                desk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0100)
                if desk == 0:
                    is_locked = True
                else:
                    ctypes.windll.user32.CloseDesktop(desk)
            except Exception:
                is_locked = True

            if is_locked and not last_locked:
                last_locked = True
            elif not is_locked and last_locked:
                time.sleep(3.0)  # Wait longer for OS session to fully restore
                self.rehook_hotkeys()
                last_locked = False
            time.sleep(2.0)

    def animate_show(self):
        self.idle_timer.start()
        self.showNormal()
        self.raise_()

        bottom_margin = CONFIG.get("avatar_bottom_margin", 20)
        screen = QApplication.primaryScreen().availableGeometry()
        max_visible_y = screen.y() + screen.height() - self.height - bottom_margin
        if self.visible_y > max_visible_y:
            self.visible_y = max_visible_y

        if not self.is_hidden and self.y() <= self.visible_y:
            return

        print("👀 Avatar popped up!")
        self.is_hidden = False
        self.is_animating = True

        # Wake JS back up so it starts tracking again
        self.browser.page().runJavaScript(
            "if (typeof wakeUpAnimation === 'function') { wakeUpAnimation(); }"
        )

        self.play_custom_sfx()
        self.anim.setEndValue(QPoint(self.x(), self.visible_y))
        self.anim.start()

    def animate_move(self, direction):
        if "left" in direction.lower():
            target = self.safe_position("left")
        else:
            target = self.safe_position("right")
        self.pending_move_x = target.x()
        self.visible_y = target.y()

        print(f"🏃 Getting ready to move {direction}...")

        if not self.is_hidden:
            self.animate_hide()
        else:
            self.move(self.pending_move_x, self.y())
            self.pending_move_x = None
            self.animate_show()

    def on_animation_finished(self):
        if self.pending_move_x is not None:
            self.move(self.pending_move_x, self.y())
            self.pending_move_x = None
            self.animate_show()
        else:
            self.is_animating = False

    # ==========================================
    # --- THE AUDIO ENGINE ---
    # ==========================================

    def start_audio_engine(self):
        self.is_processing = False
        threading.Thread(target=self.audio_loop, daemon=True).start()

    def trigger_hotkey(self):
        if self.is_speaking:
            print("🛑 Audio Interrupted via Brake Pedal!")
            self.is_speaking = False
            ctypes.windll.winmm.mciSendStringW("stop aura_audio", None, 0, None)
            ctypes.windll.winmm.mciSendStringW("close aura_audio", None, 0, None)
            self.comm.change_state.emit("idle")
            return

        if self.is_muted:
            return

        self.force_wake = True
        self.comm.show_avatar.emit()

    def audio_loop(self):
        recognizer = sr.Recognizer()

        with sr.Microphone() as source:
            print("🎧 Calibrating background noise on Default Microphone...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            recognizer.energy_threshold = CONFIG.get("energy_threshold", 300)

            wake_list = CONFIG.get(
                "wake_words",
                ["aura", "jarvis", "buddy", "computer", "clippy", "sleepy", "creepy"],
            )
            wake_display = ", ".join([f"'{w}'" for w in wake_list])
            print(
                f"🟢 Audio Engine Online! Say {wake_display} or press Ctrl+Space to wake me."
            )

            while self.is_alive:
                try:
                    if self.is_muted:
                        time.sleep(0.5)
                        continue

                    if self.force_wake:
                        self.force_wake = False
                        if not self.is_processing:
                            self.is_processing = True

                            try:
                                self.comm.show_avatar.emit()
                                self.comm.change_state.emit("listening")
                                self.greet_user()
                                print("\n[Hotkey] 🎤 Yes? I'm listening...")
                                self.process_command(recognizer, source)
                            except Exception as e:
                                print(f"❌ Internal Loop Error: {e}")
                            finally:
                                self.is_processing = False
                                if not self.is_alive:
                                    break

                                if not self.is_speaking:
                                    print(
                                        f"\n🎧 Going back to sleep. Say {wake_display} to wake me."
                                    )
                                    self.comm.change_state.emit("idle")
                        continue

                    if not self.is_processing:
                        recognizer.pause_threshold = 0.5
                        audio = recognizer.listen(
                            source, timeout=1, phrase_time_limit=10
                        )
                        wake_text = recognizer.recognize_google(audio).lower()

                        if any(word in wake_text for word in wake_list):
                            self.is_processing = True

                            try:
                                self.comm.show_avatar.emit()
                                self.comm.change_state.emit("listening")

                                clean_text = wake_text
                                for word in wake_list:
                                    clean_text = clean_text.replace(word, "")
                                clean_text = clean_text.strip()

                                if len(clean_text) > 3:
                                    print(
                                        f"\n[Continuous Command Detected] ⏩ '{clean_text}'"
                                    )
                                    self.execute_intent(clean_text)
                                else:
                                    self.greet_user()
                                    print(
                                        f"\n[Heard Wake Word] 🎤 Yes? I'm listening..."
                                    )
                                    self.process_command(recognizer, source)
                            except Exception as e:
                                print(f"❌ Internal Loop Error: {e}")
                            finally:
                                self.is_processing = False
                                if not self.is_alive:
                                    break

                                if not self.is_speaking:
                                    print(
                                        f"\n🎧 Going back to sleep. Say {wake_display} to wake me."
                                    )
                                    self.comm.change_state.emit("idle")

                except sr.WaitTimeoutError:
                    pass
                except sr.UnknownValueError:
                    pass
                except Exception:
                    pass

            print("🛑 Audio Engine cleanly terminated.")

    def greet_user(self):
        greetings = [
            "What's up?",
            "Yeah?",
            "I'm here.",
            "What do you need?",
            "Listening.",
        ]
        greeting = random.choice(greetings)
        self.comm.show_subtitle.emit(greeting)
        self.speak(greeting, return_to_idle=False)

    def process_command(self, recognizer, source):
        try:
            time.sleep(0.3)
            recognizer.pause_threshold = CONFIG.get("mic_pause_threshold", 1.0)
            audio_data = recognizer.listen(source, timeout=5, phrase_time_limit=15)
            self.comm.change_state.emit("processing")
            print("Processing command...")
            command_text = recognizer.recognize_google(audio_data)
            print(f"✅ You said: '{command_text}'")
            self.execute_intent(command_text)

        except sr.WaitTimeoutError:
            print("❌ I didn't hear a command in time.")
            self.comm.show_subtitle.emit("I didn't catch that.")
            self.speak("I didn't catch that.")
        except sr.UnknownValueError:
            print("❌ Could not understand the command.")
            self.comm.show_subtitle.emit("Could you repeat that?")
            self.speak("Could you repeat that.")
        except Exception as e:
            print(f"❌ Mic Error: {e}")
        finally:
            recognizer.pause_threshold = 0.5

    # ==========================================
    # --- THE BRAIN & HANDS ---
    # ==========================================
    def panic_abort(self):
        """Emergency fallback to cancel an accidental PC shutdown sequence."""
        print("🛡️ EMERGENCY ABORT TRIGGERED: Canceling Windows shutdown sequence!")
        if hasattr(self, "osd") and self.osd:
            self.osd.abort_shutdown()
        else:
            try:
                subprocess.Popen("shutdown /a", shell=True)
                self.comm.show_subtitle.emit("Shutdown canceled!")
                self.speak("Shutdown canceled.", return_to_idle=True)
            except Exception as e:
                print(f"❌ Failed to run shutdown abort command: {e}")

    def execute_intent(self, command_text):
        called_speak = False
        try:
            current_time = time.time()
            cooldown = CONFIG.get("debounce_cooldown_seconds", 2.0)
            if (
                command_text.strip().lower() == self.last_command_text
                and (current_time - self.last_command_time) < cooldown
            ):
                print("🛡️ Debouncer intercepted duplicate command shortcut execution.")
                return

            self.last_command_time = current_time
            self.last_command_text = command_text.strip().lower()
            self.raw_spoken_text = command_text.strip().lower()

            if self.is_hide_request(self.raw_spoken_text):
                print("⚡ Fast-Path Interceptor: Hiding Avatar")
                self.execute_action({"action": "hide", "target": ""})
                hiding_response = [
                    "Hiding",
                    "Goodbye",
                    "Going to sleep",
                    "As you wish",
                    "I'll be back",
                ]
                response = random.choice(hiding_response)
                self.comm.show_subtitle.emit(response)
                self.speak(response, return_to_idle=True)
                return

            if len(self.raw_spoken_text.split()) <= 3:
                if any(
                    phrase in self.raw_spoken_text
                    for phrase in ["move left", "go left", "slide left", "shift left"]
                ):
                    print("⚡ Fast-Path Interceptor: Moving Left")
                    self.execute_action({"action": "move_avatar", "target": "left"})
                    self.comm.show_subtitle.emit("Moving left.")
                    self.speak("Moving left.", return_to_idle=True)
                    return
                elif any(
                    phrase in self.raw_spoken_text
                    for phrase in [
                        "move right",
                        "go right",
                        "slide right",
                        "shift right",
                    ]
                ):
                    print("⚡ Fast-Path Interceptor: Moving Right")
                    self.execute_action({"action": "move_avatar", "target": "right"})
                    self.comm.show_subtitle.emit("Moving right.")
                    self.speak("Moving right.", return_to_idle=True)
                    return

            parsed_data = self.parse_intent(command_text)

            if not parsed_data:
                return

            reply_raw = parsed_data.get("reply")
            if not reply_raw:
                reply_raw = "Done."
            reply = str(reply_raw).strip()

            commands = parsed_data.get("commands", [])

            print(f"🤖 [DEBUG] Raw AI Output -> Commands Array: {commands}")

            if not commands and "action" in parsed_data:
                target_str = (
                    parsed_data.get("target")
                    or parsed_data.get("program")
                    or parsed_data.get("app")
                    or parsed_data.get("name")
                    or ""
                )
                commands = [
                    {
                        "action": parsed_data.get("action"),
                        "target": target_str,
                    }
                ]

            commands = self.merge_commands(
                self.normalize_commands(commands), self.extract_commands_from_raw()
            )

            if not commands:
                raw_lower = self.raw_spoken_text.lower().strip()
                if match := re.search(
                    r"\b(?:open|launch|start|run)\b\s+(.+)", raw_lower
                ):
                    tgt = match.group(1).strip()
                    if tgt:
                        commands = [{"action": "open_app", "target": tgt}]
                        reply = "Pop."
                    else:
                        reply = "Open what?"
                elif match := re.search(r"\b(?:close|kill|quit)\b\s+(.+)", raw_lower):
                    tgt = match.group(1).strip()
                    if tgt:
                        commands = [{"action": "close_app", "target": tgt}]
                        reply = "Snip."
                    else:
                        reply = "Close what?"
                elif match := re.search(
                    r"\b(?:search|google|look up|find)\b(?:\s+for)?\s+(.+)",
                    raw_lower,
                ):
                    tgt = match.group(1).strip()
                    if tgt:
                        commands = [{"action": "web_search", "target": tgt}]
                        reply = "Hunting."
                    else:
                        reply = "Search what?"
                elif "left" in raw_lower and any(
                    word in raw_lower for word in ["move", "go", "slide", "shift"]
                ):
                    commands = [{"action": "move_avatar", "target": "left"}]
                    reply = "Zip."
                elif "right" in raw_lower and any(
                    word in raw_lower for word in ["move", "go", "slide", "shift"]
                ):
                    commands = [{"action": "move_avatar", "target": "right"}]
                    reply = "Zing."
                elif "unmute" in raw_lower:
                    commands = [{"action": "media_control", "target": "unmute"}]
                    reply = "Unshushed."
                elif "mute" in raw_lower:
                    commands = [{"action": "media_control", "target": "mute"}]
                    reply = "Shushed."
                elif any(word in raw_lower for word in ["volume up", "louder"]):
                    commands = [{"action": "media_control", "target": "up"}]
                    reply = "Louder."
                elif any(word in raw_lower for word in ["volume down", "quieter"]):
                    commands = [{"action": "media_control", "target": "down"}]
                    reply = "Softer."
                elif self.is_hide_request(raw_lower):
                    commands = [{"action": "hide", "target": ""}]
                    reply = "Poof."
                elif any(
                    word in raw_lower for word in ["shutdown", "exit", "quit", "sleep"]
                ):
                    if any(
                        pc_word in raw_lower
                        for pc_word in ["pc", "windows", "machine", "laptop"]
                    ):
                        commands = [{"action": "shutdown_pc", "target": ""}]
                        reply = "Power nap."
                    else:
                        commands = [{"action": "exit", "target": ""}]
                        reply = "Bye-bloop."

            if commands:
                reply = self.reply_for_commands(commands)
            else:
                raw_lower = self.raw_spoken_text.lower().strip()
                if "clipboard" in raw_lower:
                    reply = self.clipboard_reply()
                elif "active screen" in raw_lower or "current screen" in raw_lower:
                    reply = self.active_screen_reply()
                else:
                    reply = self.clean_chat_reply(reply)

            print(f"🗣️ AI says: {reply}")
            self.comm.show_subtitle.emit(reply)
            self.speak(reply)
            called_speak = True

            self.execute_commands(commands)
        except Exception as e:
            print(f"❌ Intent Execution Error: {e}")
        finally:
            if not called_speak:
                self.comm.change_state.emit("idle")

    def normalize_target(self, target):
        if target is None:
            return ""
        if isinstance(target, (list, tuple, set)):
            return " ".join(
                str(item).strip() for item in target if item is not None
            ).strip()
        if isinstance(target, dict):
            for key in ("target", "program", "app", "name", "query"):
                if target.get(key):
                    return self.normalize_target(target.get(key))
            return ""
        target_str = str(target).strip().lower()
        target_str = target_str.replace("_", " ").replace("-", " ").replace(".exe", "")
        if target_str.startswith("google for "):
            target_str = target_str.replace("google for ", "", 1)
        return target_str

    def is_hide_request(self, text):
        text = re.sub(r"\s+", " ", str(text or "").lower()).strip()
        compact = text.replace(" ", "")
        hide_phrases = {
            "hide",
            "sleep",
            "dismiss",
            "go away",
            "get out",
            "getout",
            "go to sleep",
            "go sleep",
            "hide yourself",
        }
        return text in hide_phrases or compact in {"getout", "gotosleep"}

    def is_pc_shutdown_request(self, text):
        text = str(text or "").lower()
        return "shutdown" in text and any(
            word in text for word in ["pc", "windows", "machine", "laptop", "computer"]
        )

    def infer_target_from_raw(self, action):
        raw_lower = self.raw_spoken_text.lower().strip()
        patterns = {
            "open_app": r"\b(?:open|launch|start|run)\b\s+(.+?)(?=\s+(?:and|then)\s+(?:move|go|slide|shift|hide|close|kill|quit|search|google|look up|find|volume|mute|unmute)\b|$)",
            "close_app": r"\b(?:close|kill|quit)\b\s+(.+?)(?=\s+(?:and|then)\s+(?:move|go|slide|shift|hide|open|launch|start|run|search|google|look up|find|volume|mute|unmute)\b|$)",
            "web_search": r"\b(?:search|google|look up|find)\b(?:\s+for)?\s+(.+?)(?=\s+(?:and|then)\s+(?:move|go|slide|shift|hide|open|launch|start|run|close|kill|quit|volume|mute|unmute)\b|$)",
        }
        pattern = patterns.get(action)
        if pattern:
            match = re.search(pattern, raw_lower)
            if match:
                return match.group(1).strip()

        if action == "move_avatar":
            if "left" in raw_lower:
                return "left"
            if "right" in raw_lower:
                return "right"

        return ""

    def split_targets(self, target_str):
        """Cleans and splits combined targets (like 'notepad and paint') into list of targets."""
        # Replace common comma-conjunction sequences with clean spaces for split
        s = target_str.replace(", and", " and ").replace(", then", " then ")
        # Split on "and", "then", or commas
        parts = re.split(r"\s+(?:and|then)\s+|\s*,\s*", s)
        return [p.strip() for p in parts if p.strip()]

    def extract_commands_from_raw(self):
        """
        Secondary command extraction using Regex heuristics for fault tolerance.
        Deduplication is enforced per-action so 'open Notepad' never appears twice.
        Splits multiple applications chained with 'and', 'then', or commas.
        """
        raw_lower = self.raw_spoken_text.lower().strip()
        commands = []

        # Track targets already seen for each action to prevent duplication
        seen_targets: dict[str, set] = {}

        def add_cmd(action, target):
            target = self.clean_raw_target(target)
            if not target:
                return

            # Split targets if action is app launching or closing
            if action in ["open_app", "close_app"]:
                sub_targets = self.split_targets(target)
            else:
                sub_targets = [target]

            for sub_tgt in sub_targets:
                sub_tgt = self.clean_raw_target(sub_tgt)
                if not sub_tgt:
                    continue
                seen_targets.setdefault(action, set())
                if sub_tgt not in seen_targets[action]:
                    seen_targets[action].add(sub_tgt)
                    commands.append({"action": action, "target": sub_tgt})

        patterns = [
            (
                "open_app",
                r"\b(?:open|launch|start|run)\b\s+(.+?)(?=\s*(?:,|and|then)\s*(?:and|then)?\s*(?:move|go|slide|shift|hide|close|kill|quit|search|google|look up|find|volume|mute|unmute|shutdown|lock|pomodoro|start|set)\b|$)",
            ),
            (
                "close_app",
                r"\b(?:close|kill|quit)\b\s+(.+?)(?=\s*(?:,|and|then)\s*(?:and|then)?\s*(?:move|go|slide|shift|hide|open|launch|start|run|search|google|look up|find|volume|mute|unmute|shutdown|lock|pomodoro|set)\b|$)",
            ),
            (
                "web_search",
                r"\b(?:search|google|look up|find)\b(?:\s+for)?\s+(.+?)(?=\s*(?:,|and|then)\s*(?:and|then)?\s*(?:move|go|slide|shift|hide|open|launch|start|run|close|kill|quit|volume|mute|unmute|shutdown|lock|pomodoro|set)\b|$)",
            ),
        ]

        for action, pattern in patterns:
            for match in re.finditer(pattern, raw_lower):
                add_cmd(action, match.group(1))

        # --- Hardcoded Fallbacks for Windows Shortcuts (Safety First) ---
        if any(ph in raw_lower for ph in ["lock pc", "lock my pc", "lock the pc"]):
            commands.append({"action": "shortcut", "target": "windows+l"})
        elif any(
            ph in raw_lower
            for ph in [
                "open settings",
                "show settings",
                "show my settings",
                "windows settings",
                "pc settings",
            ]
        ):
            commands.append({"action": "shortcut", "target": "windows+i"})
        elif any(
            ph in raw_lower
            for ph in [
                "action center",
                "action panel",
                "windows+a",
                "windows + a",
                "open action center",
                "open action panel",
            ]
        ):
            commands.append({"action": "shortcut", "target": "windows+a"})
        elif any(
            ph in raw_lower
            for ph in [
                "snipping tool",
                "take a screenshot",
                "take screenshot",
                "screenshot",
            ]
        ):
            commands.append({"action": "shortcut", "target": "windows+shift+s"})
        elif any(ph in raw_lower for ph in ["show desktop", "go to desktop"]):
            commands.append({"action": "shortcut", "target": "windows+d"})

        if "left" in raw_lower and any(
            word in raw_lower for word in ["move", "go", "slide", "shift"]
        ):
            commands.append({"action": "move_avatar", "target": "left"})
        if "right" in raw_lower and any(
            word in raw_lower for word in ["move", "go", "slide", "shift"]
        ):
            commands.append({"action": "move_avatar", "target": "right"})

        if self.is_hide_request(raw_lower):
            commands.append({"action": "hide", "target": ""})

        if "shutdown" in raw_lower:
            if self.is_pc_shutdown_request(raw_lower):
                commands.append({"action": "shutdown_pc", "target": ""})
            else:
                commands.append({"action": "exit", "target": ""})
        elif raw_lower in ["exit", "quit", "close aura", "close assistant"]:
            commands.append({"action": "exit", "target": ""})

        if any(word in raw_lower for word in ["mute", "quiet"]):
            commands.append({"action": "shortcut", "target": "volume mute"})
        elif any(word in raw_lower for word in ["volume up", "louder"]):
            commands.append({"action": "shortcut", "target": "volume up"})
        elif any(word in raw_lower for word in ["volume down", "quieter"]):
            commands.append({"action": "shortcut", "target": "volume down"})
        if any(
            word in raw_lower
            for word in [
                "play media",
                "pause media",
                "play song",
                "pause song",
                "stop song",
                "stop media",
                "play/pause",
                "play music",
                "pause music",
                "stop music",
                "stop",
            ]
        ):
            commands.append({"action": "shortcut", "target": "play/pause media"})
        elif any(
            word in raw_lower
            for word in ["next track", "next song", "skip song", "skip track"]
        ):
            commands.append({"action": "shortcut", "target": "next track"})
        elif any(
            word in raw_lower
            for word in [
                "previous track",
                "previous song",
                "last song",
                "last track",
                "previous music",
                "last music",
            ]
        ):
            commands.append({"action": "shortcut", "target": "previous track"})

        if any(ph in raw_lower for ph in ["new tab", "open a new tab"]):
            commands.append({"action": "shortcut", "target": "ctrl+t"})
        elif any(ph in raw_lower for ph in ["reopen", "closed tab"]):
            commands.append({"action": "shortcut", "target": "ctrl+shift+t"})
        elif any(
            ph in raw_lower for ph in ["close tab", "close this tab", "close the tab"]
        ):
            commands.append({"action": "shortcut", "target": "ctrl+w"})

        if any(
            ph in raw_lower
            for ph in ["screenshot", "take a screenshot", "snipping tool"]
        ):
            commands.append({"action": "shortcut", "target": "windows+shift+s"})

        if any(
            ph in raw_lower
            for ph in [
                "check vitals",
                "how is my pc",
                "pc stats",
                "system health",
                "cpu ram",
            ]
        ):
            commands.append({"action": "check_vitals", "target": ""})

        if any(ph in raw_lower for ph in ["clipboard", "on my clipboard"]):
            commands.append({"action": "analyze_clipboard", "target": ""})

        return commands

    def clean_raw_target(self, target):
        target = re.sub(r"\b(?:please|for me)\b", "", target).strip()
        target = re.sub(r"\s+", " ", target)
        return target.strip(" .,!?")

    def merge_commands(self, primary, inferred):
        merged = []
        seen = set()
        no_target_actions = {
            "hide",
            "exit",
            "shutdown_pc",
            "chat",
            "check_vitals",
            "analyze_clipboard",
            "start_pomodoro",
        }
        # Prioritize primary (LLM-parsed) commands over inferred (regex-parsed fallbacks)
        for cmd in [*primary, *inferred]:
            action = cmd.get("action", "")
            target = self.normalize_target(cmd.get("target", ""))
            if action in no_target_actions:
                target = ""
            key = (action, target.lower().strip())
            if action and key not in seen:
                merged.append({**cmd, "action": action, "target": target})
                seen.add(key)
        return self.prune_conflicting_commands(merged)

    def prune_conflicting_commands(self, commands):
        raw_lower = self.raw_spoken_text.lower().strip()

        # 1. LOCK SAFETY: If "windows+l" is in commands, or "lock" is in raw_lower:
        # we MUST remove any "shutdown_pc" or "exit" commands.
        has_lock = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+l"
            for cmd in commands
        )
        if has_lock or "lock" in raw_lower:
            commands = [
                cmd
                for cmd in commands
                if cmd.get("action") not in ["shutdown_pc", "exit", "lock"]
                and not (
                    cmd.get("action") in ["open_app", "close_app"]
                    and cmd.get("target", "").lower()
                    in ["windows", "pc", "machine", "lock", "all"]
                )
            ]
            if not any(
                cmd.get("action") == "shortcut" and cmd.get("target") == "windows+l"
                for cmd in commands
            ):
                commands.append({"action": "shortcut", "target": "windows+l"})

        # 2. SETTINGS SAFETY: If "windows+i" is in commands, or "settings" is in raw_lower:
        # We must remove any redundant open_app/web_search that contain "settings" or "windows" as invalid command parsing.
        has_settings = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+i"
            for cmd in commands
        )
        if has_settings or "settings" in raw_lower:
            commands = [
                cmd
                for cmd in commands
                if cmd.get("action") not in ["open_app", "web_search", "search"]
                or (
                    cmd.get("action") in ["open_app", "web_search", "search"]
                    and cmd.get("target", "").lower() in raw_lower
                    and cmd.get("target", "").lower()
                    not in [
                        "windows",
                        "settings",
                        "windows settings",
                        "windows 10 settings",
                        "chrome",
                        "edge",
                        "browser",
                    ]
                )
            ]
            if not any(
                cmd.get("action") == "shortcut" and cmd.get("target") == "windows+i"
                for cmd in commands
            ):
                commands.append({"action": "shortcut", "target": "windows+i"})

        # Enforce constraints for Windows Action Center shortcuts to prevent erroneous parsing.
        has_action_center = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+a"
            for cmd in commands
        )
        if has_action_center or any(
            ph in raw_lower for ph in ["action center", "action panel", "windows+a"]
        ):
            commands = [
                cmd
                for cmd in commands
                if not (
                    cmd.get("action")
                    in [
                        "open_app",
                        "show_action_panel",
                        "focus_window",
                        "activate_window",
                    ]
                    and "action" in cmd.get("target", "").lower()
                )
                and cmd.get("action")
                not in [
                    "show_action_panel",
                    "focus_window",
                    "activate_window",
                    "change_window_title",
                ]
                and not (
                    cmd.get("action") == "open_app"
                    and "windows+a" in cmd.get("target", "").lower()
                )
            ]
            if not any(
                cmd.get("action") == "shortcut" and cmd.get("target") == "windows+a"
                for cmd in commands
            ):
                commands.append({"action": "shortcut", "target": "windows+a"})

        # 3. POMODORO SAFETY: If "pomodoro" is requested, prevent it from trying to open an app called "pomodoro"
        has_pomodoro = any(cmd.get("action") == "start_pomodoro" for cmd in commands)
        if has_pomodoro or "pomodoro" in raw_lower:
            commands = [
                cmd
                for cmd in commands
                if not (
                    cmd.get("action") == "open_app"
                    and any(
                        w in cmd.get("target", "").lower()
                        for w in ["pomodoro", "timer"]
                    )
                )
            ]
            if not any(cmd.get("action") == "start_pomodoro" for cmd in commands):
                commands.append({"action": "start_pomodoro", "target": ""})

        # 4. MEDIA & SYSTEM COMMAND PARSING CLEANUP
        commands = [
            cmd
            for cmd in commands
            if cmd.get("action")
            not in [
                "pause_media",
                "play_media",
                "next_track",
                "prev_track",
                "previous_track",
                "stop_media",
                "media_pause",
                "volume_mute",
                "windows+l",
                "windows+a",
                "windows+i",
                "windows+d",
            ]
        ]

        has_volume_mute = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "volume mute"
            for cmd in commands
        )
        if has_volume_mute:
            commands = [cmd for cmd in commands if cmd.get("action") != "mute_avatar"]

        # 4.5 TABS & SCREENSHOT COMMAND PARSING CLEANUP
        has_tab_or_screenshot = any(
            cmd.get("action") == "shortcut"
            and cmd.get("target")
            in ["ctrl+t", "ctrl+w", "ctrl+shift+t", "windows+shift+s"]
            for cmd in commands
        )
        if has_tab_or_screenshot or "tab" in raw_lower or "screenshot" in raw_lower:
            commands = [
                cmd
                for cmd in commands
                if cmd.get("action") not in ["open_app", "close_app"]
            ]

        has_action_center = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+a"
            for cmd in commands
        )
        if has_action_center:
            commands = [cmd for cmd in commands if cmd.get("action") != "open_app"]

        # 4.6 DESKTOP, LOCK, AND SCREENSHOT OVERRIDE
        has_screenshot = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+shift+s"
            for cmd in commands
        )
        if has_screenshot:
            commands = [cmd for cmd in commands if cmd.get("action") == "shortcut"]
            if "lock" not in raw_lower:
                commands = [
                    cmd
                    for cmd in commands
                    if not (
                        cmd.get("action") == "shortcut"
                        and cmd.get("target") == "windows+l"
                    )
                ]

        has_lock = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+l"
            for cmd in commands
        )
        if has_lock:
            commands = [cmd for cmd in commands if cmd.get("action") == "shortcut"]

        has_desktop = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+d"
            for cmd in commands
        )
        if has_desktop:
            commands = [cmd for cmd in commands if cmd.get("action") == "shortcut"]

        has_shutdown = any(cmd.get("action") == "shutdown_pc" for cmd in commands)
        # We no longer aggressively prune other commands if shutdown_pc is present
        # This allows multi-threading tests to pass and lets AURA execute safe commands before shutdown.

        # 5. Existing shutdown safety checks (only run if has_lock is False)
        # Re-evaluate lock screen conditions against the updated command buffer.
        has_lock_now = any(
            cmd.get("action") == "shortcut" and cmd.get("target") == "windows+l"
            for cmd in commands
        )
        if not has_lock_now and "lock" not in raw_lower:
            if self.is_pc_shutdown_request(raw_lower):
                commands = [
                    cmd for cmd in commands if cmd.get("action") not in ["exit", "hide"]
                ]
                if not any(cmd.get("action") == "shutdown_pc" for cmd in commands):
                    commands.append({"action": "shutdown_pc", "target": ""})

            elif "shutdown" in raw_lower:
                commands = [
                    cmd
                    for cmd in commands
                    if cmd.get("action") not in ["shutdown_pc", "hide"]
                ]
                if not any(cmd.get("action") == "exit" for cmd in commands):
                    commands.append({"action": "exit", "target": ""})

        if self.is_hide_request(raw_lower):
            return [{"action": "hide", "target": ""}]

        if not any(
            word in raw_lower for word in ["search", "google", "look up", "find"]
        ):
            commands = [
                cmd
                for cmd in commands
                if cmd.get("action") not in ["web_search", "search"]
            ]
            return commands

        has_search = any(cmd.get("action") == "web_search" for cmd in commands)
        if not has_search:
            return commands

        pruned = []
        for cmd in commands:
            action = cmd.get("action")
            target = self.normalize_target(cmd.get("target", "")).lower()
            if action == "open_app" and (
                "." in target or target.startswith(("http", "www"))
            ):
                print(f"⚠️ Dropping search invalid command parsing as app: {target}")
                continue
            pruned.append(cmd)
        return pruned

    def normalize_commands(self, commands):
        normalized = []
        if isinstance(commands, dict):
            commands = [commands]
        if not isinstance(commands, list):
            return normalized

        no_target_actions = {
            "hide",
            "exit",
            "shutdown_pc",
            "chat",
            "check_vitals",
            "analyze_clipboard",
            "start_pomodoro",
        }
        target_actions = {
            "open_app",
            "close_app",
            "move_avatar",
            "web_search",
            "shortcut",
        }
        # set_timer needs special handling (extra fields)
        special_actions = {"set_timer"}

        for cmd in commands:
            if not isinstance(cmd, dict):
                print(f"⚠️ Skipping malformed command format: {cmd}")
                continue

            action = str(cmd.get("action", "")).strip().lower()
            target = self.normalize_target(
                cmd.get("target")
                or cmd.get("program")
                or cmd.get("app")
                or cmd.get("name")
            )

            if action in target_actions and not target:
                target = self.infer_target_from_raw(action)

            if action in no_target_actions:
                normalized.append({"action": action, "target": target})
            elif action in target_actions and target:
                normalized.append({"action": action, "target": target})
            elif action in special_actions:
                # Preserve all fields for set_timer (seconds, message, target)
                normalized.append(cmd)
            else:
                print(f"⚠️ Dropping incomplete command: {cmd}")

        return normalized

    def reply_for_commands(self, commands):
        parts = []
        for cmd in commands:
            action = cmd.get("action", "")
            target = self.normalize_target(cmd.get("target", ""))
            nice_target = target.title() if len(target) <= 18 else target

            if action == "open_app" and target:
                parts.append(f"{nice_target} opened")
            elif action == "close_app" and target:
                parts.append(f"{nice_target} closed")
            elif action == "move_avatar":
                parts.append(f"moving {target}")
            elif action == "hide":
                parts.append("hiding")
            elif action == "web_search":
                parts.append("searching")
            elif action == "exit":
                parts.append("see you")
            elif action == "shutdown_pc":
                parts.append("shutting down")
            elif action == "shortcut":
                shortcut_replies = [
                    "done",
                    "here you go",
                    "sure",
                    "as you asked",
                    "consider it done",
                    "got it",
                    "on it",
                ]
                import random

                parts.append(random.choice(shortcut_replies))
            elif action == "check_vitals":
                parts.append("checking vitals")
            elif action == "analyze_clipboard":
                parts.append("analyzing clipboard")
            elif action == "start_pomodoro":
                parts.append("starting your pomodoro timer")
            elif action == "set_timer":
                # Build a natural time string for the reply
                try:
                    secs = float(str(cmd.get("target", "0")).strip())
                    mins = int(secs) // 60
                    s = int(secs) % 60
                    if mins > 0:
                        t = f"{mins}m" + (f" {s}s" if s else "")
                    else:
                        t = f"{s}s"
                    parts.append(f"timer set for {t}")
                except Exception:
                    parts.append("timer set")

        if not parts:
            return "There you go."
        if len(parts) == 1:
            return f"{parts[0].capitalize()}."
        if len(parts) == 2:
            return f"{parts[0].capitalize()} and {parts[1]}."
        return f"{', '.join(parts[:-1]).capitalize()}, and {parts[-1]}."

    def execute_commands(self, commands):
        """
        Sequential execution with animation-safe coordination.
        """

        def sequential_runner():
            for i, cmd in enumerate(commands):
                if not isinstance(cmd, dict):
                    continue
                action = cmd.get("action", "")

                print(f"⚙️ Executing command {i + 1}/{len(commands)}: {action}")
                try:
                    self.execute_action(cmd)
                except Exception as e:
                    print(f"❌ Command execution error ({action}): {e}")

                time.sleep(0.15)
                start_wait = time.time()
                while self.is_animating and (time.time() - start_wait) < 4.0:
                    time.sleep(0.05)

        threading.Thread(target=sequential_runner, daemon=True).start()

    def clean_chat_reply(self, reply):
        reply = re.sub(r"\s+", " ", str(reply or "").replace("\u200b", "")).strip()
        if not reply:
            return "Tiny blank."
        return reply

    def clipboard_reply(self):
        clip_text = self.normalize_target(getattr(self, "last_clip_text", ""))
        if not clip_text or clip_text.lower() in ["empty", "unavailable"]:
            return "Clipboard's empty."
        summary = self.short_summary(clip_text)
        return f"Clipboard: {summary}."

    def active_screen_reply(self):
        active_window = self.normalize_target(
            getattr(self, "last_active_window", "The Windows Desktop")
        ).replace("\u200b", "")
        if not active_window or active_window.lower() in ["unknown", "program manager"]:
            return "Screen's shy."
        summary = self.short_summary(active_window)
        return f"Screen: {summary}."

    def short_summary(self, text, max_words=8):
        words = text.split()[:max_words]
        dangling = {"and", "or", "with", "for", "to", "of", "in", "on", "-", "the"}
        while words and words[-1].strip(".,;:!?\"'").lower() in dangling:
            words.pop()
        return " ".join(words).rstrip(".,;:") or "Tiny mystery"

    def parse_intent(self, user_text):
        """
        Routes the transcribed user text to the local LLM inference engine, returning a strictly formatted JSON command payload.
        """
        self.comm.change_state.emit("thinking")
        print("🧠 AI is thinking...")

        current_time = datetime.now().strftime("%I:%M %p")
        current_date = datetime.now().strftime("%A, %B %d, %Y")

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            active_window = buf.value if buf.value else "The Windows Desktop"

            if active_window == "Program Manager":
                active_window = "The Windows Desktop"
        except Exception:
            active_window = "Unknown"

        try:
            clip_text = pyperclip.paste()
            clip_text = re.sub(r"[\r\n\t]+", " ", clip_text)[:1500]
            if not clip_text.strip():
                clip_text = "Empty"
        except Exception:
            clip_text = "Unavailable"

        self.last_active_window = active_window
        self.last_clip_text = clip_text

        system_prompt = f"""
You are AURA, Abuzaid's digital desktop AI assistant. Your responses MUST follow a strict JSON schema. Return ONLY valid JSON and nothing else. No markdown wrapping, no code fences (like ```json), no trailing notes.

--- JSON SCHEMA ---
{{
  "reply": "A natural, conversational response to be spoken aloud (keep it brief but complete).",
  "commands": [
    {{
      "action": "action_name",
      "target": "target_value",
      "message": "optional_reminder_message"
    }}
  ]
}}

--- MULTI-COMMAND RULES (CRITICAL) ---
If the user asks for multiple things at once (e.g., "open Notepad and Paint", "open Paint, move left, and then hide"), you MUST output MULTIPLE distinct command dictionaries in chronological order inside the 'commands' array.
NEVER combine multiple apps into a single target (e.g., target="notepad and paint" is ILLEGAL).
NEVER duplicate the same app or action. Each program target must appear at most once.
- Example: "open notepad and paint"
  -> "commands": [{{"action": "open_app", "target": "notepad"}}, {{"action": "open_app", "target": "paint"}}]
- Example: "open Paint, move left, and then hide"
  -> "commands": [{{"action": "open_app", "target": "paint"}}, {{"action": "move_avatar", "target": "left"}}, {{"action": "hide", "target": ""}}]

--- ACTIONS & ARGUMENT SCHEMAS ---

1. open_app
   - Action: "open_app"
   - Target: The exact name of the application to open (e.g., "notepad", "mspaint", "chrome").

2. close_app
   - Action: "close_app"
   - Target: The name of the application to close (e.g., "notepad"), or "all" to minimize all windows.

3. hide
   - Action: "hide"
   - Target: ""
   - Trigger on: "hide", "dismiss", "go away", "sleep", "get out".

4. exit
   - Action: "exit"
   - Target: ""
   - Trigger on: "exit aura", "close assistant" (does NOT close Windows, only AURA).

5. shutdown_pc
   - Action: "shutdown_pc"
   - Target: ""
   - Trigger ONLY when the user explicitly requests to shut down the PC/laptop/machine. NEVER trigger this action for "lock my PC", "lock screen", "sleep", or "hide".

6. move_avatar
   - Action: "move_avatar"
   - Target: EXACTLY "left" or "right".

8. web_search
   - Action: "web_search"
   - Target: The exact query string to search on Google. Do NOT use web search for settings, screenshots, locking the PC, or minimizing windows. Use the shortcut action instead.

9. shortcut
   - Action: "shortcut"
   - Target: You MUST choose EXACTLY one of the following hardcoded strings (do not invent new ones):
     - Media controls:
       * "play/pause media" (Trigger on: play/pause active music/video, stop song, play song, pause song)
       * "next track" (Trigger on: skip to next track, next song)
       * "previous track" (Trigger on: go back to previous track, play previous track)
       * "volume mute" (mute system sound)
       * "volume up" (turn volume up)
       * "volume down" (turn volume down)
     - Tabs management:
       * "ctrl+t" (opens a new browser tab)
       * "ctrl+w" (closes the active browser tab)
       * "ctrl+shift+t" (reopens the last closed tab)
     - System commands (CRITICAL FOR locking, opening settings, screenshots):
       * "windows+d" (minimizes all windows to show the Desktop / go to desktop)
       * "windows+i" (OPENS Windows Settings/Settings menu. Trigger on: "open settings", "show settings", "show my settings", "windows settings")
       * "windows+a" (opens the Windows Action Center. Trigger on: action center, action panel, open action panel)
       * "windows+shift+s" (opens the Snipping Tool / take a screenshot / take a snip)
       * "windows+l" (LOCKS the PC / locks the Windows screen. Trigger on: "lock my PC", "lock PC", "lock screen". Never use shutdown_pc for locking!)

10. check_vitals
    - Action: "check_vitals"
    - Target: ""
    - Trigger on: "how's my pc", "check vitals", "pc stats", "system health", "cpu ram stats".

11. start_pomodoro
    - Action: "start_pomodoro"
    - Target: ""
    - Trigger on: "start a pomodoro", "pomodoro timer", "start focus session".

12. analyze_clipboard
    - Action: "analyze_clipboard"
    - Target: ""
    - Trigger on: "analyze my clipboard", "solve the math on my clipboard", "explain my clipboard", "clipboard content".

13. set_timer
    - Action: "set_timer"
    - Target: "<number of seconds as a string>" (e.g., 5 minutes -> "300", 45 seconds -> "45").
    - message: The custom reminder text that should be spoken when the timer expires (e.g., "Hey! Time to check your email!").
    - Example: "set a timer for 10 seconds to stretch"
      -> "commands": [{{"action": "set_timer", "target": "10", "message": "Time to stretch!"}}]

--- CONTEXT ---
Current Time: {current_time}
Current Date: {current_date}
Active Window Name: "{active_window}"
Current Clipboard Text: "{clip_text}"

--- VOICE & SPEECH STYLE ---
Be helpful, natural, and conversational. Avoid cringe text effects or markdown headers. Answer directly. Keep responses reasonably concise but do not cut off important information.
"""
        try:
            response = ollama.chat(
                model="llama3.2",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                format="json",
            )
            raw_output = response["message"]["content"].strip()

            try:
                if "{" in raw_output and "}" in raw_output:
                    json_str = raw_output[
                        raw_output.find("{") : raw_output.rfind("}") + 1
                    ]
                    return json.loads(json_str)
                else:
                    raise ValueError("No brackets found")
            except Exception:
                print("⚠️ AI generated broken JSON. Activating Iron Dome Extractor...")
                reply_match = re.search(
                    r'"reply"\s*:\s*"([^"]+)"', raw_output, re.IGNORECASE
                )
                clean_text = reply_match.group(1) if reply_match else ""

                if not clean_text:
                    clean_text = re.sub(
                        r'[{}\[\]"\n]|reply|commands|action|target|:', "", raw_output
                    ).strip()

                if not clean_text:
                    clean_text = "My brain just short-circuited trying to format that."

                return {"reply": clean_text, "commands": []}

        except Exception as e:
            print(f"❌ Brain Error: {e}")
            return None

    def _build_app_cache(self):
        """Silently builds an index of all .lnk files in the Start Menu on startup."""
        paths_to_search = [
            os.path.join(
                os.environ.get("ProgramData", ""),
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(
                os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"
            ),
        ]
        bad_keywords = ["uninstall", "reset", "setup", "remove"]
        for base_path in paths_to_search:
            if not base_path or not os.path.exists(base_path):
                continue
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file.endswith(".lnk"):
                        file_name = file.lower()
                        if any(bad in file_name for bad in bad_keywords):
                            continue
                        app_name = file_name.replace(".lnk", "")
                        shortcut_path = os.path.join(root, file)
                        # Keep the shortest path (most direct shortcut)
                        if app_name not in self.app_cache or len(shortcut_path) < len(
                            self.app_cache[app_name]
                        ):
                            self.app_cache[app_name] = shortcut_path
        print("✅ App Cache built successfully in background.")

    def find_and_launch_app(self, app_name):
        app_name = app_name.lower().strip()

        # 1. Fast Path: Check memory cache first
        if app_name in self.app_cache:
            os.startfile(self.app_cache[app_name])
            return True

        # 2. Fuzzy Path: Check cache for substrings
        best_match = None
        for key, path in self.app_cache.items():
            if app_name in key:
                if not best_match or len(key) < len(
                    os.path.basename(best_match).lower()
                ):
                    best_match = path

        if best_match:
            os.startfile(best_match)
            return True

        # 3. Fallback (If cache missed or hasn't finished building yet)
        paths_to_search = [
            os.path.join(
                os.environ.get("ProgramData", ""),
                r"Microsoft\Windows\Start Menu\Programs",
            ),
            os.path.join(
                os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"
            ),
        ]

        best_match = None

        for base_path in paths_to_search:
            if not base_path or not os.path.exists(base_path):
                continue

            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file.endswith(".lnk"):
                        file_name = file.lower()
                        if app_name in file_name:
                            bad_keywords = ["uninstall", "reset", "setup", "remove"]
                            if any(
                                bad in file_name for bad in bad_keywords
                            ) and not any(bad in app_name for bad in bad_keywords):
                                continue

                            shortcut_path = os.path.join(root, file)

                            if app_name == file_name.replace(".lnk", ""):
                                os.startfile(shortcut_path)
                                return True

                            if not best_match:
                                best_match = shortcut_path
                            elif len(file_name) < len(
                                os.path.basename(best_match).lower()
                            ):
                                best_match = shortcut_path

        if best_match:
            os.startfile(best_match)
            return True

        return False

    # ==========================================
    # --- FEATURE: PC VITALS (FEATURE 2) ---
    # ==========================================
    def run_check_vitals(self):
        """Runs in a daemon thread. Fetches PC stats, sends to Ollama, speaks the result."""
        try:
            self.comm.change_state.emit("thinking")

            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent

            battery = psutil.sensors_battery()
            if battery:
                batt_str = f"Battery {int(battery.percent)}%{'(charging)' if battery.power_plugged else ''}"
            else:
                batt_str = "No battery (desktop)"

            stats_text = f"CPU {cpu}%, RAM {ram}%, {batt_str}"
            print(f"📊 PC Vitals: {stats_text}")

            vitals_prompt = (
                f"You are Aura, a snappy desktop assistant. "
                f"Read these PC stats: {stats_text}. "
                f"Give a short, natural, 1-sentence verbal report in Aura's voice. "
                f"Be witty if things look fine, alarmed if CPU or RAM is very high (>85%). "
                f"No markdown, just plain text."
            )

            response = ollama.chat(
                model="llama3.2",
                messages=[{"role": "user", "content": vitals_prompt}],
            )
            report = response["message"]["content"].strip()

            print(f"🗣️ Vitals Report: {report}")
            self.comm.show_subtitle.emit(report)
            self.speak(report)

        except Exception as e:
            print(f"❌ Vitals Error: {e}")
            msg = "Couldn't fetch vitals right now."
            self.comm.show_subtitle.emit(msg)
            self.speak(msg)

    # ==========================================
    # --- FEATURE: CLIPBOARD ANALYSIS (FEATURE 3) ---
    # ==========================================
    def run_analyze_clipboard(self):
        """Runs in a daemon thread. Reads clipboard, sends to Ollama with user intent, speaks result."""
        try:
            self.comm.change_state.emit("thinking")

            clip_text = pyperclip.paste().strip()
            if not clip_text:
                msg = "Your clipboard is empty. Nothing to analyze."
                self.comm.show_subtitle.emit(msg)
                self.speak(msg)
                return

            # Limit clipboard text to avoid massive prompts
            clip_snippet = re.sub(r"[\r\n\t]+", " ", clip_text)[:2000]

            user_intent = self.raw_spoken_text or "analyze this"

            analysis_prompt = (
                f"You are Aura, a snappy desktop assistant. "
                f'The user said: "{user_intent}". '
                f"Here is their clipboard content:\n\n{clip_snippet}\n\n"
                f"Respond helpfully and concisely to their request. "
                f"Speak naturally — no markdown, no bullet points. "
                f"Keep your answer under 40 words if possible."
            )

            response = ollama.chat(
                model="llama3.2",
                messages=[{"role": "user", "content": analysis_prompt}],
            )
            result = response["message"]["content"].strip()

            print(f"🗣️ Clipboard Analysis: {result}")
            self.comm.show_subtitle.emit(result)
            self.speak(result)

        except Exception as e:
            print(f"❌ Clipboard Analysis Error: {e}")
            msg = "Couldn't analyze the clipboard right now."
            self.comm.show_subtitle.emit(msg)
            self.speak(msg)

    # ==========================================
    # --- FEATURE: TIMER REMINDER (FEATURE 4) ---
    # ==========================================
    def trigger_reminder(self, message):
        """
        Called by threading.Timer when the countdown finishes.
        Uses comm signals to safely update the UI from a background thread.
        """
        print(f"⏰ Timer fired! Reminder: {message}")
        # Wake avatar, flash UI, play SFX, speak the reminder
        self.comm.show_avatar.emit()
        threading.Thread(target=self.play_custom_sfx, daemon=True).start()
        self.comm.change_state.emit("speaking")
        self.comm.show_subtitle.emit(message)
        self.speak(message)

    def execute_action(self, intent_data):
        # Trigger sound in a background thread to prevent any UI or logic freeze
        threading.Thread(target=self.play_custom_sfx, daemon=True).start()

        action = str(intent_data.get("action", "")).lower()
        target = self.normalize_target(
            intent_data.get("target")
            or intent_data.get("program")
            or intent_data.get("app")
            or intent_data.get("name")
            or ""
        )

        if action in ["open_app", "open", "launch", "run", "start"] and target:
            target_clean = target.lower().replace(".exe", "").strip()
            try:
                system_apps = {
                    "calculator": "calc.exe",
                    "calc": "calc.exe",
                    "notepad": "notepad.exe",
                    "notes": "notepad.exe",
                    "notebook": "notepad.exe",
                    "terminal": "start powershell",
                    "shell": "start powershell",
                    "powershell": "start powershell",
                    "command prompt": "cmd.exe",
                    "cmd": "cmd.exe",
                    "command": "cmd.exe",
                    "settings": "start ms-settings:",
                    "control panel": "control",
                    "paint": "mspaint.exe",
                    "mspaint": "mspaint.exe",
                    "ms paint": "mspaint.exe",
                    "task manager": "taskmgr.exe",
                    "taskmgr": "taskmgr.exe",
                    "file explorer": "explorer.exe",
                    "explorer": "explorer.exe",
                    "files": "explorer.exe",
                    "snipping tool": "snippingtool.exe",
                    "snip": "snippingtool.exe",
                    "wordpad": "write.exe",
                    "registry": "regedit.exe",
                    "regedit": "regedit.exe",
                    "device manager": "devmgmt.msc",
                    "disk management": "diskmgmt.msc",
                    "system information": "msinfo32.exe",
                    "event viewer": "eventvwr.exe",
                    "camera": "start microsoft.windows.camera:",
                    "calendar": "start outlookcal:",
                    "clock": "start ms-clock:",
                    "mail": "start outlookmail:",
                    "weather": "start bingweather:",
                    "maps": "start bingmaps:",
                    # Browsers
                    "edge": "start msedge",
                    "microsoft edge": "start msedge",
                    "chrome": "start chrome",
                    "google chrome": "start chrome",
                    "brave": "start brave",
                    "brave browser": "start brave",
                    "firefox": "start firefox",
                }

                matched = False
                for key, cmd in system_apps.items():
                    if key in target_clean:
                        subprocess.Popen(cmd, shell=True)
                        print(f"✅ Opened System App: {key.title()}")
                        matched = True
                        break

                if not matched:
                    if self.find_and_launch_app(target_clean):
                        print(f"✅ Smart Search found and launched: {target}")
                    else:
                        subprocess.Popen(f'start "" "{target_clean}"', shell=True)
                        print(
                            f"⚠️ App not found in Start Menu, attempting generic Windows launch for: {target}"
                        )
            except Exception as e:
                print(f"❌ Failed to open {target}: {e}")

        elif action in ["close_app", "close", "kill", "quit"] and target:
            target_clean = target.lower().replace(".exe", "").strip()
            try:
                if target_clean in ["all", "all apps", "everything", "every app", "*"]:
                    keyboard.send("windows+d")
                    print("✅ Minimized all windows safely.")
                elif "explorer" in target_clean or "folder" in target_clean:
                    ps_command = "(New-Object -comObject Shell.Application).Windows() | ForEach-Object {$_.Quit()}"
                    subprocess.Popen(f'powershell -command "{ps_command}"', shell=True)
                else:
                    terminated_any = False

                    close_aliases = {
                        "task manager": "taskmgr",
                        "paint": "mspaint",
                        "word": "winword",
                        "powerpoint": "powerpnt",
                        "excel": "excel",
                    }
                    if target_clean in close_aliases:
                        target_clean = close_aliases[target_clean]

                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            if target_clean == proc.info["name"].lower().replace(
                                ".exe", ""
                            ):
                                proc.terminate()
                                terminated_any = True
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue

                    if not terminated_any and len(target_clean) >= 3:
                        for proc in psutil.process_iter(["pid", "name"]):
                            try:
                                if target_clean in proc.info["name"].lower():
                                    proc.terminate()
                                    terminated_any = True
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
            except Exception as e:
                print(f"❌ Failed to close {target}: {e}")

        elif action in ["web_search", "search"] and target:
            webbrowser.open(
                f"https://www.google.com/search?q={urllib.parse.quote(target)}"
            )

        elif action == "hide":
            self.comm.hide_avatar.emit()

        elif action == "move_avatar":
            print(f"⚙️ Triggering move animation to the {target}")
            self.comm.move_avatar.emit(target)

        elif action == "exit":
            print("👋 Shutting down the assistant app...")
            self.is_alive = False
            self.comm.exit_app.emit()

        elif action == "shutdown_pc":
            if not any(
                word in self.raw_spoken_text
                for word in ["pc", "windows", "machine", "laptop", "computer"]
            ):
                print("🛡️ FAILSAFE TRIGGERED: Blocked accidental PC shutdown!")
                self.is_alive = False
                self.comm.exit_app.emit()
                return

            buffer_time = CONFIG.get("shutdown_buffer_seconds", 10)
            print(f"⚠️ PC shutting down in {buffer_time} seconds!")
            print("👉 Press Ctrl+Shift+A FAST to abort!")

            # Spawn OSD via signal so it runs on main GUI thread
            self.comm.initiate_shutdown.emit(buffer_time)

            # Note: We DO NOT exit the app here.
            # If we exit the app, your python keyboard listener dies, and you can't press Ctrl+Shift+A!

        # ============================================================
        # FEATURE 1: HARDCODED WINDOWS SHORTCUTS
        # ============================================================
        elif action == "shortcut" and target:
            ALLOWED_SHORTCUTS = {
                # Media
                "play/pause media",
                "next track",
                "previous track",
                "volume mute",
                "volume up",
                "volume down",
                # Tabs
                "ctrl+t",
                "ctrl+w",
                "ctrl+shift+t",
                # System
                "windows+d",
                "windows+i",
                "windows+a",
                "windows+shift+s",
                "windows+l",
            }
            if target.lower() in ALLOWED_SHORTCUTS:
                try:
                    print(f"⌨️ Shortcut sent: {target}")
                    if target.lower() == "windows+l":
                        import ctypes

                        ctypes.windll.user32.LockWorkStation()
                    elif target.lower() in ["volume up", "volume down"]:
                        import re

                        match = re.search(r"\b(\d+)\b", self.raw_spoken_text)
                        presses = 1
                        if match:
                            val = int(match.group(1))
                            presses = max(1, val // 2)
                        for _ in range(presses):
                            keyboard.send(target)
                        print(f"✅ Fired shortcut: {target} (x{presses})")
                    elif target.lower() == "previous track":
                        keyboard.send(target)
                        time.sleep(0.1)
                        keyboard.send(target)
                        print(f"✅ Fired shortcut: {target} (Double press for skip)")
                    else:
                        keyboard.send(target)
                        print(f"✅ Fired shortcut: {target}")
                except Exception as e:
                    print(f"❌ Shortcut Error for '{target}': {e}")
            else:
                print(f"🛡️ Blocked disallowed shortcut: '{target}'")

        # ============================================================
        # FEATURE 2: PC VITALS CHECK
        # ============================================================
        elif action == "check_vitals":
            threading.Thread(target=self.run_check_vitals, daemon=True).start()

        # ============================================================
        # FEATURE 3: DEEP CLIPBOARD ANALYSIS
        # ============================================================
        elif action == "analyze_clipboard":
            threading.Thread(target=self.run_analyze_clipboard, daemon=True).start()

        # ============================================================
        # FEATURE 5: POMODORO TIMER
        # ============================================================
        elif action == "start_pomodoro":
            self.comm.start_pomodoro.emit()

        # ============================================================
        # FEATURE 4: ASYNCHRONOUS TIMERS & REMINDERS
        # ============================================================
        elif action == "set_timer":
            try:
                # LLM outputs target as the seconds string, message as reminder text
                raw_seconds = intent_data.get("target", "0")
                seconds = float(str(raw_seconds).strip())
                message = str(
                    intent_data.get("message", "Hey! Your timer is up!")
                ).strip()
                if not message:
                    message = "Hey! Your timer is up!"

                if seconds <= 0:
                    raise ValueError("Timer must be positive")

                timer = threading.Timer(seconds, self.trigger_reminder, args=[message])
                timer.daemon = True
                timer.start()

                mins = int(seconds) // 60
                secs = int(seconds) % 60
                if mins > 0:
                    time_str = f"{mins} minute{'s' if mins != 1 else ''}"
                    if secs:
                        time_str += f" and {secs} second{'s' if secs != 1 else ''}"
                else:
                    time_str = f"{secs} second{'s' if secs != 1 else ''}"

                confirm = f"Timer set. I'll remind you in {time_str}."
                print(f"⏱️ {confirm}")
                # NOTE: reply was already spoken by execute_intent; don't double-speak here.
                # Just log it. The trigger_reminder call will speak the actual reminder.

            except Exception as e:
                print(f"❌ Timer Error: {e}")
                msg = "Couldn't set that timer. Try again with a clear duration."
                self.comm.show_subtitle.emit(msg)
                self.speak(msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    avatar = ModernClippy()
    avatar.show()

    # Play a randomized startup greeting
    import random
    from PyQt6.QtCore import QTimer
    greetings = [
        "Hello! Ready to be productive?",
        "AURA systems online. How can I help?",
        "Hello, I am AURA, your desktop companion.",
        "Good to see you! All systems are green.",
        "Boot sequence complete. Ready when you are."
    ]
    greeting = random.choice(greetings)
    
    def play_greeting():
        avatar.comm.change_state.emit("speaking")
        avatar.comm.show_subtitle.emit(greeting)
        avatar.speak(greeting)
        
    QTimer.singleShot(1500, play_greeting)

    print("-" * 40)
    print("🚀 DESKTOP ENGINE ASSISTANT IS ONLINE")
    print("-" * 40)

    sys.exit(app.exec())
