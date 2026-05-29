# Aura-Desktop
Aura Desktop is a privacy-first, voice-activated system agent powered by local LLMs. Inspired by the nostalgia of Clippy, Aura takes it to the next level with a modern 3D WebGL avatar, native system automation, and 100% offline processing.
# 🌌 Aura Desktop

A privacy-first, voice-activated desktop agent powered entirely by local LLMs. 

Inspired by the nostalgia of the original Windows Clippy, Aura takes the concept of a desktop companion into the modern era. Instead of just another retro chat window, Aura is a true **system agent**. It listens ambiently for a wake word, processes complex commands using local AI, and actively manages your PC—opening applications, closing tasks, and moving around your screen—all without sending a single byte of data to the cloud.

## ✨ Core Features

* 🎙️ **Ambient Voice Engine:** Say "Jarvis", "Buddy", or "Computer" from across the room to wake up the assistant.
* ⚙️ **Native System Automation:** Tell it to "Open Chrome," "Close Calculator," or "Hide everything" (triggers a safe Boss Key minimize).
* 🧠 **Local AI Processing:** Uses Ollama to parse intents offline. Built-in failsafes intercept AI hallucinations to prevent rogue actions.
* 🎨 **Modern 3D UI:** A transparent, frameless PyQt6 window rendering a custom interactive 3D WebGL avatar with frosted-glass dynamic subtitles and audio earcons.
* 🛡️ **Ironclad Privacy:** 100% offline. No telemetry, no API keys, and a built-in "Do Not Disturb" system tray mute toggle.

## 🛠️ Tech Stack

* **Backend:** Python 3.11 (SpeechRecognition, psutil, winsound)
* **Desktop UI:** PyQt6 & QtWebEngine
* **3D Rendering:** Three.js (WebGL) + HTML5/CSS3
* **AI Engine:** Ollama (Llama 3.2 3B recommended)

## 📦 Developer Quick Start

1. **Install Ollama:** Download and install [Ollama](https://ollama.com/), then pull the required model:
   ```bash
   ollama run llama3.2
Clone the Repository:

Bash
git clone [https://github.com/Abuzaidk1234/Aura-Desktop.git](https://github.com/Abuzaidk1234/Aura-Desktop.git)
cd Aura-Desktop
Install Dependencies:

Bash
pip install pyqt6 PyQt6-WebEngine SpeechRecognition pyaudio psutil keyboard ollama
Launch the Engine:

Bash
python main.py
(Note: A one-click Windows installer .exe is planned for future releases once core development is fully finalized.)
