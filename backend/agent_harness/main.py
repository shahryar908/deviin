"""Interactive REPL for the harness."""

import sys

import agent


def main() -> None:
    print("devin harness (Groq) — type a task, 'quit' to exit")
    try:
        import sandbox
        sandbox.health()
        print("sandbox: envd reachable")
    except Exception as e:
        print(f"sandbox: WARNING — {e}")

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.lower() in ("quit", "exit"):
            break
        if not line:
            continue
        print(agent.run(line))


if __name__ == "__main__":
    main()
