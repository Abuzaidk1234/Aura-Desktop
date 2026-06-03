import os
import sys
import json

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(base_dir, "config.json")
DEFAULT_CONFIG = {
    "wake_words": ["aura", "jarvis", "buddy", "computer", "clippy", "sleepy", "creepy", "ora", "ara", "laura", "are a"],
    "idle_timeout_minutes": 5,
    "shutdown_buffer_seconds": 20,
    "energy_threshold": 300,
    "debounce_cooldown_seconds": 2.0,
    "mic_pause_threshold": 1.5,
    "tts_voice": "en-US-ChristopherNeural",
    "tts_rate": "+15%",
    "avatar_left_margin": 20,
    "avatar_tray_safe_right_margin": 270,
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

def save_config(new_config):
    global CONFIG
    CONFIG.update(new_config)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(CONFIG, f, indent=4)
    except Exception as e:
        print(f"Failed to save config: {e}")

CONFIG = load_config()
