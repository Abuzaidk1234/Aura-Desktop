import json
import os
import subprocess
import sys
import threading
import time
import winsound

import keyboard
import ollama
import psutil
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
    QMenu,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# --- Configuration Layer ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "wake_words": ["jarvis", "buddy", "computer", "clippy", "sleepy", "creepy"],
    "idle_timeout_minutes": 5,
    "shutdown_buffer_seconds": 10,
    "energy_threshold": 300,
    "debounce_cooldown_seconds": 2.0,
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG


CONFIG = load_config()


# --- Thread-Safe Signals ---
class Communicate(QObject):
    toggle_click = pyqtSignal()
    wake_up = pyqtSignal()
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
                self.window.visible_y = self.window.y()
                return True
        return super().eventFilter(obj, event)


# --- The Main Application ---
class ModernClippy(QWidget):
    def __init__(self):
        super().__init__()

        self.is_interactive = False
        self.force_wake = False
        self.is_hidden = False
        self.is_muted = False
        self.visible_y = 0
        self.is_alive = True
        self.pending_move_x = None
        self.last_command_time = 0
        self.last_command_text = ""
        self.raw_spoken_text = ""

        # --- THE FIX 1: Changed Tool to ToolTip so Windows never minimizes it! ---
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.ToolTip
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
        self.comm.hide_avatar.connect(self.animate_hide)
        self.comm.show_avatar.connect(self.animate_show)
        self.comm.exit_app.connect(QApplication.instance().quit)
        self.comm.move_avatar.connect(self.animate_move)
        self.comm.change_state.connect(self.update_ui_state)
        self.comm.show_subtitle.connect(self.display_subtitle_text)

        keyboard.add_hotkey("ctrl+shift+c", self.comm.toggle_click.emit)
        keyboard.add_hotkey("ctrl+space", self.comm.wake_up.emit)
        keyboard.add_hotkey("ctrl+shift+x", self.panic_abort)

        self.position_in_corner()

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(800)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.on_animation_finished)

        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(CONFIG.get("idle_timeout_minutes", 5) * 60 * 1000)
        self.idle_timer.timeout.connect(self.animate_hide)
        self.idle_timer.start()

        self.start_audio_engine()

    def update_ui_state(self, state_name):
        self.browser.page().runJavaScript(
            f"if (typeof setClippyState === 'function') {{ setClippyState('{state_name}'); }}"
        )

    def display_subtitle_text(self, text):
        safe_text = text.replace('"', '\\"').replace("\n", " ")
        self.browser.page().runJavaScript(
            f"if (typeof showSubtitle === 'function') {{ showSubtitle(\"{safe_text}\"); }}"
        )

    def play_earcon(self, sound_type):
        def sound_worker():
            try:
                if sound_type == "wake":
                    winsound.Beep(988, 80)
                    winsound.Beep(1318, 120)
                elif sound_type == "sleep":
                    winsound.Beep(1175, 100)
                    winsound.Beep(880, 150)
            except Exception:
                pass

        threading.Thread(target=sound_worker, daemon=True).start()

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
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.width - 20
        y = screen.height() - self.height
        self.visible_y = y
        self.move(x, y)

    def toggle_ghost_mode(self):
        self.is_interactive = not self.is_interactive
        if self.is_interactive:
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
            print("Avatar is now INTERACTABLE (Solid)")
        else:
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
            print("Avatar is now CLICK-THROUGH (Ghost)")
        self.show()

    def animate_hide(self):
        screen_height = QApplication.primaryScreen().availableGeometry().height()
        target_y = screen_height + 50

        if self.y() >= target_y:
            self.is_hidden = True
            return

        print("🫣 Avatar is hiding...")
        self.is_hidden = True

        self.anim.setEndValue(QPoint(self.x(), target_y))
        self.anim.start()
        self.comm.change_state.emit("idle")

    def animate_show(self):
        self.idle_timer.start()

        if not self.is_hidden and self.y() <= self.visible_y:
            return

        print("👀 Avatar popped up!")
        self.is_hidden = False

        self.anim.setEndValue(QPoint(self.x(), self.visible_y))
        self.anim.start()

    def animate_move(self, direction):
        screen = QApplication.primaryScreen().availableGeometry()

        if "left" in direction.lower():
            self.pending_move_x = 20
        else:
            self.pending_move_x = screen.width() - self.width - 20

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

    # ==========================================
    # --- THE AUDIO ENGINE ---
    # ==========================================

    def start_audio_engine(self):
        self.is_processing = False
        threading.Thread(target=self.audio_loop, daemon=True).start()

    def trigger_hotkey(self):
        if self.is_muted:
            return
        self.force_wake = True
        self.comm.show_avatar.emit()

    def audio_loop(self):
        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 0.5

        with sr.Microphone() as source:
            print("🎧 Calibrating background noise on Default Microphone...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            recognizer.energy_threshold = CONFIG.get("energy_threshold", 300)

            wake_list = CONFIG.get("wake_words", ["jarvis", "buddy"])
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
                            self.play_earcon("wake")
                            print("\n[Hotkey] 🎤 Yes? I'm listening...")
                            self.comm.change_state.emit("listening")
                            self.process_command(recognizer, source)
                            self.is_processing = False

                            if not self.is_alive:
                                break
                            print(
                                f"\n🎧 Going back to sleep. Say {wake_display} to wake me."
                            )
                            self.play_earcon("sleep")
                            self.comm.change_state.emit("idle")
                        continue

                    if not self.is_processing:
                        audio = recognizer.listen(
                            source, timeout=1, phrase_time_limit=3
                        )
                        wake_text = recognizer.recognize_google(audio).lower()

                        if any(word in wake_text for word in wake_list):
                            self.is_processing = True
                            self.play_earcon("wake")
                            self.comm.show_avatar.emit()
                            self.comm.change_state.emit("listening")

                            clean_text = wake_text.replace("hey", "")
                            for word in wake_list:
                                clean_text = clean_text.replace(word, "")
                            clean_text = clean_text.strip()

                            if len(clean_text) > 3:
                                print(
                                    f"\n[Continuous Command Detected] ⏩ '{clean_text}'"
                                )
                                self.execute_intent(clean_text)
                            else:
                                print(f"\n[Heard Wake Word] 🎤 Yes? I'm listening...")
                                self.process_command(recognizer, source)

                            self.is_processing = False

                            if not self.is_alive:
                                break
                            print(
                                f"\n🎧 Going back to sleep. Say {wake_display} to wake me."
                            )
                            self.play_earcon("sleep")
                            self.comm.change_state.emit("idle")

                except sr.WaitTimeoutError:
                    pass
                except sr.UnknownValueError:
                    pass
                except Exception:
                    pass

            print("🛑 Audio Engine cleanly terminated.")

    def process_command(self, recognizer, source):
        try:
            recognizer.pause_threshold = 2.0
            audio_data = recognizer.listen(source, timeout=5, phrase_time_limit=15)
            self.comm.change_state.emit("processing")
            print("Processing command...")
            command_text = recognizer.recognize_google(audio_data)
            print(f"✅ You said: '{command_text}'")
            self.execute_intent(command_text)

        except sr.WaitTimeoutError:
            print("❌ I didn't hear a command in time.")
        except sr.UnknownValueError:
            print("❌ Could not understand the command.")
        except Exception as e:
            print(f"❌ Mic Error: {e}")
        finally:
            recognizer.pause_threshold = 0.5

    # ==========================================
    # --- THE BRAIN & HANDS ---
    # ==========================================

    def execute_intent(self, command_text):
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

        parsed_data = self.parse_intent(command_text)
        if parsed_data:
            reply = parsed_data.get("reply", "Executing commands!")
            commands = parsed_data.get("commands", [])
            print(f"🤖 [DEBUG] Raw AI Output -> Commands Array: {commands}")

            # --- THE FIX 2: Check for rogue keys if the array is empty ---
            if not commands and "action" in parsed_data:
                # LLM hallucinates "program", "app", or "name" instead of "target"
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

            if not commands:
                raw_lower = self.raw_spoken_text.lower().strip()
                if "open" in raw_lower or "launch" in raw_lower:
                    tgt = raw_lower.replace("open", "").replace("launch", "").strip()
                    commands = [{"action": "open_app", "target": tgt}]
                    print(
                        f"🛡️ FAILSAFE ACTIVATED: Python manually extracted 'Open {tgt}'"
                    )
                elif "close" in raw_lower or "kill" in raw_lower:
                    tgt = raw_lower.replace("close", "").replace("kill", "").strip()
                    commands = [{"action": "close_app", "target": tgt}]
                    print(
                        f"🛡️ FAILSAFE ACTIVATED: Python manually extracted 'Close {tgt}'"
                    )
                elif "hide" in raw_lower or "go away" in raw_lower:
                    commands = [{"action": "hide", "target": ""}]
                    print(
                        f"🛡️ FAILSAFE ACTIVATED: Python triggered manual Hide command."
                    )

            print(f"🗣️ AI says: {reply}")
            self.comm.show_subtitle.emit(reply)

            if not commands:
                print("⚠️ AI didn't format any actionable commands. Try rephrasing.")

            for cmd in commands:
                self.execute_action(cmd)
                time.sleep(1.0)

    def parse_intent(self, user_text):
        self.comm.change_state.emit("thinking")
        print("🧠 AI is thinking...")

        system_prompt = """
        You are the brain of a desktop assistant. Extract the intent from the user's command.
        Output ONLY valid JSON.

        Categories:
        1. "open_app" (Open a program)
        2. "close_app" (Close, quit, or kill a running program)
        3. "hide" (The user wants you to visually drop below the screen or minimize. Use this for "go away", "get out", "hide yourself", "minimize")
        4. "exit" (STRICTLY for shutting down the assistant app itself)
        5. "shutdown_pc" (EXTREMELY STRICT: Only use if the user asks to turn off their physical machine)
        6. "move_avatar" (Move your position on screen. Target: "left" or "right")
        7. "chat" (General conversation)

        CRITICAL REQUIREMENT:
        - The target parameter MUST be named "target". NEVER use keys like 'program', 'app', or 'name'.
        - You must format the output exactly like this example structure.

        EXAMPLE INPUT: "open ms paint and move left"
        EXAMPLE OUTPUT:
        {
            "reply": "Opening MS Paint and moving to the left!",
            "commands": [
                {"action": "open_app", "target": "ms paint"},
                {"action": "move_avatar", "target": "left"}
            ]
        }
        """
        try:
            response = ollama.chat(
                model="llama3.2",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
            )
            raw_output = response["message"]["content"].strip()
            return json.loads(raw_output)
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
        action = intent_data.get("action", "").lower()
        # Fallback just in case the AI still sneaks a bad key past the JSON parser
        target = (
            intent_data.get("target")
            or intent_data.get("program")
            or intent_data.get("app")
            or ""
        )

        if action in ["open_app", "open", "launch", "run", "start"] and target:
            target_clean = target.lower()
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
            target_clean = target.lower().strip()
            try:
                if target_clean in ["all", "all apps", "everything", "every app"]:
                    print("🛡️ SAFETY OVERRIDE: Executing 'Boss Key' instead...")
                    keyboard.send("windows+d")
                    print("✅ Minimized all windows safely.")
                elif "explorer" in target_clean or "folder" in target_clean:
                    ps_command = "(New-Object -comObject Shell.Application).Windows() | ForEach-Object {$_.Quit()}"
                    subprocess.Popen(f'powershell -command "{ps_command}"', shell=True)
                    print("✅ Safely closed open File Explorer windows.")
                else:
                    terminated_any = False
                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            p_name = proc.info["name"].lower()
                            if (
                                target_clean in p_name
                                or target_clean.replace(" ", "") in p_name
                            ):
                                proc.terminate()
                                print(
                                    f"✅ Dynamically matched and closed target process: {proc.info['name']}"
                                )
                                terminated_any = True
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue

                    if not terminated_any:
                        subprocess.Popen(
                            f'taskkill /F /IM "{target_clean}.exe" /T', shell=True
                        )
                        print(
                            f"⚠️ Process search ambiguous, executed fallback string hunt for: {target_clean}.exe"
                        )
            except Exception as e:
                print(f"❌ Failed to close {target}: {e}")

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
                for word in ["pc", "computer", "windows", "machine", "laptop"]
            ):
                print("🛡️ FAILSAFE TRIGGERED: Blocked accidental PC shutdown!")
                self.is_alive = False
                self.comm.exit_app.emit()
                return

            buffer = CONFIG.get("shutdown_buffer_seconds", 10)
            print(
                f"⚠️ WARNING: Initiating Windows PC Shutdown sequence in {buffer} seconds..."
            )
            print("👉 Press Ctrl+Shift+X to execute a cancellation abort!")
            self.is_alive = False
            subprocess.Popen(f"shutdown /s /t {buffer}", shell=True)
            self.comm.exit_app.emit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    avatar = ModernClippy()
    avatar.show()

    print("-" * 40)
    print("🚀 DESKTOP ENGINE ASSISTANT IS ONLINE")
    print("-" * 40)

    sys.exit(app.exec())
