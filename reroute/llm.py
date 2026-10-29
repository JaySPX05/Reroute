"""One small wrapper around SAP Generative AI Hub.

If the AICORE_* variables (or ~/.aicore/config.json) are missing, or the call fails,
every function returns None and callers use their offline fallback. The demo never
breaks because the network or the trial is down.
"""
import json
import logging
import os
import re
from pathlib import Path

from . import config

log = logging.getLogger("reroute.llm")
_last_error = ""


def available() -> bool:
    if config.LLM_DISABLED:
        return False
    has_env = all(os.getenv(v) for v in config.AICORE_VARS)
    home = Path(os.getenv("AICORE_HOME", Path.home() / ".aicore"))
    return has_env or (home / "config.json").exists()


def mode() -> str:
    """'orchestration' when ORCHESTRATION_URL is set (any model, e.g. Claude), else 'native' (OpenAI models)."""
    return "orchestration" if config.ORCHESTRATION_URL else "native"


def status() -> str:
    if config.LLM_DISABLED:
        return "off (REROUTE_LLM=off)"
    if not available():
        return "not configured (offline templates)"
    return (f"Generative AI Hub · {config.LLM_MODEL} · {mode()}"
            + (f" · last error: {_last_error}" if _last_error else ""))


def _chat_native(messages, temperature, max_tokens):
    from gen_ai_hub.proxy.native.openai import chat as gh_chat  # pip install sap-ai-sdk-gen
    resp = gh_chat.completions.create(model_name=config.LLM_MODEL, messages=messages,
                                      temperature=temperature, max_tokens=max_tokens)
    return resp.choices[0].message.content


def _chat_orchestration(messages, temperature, max_tokens):
    """Generative AI Hub orchestration service: one API for every model in the hub.

    Each message's text is passed as a template value ({{?m0}}, {{?m1}} ...) so braces in
    our JSON facts can never be mistaken for template placeholders.
    """
    from gen_ai_hub.orchestration.models.config import OrchestrationConfig
    from gen_ai_hub.orchestration.models.llm import LLM
    from gen_ai_hub.orchestration.models.message import SystemMessage, UserMessage
    from gen_ai_hub.orchestration.models.template import Template, TemplateValue
    from gen_ai_hub.orchestration.service import OrchestrationService
    try:
        from gen_ai_hub.orchestration.models.message import AssistantMessage
    except ImportError:  # older SDKs: replay earlier answers as user context
        AssistantMessage = UserMessage
    kinds = {"system": SystemMessage, "user": UserMessage, "assistant": AssistantMessage}
    template_msgs, values = [], []
    for i, m in enumerate(messages):
        template_msgs.append(kinds.get(m["role"], UserMessage)("{{?m%d}}" % i))
        values.append(TemplateValue(name=f"m{i}", value=m["content"]))
    cfg = OrchestrationConfig(
        template=Template(messages=template_msgs, defaults=[]),
        llm=LLM(name=config.LLM_MODEL, version="latest",
                parameters={"max_tokens": max_tokens, "temperature": temperature}))
    service = OrchestrationService(api_url=config.ORCHESTRATION_URL, config=cfg)
    result = service.run(template_values=values)
    return result.orchestration_result.choices[0].message.content


def chat(messages: list, temperature: float = 0.2, max_tokens: int = 700):
    """Send OpenAI-style messages [{role, content}] to Generative AI Hub."""
    global _last_error
    if not available():
        return None
    try:
        call = _chat_orchestration if mode() == "orchestration" else _chat_native
        text = call(messages, temperature, max_tokens)
        _last_error = ""
        return text
    except Exception as e:  # network, auth, no deployment, quota ...
        _last_error = str(e)[:160]
        log.warning("Generative AI Hub call failed: %s", e)
        return None


def chat_json(messages: list):
    """Like chat(), but parses the first JSON object in the reply."""
    text = chat(messages, temperature=0)
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
