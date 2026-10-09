"""The well-behaved agent: Claude on Bedrock (falls back to the Anthropic API) plus a harmless read_file tool.

    AGENTWATCH_ENDPOINT=... AGENTWATCH_OWNER=... AGENTWATCH_KEY=... python demo/demo_agent.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `models` / `common` import when run as a script

import common  # noqa: E402
from models import ANTHROPIC_MODEL_ID, BEDROCK_MODEL_ID  # noqa: E402,F401  (re-exported for tests)

AGENT_ID = "demo-bot"
NOTES_PATH = str(Path(__file__).resolve().parent / "notes.txt")


def _bedrock():
    import boto3
    return boto3.client("bedrock-runtime", region_name="us-west-2")


def _anthropic():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def make_client(aw, bedrock_factory=_bedrock, anthropic_factory=_anthropic):
    """Wrapped Bedrock client if a 1-token probe works; otherwise a wrapped Anthropic client.

    The probe goes through the wrapper, so its (tiny) cost is recorded like any other call.
    """
    try:
        client = aw.wrap(bedrock_factory())
        client.converse(modelId=BEDROCK_MODEL_ID, messages=[{"role": "user", "content": [{"text": "ping"}]}],
                        inferenceConfig={"maxTokens": 1})
        return client
    except Exception as e:  # ImportError, AccessDeniedException, throttling, no model access, ...
        print(f"Bedrock unavailable ({type(e).__name__}); falling back to Anthropic API")
    return aw.wrap(anthropic_factory())


def main(client=None, transport=None, notes_path: str = NOTES_PATH) -> int:
    aw = common.init(AGENT_ID, transport=transport)
    llm = aw.wrap(client) if client is not None else make_client(aw)
    tools = aw.tools({"read_file": common.read_file})
    try:
        notes = tools["read_file"](notes_path)
        print("notes:", notes.strip())
        print("agent:", common.ask(llm, f"Give me one study tip based on these notes:\n{notes}"))
    finally:
        aw._sender.flush(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
