"""Terminal entry point for the Nova Python chatbot."""
from assistant import LocalAssistant


def main() -> None:
    bot = LocalAssistant()
    print("=" * 54)
    print("                 NOVA CHAT ASSISTANT")
    print("          Local-first | Python | No API required")
    print("=" * 54)
    print("Hello! I'm Nova. Type /help for features or /quit to exit.")
    if bot.storage.load_warning:
        print(f"\nNotice: {bot.storage.load_warning}")
    while True:
        try:
            message = input("\nYou > ")
        except (EOFError, KeyboardInterrupt):
            print("\nNova > Session closed. See you next time!")
            break
        reply = bot.process(message)
        if reply == "EXIT":
            print("Nova > Goodbye! Your saved tasks and notes are kept on this device.")
            break
        print(f"\nNova > {reply}")


if __name__ == "__main__":
    main()
