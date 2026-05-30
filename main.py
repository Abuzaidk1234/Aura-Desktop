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
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# --- Configuration Layer ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "wake_words": ["aura", "jarvis", "buddy", "computer", "clippy", "sleepy", "creepy"],
    "idle_timeout_minutes": 5,
    "shutdown_buffer_seconds": 10,
    "energy_threshold": 300,
    "debounce_cooldown_seconds": 2.0,
    "mic_pause_threshold": 1.0,
    "tts_voice": "en-US-ChristopherNeural",
    "tts_rate": "+15%",
    "avatar_left_margin": 20,
    "avatar_tray_safe_right_margin": 340,
    "avatar_bottom_margin": 20,
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            if "aura" not in config.get("wake_words", []):
                config.setdefault("wake_words", []).insert(0, "aura")
                with open(CONFIG_FILE, "w") as fw:
                    json.dump(config, fw, indent=4)
            return config
    except Exception:
        return DEFAULT_CONFIG


CONFIG = load_config()


# --- Thread-Safe Signals ---
class Communicate(QObject):
    toggle_click = pyqtSignal()
    wake_up = pyqtSignal()
    open_text_prompt = pyqtSignal()
    hide_avatar = pyqtSignal()
    show_avatar = pyqtSignal()
    exit_app = pyqtSignal()
    move_avatar = pyqtSignal(str)
    change_state = pyqtSignal(str)
    show_subtitle = pyqtSignal(str)


# --- UI Drag Filter ---
class DragFilter(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.dragPos = None

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.RightButton:
                    self.dragPos = event.globalPosition().toPoint()
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                if self.dragPos and event.buttons() == Qt.MouseButton.RightButton:
                    diff = event.globalPosition().toPoint() - self.dragPos
                    self.window.move(self.window.pos() + diff)
                    self.dragPos = event.globalPosition().toPoint()
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.RightButton:
                    self.dragPos = None
                    if not self.window.is_hidden:
                        self.window.visible_y = self.window.y()
                        self.window.pending_move_x = None
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


# --- The Main Application ---
class ModernClippy(QWidget):
    def __init__(self):
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

        keyboard.add_hotkey("ctrl+shift+c", self.comm.toggle_click.emit)
        keyboard.add_hotkey("ctrl+space", self.comm.wake_up.emit)
        keyboard.add_hotkey("ctrl+shift+space", self.comm.open_text_prompt.emit)
        keyboard.add_hotkey("ctrl+shift+x", self.comm.exit_app.emit)
        keyboard.add_hotkey("ctrl+shift+a", self.panic_abort)
        self.position_in_corner()

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(800)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.on_animation_finished)

        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(CONFIG.get("idle_timeout_minutes", 5) * 60 * 1000)
        self.idle_timer.timeout.connect(self.trigger_idle_sleep)
        self.idle_timer.start()

        self.enforcer_timer = QTimer(self)
        self.enforcer_timer.setInterval(500)
        self.enforcer_timer.timeout.connect(self.enforce_visibility)
        self.enforcer_timer.start()

        self.start_audio_engine()

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

    def show_text_input(self):
        self.showNormal()
        self.raise_()
        text, ok = QInputDialog.getText(self, "Aura Silent Mode", "Type your command:")
        if ok and text.strip():
            print(f"\n⌨️ [Silent Command Detected] ⏩ '{text.strip()}'")
            self.comm.change_state.emit("listening")
            threading.Thread(
                target=self.execute_intent, args=(text.strip(),), daemon=True
            ).start()

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

    def panic_abort(self):
        print("\n🛑 PANIC OVERRIDE TRIGGERED: Aborting all active sequences!")
        try:
            subprocess.Popen("shutdown /a", shell=True)
            print("✅ Sent Windows Abort Shutdown command.")
        except Exception as e:
            print(f"❌ Failed to send abort command: {e}")

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
        self.play_custom_sfx()
        self.anim.setEndValue(QPoint(self.x(), target_y))
        self.anim.start()
        self.comm.change_state.emit("idle")

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
        return str(target).strip()

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
            word in text for word in ["pc", "windows", "machine", "laptop"]
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

        if action == "media_control":
            if "unmute" in raw_lower:
                return "unmute"
            if "mute" in raw_lower:
                return "mute"
            if any(word in raw_lower for word in ["up", "increase", "raise", "louder"]):
                return "up"
            if any(
                word in raw_lower for word in ["down", "decrease", "lower", "quieter"]
            ):
                return "down"

        return ""

    def extract_commands_from_raw(self):
        raw_lower = self.raw_spoken_text.lower().strip()
        commands = []

        patterns = [
            (
                "open_app",
                r"\b(?:open|launch|start|run)\b\s+(.+?)(?=\s+(?:and|then)\s+(?:move|go|slide|shift|hide|close|kill|quit|search|google|look up|find|volume|mute|unmute)\b|$)",
            ),
            (
                "close_app",
                r"\b(?:close|kill|quit)\b\s+(.+?)(?=\s+(?:and|then)\s+(?:move|go|slide|shift|hide|open|launch|start|run|search|google|look up|find|volume|mute|unmute)\b|$)",
            ),
            (
                "web_search",
                r"\b(?:search|google|look up|find)\b(?:\s+for)?\s+(.+?)(?=\s+(?:and|then)\s+(?:move|go|slide|shift|hide|open|launch|start|run|close|kill|quit|volume|mute|unmute)\b|$)",
            ),
        ]

        for action, pattern in patterns:
            for match in re.finditer(pattern, raw_lower):
                target = self.clean_raw_target(match.group(1))
                if target:
                    commands.append({"action": action, "target": target})

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

        if "unmute" in raw_lower:
            commands.append({"action": "media_control", "target": "unmute"})
        elif "mute" in raw_lower:
            commands.append({"action": "media_control", "target": "mute"})
        elif any(word in raw_lower for word in ["volume up", "louder"]):
            commands.append({"action": "media_control", "target": "up"})
        elif any(word in raw_lower for word in ["volume down", "quieter"]):
            commands.append({"action": "media_control", "target": "down"})

        return commands

    def clean_raw_target(self, target):
        target = re.sub(r"\b(?:please|for me)\b", "", target).strip()
        target = re.sub(r"\s+", " ", target)
        return target.strip(" .,!?")

    def merge_commands(self, primary, inferred):
        merged = []
        seen = set()
        no_target_actions = {"hide", "exit", "shutdown_pc", "chat"}
        for cmd in [*inferred, *primary]:
            action = cmd.get("action", "")
            target = self.normalize_target(cmd.get("target", ""))
            if action in no_target_actions:
                target = ""
            key = (action, target)
            if action and key not in seen:
                merged.append({"action": action, "target": target})
                seen.add(key)
        return self.prune_conflicting_commands(merged)

    def prune_conflicting_commands(self, commands):
        raw_lower = self.raw_spoken_text.lower().strip()
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
                print(f"⚠️ Dropping search hallucination as app: {target}")
                continue
            pruned.append(cmd)
        return pruned

    def normalize_commands(self, commands):
        normalized = []
        if isinstance(commands, dict):
            commands = [commands]
        if not isinstance(commands, list):
            return normalized

        no_target_actions = {"hide", "exit", "shutdown_pc", "chat"}
        target_actions = {
            "open_app",
            "close_app",
            "move_avatar",
            "media_control",
            "web_search",
        }

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
            elif action == "media_control":
                media_replies = {
                    "mute": "muted",
                    "unmute": "unmuted",
                    "up": "volume up",
                    "down": "volume down",
                }
                parts.append(media_replies.get(target, "media adjusted"))
            elif action == "exit":
                parts.append("see you")
            elif action == "shutdown_pc":
                parts.append("shutting down")

        if not parts:
            return "There you go."
        if len(parts) == 1:
            return f"{parts[0].capitalize()}."
        if len(parts) == 2:
            return f"{parts[0].capitalize()} and {parts[1]}."
        return f"{', '.join(parts[:-1]).capitalize()}, and {parts[-1]}."

    def execute_commands(self, commands):
        threads = []
        for cmd in commands:
            if not isinstance(cmd, dict):
                print(f"⚠️ Skipping malformed command format: {cmd}")
                continue
            worker = threading.Thread(
                target=self.execute_action, args=(cmd,), daemon=True
            )
            worker.start()
            threads.append(worker)

        for worker in threads:
            worker.join(timeout=0.5)

    def clean_chat_reply(self, reply):
        reply = re.sub(r"\s+", " ", str(reply or "").replace("\u200b", "")).strip()
        if not reply:
            return "Tiny blank."
        words = reply.split()
        if len(words) > 14:
            return " ".join(words[:14]).strip("\"'").rstrip(".,;:") + "."
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
        You are Aura, Abuzaid's quirky, snappy desktop assistant. Return ONLY valid JSON:
        {{"reply":"...","commands":[{{"action":"...","target":"..."}}]}}.
        No markdown, no notes, no extra keys. reply is always a string. commands is
        always a list.

        Context: time={current_time}; date={current_date}; active_screen="{active_window}";
        clipboard="{clip_text}".

        Reply rule: keep it natural and brief, not random sound effects. Good style:
        "Paint opened.", "Moving.", "There you go.", "As you wish.", "Happy painting."
        Avoid cringe one-word noises like pop, zip, zap, zing. For chat, answer briefly
        in Aura's voice. If asked who created you, say Abuzaid. If asked hu r u, say I am Aura, your digital assistant.
        when asked to hide, Go to sleep, go away, get out. give hide your self and give natural response like "going", "I'll be back", "ok", "as you wish".

        Actions: open_app opens apps. close_app closes apps; target "all" means
        minimize everything. hide hides Aura for "hide", "get out", "go away", or
        "go to sleep". exit closes Aura only; plain "shutdown" means exit. shutdown_pc
        turns off Windows only when the user explicitly says "shutdown pc/windows/laptop".
        move_avatar moves Aura; target
        exactly "left" or "right". media_control targets exactly "mute", "unmute",
        "up", or "down". web_search targets the exact search phrase. chat uses no
        command.

        Every command target MUST be a plain string. Never use null, arrays, or objects.
        Use active_screen or clipboard only when explicitly asked. For clipboard, give
        a short summary, not raw pasted text. If target is missing or unclear, commands=[]
        and ask a tiny clarification. Never invent targets.
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

    def find_and_launch_app(self, app_name):
        app_name = app_name.lower().strip()

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

        elif action == "media_control":
            try:
                if target in ["mute", "unmute"]:
                    keyboard.send("volume mute")
                elif target == "up":
                    for _ in range(5):
                        keyboard.send("volume up")
                elif target == "down":
                    for _ in range(5):
                        keyboard.send("volume down")
            except Exception as e:
                print(f"❌ Volume Error: {e}")

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
                for word in ["pc", "windows", "machine", "laptop"]
            ):
                print("🛡️ FAILSAFE TRIGGERED: Blocked accidental PC shutdown!")
                self.is_alive = False
                self.comm.exit_app.emit()
                return

            buffer_time = CONFIG.get("shutdown_buffer_seconds", 10)
            subprocess.Popen(f"shutdown /s /t {buffer_time}", shell=True)
            print(f"⚠️ PC shutting down in {buffer_time} seconds!")
            print("👉 Press Ctrl+Shift+A FAST to abort!")

            # Note: We DO NOT exit the app here.
            # If we exit the app, your python keyboard listener dies, and you can't press Ctrl+Shift+A!


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    avatar = ModernClippy()
    avatar.show()

    print("-" * 40)
    print("🚀 DESKTOP ENGINE ASSISTANT IS ONLINE")
    print("-" * 40)

    sys.exit(app.exec())
