import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.octopus_it import (
    FALLBACK_TOKEN_LIFETIME,
    TOKEN_EXPIRY_MARGIN,
    OctopusCoordinator,
    token_expires_at,
)

from .test_statistics import ACCOUNT


def make_jwt(exp: float) -> str:
    def encode(part: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")

    return f"{encode({'alg': 'HS256'})}.{encode({'exp': exp})}.signature"


def test_token_expires_at_uses_exp_claim_minus_margin():
    assert token_expires_at(make_jwt(2_000_000_000)) == 2_000_000_000 - TOKEN_EXPIRY_MARGIN


def test_token_expires_at_falls_back_when_token_is_not_a_jwt(freezer):
    freezer.move_to("2026-10-24 12:00:00+00:00")

    for token in ("not-a-jwt", "a.b.c", "a.e30.c", ""):
        assert token_expires_at(token) == time.time() + FALLBACK_TOKEN_LIFETIME


def fake_session(logins: list):
    def post(url, json=None, headers=None):
        resp = MagicMock(status=200)
        if json["operationName"] == "Login":
            logins.append(1)
            token = make_jwt(time.time() + 3600)
            resp.json = AsyncMock(
                return_value={"data": {"obtainKrakenToken": {"token": token}}}
            )
        else:
            resp.json = AsyncMock(
                return_value={"data": {"viewer": {"accounts": [{"number": ACCOUNT}]}}}
            )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=resp)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    session = MagicMock(post=post)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


async def test_token_is_reused_until_close_to_expiry_then_renewed(
    hass: HomeAssistant, freezer
):
    freezer.move_to("2026-10-24 12:00:00+00:00")
    logins = []
    coordinator = OctopusCoordinator(hass, "user@example.com", "secret", 3600)

    with patch("aiohttp.ClientSession", side_effect=lambda *a, **k: fake_session(logins)):
        first = await coordinator._async_get_token()
        freezer.move_to("2026-10-24 12:30:00+00:00")
        assert await coordinator._async_get_token() == first
        assert len(logins) == 1

        # The token lasts one hour; within the safety margin of that we log in again.
        freezer.move_to("2026-10-24 12:59:30+00:00")
        await coordinator._async_get_token()

    assert len(logins) == 2
