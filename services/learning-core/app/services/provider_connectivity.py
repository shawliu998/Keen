from __future__ import annotations

from ..answer_service import create_chat_provider
from ..local_chat_providers import LocalProviderError
from ..settings import LocalChatSettings


class ProviderConnectivityError(RuntimeError):
    pass


async def test_provider_connectivity(settings: LocalChatSettings) -> str:
    provider = create_chat_provider(settings)
    try:
        await provider.probe_model()  # type: ignore[attr-defined]
    except LocalProviderError as error:
        raise ProviderConnectivityError(
            "Keen could not confirm the provider model. Check the endpoint, model access, and API key, then retry."
        ) from error
    finally:
        await provider.aclose()  # type: ignore[attr-defined]
    return "Connected"
