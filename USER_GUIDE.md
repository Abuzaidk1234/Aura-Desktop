# AURA User Guide 📖

Welcome to the ultimate guide for using AURA. This document breaks down every feature, keyboard shortcut, voice command, and integration built into your desktop assistant, so you can achieve the perfect workflow.

## 1. Launching & Waking AURA

### How to Start AURA
*   **The Silent Way (Recommended):** If you ran the `AURASetup.exe` installer, just double-click the **AURA** shortcut on your desktop! The installer packages AURA into a neat, silent background process so you never see any ugly CMD windows. AURA can also be configured to start automatically on Windows startup.
*   **The Developer Way:** Run `python main.py` in your terminal if you want to see his real-time logs and thought process.

AURA runs silently in the background and only activates when you need him. 

### Keyboard Shortcuts
*   **Voice Wake-Up (`Ctrl + Space`)**: Instantly opens AURA's ears. Start speaking immediately.
*   **Text Input (`Ctrl + Shift + Space`)**: Opens the sleek text input box. Type your command and press Enter.
*   **The "Brake Pedal" (`Ctrl + Space`)**: If AURA is in the middle of a long explanation and you want him to stop, press this to instantly cut him off and clear his text box.
*   **Toggle Mouse Click-Through (`Ctrl + Shift + C`)**: Toggles whether your mouse clicks pass right through the 3D avatar or interact with it.
*   **Master Kill-Switch (`Ctrl + Shift + Alt + Q`)**: Instantly shuts down the AURA application in an emergency.

### System Tray & The Modular Settings Menu
When AURA is running, he lives in your Windows System Tray (the small arrow in the bottom right of your screen).
*   **Right-Click the AURA Icon**: Opens a context menu to toggle Ghost Mode, Mute the Microphone, or completely exit AURA.
*   **Left-Click the AURA Icon**: Opens the gorgeous, frosted-glass **AURA Settings Window**. The settings are logically divided into tabs:
    *   **Startup Toggle:** Permanently pinned to the top, allowing you to instantly guarantee AURA boots silently when you start Windows.
    *   **Voice & Audio Tab:** Change Wake Words, TTS Voice, Speech Rate, Microphone Sensitivity, and Mic Pause Timeout.
    *   **Positioning Tab:** Customize the exact pixel margins for where the avatar sits above your taskbar.
    *   **Behavior Tab:** Adjust Command Cooldown and Idle Timeout.

### Voice Wake Words
If background listening is enabled, AURA is always listening for these keywords:
`"Aura", "Jarvis", "Buddy", "Computer", "Clippy"`

---

## 2. Windows System Integrations

AURA is deeply wired into your Windows Operating System. He can control apps and manage windows without requiring your mouse.

### Application Control
Just ask AURA to open or close any app. He scans your Start Menu automatically to know what's installed!
*   **"Open Notepad"** or **"Launch Spotify"**
*   **"Close Paint"** or **"Minimize everything"**

### Lightning-Fast Interceptor (Shortcuts & System Controls)
AURA has a built-in "Fast-Path" interceptor for common system commands. If you speak a supported command in **4 words or less**, AURA will completely bypass the AI brain (saving you ~7 seconds of thinking time) and execute it instantly!

*Note: If you chain commands together (e.g., "Play music and lock my PC"), AURA will intelligently route it through the AI to execute both sequentially.*

**Instantly Supported Commands:**
*   **"Take a screenshot"** -> Opens Snipping Tool (`Win + Shift + S`)
*   **"Show my desktop"** -> Minimizes all windows (`Win + D`)
*   **"Open my settings"** -> Launches Windows Settings (`Win + I`)
*   **"Open Action Center"** -> Opens the Action Panel (`Win + A`)
*   **"Lock my PC"** -> Instantly locks your screen (`Win + L`)
*   **"Shut down PC"** -> Instantly triggers the shutdown OSD
*   **"Start Pomodoro"** -> Instantly launches the gorgeous Pomodoro focus timer
*   **"Exit Aura"** -> Instantly closes the assistant

---

## 3. The Invincible Pomodoro Timer & Custom Timers

AURA features a highly aggressive, bulletproof timer system designed for deep focus work.

*   **Pomodoro Mode:** Say **"Start a Pomodoro session"** or **"Start Pomodoro"**. A gorgeous, frosted-glass Pomodoro timer window will appear on your screen to help you track 25-minute focus intervals. This Pomodoro timer is injected natively into Windows rendering at `HWND_TOPMOST` every 500 milliseconds, meaning **no application (even full-screen ones like Paint or Chrome) can ever bury it!**
*   **Ad-hoc Timers:** Say **"Set a timer for 5 minutes to check the oven"**. AURA will start a silent background timer and speak your custom reminder when the time is up.

---

## 4. Web & Media Commands

### Web Browsing
AURA handles browser tabs beautifully, whether you're using Chrome, Edge, or Brave.
*(Note: Short tab commands are automatically Lightning-Fast Intercepted!)*
*   **"Open a new tab"** -> `Ctrl + T`
*   **"Close this tab"** -> `Ctrl + W`
*   **"Reopen the tab I just closed"** -> `Ctrl + Shift + T`
*   **"Search Google for the theory of relativity"** -> Automatically opens your browser and searches Google.

### Media Controls
Control your music and videos effortlessly.
*(Note: Short media commands are automatically Lightning-Fast Intercepted!)*
*   **"Play/Pause my music"** -> `Media Play/Pause`
*   **"Skip to the next track"** -> `Media Next`
*   **"Go back a song"** -> `Media Previous`
*   **"Mute the volume"**, **"Turn it up"**, or **"Turn it down"**

---

## 5. Advanced AI Superpowers

> [!IMPORTANT]
> **The Ollama Requirement (Non-Negotiable)**
> AURA's intelligence relies completely on [Ollama](https://ollama.com/) running the **Llama 3.2** model locally on your machine. This requires a one-time ~2GB model download. 
> 
> *Why is this required?* AURA is designed to be the ultimate private assistant. He reads your clipboard, your screen, and your personal system vitals. By forcing a local AI model instead of a lightweight Cloud API, **your private data physically never leaves your computer.** Without Ollama, AURA has no brain and cannot function.

### The Hybrid "Smart Fallback" Voice Engine (Online vs Offline)
AURA is designed to never fail and constantly monitors your internet connection, displaying an active Network Indicator in the Settings Window.

*   **🟢 When Online (Cloud Voice Engine Active):** He uses Google's lightning-fast Speech-To-Text API for flawless transcription and Microsoft Edge's Neural TTS for an ultra-realistic, deeply expressive voice.
*   **🔴 When Offline (Local Voice Engine Active):** He seamlessly falls back to 100% on-device local engines. He uses the highly optimized C++ **faster-whisper** engine to understand your speech with near-human accuracy, and the **Piper TTS** engine to speak back to you. This ensures that even in a complete internet outage, your assistant remains completely functional without compromising accuracy.

### Clipboard Analysis
AURA can read whatever you currently have copied to your clipboard.
*   **How to use:** Copy a block of code, a math problem, or an email to your clipboard. Then say, **"Analyze this"** or **"Explain my clipboard"**.
*   **What happens:** AURA will read the text, summarize it, and speak the analysis directly to you.

### PC Vitals Check
*   **How to use:** Say **"How's my PC?"** or **"Check vitals"**.
*   **What happens:** AURA hooks into the `psutil` library to scan your CPU utilization, RAM usage, and battery life, then delivers a witty, natural-language health report.


---

## 6. System-Wide Frosted Aesthetics (Mica Explorer Setup)

If you love the blurred, liquid-glass aesthetic used inside AURA's UI, you can force this look across all your other Windows applications.
To do this, you can install **Mica For Everyone (MFE)** or its successor, **Mica Explorer**.

**How to set up Mica Explorer:**
1. Navigate to the official GitHub repository for Mica Explorer or MFE.
2. Download the latest Release installer.
3. Once installed, run the program. It will sit in your system tray.
4. Add a "Global Rule" and set the Backdrop Type to `Acrylic` or `Mica`.
5. This will inject modern blur materials into older Win32 applications (like Explorer, Task Manager, etc.), creating a unified, hyper-modern desktop environment perfectly suited for AURA.

---

## 7. The OSD Shutdown System

When you ask AURA to **"Shut down my PC"**, he won't just yank the plug. 
He summons a massive, gorgeous "Liquid Glass" On-Screen Display (OSD) in the center of your screen with a 20-second countdown.
*   **"CANCEL"**: Aborts the shutdown cleanly.
*   **"Shut down now"**: Bypasses the timer and shuts off the machine instantly.

---

## 8. Known Shortcomings & Tips

To get the most flawless experience out of AURA, keep these quirks in mind:

*   **Multi-Command Phrasing:** AURA is brilliant at executing multiple actions in a row (e.g., *"Open Notepad, move to the left, and then hide"*). However, **do not combine targets**. Saying *"Open Notepad and Paint"* is perfectly fine, but understand that internally AURA executes this sequentially, not simultaneously.
*   **Background Noise Calibration:** When you first boot AURA, he calibrates for 1 second against ambient room noise. Keep the room quiet during boot for optimal listening.
*   **LLM Processing Times:** Complex queries (like analyzing massive clipboards) might take a few seconds longer depending on your GPU/CPU hardware running Ollama. 
