from fastapi import APIRouter, HTTPException, Request

from ..schemas import ProviderConnectionTestResponse
from ..services.provider_connectivity import (
    ProviderConnectivityError,
    test_provider_connectivity,
)

router = APIRouter(prefix="/v1/provider", tags=["provider"])


@router.post("/test", response_model=ProviderConnectionTestResponse)
async def test_provider(request: Request) -> ProviderConnectionTestResponse:
    settings = request.app.state.settings.local_chat
    if settings is None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "No provider is configured. Save an Ollama or OpenAI-compatible provider first.",
                "retryable": False,
                "recovery": "Open Settings and save a provider configuration.",
            },
        )
    try:
        detail = await test_provider_connectivity(settings)
    except ProviderConnectivityError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(error),
                "retryable": True,
                "recovery": "Check the provider endpoint, model access, and API key, then retry.",
            },
        ) from None
    return ProviderConnectionTestResponse(
        status="connected",
        provider=settings.provider,
        model=settings.model,
        detail=detail,
    )
