"""camera platform tests."""

from http import HTTPStatus

import pytest
from homeassistant.components import camera
from homeassistant.components.camera import CameraEntityFeature, CameraState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .conftest import BridgeClient, call_service, entity_id_for

STILL = "http://cam.local/still.jpg"


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
