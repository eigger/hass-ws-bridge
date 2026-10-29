"""image platform tests."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientConnectionResetError
from homeassistant.components import image
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import BridgeClient, entity_id_for, get_bridge

STILL = "http://cam.local/still.jpg"
JPEG = b"\xff\xd8\xff\xe0ws-bridge\xff\xd9"


async def _wait_for_frame(
    hass: HomeAssistant, client: BridgeClient, unique_id: str, gateway_id: str = "gw1"
) -> None:
    """Wait for the real aiohttp WebSocket reader to deliver one binary frame."""
    bridge = get_bridge(hass, client.entry)
    ns_uid = f"{gateway_id}__{unique_id}"
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


async def test_media_owner_replacement_keeps_frame_and_closes_upload_socket(
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
    bridge = get_bridge(hass, client.entry)
    assert not bridge._media_connections
    # The last image stays served; only the producer socket is revoked.
    assert bridge.latest_media_frame("gw1__snap") == JPEG


async def test_media_socket_close_keeps_last_frame_and_rebind_keeps_it(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    """A snapshot producer closing its upload socket must not blank the image."""
    await client.entity("snap", "image", "Snap")
    entity_id = entity_id_for(hass, "image", "snap")
    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")
    bridge = get_bridge(hass, client.entry)

    await media.ws.close()
    for _ in range(100):
        await hass.async_block_till_done()
        if not bridge.has_media_connection("gw1__snap"):
            break
        await asyncio.sleep(0.01)
    assert not bridge.has_media_connection("gw1__snap")
    assert bridge.latest_media_frame("gw1__snap") == JPEG
    assert (await image.async_get_image(hass, entity_id)).content == JPEG

    # The next snapshot cycle binds a new socket without dropping the frame.
    session = await client.ok("media_open", unique_id="snap")
    media2 = await bridge_client_factory()
    bound2 = await media2.ok("media_connect", session_id=session["session_id"])
    assert bridge.has_media_connection("gw1__snap")
    assert bridge.latest_media_frame("gw1__snap") == JPEG
    await media2.ws.send_bytes(bytes([bound2["handler_id"]]) + JPEG)
    assert bridge.latest_media_frame("gw1__snap") == JPEG


async def test_uploaded_frame_is_persisted_restored_and_deleted(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    """The last JPEG survives a restart and is dropped with its entity."""
    await client.entity("snap", "image", "Snap")
    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")
    bridge = get_bridge(hass, client.entry)

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    path = bridge._media_file("gw1__snap")
    # The write runs in the executor; wait for it instead of assuming
    # async_block_till_done covers it (flaky on slow runners).
    for _ in range(200):
        if await hass.async_add_executor_job(path.exists):
            break
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()
    assert await hass.async_add_executor_job(path.read_bytes) == JPEG

    # Simulate a restart: no live frame, only the persisted copy is loaded.
    bridge._clear_media_frame("gw1__snap")
    assert bridge.latest_media_frame("gw1__snap") is None
    bridge._media_wanted = {path.name: "gw1__snap"}
    await hass.async_add_executor_job(bridge._load_media_files)
    assert bridge.latest_media_frame("gw1__snap") == JPEG

    await client.ok("remove", unique_id="snap")
    await hass.async_block_till_done()
    assert not await hass.async_add_executor_job(path.exists)
    assert bridge.latest_media_frame("gw1__snap") is None


async def test_gateway_disconnect_keeps_last_frame(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    """A rebooting/reconnecting gateway must not blank its last snapshot."""
    await client.entity("snap", "image", "Snap")
    entity_id = entity_id_for(hass, "image", "snap")
    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")
    bridge = get_bridge(hass, client.entry)

    await client.close()
    await hass.async_block_till_done()
    assert not bridge._media_connections
    assert bridge.latest_media_frame("gw1__snap") == JPEG
    assert (await image.async_get_image(hass, entity_id)).content == JPEG


async def test_unload_flushes_pending_frame_save(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    """A frame uploaded within the debounce window is persisted on unload."""
    await client.entity("snap", "image", "Snap")
    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")
    path = get_bridge(hass, client.entry)._media_file("gw1__snap")
    assert not await hass.async_add_executor_job(path.exists)

    await hass.config_entries.async_unload(client.entry.entry_id)
    for _ in range(200):
        if await hass.async_add_executor_job(path.exists):
            break
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()
    assert await hass.async_add_executor_job(path.read_bytes) == JPEG


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
    denied = await media.send("connect", gateway_id="other", name="Other")
    assert denied["error"]["code"] == "media_connection"
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


async def test_control_gateway_switch_revokes_old_media_handler(
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
    await client.connect("other", "Other")
    bridge = get_bridge(hass, client.entry)
    assert not bridge._media_connections
    # The producer is revoked but the last image is kept.
    assert bridge.latest_media_frame("gw1__snap") == JPEG

    # Handler revocation closes the old upload socket; either aiohttp rejects
    # the write or it is ignored while the close is being processed.
    try:
        await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    except (ClientConnectionResetError, ConnectionResetError):
        pass
    await asyncio.sleep(0.01)
    await hass.async_block_till_done()
    assert bridge.latest_media_frame("gw1__snap") == JPEG


@pytest.mark.parametrize("new_gateway", ["gw1", "other"])
async def test_obsolete_control_subscription_preserves_new_media(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
    new_gateway: str,
) -> None:
    """Closing an older connect subscription must not revoke the latest owner."""
    await client.entity("snap", "image", "Snap")
    old_connect_id = client.connect_id
    assert old_connect_id is not None
    await client.connect(new_gateway, "New Gateway")
    if new_gateway != "gw1":
        await client.entity("snap", "image", "Snap")

    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap", new_gateway)

    bridge = get_bridge(hass, client.entry)
    control_connection = next(iter(bridge._conn_client))
    control_connection.subscriptions[old_connect_id]()
    assert bridge.latest_media_frame(f"{new_gateway}__snap") == JPEG
    assert media.ws.closed is False


async def test_url_fetch_finishing_after_upload_preserves_jpeg_mime(
    hass: HomeAssistant, client: BridgeClient
) -> None:
    await client.entity("snap", "image", "Snap")
    await client.state("snap", {"image_url": "http://camera.local/image.png"})
    bridge = get_bridge(hass, client.entry)
    entity = bridge._entities["gw1__snap"]
    started = asyncio.Event()
    release = asyncio.Event()

    async def _delayed_url(_url: str) -> image.Image:
        started.set()
        await release.wait()
        return image.Image("image/png", b"png")

    with patch.object(entity, "_async_load_image_from_url", _delayed_url):
        pending = asyncio.create_task(
            image.async_get_image(hass, entity_id_for(hass, "image", "snap"))
        )
        await started.wait()
        bridge._store_media_frame("gw1", "gw1__snap", JPEG)
        release.set()
        fetched = await pending
    assert fetched.content == JPEG
    assert fetched.content_type == "image/jpeg"


async def test_reconnect_does_not_reuse_obsolete_subscription_generation(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    """A later reconnect must not make an old cleanup callback current again."""
    await client.entity("snap", "image", "Snap")
    first_connect_id = client.connect_id
    assert first_connect_id is not None
    await client.connect()
    second_connect_id = client.connect_id
    assert second_connect_id is not None

    bridge = get_bridge(hass, client.entry)
    control_connection = next(iter(bridge._conn_client))
    # Simulate the newest subscription ending, then a reconnect on the same
    # physical WebSocket. The first callback must remain obsolete.
    control_connection.subscriptions[second_connect_id]()
    await client.connect()
    session = await client.ok("media_open", unique_id="snap")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await _wait_for_frame(hass, client, "snap")

    control_connection.subscriptions[first_connect_id]()
    assert bridge.latest_media_frame("gw1__snap") == JPEG
