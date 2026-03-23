"""Generate and save Google OAuth token.json for runtime usage."""

import os

from dotenv import load_dotenv
from meet_service import create_token_payload


def main() -> None:
    load_dotenv()
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    token_payload = create_token_payload()
    with open(token_file, "w") as fh:
        fh.write(token_payload)
    print(f"Token written to {token_file}")


if __name__ == "__main__":
    main()
