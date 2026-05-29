import speech_recognition as sr


def test_microphones():
    print("--- Available Microphones ---")
    # This prints out every audio device Python can see
    mic_list = sr.Microphone.list_microphone_names()
    for index, name in enumerate(mic_list):
        print(f"[{index}] {name}")
    print("-----------------------------\n")


def listen_and_transcribe():
    recognizer = sr.Recognizer()

    # --- THE FIX: Force Python to use WO Mic (Index 2) ---
    with sr.Microphone(device_index=2) as source:
        print("Adjusting for background noise... (Please be quiet for 2 seconds)")
        recognizer.adjust_for_ambient_noise(source, duration=2)

        recognizer.energy_threshold = 300

        print("\n🎤 LISTENING! Speak now... (Press Ctrl+C to stop if it gets stuck)")

        try:
            audio_data = recognizer.listen(source, phrase_time_limit=10)

            print("Processing audio...")
            text = recognizer.recognize_google(audio_data)
            print(f"\n✅ You said: '{text}'")

        except sr.UnknownValueError:
            print("\n❌ Google Speech Recognition could not understand the audio.")
        except sr.RequestError as e:
            print(f"\n❌ Could not request results; {e}")
        except KeyboardInterrupt:
            print("\nStopped listening.")


if __name__ == "__main__":
    test_microphones()
    listen_and_transcribe()
