import json
from datetime import date, time

import httpx
import pytest

from app.services.ai_parser import (
    AiParserError,
    BoardParseContext,
    MAX_ITEMS,
    OpenAICompatibleBoardParser,
    ParsedBoardPayload,
    validate_provider_endpoint,
)
from app.core.config import settings
from app.schemas.performance_boards import AiParserSettingsUpdate
from app.services.ai_settings import decrypt_api_key, read_ai_settings, update_ai_settings
from app.models.entities import EncryptedAiParserSettings, Performance, Theater, TheaterSlot, User
from app.models.enums import BoardParserType, UserRole
from app.services.performance_boards import create_board_revision_with_ai


@pytest.fixture(autouse=True)
def allow_mock_provider(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider_allowed_hosts", "provider.example")


def _response(payload):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})


def _public_resolver(*args, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


@pytest.mark.asyncio
async def test_openai_parser_accepts_strict_structured_json():
    payload = {"players": [], "wishes": [], "designations": [], "unresolved_lines": []}
    transport = httpx.MockTransport(lambda request: _response(payload))
    parser = OpenAICompatibleBoardParser(
        endpoint="https://provider.example/v1",
        api_key="top-secret",
        model="model-a",
        timeout_seconds=3,
        transport=transport,
        resolver=_public_resolver,
    )
    result = await parser.parse("#玩家信息", BoardParseContext(performance_id=1))
    assert result == ParsedBoardPayload.model_validate(payload)


@pytest.mark.asyncio
async def test_request_is_pinned_to_validated_ip_with_host_sni_and_no_env_proxy():
    seen, client_kwargs = [], []

    def handler(request):
        seen.append(request)
        return _response({"players": [], "wishes": [], "designations": [], "unresolved_lines": []})

    def factory(**kwargs):
        client_kwargs.append(kwargs.copy())
        return httpx.AsyncClient(**kwargs)

    parser = OpenAICompatibleBoardParser(
        endpoint="https://provider.example/v1",
        api_key="secret",
        model="m",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
        resolver=_public_resolver,
        client_factory=factory,
    )
    await parser.parse("x", BoardParseContext(performance_id=1))
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "provider.example"
    assert seen[0].extensions["sni_hostname"] == "provider.example"
    assert client_kwargs[0]["trust_env"] is False
    assert client_kwargs[0]["follow_redirects"] is False


@pytest.mark.asyncio
async def test_each_request_resolves_again_and_rebinding_to_private_is_rejected_before_send():
    answers = iter(["93.184.216.34", "10.0.0.5"])
    seen = []

    def resolver(*a, **k):
        return [(2, 1, 6, "", (next(answers), 443))]

    parser = OpenAICompatibleBoardParser(
        endpoint="https://provider.example/v1",
        api_key="s",
        model="m",
        timeout_seconds=1,
        transport=httpx.MockTransport(
            lambda request: (
                seen.append(request),
                _response(
                    {"players": [], "wishes": [], "designations": [], "unresolved_lines": []}
                ),
            )[1]
        ),
        resolver=resolver,
    )
    await parser.parse("x", BoardParseContext(performance_id=1))
    with pytest.raises(ValueError, match="not_allowed"):
        await parser.parse("x", BoardParseContext(performance_id=1))
    assert len(seen) == 1 and seen[0].url.host == "93.184.216.34"


@pytest.mark.asyncio
async def test_ipv6_pin_uses_bracketed_authority_and_original_tls_name():
    seen = []

    def resolver(*a, **k):
        return [(10, 1, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0))]

    parser = OpenAICompatibleBoardParser(
        endpoint="https://provider.example/v1",
        api_key="s",
        model="m",
        timeout_seconds=1,
        transport=httpx.MockTransport(
            lambda request: (
                seen.append(request),
                _response(
                    {"players": [], "wishes": [], "designations": [], "unresolved_lines": []}
                ),
            )[1]
        ),
        resolver=resolver,
    )
    await parser.parse("x", BoardParseContext(performance_id=1))
    assert seen[0].url.host == "2606:2800:220:1:248:1893:25c8:1946"
    assert str(seen[0].url).startswith("https://[2606:2800:")
    assert seen[0].headers["host"] == "provider.example"
    assert seen[0].extensions["sni_hostname"] == "provider.example"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        _response({"players": "wrong", "wishes": [], "designations": [], "unresolved_lines": []}),
        httpx.Response(503, text="upstream leaked detail"),
    ],
)
async def test_openai_parser_returns_sanitized_errors(response, caplog):
    secret = "never-show-this-key"
    parser = OpenAICompatibleBoardParser(
        endpoint="https://provider.example/v1",
        api_key=secret,
        model="model-a",
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda request: response),
        resolver=_public_resolver,
    )
    with pytest.raises(AiParserError) as exc:
        await parser.parse("text", BoardParseContext(performance_id=1))
    assert secret not in str(exc.value)
    assert secret not in caplog.text
    assert "upstream leaked detail" not in str(exc.value)


@pytest.mark.asyncio
async def test_openai_parser_sanitizes_timeout():
    def timeout(_request):
        raise httpx.ReadTimeout("request containing never-show-this-key")

    parser = OpenAICompatibleBoardParser(
        endpoint="https://provider.example/v1",
        api_key="never-show-this-key",
        model="model-a",
        timeout_seconds=1,
        transport=httpx.MockTransport(timeout),
        resolver=_public_resolver,
    )
    with pytest.raises(AiParserError, match="ai_provider_timeout"):
        await parser.parse("text", BoardParseContext(performance_id=1))


def test_api_key_is_encrypted_at_rest_and_masked_on_read(db_session, monkeypatch):
    monkeypatch.setattr(settings, "settings_encryption_key", "test-encryption-key")
    secret = "sk-plain-must-never-be-stored"
    row = update_ai_settings(
        db_session,
        AiParserSettingsUpdate(
            enabled=True,
            endpoint="https://provider.example/v1",
            api_key=secret,
            model_name="model-a",
            timeout_seconds=5,
        ),
        resolver=_public_resolver,
    )
    assert secret not in row.encrypted_api_key
    assert decrypt_api_key(row) == secret
    assert read_ai_settings(row).api_key_masked == "••••••••"
    assert secret not in read_ai_settings(row).model_dump_json()


def test_saving_key_requires_server_encryption_configuration(db_session, monkeypatch):
    monkeypatch.setattr(settings, "settings_encryption_key", None)
    with pytest.raises(ValueError, match="settings_encryption_key_required"):
        update_ai_settings(
            db_session,
            AiParserSettingsUpdate(
                enabled=True,
                endpoint="https://provider.example/v1",
                api_key="secret",
                model_name="model-a",
                timeout_seconds=5,
            ),
            resolver=_public_resolver,
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example:8443/v1",
        "https://provider.example/v1?q=1",
        "https://provider.example/v1#fragment",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
    ],
)
def test_provider_endpoint_rejects_unsafe_urls(endpoint):
    with pytest.raises(ValueError, match="not_allowed"):
        validate_provider_endpoint(endpoint, _public_resolver)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1", "fe80::1", "224.0.0.1"],
)
def test_provider_endpoint_rejects_non_global_dns_answers(address):
    def resolver(*a, **k):
        return [(2, 1, 6, "", (address, 443))]

    with pytest.raises(ValueError, match="not_allowed"):
        validate_provider_endpoint("https://provider.example/v1", resolver)


def test_structured_payload_rejects_ids_invalid_enum_nonfinite_and_limits():
    base = {"players": [], "wishes": [], "designations": [], "unresolved_lines": []}
    with pytest.raises(Exception):
        ParsedBoardPayload.model_validate({**base, "player_id": 1})
    with pytest.raises(Exception):
        ParsedBoardPayload.model_validate(
            {
                **base,
                "designations": [
                    {"designation_type": "invented", "actor_name": "a", "role_name": "r"}
                ],
            }
        )
    with pytest.raises(Exception):
        ParsedBoardPayload.model_validate(
            {
                **base,
                "players": [
                    {
                        "player_name": "p",
                        "player_character_name": "c",
                        "paired_role_name": "r",
                        "confidence": {"x": float("nan")},
                    }
                ],
            }
        )
    with pytest.raises(Exception):
        ParsedBoardPayload.model_validate({**base, "unresolved_lines": ["x"] * (MAX_ITEMS + 1)})
    with pytest.raises(Exception):
        ParsedBoardPayload.model_validate({**base, "unresolved_lines": ["x" * 1001]})


@pytest.mark.asyncio
async def test_provider_response_byte_cap_and_redirect_are_sanitized():
    for response, message in [
        (httpx.Response(200, content=b"x" * 256_001), "too_large"),
        (httpx.Response(302, headers={"location": "http://127.0.0.1"}), "http_error"),
    ]:
        parser = OpenAICompatibleBoardParser(
            endpoint="https://provider.example/v1",
            api_key="secret",
            model="m",
            timeout_seconds=1,
            transport=httpx.MockTransport(lambda _: response),
            resolver=_public_resolver,
        )
        with pytest.raises(AiParserError, match=message):
            await parser.parse("x", BoardParseContext(performance_id=1))


def test_previous_key_decrypts_versioned_ciphertext(db_session, monkeypatch):
    monkeypatch.setattr(settings, "settings_encryption_key", "old-key")
    row = update_ai_settings(
        db_session,
        AiParserSettingsUpdate(
            enabled=True,
            endpoint="https://provider.example/v1",
            api_key="secret",
            model_name="m",
            timeout_seconds=2,
        ),
        resolver=_public_resolver,
    )
    monkeypatch.setattr(settings, "settings_encryption_key", "new-key")
    monkeypatch.setattr(settings, "settings_previous_encryption_keys", "old-key")
    assert decrypt_api_key(row) == "secret"


@pytest.mark.asyncio
async def test_unreadable_ciphertext_falls_back_without_leaking(db_session, monkeypatch, caplog):
    monkeypatch.setattr(settings, "settings_encryption_key", "current-key")
    theater = Theater(name="t")
    slot = TheaterSlot(theater=theater, name="s", start_time=time(19))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 1, 1),
        slot_name_snapshot="s",
        start_time_snapshot=time(19),
    )
    user = User(email="a@b.c", password_hash="x", role=UserRole.ADMIN)
    db_session.add_all(
        [
            performance,
            user,
            EncryptedAiParserSettings(
                id=1,
                enabled=True,
                endpoint="https://provider.example/v1",
                encrypted_api_key="v1:bad:ciphertext-secret",
                model_name="m",
                timeout_seconds=1,
            ),
        ]
    )
    db_session.commit()
    revision = await create_board_revision_with_ai(db_session, performance.id, "#玩家信息", user.id)
    assert revision.parser_type == BoardParserType.DETERMINISTIC
    assert "ciphertext-secret" not in caplog.text
