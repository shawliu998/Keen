from __future__ import annotations

import pytest

from app.provider_endpoints import (
    ProviderEndpointError,
    ProviderKind,
    validate_ollama_endpoint,
    validate_embedding_endpoint,
    validate_openai_compatible_endpoint,
    validate_provider_endpoint,
    validate_redirect_target,
)


@pytest.mark.parametrize(
    ("url", "canonical", "host", "port"),
    [
        (
            "http://127.0.0.1:11434",
            "http://127.0.0.1:11434",
            "127.0.0.1",
            11434,
        ),
        (
            "HTTP://127.23.45.67:8080/v1",
            "http://127.23.45.67:8080/v1",
            "127.23.45.67",
            8080,
        ),
        (
            "http://[0:0:0:0:0:0:0:1]:9000/api",
            "http://[::1]:9000/api",
            "::1",
            9000,
        ),
    ],
)
def test_openai_compatible_accepts_only_explicit_loopback_literals(
    url: str,
    canonical: str,
    host: str,
    port: int,
) -> None:
    endpoint = validate_openai_compatible_endpoint(url)

    assert endpoint.provider is ProviderKind.OPENAI_COMPATIBLE
    assert endpoint.url == canonical
    assert endpoint.host == host
    assert endpoint.port == port


def test_ollama_has_an_explicit_provider_kind() -> None:
    endpoint = validate_ollama_endpoint("http://127.0.0.1:11434/api")

    assert endpoint.provider is ProviderKind.OLLAMA
    assert endpoint.url == "http://127.0.0.1:11434/api"


def test_openai_compatible_permits_https_remote_origin_but_not_redirect_escape() -> (
    None
):
    endpoint = validate_openai_compatible_endpoint("https://api.example.com/v1")
    assert endpoint.host == "api.example.com"
    assert endpoint.port == 443
    with pytest.raises(ProviderEndpointError, match="configured origin"):
        validate_redirect_target(endpoint, "https://other.example.com:443/v1/models")


def test_remote_ipv6_keeps_a_bracketed_canonical_authority_and_embeddings_stay_loopback() -> (
    None
):
    endpoint = validate_openai_compatible_endpoint("https://[2001:db8::1]:8443/v1")
    assert endpoint.url == "https://[2001:db8::1]:8443/v1"
    with pytest.raises(ProviderEndpointError, match="embedding provider URL"):
        validate_embedding_endpoint(
            ProviderKind.OPENAI_COMPATIBLE, "https://api.example.com/v1"
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:11434",
        "file:///tmp/provider.sock",
        "ftp://127.0.0.1:11434",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:not-a-port",
        "http://0.0.0.0:11434",
        "http://192.168.1.2:11434",
        "http://8.8.8.8:11434",
        "http://localhost:11434",
        "http://localhost.localdomain:11434",
        "http://example.com:11434",
        "http://2130706433:11434",
        "http://127.1:11434",
        "http://0177.0.0.1:11434",
        "http://[::]:11434",
        "http://[::ffff:127.0.0.1]:11434",
        "http://[fe80::1]:11434",
        "http://[::1%25lo0]:11434",
        "http://user@127.0.0.1:11434",
        "http://user:secret@127.0.0.1:11434",
        "http://127.0.0.1:11434#models",
        "http://127.0.0.1:11434#",
        "https://api.example.com/v1?api_key=forbidden",
        "http://127.0.0.1%3A11434",
        "http://127.0.0.1:11434\\@example.com",
        "http://127.0.0.1:11434/has space",
        "http://127.0.0.1:11434/has\nnewline",
        "//127.0.0.1:11434",
        "",
    ],
)
def test_rejects_non_loopback_and_ambiguous_provider_urls(url: str) -> None:
    with pytest.raises(ProviderEndpointError):
        validate_ollama_endpoint(url)


def test_rejects_unknown_provider_kind_even_if_url_is_safe() -> None:
    with pytest.raises(ProviderEndpointError, match="provider kind"):
        validate_provider_endpoint(  # type: ignore[arg-type]
            "ollama-typo",
            "http://127.0.0.1:11434",
        )


def test_redirect_revalidates_absolute_and_scheme_relative_targets() -> None:
    endpoint = validate_ollama_endpoint("http://127.0.0.1:11434/api/chat")

    with pytest.raises(ProviderEndpointError, match="loopback IP literal"):
        validate_redirect_target(endpoint, "http://example.com:80/steal")
    with pytest.raises(ProviderEndpointError, match="loopback IP literal"):
        validate_redirect_target(endpoint, "//localhost:11434/steal")
    with pytest.raises(ProviderEndpointError, match="scheme must be http"):
        validate_redirect_target(endpoint, "https://127.0.0.1:11434/steal")


def test_redirect_accepts_relative_or_explicit_loopback_target() -> None:
    endpoint = validate_openai_compatible_endpoint(
        "http://127.0.0.1:8080/v1/chat/completions"
    )

    relative = validate_redirect_target(endpoint, "../models")
    explicit = validate_redirect_target(endpoint, "http://127.0.0.1:8080/v1")

    assert relative.url == "http://127.0.0.1:8080/v1/models"
    assert relative.provider is ProviderKind.OPENAI_COMPATIBLE
    assert explicit.url == "http://127.0.0.1:8080/v1"
    with pytest.raises(ProviderEndpointError, match="configured origin"):
        validate_redirect_target(endpoint, "http://127.0.0.2:9000/v1")


@pytest.mark.parametrize(
    "location",
    [
        "",
        " /v1/models",
        "/v1/models\r\nX-Injected: yes",
        "\\\\example.com/steal",
        "#fragment",
    ],
)
def test_redirect_rejects_empty_or_ambiguous_locations(location: str) -> None:
    endpoint = validate_ollama_endpoint("http://127.0.0.1:11434/api/chat")

    with pytest.raises(ProviderEndpointError):
        validate_redirect_target(endpoint, location)
