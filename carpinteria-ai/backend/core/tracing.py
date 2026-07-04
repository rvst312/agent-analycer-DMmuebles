"""
LangSmith tracing helpers.

Set these env vars to enable tracing:
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=<your-langsmith-key>
  LANGCHAIN_PROJECT=carpinteria-ai        # optional, defaults below
  LANGCHAIN_ENDPOINT=https://api.smith.langchain.com  # optional
"""
import os

import anthropic


def is_tracing_enabled() -> bool:
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"


def get_anthropic_client(**kwargs) -> anthropic.Anthropic:
    """
    Returns an Anthropic client. When LangSmith tracing is active the client
    is wrapped so every messages.create call is captured as a run in the
    configured LangSmith project.
    """
    client = anthropic.Anthropic(**kwargs)
    if is_tracing_enabled():
        try:
            from langsmith.wrappers import wrap_anthropic
            return wrap_anthropic(client)
        except ImportError:
            pass
    return client
