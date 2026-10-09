"""The misbehaving agent: asks the LLM, then its scripted tool step tries to read .env.

With ".env" in this agent's Blocked_Paths, the SDK raises PathBlocked before the file is opened,
reports a blocked event, and the backend emails the alert.

    AGENTWATCH_ENDPOINT=... AGENTWATCH_OWNER=... AGENTWATCH_KEY=... python demo/bad_agent.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `models` / `common` import when run as a script

from agentwatch import PathBlocked  # noqa: E402

import common  # noqa: E402
from models import BEDROCK_MODEL_ID  # noqa: E402,F401  (re-exported for tests)

AGENT_ID = "bad-bot"


def main(client=None, transport=None) -> int:
    """0 if the .env read was blocked, 1 if it went through."""
    aw = common.init(AGENT_ID, transport=transport)
    if client is None:
        import boto3
        client = boto3.client("bedrock-runtime", region_name="us-west-2")
    llm, tools = aw.wrap(client), aw.tools({"read_file": common.read_file})

    print("agent:", common.ask(llm, "In one sentence: what is a .env file?"))
    print("agent: let me just check the .env file for you...")
    try:
        tools["read_file"](".env")
    except PathBlocked as e:
        print(f"PathBlocked: {e.detail} (Agent Watch stopped the read; an alert email is on its way)")
        return 0
    finally:
        aw._sender.flush(5)
    print("read_file('.env') was NOT blocked. Add .env to this agent's blocked paths.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
