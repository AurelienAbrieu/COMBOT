import os
import re
from pathlib import Path

from strands import Agent
from strands.models.bedrock import BedrockModel


_PROVIDER_CONTEXT_DEFAULTS: dict[str, int] = {
    "anthropic": 200_000,
    "meta": 128_000,
    "amazon": 128_000,
    "mistral": 32_000,
}

_INFERENCE_PROFILE_PREFIX = re.compile(r"^(global|us|eu|ap)\.", flags=re.IGNORECASE)


def _strip_inference_profile_prefix(model_id: str) -> str:
    return _INFERENCE_PROFILE_PREFIX.sub("", model_id)


def _get_context_via_bedrock_metadata(model_id: str) -> int | None:
    try:
        import boto3
        base_id = _strip_inference_profile_prefix(model_id)
        bedrock = boto3.client("bedrock", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        resp = bedrock.get_foundation_model(modelIdentifier=base_id)
        provider = resp["modelDetails"].get("providerName", "").lower()
        return _PROVIDER_CONTEXT_DEFAULTS.get(provider)
    except Exception:
        return None


def _resolve_bedrock_model_id() -> str:
    default_model = "anthropic.claude-3-haiku-20240307-v1:0"
    configured_model = os.environ.get("AWS_BEDROCK_MODEL", default_model).strip()
    if configured_model == "anthropic.claude-opus-4-5-20251101-v1:0":
        return default_model
    return configured_model


def get_loaded_model_info() -> str:
    configured_model = os.environ.get("AWS_BEDROCK_MODEL", "anthropic.claude-3-haiku-20240307-v1:0").strip()
    resolved_model = _resolve_bedrock_model_id()
    if configured_model != resolved_model:
        return f"Bedrock model target: {resolved_model} (fallback from {configured_model})"
    return f"Bedrock model target: {resolved_model}"


def get_loaded_model_metadata() -> dict:
    configured_model = os.environ.get("AWS_BEDROCK_MODEL", "anthropic.claude-3-haiku-20240307-v1:0").strip()
    resolved_model = _resolve_bedrock_model_id()

    max_context_tokens = None
    max_context_source = "unknown"

    env_override = os.environ.get("AWS_BEDROCK_MAX_CONTEXT_TOKENS", "").strip()
    if env_override:
        try:
            max_context_tokens = int(env_override)
            max_context_source = "env"
        except ValueError:
            pass

    if max_context_tokens is None:
        max_context_tokens = _get_context_via_bedrock_metadata(resolved_model)
        if max_context_tokens is not None:
            max_context_source = "bedrock-provider"

    if max_context_tokens is None:
        base_id = _strip_inference_profile_prefix(resolved_model)
        prefix = base_id.split(".")[0].lower() if "." in base_id else ""
        ctx = _PROVIDER_CONTEXT_DEFAULTS.get(prefix)
        if ctx is not None:
            max_context_tokens = ctx
            max_context_source = "id-prefix"

    return {
        "configured_model": configured_model,
        "resolved_model": resolved_model,
        "max_context_tokens": max_context_tokens,
        "max_context_source": max_context_source,
    }


from .tools_status import (
    get_locker_status,
    get_locker_zone_status,
    get_locker_device_snapshot,
    search_parcels,
)
from .tools_pickup import (
    view_pickup_code,
    resend_pickup_code,
)
from .tools_lockers import (
    find_nearby_lockers,
)
from .tools_couriers import (
    add_courier,
    remove_courier,
)
from .tools_reports import (
    generate_report,
)


SYSTEM_PROMPT = """You are an assistant for Quadient smart locker Carrier Operation Managers.
You help carriers check locker status, track parcels, manage pickup codes, find nearby lockers, manage couriers, and generate reports.
Always reply in ENGLISH regardless of user language.

# Tool Usage Rules

All tools have detailed docstrings - read them. Key rules only:

## Read-only tools: execute directly, no confirmation needed.
## Modification tools (add_courier, remove_courier, resend_pickup_code, generate_report): ALWAYS require explicit user confirmation before executing.

Confirmation flow for modifications:
1. Gather required info and validate
2. Describe exactly what you will do
3. Ask "Should I proceed? (yes/no)"
4. Execute ONLY after explicit user confirmation

## Tool selection hints:
- "status of locker" / "locker status" / "device status" → get_locker_status (pass the device ID)
- "zone status" / "status of zone" / "state of box" → get_locker_zone_status (pass device ID and exact zone path)
- "device snapshot" / "raw device payload" / "technical details of locker" → get_locker_device_snapshot (pass device ID)
- "parcel status" / "where is parcel" / "track parcel" / "parcels in locker" / "parcels to pick up" / "colis à récupérer" → search_parcels (pass device_ids and/or parcel_number; use statuses="RETCFM,LIVEXP,LIVBLK" for parcels to collect, "LIVCFP" for loaded parcels)
- "pickup code" / "view code" / "PIN code" / "access code for parcel" → view_pickup_code
- "resend code" / "resend notification" / "send pickup code again" → resend_pickup_code
- "nearby lockers" / "lockers in the area" / "find locker" / "available lockers" / "accessible devices" / "devices I can access" / "active or maintenance devices" → find_nearby_lockers (optionally pass GPS coordinates, radius, statuses, or no coordinates for a full accessible-device list)
- "add courier" / "register carrier" / "new delivery agent" → add_courier
- "remove courier" / "delete carrier" / "unregister delivery agent" → remove_courier
- "generate report" / "send report" / "report by email" / "occupation rate" / "activity report" → generate_report
- "number of parcels dropped" / "parcel drop count" → generate_report with report_type="parcel_drop"

## Period interpretation:
- "since beginning of the month" → use first day of current month
- "last month" → previous calendar month
- "last week" → previous 7 days
- "over the last month" → last 30 days

## Locker status follow-up:
- When reporting locker status with blocked boxes or expired parcels, proactively ask if the user wants to extend the period for expired parcels.
- If the user says "yes", ask until which date.
- When proposing a quick locker status check example, use locker ID DEMO00001 by default.

# Output Rules

- Keep responses concise: plain text, at most 2-3 short sentences.
- Report tool results directly - don't elaborate unnecessarily.
- NEVER invent, infer, or summarize data not present in tool output.
- If API error: explain simply, suggest alternatives, never auto-retry.
- After answering, suggest a relevant follow-up action (e.g. "Do you need to check the status of locker DEMO00001?", "Do you need to check the status of another parcel?", "Do you need to know the occupation rate?").
- When listing lockers or parcels, present the data clearly.
- Do not use markdown tables. Use simple text formatting.
"""


def create_agent() -> Agent:
    """Create and return a new agent instance with all tools configured."""
    model = BedrockModel(model_id=_resolve_bedrock_model_id())

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            get_locker_status,
            get_locker_zone_status,
            get_locker_device_snapshot,
            search_parcels,
            view_pickup_code,
            resend_pickup_code,
            find_nearby_lockers,
            add_courier,
            remove_courier,
            generate_report,
        ],
    )

    return agent
