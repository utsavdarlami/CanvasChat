import json
import sys
import argparse
import requests
import time
from pathlib import Path


def parse_log_file(filepath):
    """Extract all Request Payloads from a debug log file."""
    payloads = []

    with open(filepath, "r", encoding="utf-8") as f:
        in_payload = False
        current_payload_lines = []
        brace_count = 0

        for line in f:
            if line.strip() == "=== Request Payload ===":
                in_payload = True
                current_payload_lines = []
                brace_count = 0
                continue

            if in_payload:
                current_payload_lines.append(line)

                # Count braces to find the end of the JSON object
                brace_count += line.count("{")
                brace_count -= line.count("}")

                # If we've started an object and brace count returns to 0, we're done
                if (
                    len(current_payload_lines) > 0
                    and "{" in "".join(current_payload_lines)
                    and brace_count == 0
                ):
                    try:
                        payload_str = "".join(current_payload_lines)
                        payload = json.loads(payload_str)
                        payloads.append(payload)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON payload in {filepath}: {e}")

                    in_payload = False

    return payloads


def run_payloads(
    payloads, endpoint, auto_mode=False, session_id_override=None, user_id_override=None
):
    """Send payloads to the backend one by one."""
    print(f"\nFound {len(payloads)} payloads to replay.")

    # Generate a consistent replay timestamp for this run so multiple payloads share the same new session
    replay_timestamp = int(time.time())

    for i, payload in enumerate(payloads, 1):
        # Override session_id and user_id to avoid corrupting the original session state
        orig_session = payload.get("session_id", "demo_session")
        orig_user = payload.get("user_id", "demo_user")

        new_session_id = (
            session_id_override or f"{orig_session}_replay_{replay_timestamp}"
        )
        new_user_id = user_id_override or f"{orig_user}_replay"

        payload["session_id"] = new_session_id
        payload["user_id"] = new_user_id

        query = payload.get("query", "No query found")
        print(f"\n--- Payload {i}/{len(payloads)} ---")
        print(f"Session ID: {new_session_id}")
        print(f"User ID: {new_user_id}")
        print(f"Query: '{query}'")

        if not auto_mode:
            input("Press Enter to send request (or Ctrl+C to exit)...")

        print("Sending request...")
        try:
            response = requests.post(
                endpoint, json=payload, headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                print("\n✅ Success! Response:")
                resp_data = response.json()

                print(resp_data.get("response", ""))
                print()

                print(resp_data.get("metadata", {}))

                # Print just the important layout changes
                action = resp_data.get("action", {})
                if action:
                    print(f"Action Type: {action.get('type')}")
                    print("Layout Delta:")
                    delta = action.get("layout_delta", {})

                    # Print moved nodes
                    for node in delta.get("updated_nodes", []):
                        print(
                            f"  - Moved '{node.get('name')}' to {node.get('display_id')} at ({node.get('x'):.1f}, {node.get('y'):.1f})"
                        )

                    # Print camera updates
                    if delta.get("camera_updates"):
                        for display, cam in delta.get("camera_updates", {}).items():
                            print(
                                f"  - Camera on {display}: pan({cam.get('pan_x'):.1f}, {cam.get('pan_y'):.1f}) zoom:{cam.get('zoom'):.3f}"
                            )
                else:
                    print(json.dumps(resp_data, indent=2))
            else:
                print(f"\n❌ Error: {response.status_code}")
                print(response.text)

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Connection Error: {e}")
            print(f"Make sure the backend is running at {endpoint}")
            break


def main():
    parser = argparse.ArgumentParser(
        description="Replay debug log payloads against the local backend."
    )
    parser.add_argument(
        "path", help="Path to a debug log file or directory containing log files."
    )
    parser.add_argument(
        "--endpoint",
        default="http://localhost:8000/api/chat",
        help="Backend chat endpoint URL",
    )
    parser.add_argument(
        "--auto", action="store_true", help="Run through all payloads without pausing"
    )
    parser.add_argument(
        "--session-id",
        help="Override the session ID. Otherwise, defaults to original_id + _replay_ + timestamp.",
    )
    parser.add_argument(
        "--user-id",
        help="Override the user ID. Otherwise, defaults to original_id + _replay.",
    )

    args = parser.parse_args()
    path = Path(args.path)

    files_to_process = []
    if path.is_file():
        files_to_process.append(path)
    elif path.is_dir():
        files_to_process.extend(path.glob("*.txt"))
    else:
        print(f"Error: {path} is not a valid file or directory.")
        sys.exit(1)

    if not files_to_process:
        print(f"No log files found at {path}")
        sys.exit(1)

    for filepath in files_to_process:
        print(f"\n{'=' * 50}\nProcessing file: {filepath.name}\n{'=' * 50}")
        payloads = parse_log_file(filepath)
        run_payloads(payloads, args.endpoint, args.auto, args.session_id, args.user_id)


if __name__ == "__main__":
    main()
