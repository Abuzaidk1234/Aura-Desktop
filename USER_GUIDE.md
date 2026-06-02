# AURA User Guide 📖

Welcome to the ultimate guide for using AURA. This document breaks down every feature, keyboard shortcut, voice command, and integration built into your desktop assistant, so you can achieve the perfect workflow.

## 1. Waking & Interacting with AURA

AURA runs silently in the background and only activates when you need her. 

### Keyboard Shortcuts
*   **Voice Wake-Up (`Ctrl + Space`)**: Instantly opens AURA's ears. Start speaking immediately.
*   **Text Input (`Ctrl + Shift + Space`)**: Opens the sleek text input box. Type your command and press Enter.
*   **The "Brake Pedal" (`Ctrl + Space`)**: If AURA is in the middle of a long explanation and you want her to stop, press this to instantly cut her off and clear her text box.
*   **Toggle Mouse Click-Through (`Ctrl + Shift + C`)**: Toggles whether your mouse clicks pass right through the 3D avatar or interact with it.
*   **Master Kill-Switch (`Ctrl + Shift + Alt + Q`)**: Instantly shuts down the AURA application in an emergency.

### Voice Wake Words
If background listening is enabled, AURA is always listening for these keywords:
`"Aura", "Jarvis", "Buddy", "Computer", "Clippy"`

---

## 2. Windows System Integrations

AURA is deeply wired into your Windows Operating System. She can control apps and manage windows without requiring your mouse.

### Application Control
Just ask AURA to open or close any app. She scans your Start Menu automatically to know what's installed!
*   **"Open Notepad"** or **"Launch Spotify"**
*   **"Close Paint"** or **"Minimize everything"**

### System Hotkeys
AURA can fire off Windows-level macros perfectly. Use natural phrasing, and she will execute the exact Windows shortcut:
*   **"Take a screenshot"** -> Opens Snipping Tool (`Win + Shift + S`)
*   **"Show my desktop"** -> Minimizes all windows (`Win + D`)
*   **"Open my settings"** -> Launches Windows Settings (`Win + I`)
*   **"Open Action Center"** -> Opens the Action Panel (`Win + A`)
*   **"Lock my PC"** -> Instantly locks your screen (`Win + L`)

---

## 3. Web & Media Commands

### Web Browsing
AURA handles browser tabs beautifully, whether you're using Chrome, Edge, or Brave.
*   **"Open a new tab"** -> `Ctrl + T`
*   **"Close this tab"** -> `Ctrl + W`
*   **"Reopen the tab I just closed"** -> `Ctrl + Shift + T`
*   **"Search Google for the theory of relativity"** -> Automatically opens your browser and searches Google.

### Media Controls
Control your music and videos effortlessly:
*   **"Play/Pause my music"** -> `Media Play/Pause`
*   **"Skip to the next track"** -> `Media Next`
*   **"Go back a song"** -> `Media Previous`
*   **"Mute the volume"**, **"Turn it up"**, or **"Turn it down"**

---

## 4. Advanced AI Superpowers

AURA utilizes the Llama 3.2 local model to provide intelligent, context-aware analysis.

### Clipboard Analysis
AURA can read whatever you currently have copied to your clipboard.
*   **How to use:** Copy a block of code, a math problem, or an email to your clipboard. Then say, **"Analyze this"** or **"Explain my clipboard"**.
*   **What happens:** AURA will read the text, summarize it, and speak the analysis directly to you.

### PC Vitals Check
*   **How to use:** Say **"How's my PC?"** or **"Check vitals"**.
*   **What happens:** AURA hooks into the `psutil` library to scan your CPU utilization, RAM usage, and battery life, then delivers a witty, natural-language health report.

### Custom Timers & Pomodoro
*   **Ad-hoc Timers:** Say **"Set a timer for 5 minutes to check the oven"**. AURA will start a silent background timer and speak your custom reminder when the time is up.
*   **Pomodoro Mode:** Say **"Start a Pomodoro session"**. A gorgeous, frosted-glass Pomodoro timer window will appear on your screen to help you track 25-minute focus intervals.

---

## 5. The OSD Shutdown System

When you ask AURA to **"Shut down my PC"**, she won't just yank the plug. 
She summons a massive, gorgeous "Liquid Glass" On-Screen Display (OSD) in the center of your screen with a 20-second countdown.
*   **"CANCEL"**: Aborts the shutdown cleanly.
*   **"Shut down now"**: Bypasses the timer and shuts off the machine instantly.

---

## 6. Known Shortcomings & Tips

To get the most flawless experience out of AURA, keep these quirks in mind:

*   **Multi-Command Phrasing:** AURA is brilliant at executing multiple actions in a row (e.g., *"Open Notepad, move to the left, and then hide"*). However, **do not combine targets**. Saying *"Open Notepad and Paint"* is perfectly fine, but understand that internally AURA executes this sequentially, not simultaneously.
*   **Speech Recognition Limitations:** Since AURA relies on the `SpeechRecognition` library and the Google Web Speech API (or Sphinx if offline), background noise or heavy accents can occasionally cause transcription errors. Ensure your microphone is close and clear.
*   **Background Noise Calibration:** When you first boot AURA, she calibrates for 1 second against ambient room noise. Keep the room quiet during boot for optimal listening.
*   **LLM Processing Times:** Complex queries (like analyzing massive clipboards) might take a few seconds longer depending on your GPU/CPU hardware running Ollama. 
