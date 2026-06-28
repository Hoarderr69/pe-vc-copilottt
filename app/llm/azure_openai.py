"""
Azure OpenAI client layer.

Centralizes config + client construction so agents don't read env vars directly.
Live calls require these environment variables:

    AZURE_OPENAI_ENDPOINT      e.g. https://my-resource.openai.azure.com
    AZURE_OPENAI_KEY           the API key
    AZURE_OPENAI_DEPLOYMENT    deployment name for the GPT-4o model (default: gpt-4o)
    AZURE_OPENAI_API_VERSION   API version (default: 2024-10-21, supports structured outputs)
"""

from __future__ import annotations

import os
from typing import List

REQUIRED_VARS: List[str] = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"]
DEFAULT_API_VERSION = "2024-10-21"
DEFAULT_DEPLOYMENT = "gpt-4o"


def missing_vars() -> List[str]:
    return [v for v in REQUIRED_VARS if not os.getenv(v)]


def is_configured() -> bool:
    return not missing_vars()


def deployment_name() -> str:
    return os.getenv("AZURE_OPENAI_DEPLOYMENT", DEFAULT_DEPLOYMENT)


def get_client():
    """Build an OpenAI/AzureOpenAI client. Raises with a clear message if unconfigured.

    Supports both Azure surfaces:
      - Classic:  https://<resource>.openai.azure.com  -> AzureOpenAI (api-version based)
      - v1 API:   https://<resource>.openai.azure.com/openai/v1 -> standard OpenAI client
        (the newer OpenAI-compatible surface; no api-version needed).
    """
    missing = missing_vars()
    if missing:
        raise RuntimeError(
            "Azure OpenAI is not configured. Set: "
            + ", ".join(missing)
            + ". See app/llm/azure_openai.py for the full list."
        )

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_KEY"]

    # Imported lazily so the rest of the app runs without the SDK configured.
    if "/openai/v1" in endpoint:
        from openai import OpenAI

        return OpenAI(base_url=endpoint.rstrip("/"), api_key=api_key)

    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION),
    )
