import ipaddress
import math
import socket
from enum import StrEnum
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import settings


PROMPT_VERSION = "board-v1"
MAX_PROVIDER_BYTES = 256_000
MAX_ITEMS = 200
MAX_RAW_TEXT = 50_000


@dataclass(frozen=True)
class ResolvedProviderEndpoint:
    endpoint: str
    hostname: str
    ip_address: str

    @property
    def pinned_base_url(self) -> str:
        authority = f"[{self.ip_address}]" if ":" in self.ip_address else self.ip_address
        path = urlsplit(self.endpoint).path.rstrip("/")
        return f"https://{authority}{path}"


def resolve_provider_endpoint(
    endpoint: str, resolver: Callable | None = None
) -> ResolvedProviderEndpoint:
    resolver = resolver or socket.getaddrinfo
    parsed = urlsplit(endpoint)
    allowed = {
        host.strip().lower()
        for host in settings.ai_provider_allowed_hosts.split(",")
        if host.strip()
    }
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("ai_provider_endpoint_not_allowed")
    if parsed.port not in (None, 443) or parsed.query or parsed.fragment:
        raise ValueError("ai_provider_endpoint_not_allowed")
    host = parsed.hostname.lower().rstrip(".")
    if host not in allowed:
        raise ValueError("ai_provider_endpoint_not_allowed")
    try:
        addresses = {item[4][0] for item in resolver(host, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("ai_provider_host_unresolvable") from exc
    if not addresses:
        raise ValueError("ai_provider_host_unresolvable")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError("ai_provider_endpoint_not_allowed")
    return ResolvedProviderEndpoint(endpoint.rstrip("/"), host, sorted(addresses)[0])


def validate_provider_endpoint(endpoint: str, resolver: Callable | None = None) -> str:
    return resolve_provider_endpoint(endpoint, resolver).endpoint


class AiParserError(RuntimeError):
    """A deliberately sanitized provider failure."""


class BoardParseContext(BaseModel):
    performance_id: int


class StrictItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confidence: dict[str, float] = Field(default_factory=dict, max_length=20)
    evidence: str | None = Field(default=None, max_length=1000)

    @field_validator("confidence")
    @classmethod
    def confidence_is_finite(cls, value):
        if any(
            len(key) > 50 or not math.isfinite(score) or not 0 <= score <= 1
            for key, score in value.items()
        ):
            raise ValueError("invalid_confidence")
        return value


class ParsedPlayer(StrictItem):
    player_name: str = Field(max_length=120)
    player_character_name: str = Field(max_length=120)
    paired_role_name: str = Field(max_length=120)
    relation_label: str | None = Field(default=None, max_length=80)
    theater_visit_ordinal: int | None = Field(default=None, ge=1)
    character_visit_ordinal: int | None = Field(default=None, ge=1)


class ParsedWish(StrictItem):
    player_name: str = Field(max_length=120)
    actor_name: str = Field(max_length=120)
    role_name: str = Field(max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class ParsedDesignationType(StrEnum):
    UNIVERSAL = "universal"
    TOP_THREE = "top_three"
    PAIRED = "paired"


class ParsedDesignation(StrictItem):
    designation_type: ParsedDesignationType
    holder_player_name: str | None = Field(default=None, max_length=120)
    player_name: str | None = Field(default=None, max_length=120)
    actor_name: str = Field(max_length=120)
    role_name: str = Field(max_length=120)
    source_month: str | None = Field(default=None, max_length=20)
    source_note: str | None = Field(default=None, max_length=1000)


class ParsedBoardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    players: list[ParsedPlayer] = Field(max_length=MAX_ITEMS)
    wishes: list[ParsedWish] = Field(max_length=MAX_ITEMS)
    designations: list[ParsedDesignation] = Field(max_length=MAX_ITEMS)
    unresolved_lines: list[str] = Field(max_length=MAX_ITEMS)

    @field_validator("unresolved_lines")
    @classmethod
    def bound_unresolved(cls, value):
        if any(len(line) > 1000 for line in value):
            raise ValueError("unresolved_line_too_long")
        return value

    @field_validator("unresolved_lines")
    @classmethod
    def bound_total(cls, value, info):
        total = len(value) + sum(
            len(info.data.get(k, [])) for k in ("players", "wishes", "designations")
        )
        if total > MAX_ITEMS:
            raise ValueError("too_many_draft_items")
        return value


class BoardParser(Protocol):
    async def parse(self, raw_text: str, context: BoardParseContext) -> ParsedBoardPayload: ...


class OpenAICompatibleBoardParser:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Callable | None = None,
        client_factory: Callable = httpx.AsyncClient,
    ):
        resolver = resolver or socket.getaddrinfo
        parsed = urlsplit(endpoint)
        allowed = {
            host.strip().lower()
            for host in settings.ai_provider_allowed_hosts.split(",")
            if host.strip()
        }
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname.lower().rstrip(".") not in allowed
        ):
            raise ValueError("ai_provider_endpoint_not_allowed")
        if (
            parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("ai_provider_endpoint_not_allowed")
        self.endpoint = endpoint.rstrip("/")
        self.resolver = resolver
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.client_factory = client_factory

    async def parse(self, raw_text: str, context: BoardParseContext) -> ParsedBoardPayload:
        resolved = resolve_provider_endpoint(self.endpoint, self.resolver)
        if len(raw_text) > MAX_RAW_TEXT:
            raise AiParserError("board_raw_text_too_large")
        schema = ParsedBoardPayload.model_json_schema()
        request = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Extract only explicit facts. Never guess missing players. Return JSON matching the supplied schema.",
                },
                {"role": "user", "content": raw_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "performance_board", "strict": True, "schema": schema},
            },
        }
        try:
            async with self.client_factory(
                transport=self.transport,
                timeout=self.timeout_seconds,
                headers={"Authorization": f"Bearer {self.api_key}"},
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{resolved.pinned_base_url}/chat/completions",
                    json=request,
                    headers={"Host": resolved.hostname},
                    extensions={"sni_hostname": resolved.hostname},
                ) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_PROVIDER_BYTES:
                            raise AiParserError("ai_provider_response_too_large")
                        chunks.append(chunk)
            envelope = httpx.Response(200, content=b"".join(chunks)).json()
            content = envelope["choices"][0]["message"]["content"]
            return ParsedBoardPayload.model_validate_json(content)
        except httpx.TimeoutException as exc:
            raise AiParserError("ai_provider_timeout") from exc
        except httpx.HTTPError as exc:
            raise AiParserError("ai_provider_http_error") from exc
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise AiParserError("ai_provider_invalid_response") from exc
