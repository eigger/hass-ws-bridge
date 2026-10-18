# WebSocket Bridge (`ws_bridge`) for Home Assistant

<!-- hass-standards:badges:start -->
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square)](#-installation)
[![Release](https://img.shields.io/github/v/release/eigger/hass-ws-bridge?style=flat-square)](https://github.com/eigger/hass-ws-bridge/releases)
[![Home Assistant minimum](https://img.shields.io/badge/HA-%E2%89%A5%202026.9.0-41BDF5?style=flat-square)](hacs.json)
[![Tests](https://img.shields.io/github/actions/workflow/status/eigger/hass-ws-bridge/tests.yml?branch=main&style=flat-square&label=Tests)](https://github.com/eigger/hass-ws-bridge/actions/workflows/tests.yml)
[![Validate](https://img.shields.io/github/actions/workflow/status/eigger/hass-ws-bridge/validate.yml?branch=main&style=flat-square&label=Validate)](https://github.com/eigger/hass-ws-bridge/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/eigger/hass-ws-bridge?style=flat-square)](LICENSE)
[![Analytics reporting installs](https://img.shields.io/badge/dynamic/json?style=flat-square&color=41BDF5&label=Usage&query=%24.ws_bridge.total&url=https%3A%2F%2Fanalytics.home-assistant.io%2Fcustom_integrations.json)](https://analytics.home-assistant.io/)
<!-- hass-standards:badges:end -->

A generic Home Assistant integration that enables **any authenticated WebSocket client** to dynamically create and update entities. It is fully decoupled from specific hardware or protocols (e.g., BLE, Zigbee); as long as the client conforms to the defined communication protocol, it works out of the box.

> [한글 README (README.ko.md)](README.ko.md)


## 🚀 Key Features

- **No Additional Brokers/Ports**: Communicates directly using Home Assistant's standard WebSocket API (`/api/websocket`) and a Long-Lived Access Token. No need to run an MQTT broker or expose extra TCP ports.
- **Dynamic Entity Provisioning**: Entities are created instantly in Home Assistant as soon as the client declares them via JSON messages over the WebSocket connection.
- **Client-based Device Grouping**: Each client (identified by `gateway_id`) is registered as a parent device (Gateway) in Home Assistant. All devices/entities declared by that client are grouped as child devices (`via_device`) under it for clean organization.
- **Bi-directional Command Routing**: Supports control components including `switch`, `number`, `select`, `button`, `update`, `light`, `cover`, `fan`, `text`, `lock`, `date`, `time`, `datetime`, `valve`, `climate`, `humidifier`, `water_heater`, `siren`, `alarm_control_panel`, `media_player`, and `camera`. Control events (`command`) triggered by the HA UI or automations are routed back exclusively to the originating client.
- **Connection State Tracking (LWT)**: If the client's WebSocket connection drops, all child devices and entities registered by that client are automatically set to `unavailable` to prevent stale states.
- **Connected Clients Diagnostic Sensor**: Provides a diagnostic sensor that reports the number of currently connected WebSocket clients (`gateway_id`) in real time.


---

## 📋 Requirements

- Home Assistant 2026.9.0 or newer (per `hacs.json`). This is a HACS custom integration, not an official Home Assistant Core integration.
- An authenticated WebSocket client and a Long-Lived Access Token.

---

## 💾 Installation

### Method 1: Via HACS (Recommended)
1. Navigate to **HACS** in your Home Assistant sidebar.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Enter `https://github.com/eigger/hass-ws-bridge` as the repository URL, set the category to **Integration**, and click **Add**.
4. Install the integration, then **restart Home Assistant**.

### Method 2: Manual Installation
1. Download the `custom_components/ws_bridge` folder from this repository.
2. Copy it into your Home Assistant configuration directory under `custom_components/`.
   * Target path: `config/custom_components/ws_bridge/`
3. **Restart Home Assistant**.

---

## ⚙️ Configuration & Setup

1. **Add Integration in HA**:
   * Navigate to **Settings** -> **Devices & Services** -> **Add Integration**.
   * Search for **WebSocket Bridge** and add it. (It will initialize instantly without requiring any UI configuration.)
2. **Allow Gateway Users**:
   * Open the integration's **Configure** (options) dialog and select the users whose tokens gateways may use.
   * The list starts empty and an empty list rejects every gateway, so this step is required.
3. **Generate Long-Lived Access Token**:
   * Log in as one of the allowed users, go to the user profile page, scroll to the bottom, and click **Create Token**. Copy the token value.
4. **Configure Client**:
   * Enter the Home Assistant WebSocket URL (e.g., `ws://192.168.1.100:8123/api/websocket`) and the generated token in your client application/device.

---

## 🧪 Quick Example

```json
// after auth_ok, send ws_bridge/connect, then declare entities, then push state
{"id": 3, "type": "ws_bridge/state", "states": [{"unique_id": "temp_1", "value": 25.4}]}
```

See the documents below for entity declaration, commands and the full message set.

---

## ⚠️ Important Limitations

- Planned but not yet accepted platforms: `vacuum` / `lawn_mower` / `remote` / `todo` (see [PROTOCOL.md §6](docs/PROTOCOL.md#6-planned-platforms)).
- When a client disconnects, its entities become `unavailable` (unless `keep_last_state_on_disconnect` is enabled for that gateway).
- Always send `auth` → `ws_bridge/connect` → `ws_bridge/entity` in that order; messages before `auth_ok` are rejected.

---

## 📚 Documentation

- [Architecture, supported platforms, protocol summary](docs/reference.md)
- [Protocol specification](docs/PROTOCOL.md) / [한국어](docs/PROTOCOL_ko.md)
- [Development & testing (Korean)](docs/development.md)

---

## 💬 Feedback & Support

🐞 Found a bug? Let us know via an [Issue](https://github.com/eigger/hass-ws-bridge/issues).  
💡 Have a question or suggestion? Join the [Discussion](https://github.com/eigger/hass-ws-bridge/discussions)!


---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
