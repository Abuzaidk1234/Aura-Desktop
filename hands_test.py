import os
import subprocess


def execute_action(intent_data):
    action = intent_data.get("action")
    target = intent_data.get("target")
    reply = intent_data.get("reply")

    # 1. First, we will eventually make the avatar "speak" this reply using TTS
    print(f"\n🗣️ Clippy says: {reply}")

    # 2. Execute OS Level Commands
    if action == "open_app" and target:
        print(f"⚙️  Executing OS command to open: {target}")

        target_clean = target.lower()

        try:
            # Common Windows apps have easy shortcuts
            if "calculator" in target_clean or "calc" in target_clean:
                subprocess.Popen("calc.exe")
            elif "notepad" in target_clean:
                subprocess.Popen("notepad.exe")
            elif "paint" in target_clean:
                subprocess.Popen("mspaint.exe")
            elif "spotify" in target_clean:
                # 'start' uses the Windows shell to find the default app
                os.system("start spotify")
            else:
                # Generic fallback for other apps
                os.system(f"start {target_clean}")

            print("✅ App launched successfully.")

        except Exception as e:
            print(f"❌ Failed to open {target}: {e}")

    elif action == "move_avatar":
        print(
            "⚙️  (Placeholder) We will trigger the PyQt window movement animation here!"
        )

    elif action == "chat":
        print("⚙️  No OS action needed. Just having a conversation.")


if __name__ == "__main__":
    # Let's test the exact dictionary your Ollama script just generated
    test_data = {
        "action": "open_app",
        "target": "calculator",
        "reply": "Opening calculator, please wait...",
    }

    execute_action(test_data)
