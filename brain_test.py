import json

import ollama


def parse_command(user_text):
    print(f"Thinking about: '{user_text}'...")

    # We give the AI a very strict System Prompt so it doesn't try to chat with us.
    # We just want it to act like a machine and return JSON data.
    system_prompt = """
    You are the brain of a desktop assistant. Your job is to extract the user's intent from their spoken text.
    You must output ONLY valid JSON. Do not include markdown formatting, backticks, or conversational text.

    Categories of actions:
    1. "open_app" (If they want to open a program)
    2. "move_avatar" (If they want to move you across the screen)
    3. "chat" (If they are just talking to you normally)

    Format:
    {"action": "<category>", "target": "<app_name_or_location_if_applicable>", "reply": "<a quick 1-sentence response>"}
    """

    try:
        response = ollama.chat(
            model="llama3.2",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )

        # Extract the raw text from the AI
        raw_output = response["message"]["content"].strip()

        # Parse it into a Python dictionary
        intent_data = json.loads(raw_output)

        print("\n🧠 AI Decoded Intent:")
        print(f"Action to take : {intent_data.get('action')}")
        print(f"Target object  : {intent_data.get('target')}")
        print(f"What to say    : {intent_data.get('reply')}")

        return intent_data

    except json.JSONDecodeError:
        print("\n❌ The AI didn't return valid JSON. It got confused.")
        print("Raw output was:", raw_output)
    except Exception as e:
        print(f"\n❌ Error connecting to Ollama: {e}")


if __name__ == "__main__":
    # Let's test it with the exact phrase your microphone just picked up
    test_phrase = "open calculator"
    parse_command(test_phrase)

    print("-" * 30)

    # Let's test a conversational one
    test_phrase_2 = "who is your favorite robot from indian movies?"
    parse_command(test_phrase_2)
