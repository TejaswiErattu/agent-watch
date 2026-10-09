"""Shared setup for the demo agents: env config, Agent Watch init, the read_file tool, one LLM call."""

from __future__ import annotations

import os
from pathlib import Path

import agentwatch

from models import ANTHROPIC_MODEL_ID, BEDROCK_MODEL_ID


def init(agent_id: str, transport=None):
    """agentwatch.init from env: AGENTWATCH_ENDPOINT, AGENTWATCH_OWNER, AGENTWATCH_KEY."""
    return agentwatch.init(agent_id=agent_id, owner_id=os.environ["AGENTWATCH_OWNER"],
                           api_key=os.environ["AGENTWATCH_KEY"], transport=transport)


def read_file(path: str) -> str:
    return Path(path).read_text()


def ask(client, question: str, max_tokens: int = 200) -> str:
    """One turn through whichever wrapped client we have (Bedrock converse or Anthropic messages)."""
    if callable(getattr(client, "converse", None)):
        r = client.converse(modelId=BEDROCK_MODEL_ID,
                            messages=[{"role": "user", "content": [{"text": question}]}],
                            inferenceConfig={"maxTokens": max_tokens})
        return "".join(c.get("text", "") for c in r["output"]["message"]["content"])
    r = client.messages.create(model=ANTHROPIC_MODEL_ID, max_tokens=max_tokens,
                               messages=[{"role": "user", "content": question}])
    return "".join(getattr(c, "text", None) or (c.get("text", "") if isinstance(c, dict) else "")
                   for c in r.content)
