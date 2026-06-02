# AURA: Your Elegant Desktop Assistant 🌌

Welcome to AURA, a cutting-edge, locally-run AI desktop assistant built to be fast, beautiful, and relentlessly helpful. Unlike generic clunky chat boxes, AURA lives elegantly on your desktop as an interactive 3D avatar with a gorgeous "liquid glass" UI. 

Powered entirely by local AI models (via Ollama) and Edge TTS, AURA respects your privacy while delivering incredible capabilities. 

## ✨ Key Features
- **3D Avatar & Liquid Glass UI**: A beautiful, transparent overlay that sits natively on your Windows desktop. 
- **Voice & Text Interactions**: Wake AURA with your voice (say "Hey Aura") or use lightning-fast keyboard shortcuts (`Ctrl+Space` for voice, `Ctrl+Shift+Space` for text).
- **Deep Windows Integration**: AURA can launch apps, search the web, manage active windows, and execute system-level hotkeys without you ever touching the mouse.
- **Context-Aware Superpowers**:
  - **Clipboard Analysis:** Copy anything and ask "analyze this" to get a fast, smart AI summary.
  - **System Vitals:** Ask "how's my PC?" to get a real-time CPU, RAM, and Battery health check.
  - **Smart Pomodoro & Timers:** Set deep-focus Pomodoro sessions or ad-hoc custom timers with vocal reminders.
- **Smart Shutdowns**: Features a custom-designed, visually stunning OSD for PC shutdowns that you can abort easily if you change your mind.
- **100% Local Brain**: AURA relies completely on Ollama for intelligence. Your clipboard, your screen, and your questions never leave your computer.
- **Ultimate Control**: A hardware-level interrupt (`Ctrl+Space` to hit the brakes on audio) and a master kill-switch (`Ctrl+Shift+Alt+Q` to terminate) guarantees AURA is always under your control.

## 🚀 Installation & Setup

1. **Install Python 3.10+**  
   Ensure you have a modern version of Python installed on your Windows machine.

2. **Install Ollama**  
   Download and install [Ollama](https://ollama.com/) so AURA has a brain. 
   Once installed, open a terminal and pull the Llama 3.2 model:
   ```bash
   ollama pull llama3.2
   ```

3. **Clone the Repository & Install Dependencies**
   ```bash
   git clone https://github.com/yourusername/aura.git
   cd aura
   pip install -r requirements.txt
   ```

4. **Launch AURA**
   ```bash
   python main.py
   ```
   *Note: AURA is designed specifically for Windows environments and utilizes Windows-specific APIs for deep OS integration.*

For a deep dive into every command, hotkey, and feature, check out the [User Guide](USER_GUIDE.md).

---
*Built with ❤️ for a smarter, sleeker desktop experience.*
