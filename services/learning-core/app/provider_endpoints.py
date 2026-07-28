from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ipaddress import IPv4Address, IPv4Network, IPv6Address, ip_address
from urllib.parse import urljoin, urlsplit, urlunsplit


class ProviderKind(str, Enum):
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"


class ProviderEndpointError(ValueError):
    """Raised when a local model endpoint is unsafe or ambiguous."""


_IPV4_LOOPBACK = IPv4Network("127.0.0.0/8")
_IPV6_LOOPBACK = IPv6Address("::1")


@dataclass(frozen=True, slots=True)
class ProviderEndpoint:
    provider: ProviderKind
    url: str
    host: str
    port: int


def validate_provider_endpoint(
    provider: ProviderKind,
    url: str,
) -> ProviderEndpoint:
    """Validate and canonicalize an explicitly configured local provider URL.

    Hostnames are deliberately not resolved. Requiring a loopback IP literal avoids
    DNS rebinding and differences between URL parsers and HTTP clients.
    """

    if not isinstance(provider, ProviderKind):
        raise ProviderEndpointError("provider kind is not supported")
    if not isinstance(url, str) or not url:
        raise ProviderEndpointError("provider URL must be a non-empty string")
    if _contains_unsafe_character(url):
        raise ProviderEndpointError(
            "provider URL must not contain whitespace or controls"
        )
    if "\\" in url:
        raise ProviderEndpointError("provider URL must not contain backslashes")

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ProviderEndpointError("provider URL is malformed") from exc

    remote_openai = (
        provider is ProviderKind.OPENAI_COMPATIBLE and parts.scheme.lower() == "https"
    )
    if parts.scheme.lower() != "http" and not remote_openai:
        raise ProviderEndpointError(
            "provider URL scheme must be http for Ollama or https for a remote OpenAI-compatible provider"
        )
    if not parts.netloc:
        raise ProviderEndpointError("provider URL must include an authority")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise ProviderEndpointError("provider URL must not include user information")
    if "%" in parts.netloc:
        raise ProviderEndpointError(
            "provider URL authority must not be percent-encoded"
        )
    if parts.fragment or "#" in url:
        raise ProviderEndpointError("provider URL must not include a fragment")
    if parts.query:
        raise ProviderEndpointError("provider URL must not include query parameters")

    try:
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ProviderEndpointError("provider URL has an invalid host or port") from exc
    if host is None:
        raise ProviderEndpointError("provider URL must include a host")
    if port is None and remote_openai:
        port = 443
    if port is None:
        raise ProviderEndpointError("provider URL must include an explicit port")
    if not 1 <= port <= 65_535:
        raise ProviderEndpointError("provider URL port is out of range")

    try:
        address = ip_address(host)
    except ValueError as exc:
        if remote_openai and host and host.isascii():
            authority = host.lower()
            if parts.port is not None:
                authority = f"{authority}:{port}"
            return ProviderEndpoint(
                provider=provider,
                url=urlunsplit(("https", authority, parts.path, parts.query, "")),
                host=host.lower(),
                port=port,
            )
        raise ProviderEndpointError(
            "provider URL host must be a loopback IP literal"
        ) from exc
    if remote_openai:
        authority = (
            f"[{host.lower()}]" if isinstance(address, IPv6Address) else host.lower()
        )
        if parts.port is not None:
            authority = f"{authority}:{port}"
        return ProviderEndpoint(
            provider=provider,
            url=urlunsplit(("https", authority, parts.path, parts.query, "")),
            host=address.compressed,
            port=port,
        )
    if isinstance(address, IPv4Address):
        if address not in _IPV4_LOOPBACK:
            raise ProviderEndpointError("provider URL host must be loopback")
        authority = f"{address.compressed}:{port}"
    elif address != _IPV6_LOOPBACK:
        raise ProviderEndpointError("provider URL host must be loopback")
    else:
        authority = f"[{address.compressed}]:{port}"

    canonical_url = urlunsplit(("http", authority, parts.path, parts.query, ""))
    return ProviderEndpoint(
        provider=provider,
        url=canonical_url,
        host=address.compressed,
        port=port,
    )


def validate_openai_compatible_endpoint(url: str) -> ProviderEndpoint:
    return validate_provider_endpoint(ProviderKind.OPENAI_COMPATIBLE, url)


def validate_ollama_endpoint(url: str) -> ProviderEndpoint:
    return validate_provider_endpoint(ProviderKind.OLLAMA, url)


def validate_embedding_endpoint(provider: ProviderKind, url: str) -> ProviderEndpoint:
    endpoint = validate_provider_endpoint(provider, url)
    try:
        address = ip_address(endpoint.host)
    except ValueError as exc:
        raise ProviderEndpointError(
            "embedding provider URL host must be a loopback IP literal"
        ) from exc
    if not endpoint.url.startswith("http://") or not address.is_loopback:
        raise ProviderEndpointError("embedding provider URL must use HTTP loopback")
    return endpoint


def validate_redirect_target(
    endpoint: ProviderEndpoint,
    location: str,
) -> ProviderEndpoint:
    """Resolve an HTTP Location value and apply the full loopback policy again."""

    if not isinstance(endpoint, ProviderEndpoint):
        raise ProviderEndpointError("redirect source endpoint is invalid")
    if not isinstance(location, str) or not location:
        raise ProviderEndpointError("redirect location must be a non-empty string")
    if _contains_unsafe_character(location):
        raise ProviderEndpointError(
            "redirect location must not contain whitespace or controls"
        )
    if "\\" in location:
        raise ProviderEndpointError("redirect location must not contain backslashes")
    target = validate_provider_endpoint(
        endpoint.provider,
        urljoin(endpoint.url, location),
    )
    if endpoint.provider is ProviderKind.OPENAI_COMPATIBLE:
        source_parts = urlsplit(endpoint.url)
        target_parts = urlsplit(target.url)
        if (
            source_parts.scheme != target_parts.scheme
            or target.host != endpoint.host
            or target.port != endpoint.port
        ):
            raise ProviderEndpointError(
                "OpenAI-compatible provider redirects must remain on the configured origin"
            )
    return target


def _contains_unsafe_character(value: str) -> bool:
    return any(character.isspace() or ord(character) < 0x20 for character in value)
