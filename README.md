<div align="center">
  <h1>🌌 Aura Desktop</h1>
  <p><b>A privacy-first, voice-activated desktop agent powered by local LLMs.</b></p>
  
  [![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
  [![PyQt6](https://img.shields.io/badge/UI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
  [![Ollama](https://img.shields.io/badge/AI-Ollama-black.svg)](https://ollama.com/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
</div>

<br>

Inspired by the nostalgia of the original Windows Clippy, **Aura** has evolved into a robust, modern system agent. Instead of a simple chatbot, Aura actively manages your PC—opening applications, moving across your screen, and executing complex workflows—all while keeping your data 100% offline.

---

## ✨ Core Capabilities

### 🎙️ Ambient Intelligence
* **Voice Activation:** Always-on listening with customizable wake words.
* **Conversational UI:** Backed by **Llama 3.2**, Aura understands natural language and intent, not just rigid commands.

### ⚙️ Native System Automation
* **Application Control:** Launch apps via shortcuts or aliases, and robustly terminate active processes.
* **Workspace Management:** Instantly clear your desktop with a "Close All" command.
* **Hardware Integration:** Control media volume and initiate system shutdown sequences directly via voice.

### 🎨 Modern & Non-Intrusive UI
* **Dynamic State:** The transparent, frameless UI moves around your screen based on commands.
* **Boss Key:** Tell Aura to "hide" and she gracefully exits the screen.
* **Context Aware:** Reads active window states and clipboard data for smarter, localized responses.

---
## ⌨️ Global Keyboard Shortcuts

Aura operates system-wide, meaning you can control her from anywhere using these global hotkeys, regardless of what app you currently have in focus:

| Shortcut | Action | Description |
| :--- | :--- | :--- |
| **`Ctrl + Space`** | **Wake / Brake** | Instantly wakes Aura to listen, or forcefully interrupts her if she is currently speaking. |
| **`Ctrl + Shift + Space`** | **Silent Mode** | Opens a text prompt so you can type a command instead of speaking it out loud. |
| **`Ctrl + Shift + C`** | **Toggle Ghost Mode** | Switches the avatar between being a solid window and a transparent, click-through overlay. |
| **`Ctrl + Shift + X`** | **Force Quit** | Instantly terminates the Aura desktop agent. |
| **`Ctrl + Shift + A`** | **Panic Abort** | Emergency brake to cancel a Windows PC shutdown if triggered accidentally. |

## 🛠️ The Tech Stack

| Component | Technology |
| :--- | :--- |
| **Backend** | Python, `psutil`, `keyboard`, Windows MCI API |
| **Frontend/UI** | PyQt6, QtWebEngine |
| **AI / NLP** | Ollama (Llama 3.2 Local Model) |
| **Audio Engine** | SpeechRecognition, Edge-TTS |

---

## 📦 Quick Start Guide

**1. Setup Local AI**
Ensure you have [Ollama](https://ollama.com/) installed and pull the required model:
```bash
ollama run llama3.2
```

**2. Clone the Repository**
```bash
git clone [https://github.com/Abuzaidk1234/Aura-Desktop.git](https://github.com/Abuzaidk1234/Aura-Desktop.git)
cd Aura-Desktop
```

**3. Install Dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure Environment**
```bash
rename config.template.json to config.json
```

**5. Launch the Engine**
```bash
python main.py
```
