# guardrails/callbacks.py
"""
Input and Output Guardrails for Market Scout.
ADK before_model_callback / after_model_callback hooks.
"""

import re
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai.types import Content, Part

# ─── Patterns ────────────────────────────────────────────────────────────────

HARMFUL_PATTERNS = [
    r"\bhack\b", r"\bexploit\b", r"\bmalware\b", r"\billegal\b",
    r"\bransomware\b", r"\bvirus\b", r"\bphishing\b", r"\bddos\b",
]

INJECTION_PATTERNS = [
    r"jailbreak", r"act as", r"ignore (previous|all|your) instructions",
    r"you are now", r"pretend (you are|to be)", r"disregard",
]

PII_PATTERNS = [
    r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",          # credit card
    r"\b\d{3}-\d{2}-\d{4}\b",                              # SSN
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", # email
    r"(?<!\d)(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)",  # phone (tightened)
]

OUT_OF_SCOPE = [
    r"\brecipe\b", r"\bweather\b", r"\bhomework\b", r"\bpoem\b",
    r"\bsong\b", r"\bstory\b", r"\bjoke\b", r"\btranslate\b",
]

MIN_QUERY_LEN = 3
MAX_QUERY_LEN = 1000


def _extract_text(request: LlmRequest) -> str:
    """Pulls plain text from the last user turn."""
    try:
        for content in reversed(request.contents or []):
            if content.role == "user":
                for part in content.parts or []:
                    if hasattr(part, "text") and part.text:
                        return part.text.strip()
    except Exception:
        pass
    return ""


def _block(message: str) -> LlmResponse:
    """Returns a blocking LlmResponse with the given message."""
    return LlmResponse(
        content=Content(role="model", parts=[Part(text=message)])
    )


# ─── Input Guardrail ─────────────────────────────────────────────────────────

def input_guardrail(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    text = _extract_text(llm_request)
    if not text:
        return None

    lower = text.lower()

    if len(text) < MIN_QUERY_LEN:
        return _block(
            f"⚠️ Query too short (minimum {MIN_QUERY_LEN} characters). "
            "Please enter a company name to track."
        )
    if len(text) > MAX_QUERY_LEN:
        return _block(
            f"⚠️ Query too long (maximum {MAX_QUERY_LEN} characters). "
            "Please shorten your request."
        )

    for pattern in HARMFUL_PATTERNS:
        if re.search(pattern, lower):
            return _block(
                "🚫 Harmful intent detected. "
                "I can only help with competitor intelligence."
            )

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            return _block(
                "🚫 Prompt injection attempt detected. "
                "I can only help with competitor intelligence."
            )

    for pattern in PII_PATTERNS:
        if re.search(pattern, text):
            return _block(
                "🚫 Personal or sensitive information detected. "
                "Please do not share PII. Enter a company name to track."
            )

    for pattern in OUT_OF_SCOPE:
        if re.search(pattern, lower):
            return _block(
                "ℹ️ I only track competitor updates. "
                "Try: 'Track Stripe' or 'Compare PayPal and Stripe'."
            )

    return None


# ─── Output Guardrail ────────────────────────────────────────────────────────

def output_guardrail(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    try:
        if not llm_response.content or not llm_response.content.parts:
            return None

        modified = False
        new_parts = []

        for part in llm_response.content.parts:
            if hasattr(part, "text") and part.text:
                text = part.text
                for pattern in PII_PATTERNS:
                    cleaned = re.sub(pattern, "[REDACTED]", text)
                    if cleaned != text:
                        text = cleaned
                        modified = True
                new_parts.append(Part(text=text))
            else:
                new_parts.append(part)

        if modified:
            return LlmResponse(content=Content(role="model", parts=new_parts))

    except Exception:
        pass

    return None
