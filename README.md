# A.U.R.A: Advanced Utility & Resource Assistant 🌌

Welcome to AURA, a cutting-edge, locally-run AI desktop assistant built to be fast, beautiful, and relentlessly helpful. Unlike generic clunky chat boxes, AURA lives elegantly on your desktop as an interactive 3D avatar with a gorgeous "liquid glass" UI. 

Powered entirely by local AI models (via Ollama) and a Hybrid Voice Engine, AURA respects your privacy while delivering incredible capabilities regardless of your internet connection. 

### 🛠️ Tech Stack
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/PyQt6-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)
![HTML/CSS](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![Three.js](https://img.shields.io/badge/Three.js-000000?style=for-the-badge&logo=threedotjs&logoColor=white)
![Blender](https://img.shields.io/badge/Blender-F5792A?style=for-the-badge&logo=blender&logoColor=white)

AURA is built on an incredible blend of technologies:
*   **Blender & Three.js:** The 3D avatar was modeled and animated in Blender, exported as a GLB, and seamlessly integrated into the desktop using Three.js inside a QWebEngineView.
*   **HTML/CSS & PyQt6:** AURA uses a hybrid UI approach. The raw desktop compositing and window logic (frameless tool windows, win32 API hooks) is handled by PyQt6, while the gorgeous frosted glass menus, animations, and overlays are styled entirely with raw HTML and CSS.
*   **Local AI Brain:** Driven entirely by `ollama` utilizing the lightweight but highly intelligent `llama3.2` LLM model.
*   **Hybrid Voice Engines:** Uses Google Speech Recognition and Edge TTS (Online), but seamlessly falls back to the blazing-fast C++ `faster-whisper` and `piper-tts` engines when your internet drops.

## ✨ Key Features
- **3D Avatar & Liquid Glass UI**: A beautiful, transparent overlay that sits natively on your Windows desktop. 
- **Voice & Text Interactions**: Wake AURA with your voice (say "Hey Aura") or use lightning-fast keyboard shortcuts (`Ctrl+Space` for voice, `Ctrl+Shift+Space` for text).
- **Deep Windows Integration**: AURA can launch apps, search the web, manage active windows, and execute system-level hotkeys without you ever touching the mouse.
- **Context-Aware Superpowers**:
  - **Clipboard Analysis:** Copy anything and ask "analyze this" to get a fast, smart AI summary.
  - **System Vitals:** Ask "how's my PC?" to get a real-time CPU, RAM, and Battery health check.

- **The Invincible Pomodoro Timer**: A massive highlight for students and developers! Say "Start Pomodoro" to instantly launch a gorgeous, frosted-glass Pomodoro timer window on your desktop to track deep-focus intervals. It is injected natively into Windows rendering at `HWND_TOPMOST` every 500 milliseconds, meaning **no application (even full-screen ones like Paint or Chrome) can ever bury it!**
- **Smart Shutdowns**: Features a custom-designed, visually stunning OSD for PC shutdowns that you can abort easily if you change your mind.
- **Hybrid "Smart Fallback" Voice Engine**: AURA uses high-fidelity cloud APIs (Google STT / Edge TTS) when connected to the internet, but seamlessly falls back to 100% offline, on-device AI engines (`faster-whisper` & Piper TTS) if you lose connection.
- **100% Local Brain**: AURA relies completely on Ollama for intelligence. Your clipboard, your screen, and your questions never leave your computer.
- **Ultimate Control**: A hardware-level interrupt (`Ctrl+Space` to hit the brakes on audio) and a master kill-switch (`Ctrl+Shift+Alt+Q` to terminate) guarantees AURA is always under your control.

## 🚀 Installation & Setup

1. **Install Python 3.10+**  
   Ensure you have a modern version of Python installed on your Windows machine.

2. **Install Ollama & Llama 3.2 (MANDATORY)**  
   > [!IMPORTANT]
   > **AURA has no brain without Ollama.** You *must* download and install [Ollama](https://ollama.com/). Once installed, open a terminal and pull the Llama 3.2 model:
   > ```bash
   > ollama pull llama3.2
   > ```
   > *Note: This will download a ~2GB local AI model to your hard drive. This is non-negotiable. AURA does not use cloud APIs (like ChatGPT). He processes everything locally to guarantee zero latency and 100% privacy for your clipboard and system data.*

3. **Clone the Repository & Install Dependencies**
   ```bash
   git clone https://github.com/Abuzaidk1234/Aura-Desktop.git
   cd Aura-Desktop
   pip install -r requirements.txt
   ```

4. **Compile the Setup Installer (Optional but Recommended)**  
   To create a professional, shareable Windows installer for AURA, simply double-click the `build_installer.bat` file in the project folder. If you have the Inno Setup Compiler (`iscc`) installed in your PATH, it will automatically build `AURASetup.exe` for you!

## 🧊 The Frosted Aesthetic (Mica For Everyone)

If you absolutely love AURA's frosted glass aesthetic and want to apply it system-wide to your other Windows applications, we highly recommend utilizing **Mica For Everyone (MFE)** or **Mica Explorer**.
These tools allow you to force Windows 10/11 to render Acrylic or Mica blur behind legacy win32 applications, perfectly complementing AURA's design language.

Check out the [Mica For Everyone GitHub](https://github.com/MicaForEveryone/MicaForEveryone) and [explorer Blur Mica GitHub](https://github.com/Maplespe/ExplorerBlurMica) to install it and customize your system!

For a deep dive into every command, hotkey, and feature, check out the [User Guide](USER_GUIDE.md).

---

### 📎 A Homage to Clippy
While AURA is a massive leap forward into the era of local AI and liquid glass UI, this project began as a spiritual homage to the original desktop companion: **Microsoft Clippy**. Although absolutely nothing of the original Clippy's simple style remains in AURA's hyper-advanced codebase, the vision of a genuinely helpful, ever-present desktop assistant lives on here. We even kept his official icon as a tribute!

Built with ❤️ for a smarter, sleeker desktop experience.
