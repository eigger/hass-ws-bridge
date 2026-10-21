"""image platform tests."""

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import BridgeClient, entity_id_for

STILL = "http://cam.local/still.jpg"


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
