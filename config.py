import os
import json

CONFIG_FILE = "config.json"
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

CONFIG = load_config()
