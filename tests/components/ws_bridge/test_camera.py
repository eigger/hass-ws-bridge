"""camera platform tests."""

import asyncio
from collections.abc import Awaitable, Callable
from http import HTTPStatus

import pytest
from homeassistant.components import camera
from homeassistant.components.camera import CameraEntityFeature, CameraState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .conftest import BridgeClient, call_service, entity_id_for, get_bridge

STILL = "http://cam.local/still.jpg"
JPEG = b"\xff\xd8\xff\xe0camera-upload\xff\xd9"


async def test_camera_still_stream_and_commands(
    hass: HomeAssistant, client: BridgeClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(STILL, content=b"jpeg-bytes")
    await client.entity("cam", "camera", "Cam", features=["on_off", "stream"])
    entity_id = entity_id_for(hass, "camera", "cam")
    flags = hass.states.get(entity_id).attributes["supported_features"]
    assert not flags & CameraEntityFeature.STREAM  # no stream_source yet

    await client.state(
        "cam",
        {
            "still_image_url": STILL,
            "stream_source": "rtsp://cam.local/stream",
            "is_on": True,
        },
    )
    state = hass.states.get(entity_id)
    assert state.attributes["supported_features"] & CameraEntityFeature.STREAM
    assert state.state == CameraState.STREAMING
    assert await camera.async_get_stream_source(hass, entity_id) == (
        "rtsp://cam.local/stream"
    )
    image = await camera.async_get_image(hass, entity_id)
    assert image.content == b"jpeg-bytes"

    await call_service(hass, "camera", "turn_off", entity_id)
    assert (await client.next_command())["action"] == "turn_off"
    await call_service(hass, "camera", "turn_on", entity_id)
    assert (await client.next_command())["action"] == "turn_on"


async def test_camera_rejects_unsafe_urls_and_handles_http_errors(
    hass: HomeAssistant,
    client: BridgeClient,
    aioclient_mock: AiohttpClientMocker,
    caplog,
) -> None:
    await client.entity("cam", "camera", "Cam")
    entity_id = entity_id_for(hass, "camera", "cam")
    await client.state(
        "cam",
        {"still_image_url": "http://127.0.0.1/admin", "stream_source": "file:///x"},
    )
    assert "Ignoring unsafe still_image_url" in caplog.text
    assert "Ignoring unsafe stream_source" in caplog.text
    assert await camera.async_get_stream_source(hass, entity_id) is None
    with pytest.raises(HomeAssistantError):
        await camera.async_get_image(hass, entity_id)
    assert aioclient_mock.call_count == 0  # never fetched

    aioclient_mock.get(STILL, status=HTTPStatus.NOT_FOUND)
    await client.state("cam", {"still_image_url": STILL})
    with pytest.raises(HomeAssistantError):
        await camera.async_get_image(hass, entity_id)
    assert "returned HTTP 404" in caplog.text


async def test_camera_serves_uploaded_jpeg(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
) -> None:
    await client.entity("cam", "camera", "Cam")
    session = await client.ok("media_open", unique_id="cam")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)

    bridge = get_bridge(hass, client.entry)
    for _ in range(50):
        if bridge.latest_media_frame("gw1__cam") == JPEG:
            break
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()
    else:
        raise AssertionError("HA did not receive the binary JPEG frame")

    image = await camera.async_get_image(hass, entity_id_for(hass, "camera", "cam"))
    assert image.content == JPEG


async def test_push_stream_fans_out_latest_jpegs_and_stops_after_last_viewer(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
    hass_client,
) -> None:
    """The real camera MJPEG endpoint shares one producer across viewers."""
    await client.entity("cam", "camera", "Cam", features=["push_stream"])
    entity_id = entity_id_for(hass, "camera", "cam")
    flags = hass.states.get(entity_id).attributes["supported_features"]
    assert not flags & CameraEntityFeature.STREAM

    session = await client.ok("media_open", unique_id="cam")
    http = await hass_client()
    first_task = asyncio.create_task(http.get(f"/api/camera_proxy_stream/{entity_id}"))
    assert (await client.next_command())["action"] == "start_stream"
    first = await asyncio.wait_for(first_task, timeout=5)
    assert first.status == HTTPStatus.OK

    # The producer commonly binds after HA has requested the first frame. Its
    # initial media_connect must not terminate this pending viewer.
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])

    second = await http.get(f"/api/camera_proxy_stream/{entity_id}")
    assert second.status == HTTPStatus.OK
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await hass.async_block_till_done()
    assert JPEG in await asyncio.wait_for(first.content.readany(), timeout=5)
    assert JPEG in await asyncio.wait_for(second.content.readany(), timeout=5)

    # Closing each HTTP consumer only releases the ESP producer after the last
    # queue has gone away. A new frame wakes the server-side writer to observe
    # each closed transport.
    first.close()
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    await hass.async_block_till_done()
    second.close()
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    assert (await client.next_command())["action"] == "stop_stream"


async def test_push_stream_url_mode_ends_waiting_viewers(
    hass: HomeAssistant,
    client: BridgeClient,
    bridge_client_factory: Callable[[], Awaitable[BridgeClient]],
    hass_client,
) -> None:
    """URL state revokes a negotiated stream before a first JPEG can arrive."""
    await client.entity("cam", "camera", "Cam", features=["push_stream"])
    entity_id = entity_id_for(hass, "camera", "cam")
    http = await hass_client()
    request = asyncio.create_task(http.get(f"/api/camera_proxy_stream/{entity_id}"))
    assert (await client.next_command())["action"] == "start_stream"
    response = await asyncio.wait_for(request, timeout=5)

    await client.state("cam", {"still_image_url": STILL})
    assert (await client.next_command())["action"] == "stop_stream"
    assert await asyncio.wait_for(response.content.read(), timeout=5) == b""

    # A fresh authenticated producer supersedes the historical URL selection.
    # The ended response was detached, so it cannot suppress this new start.
    session = await client.ok("media_open", unique_id="cam")
    media = await bridge_client_factory()
    bound = await media.ok("media_connect", session_id=session["session_id"])
    replacement_task = asyncio.create_task(
        http.get(f"/api/camera_proxy_stream/{entity_id}")
    )
    assert (await client.next_command())["action"] == "start_stream"
    replacement = await asyncio.wait_for(replacement_task, timeout=5)
    await media.ws.send_bytes(bytes([bound["handler_id"]]) + JPEG)
    assert JPEG in await asyncio.wait_for(replacement.content.readany(), timeout=5)


async def test_push_stream_start_error_and_control_disconnect_cleanup(
    hass: HomeAssistant,
    client: BridgeClient,
    hass_client,
) -> None:
    """No producer gives 502; a disconnected producer releases a live viewer."""
    await client.entity("cam", "camera", "Cam", features=["push_stream"])
    entity_id = entity_id_for(hass, "camera", "cam")
    bridge = get_bridge(hass, client.entry)
    entity = bridge._entities["gw1__cam"]
    http = await hass_client()

    gateway = bridge._clients.pop("gw1")
    unavailable = await http.get(f"/api/camera_proxy_stream/{entity_id}")
    assert unavailable.status == HTTPStatus.BAD_GATEWAY

    # Restore the real control client, then prove connection teardown wakes the
    # pending first-frame queue without relying on an uploaded frame.
    bridge._clients["gw1"] = gateway
    request = asyncio.create_task(http.get(f"/api/camera_proxy_stream/{entity_id}"))
    assert (await client.next_command())["action"] == "start_stream"
    response = await asyncio.wait_for(request, timeout=5)
    await client.close()
    assert await asyncio.wait_for(response.content.read(), timeout=5) == b""
    assert not entity._push_stream_started
