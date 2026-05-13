"""Dev harness: terminal client for POST /chat (requires `skillforge start` + API key)."""
import argparse
import json
import sys
import uuid

import httpx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    args = ap.parse_args()

    session_id = str(uuid.uuid4())
    conversation = []
    print(f"\nskillforge chat — session {session_id[:8]}")
    print("Commands: 'exit' to quit, 'reset' for new session\n")

    while True:
        try:
            prompt = input("you ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        if prompt == "exit":
            break
        if prompt == "reset":
            session_id = str(uuid.uuid4())
            conversation = []
            print(f"[new session: {session_id[:8]}]\n")
            continue

        full = []
        picked = []
        try:
            with httpx.stream(
                "POST",
                f"{args.url}/chat",
                json={"prompt": prompt, "session_id": session_id, "conversation": conversation},
                timeout=120.0,
            ) as r:
                if r.status_code != 200:
                    print(f"[error {r.status_code}] {r.read().decode()}")
                    continue
                print("claude ▸ ", end="", flush=True)
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if "delta" in data:
                        sys.stdout.write(data["delta"])
                        sys.stdout.flush()
                        full.append(data["delta"])
                    elif "done" in data:
                        picked = data.get("picked", [])
                    elif "error" in data:
                        print(f"\n[stream error] {data['error']}")
        except httpx.HTTPError as e:
            print(f"\n[connection error] {e}")
            print("Is the server running? Try: skillforge start")
            continue

        print()
        if picked:
            print(f"   \033[2m↳ skills used: {', '.join(picked)}\033[0m")
        print()
        conversation.append({"role": "user", "content": prompt})
        conversation.append({"role": "assistant", "content": "".join(full)})


if __name__ == "__main__":
    main()
