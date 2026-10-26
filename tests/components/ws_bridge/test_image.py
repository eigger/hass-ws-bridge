"""image platform tests."""

import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import image
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, entity_id_for, get_bridge

STILL = "http://cam.local/still.jpg"
JPEG = b"\xff\xd8\xff\xe0ws-bridge\xff\xd9"


async def _wait_for_frame(
    hass: HomeAssistant, client: BridgeClient, unique_id: str
) -> None:
    """Wait for the real aiohttp WebSocket reader to deliver one binary frame."""
    bridge = get_bridge(hass, client.entry)
    ns_uid = f"gw1__{unique_id}"
    for _ in range(50):
        if bridge.latest_media_frame(ns_uid) == JPEG:
            return
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()
    raise AssertionError("HA did not receive the binary JPEG frame")


async def test_image_url_and_last_updated(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("snap", "image", "Snap")
    entity_id = entity_id_for(hass, "image", "snap")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await client.state("snap", {"image_url": STILL})
    first = hass.states.get(entity_id).state
    assert first != STATE_UNKNOWN  # state is image_last_updated

    # Same URL (with other keys) → not re-stamped.
    await client.state("snap", {"image_url": STILL, "extra": 1})
    assert hass.states.get(entity_id).state == first

    await client.state("snap", {"image_url": "http://cam.local/still2.jpg"})
    assert hass.states.get(entity_id).state != first

    await client.state("snap", {"image_last_updated": "2026-08-13T07:30:00+00:00"})
    assert hass.states.get(entity_id).state == "2026-08-13T07:30:00+00:00"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://169.254.169.254/latest",
        "file:///etc/passwd",
        "ftp://cam.local/x",
    ],
)
async def test_image_rejects_unsafe_url(
    hass: HomeAssistant, client: BridgeClient, url, caplog
) -> None:
    await client.entity("snap", "image", "Snap")
    await client.state("snap", {"image_url": url})
    assert hass.states.get(entity_id_for(hass, "image", "snap")).state == (
        STATE_UNKNOWN
    )
    assert "Ignoring unsafe image_url" in caplog.text


async def test_image_uploaded_jpeg_uses_dedicated_authenticated_socket(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    """A pushed frame supersedes URL bytes without putting bytes in state/store."""
    await client.entity("snap", "image", "Snap")
    entity_id = entity_id_for(hass, "image", "snap")
    previous = hass.states.get(entity_id).state

    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")

    fetched = await image.async_get_image(hass, entity_id)
    assert fetched.content == JPEG
    assert hass.states.get(entity_id).state != previous
    bridge = get_bridge(hass, client.entry)
    assert bridge.latest_media_frame("gw1__snap") == JPEG
    # A consumed session cannot attach another upload socket.
    another = await bridge_client_factory()
    denied = await another.send("media_connect", session_id=session["session_id"])
    assert denied["success"] is False
    assert denied["error"]["code"] == "invalid_media_session"


async def test_media_owner_replacement_clears_frame_and_upload_socket(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    await client.entity("snap", "image", "Snap")
    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")

    # Reannouncing through the same control socket preserves the producer.
    await client.connect()
    assert get_bridge(hass, client.entry).latest_media_frame("gw1__snap") == JPEG

    # A different control socket that claims the same gateway replaces ownership.
    replacement = await bridge_client_factory()
    await replacement.connect()
    await hass.async_block_till_done()
    assert get_bridge(hass, client.entry).latest_media_frame("gw1__snap") is None


async def test_media_requires_declared_entity_and_expires_before_connect(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    """Only declared image/camera entities can reserve an upload endpoint."""
    await client.entity("temperature", "sensor", "Temperature")
    invalid = await client.send("media_open", unique_id="temperature")
    assert invalid["error"]["code"] == "invalid_media_entity"

    await client.entity("snap", "image", "Snap")
    opened = await client.ok("media_open", unique_id="snap")
    bridge = get_bridge(hass, client.entry)
    bridge._media_sessions[opened["session_id"]].expires_at = 0
    media = await bridge_client_factory()
    expired = await media.send("media_connect", session_id=opened["session_id"])
    assert expired["error"]["code"] == "invalid_media_session"


async def test_url_state_and_remove_invalidate_uploaded_media(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    await client.entity("snap", "image", "Snap")
    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")
    bridge = get_bridge(hass, client.entry)

    await client.state("snap", {"image_url": STILL})
    assert bridge.latest_media_frame("gw1__snap") is None
    assert not bridge._media_connections

    # Remove is idempotent after URL mode and leaves no pending/cache state.
    await client.ok("remove", unique_id="snap")
    assert not bridge._media_sessions
    assert not bridge._media_frames


async def test_replaced_control_cannot_open_media_session(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    await client.entity("snap", "image", "Snap")
    replacement = await bridge_client_factory()
    await replacement.connect()
    denied = await client.send("media_open", unique_id="snap")
    assert denied["error"]["code"] == "invalid_media_entity"


async def test_control_and_bound_media_socket_cannot_rebind(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    await client.entity("a", "image", "A")
    await client.entity("b", "image", "B")
    first = await client.ok("media_open", unique_id="a")
    # A control connection is never an upload connection: otherwise URL-mode
    # cleanup could close the command/control socket.
    denied = await client.send("media_connect", session_id=first["session_id"])
    assert denied["error"]["code"] == "invalid_media_session"

    media = await bridge_client_factory()
    first = await client.ok("media_open", unique_id="a")
    await media.ok("media_connect", session_id=first["session_id"])
    second = await client.ok("media_open", unique_id="b")
    denied = await media.send("media_connect", session_id=second["session_id"])
    assert denied["error"]["code"] == "invalid_media_session"


async def test_uploaded_jpeg_resets_url_content_type(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    await client.entity("snap", "image", "Snap")
    await client.state("snap", {"image_url": "http://camera.local/image.png"})
    bridge = get_bridge(hass, client.entry)
    entity = bridge._entities["gw1__snap"]
    with patch.object(
        entity,
        "_async_load_image_from_url",
        AsyncMock(return_value=image.Image("image/png", b"png")),
    ):
        fetched = await image.async_get_image(
            hass, entity_id_for(hass, "image", "snap")
        )
    assert fetched.content_type == "image/png"

    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")
    fetched = await image.async_get_image(hass, entity_id_for(hass, "image", "snap"))
    assert fetched.content == JPEG
    assert fetched.content_type == "image/jpeg"
