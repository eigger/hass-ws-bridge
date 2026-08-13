# WebSocket Bridge Communication Protocol Specification (PROTOCOL)

This document defines the communication protocol between the `ws_bridge` Home Assistant integration and its WebSocket clients (such as gateway apps, scripts, or ESP32 firmware).

The integration utilizes Home Assistant's standard WebSocket API (`/api/websocket`). After establishing a connection and completing the standard authentication handshake, clients can use custom commands to dynamically declare entities, update states, and receive command requests. No additional ports or brokers (like MQTT) are needed.

---

## 1. Role Definitions

- **Client**: Responsible for **declaring** entities, **pushing** state updates, and executing control commands sent from Home Assistant.
- **Integration**: Responsible for **creating** entities based on client declarations and **updating** their states. For control platforms (`switch`, `number`, `select`, `button`, `update`), it **relays** command requests from HA back to the originating client. It has no hardware-specific decoding logic.

---

## 2. Connection and Authentication

1. The client establishes a connection to `wss://<HA_URL>/api/websocket`.
2. The client performs the standard Home Assistant authentication handshake:
   - Receive: `{"type": "auth_required", "ha_version": "..."}`
   - Send: `{"type": "auth", "access_token": "<LONG_LIVED_ACCESS_TOKEN>"}`
   - Receive: `{"type": "auth_ok", "ha_version": "..."}`
3. **Only after `auth_ok`** may the client send `ws_bridge/*` commands below.
4. The client registers its gateway session:
   - Send: `{"id": <n>, "type": "ws_bridge/connect", "gateway_id": "<unique_id>", "name": "<display_name>"}`
   - `gateway_id` (String, Required): A unique identifier for the client. Used to create a gateway device in HA and namespace all associated devices and entities to avoid collision.
   - `name` (String, Optional): Human-readable gateway display name. Also used as the gateway subentry title in integration settings.
   - `app_version` (String, Optional): The firmware or application version of the client. Updates the gateway device's `sw_version` in Home Assistant.
   - `keep_last_state_on_disconnect` (Boolean, Optional, default `false`): When `true`, this gateway's entities are **not** marked `unavailable` when the WebSocket connection drops (including an ungraceful disconnect, e.g. power/Wi-Fi loss) — they keep showing their last reported state, similar to MQTT retained state without a Last Will/Testament. The integration remembers this value for the gateway (persisted to disk) until the next `ws_bridge/connect` changes it; the default (`false`) matches the previous behavior (mark unavailable on disconnect). This also covers an **HA restart**: entities for a `keep_last_state_on_disconnect` gateway are recreated immediately at HA startup from their persisted declaration and last state — available, with the last known value — without waiting for the client to reconnect.
   - On `ws_bridge/connect`, a matching subentry is **created automatically** if one does not exist (no manual registration).
   - The integration binds this WebSocket connection with the `gateway_id` to route commands specifically to this client.

> **Reconnection**: When a client reconnects, it should re-send all entity declarations (idempotent) and states. The integration will automatically restore or update them. After an HA restart, the integration persists the last state to disk, so previous values may appear before the client re-sends states (immediately, for `keep_last_state_on_disconnect` gateways — see above). Re-sending states on reconnect is still recommended for up-to-date values.

### Required Message Order

```
connect → receive auth_required → send auth → receive auth_ok → ws_bridge/connect → ws_bridge/entity → ws_bridge/state
```

Sending `ws_bridge/entity` (or any other command) before `auth_ok` causes Home Assistant to reject it as a malformed auth message (`Auth message incorrectly formatted`).

### Optional Fields

- Omit unused optional keys from JSON rather than sending explicit `null` values. (`null` is tolerated in 0.1.2+, but omission is recommended.)

### Device Hierarchy (Grouping)
Entities are organized hierarchically under their respective gateway and sub-devices:
```
Gateway Device (e.g., "Living Room Gateway" via gateway_id)
   └─ via_device ─ Sub-Device (e.g., "Multi-Sensor 1" via device_id)
                      └─ Entities (e.g., RPM, Temperature, Light, etc.)
```
The integration handles namespacing internally:
- Entity unique_id: `{gateway_id}__{unique_id}`
- Device identifier: `{gateway_id}:{device_id}`

---

## 3. Messages (Client → Home Assistant)

### 3.1 Entity Declaration (`ws_bridge/entity`)
Declares a new entity or updates its metadata. This command is idempotent; calling it multiple times will update metadata without duplicate creation.

* **Request**
  ```json
  {
    "id": 2,
    "type": "ws_bridge/entity",
    "unique_id": "multisensor_lux",
    "platform": "sensor",
    "name": "Illuminance Sensor",
    "device": {
      "id": "multisensor_01",
      "name": "Multi-Sensor"
    },
    "device_class": "illuminance",
    "unit_of_measurement": "lx",
    "state_class": "measurement",
    "icon": "mdi:weather-sunny",
    "entity_category": "diagnostic"
  }
  ```
  - `unique_id` (String, Required): Unique identifier within the client namespace.
  - `platform` (String, Required): Entity type. Must be one of: `sensor`, `binary_sensor`, `text_sensor`, `device_tracker`, `switch`, `number`, `select`, `button`, `update`.
  - `name` (String, Required): Name of the entity.
  - `device` (Object, Optional): The sub-device this entity belongs to.
    - `id` (String, Required): Unique sub-device ID.
    - `name` (String, Optional): Sub-device display name.
  - `device_class` (String, Optional): Home Assistant standard device class. Applies to every platform (e.g. `outlet`/`switch` for `switch`, `humidity`/`temperature` for `number`, `restart`/`identify`/`update` for `button`), not just `sensor`/`binary_sensor`.
  - `unit_of_measurement` (String, Optional): Unit of measurement.
  - `state_class` (String, Optional): HA state class for statistics.
  - `suggested_display_precision` (Integer, Optional, `sensor` platform): Number of decimal places to round the displayed value to (mirrors the client's own rounding config, e.g. ESPHome's `accuracy_decimals`). Without it, Home Assistant shows the raw float exactly as received, which for many sensors means long, noisy decimals (e.g. `48.85864` instead of `48.9`).
  - `icon` (String, Optional): Icon name (e.g., `mdi:thermometer`).
  - `entity_category` (String, Optional): Entity category, either `"config"` or `"diagnostic"`.
  - **Platform-Specific Fields**:
    - **`select` platform**: `options` (List of String, Required) - List of selectable options.
    - **`number` platform**: `min`, `max`, `step` (Float, Optional) - Range and step configuration.
    - **`device_tracker` platform**: no extra declare fields — the location travels in the state `value` object (see §3.2).
    - **`update` platform**: no extra declare fields — versions travel in the state `value` object (see §3.2). `device_class` defaults to `firmware` on the HA side if omitted.

* **Response**
  ```json
  {
    "id": 2,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

#### Platform Reference:
| Platform | Direction | State Value Type | Command Action |
|:---|:---:|:---|:---|
| `sensor` | Read | Number/String | — |
| `binary_sensor` | Read | Boolean | — |
| `text_sensor` | Read | String | — (created as an HA `sensor` entity — HA has no separate text-sensor domain) |
| `device_tracker` | Read | Object (`latitude`/`longitude`, see §3.2) | — |
| `switch` | Control | Boolean | `turn_on` / `turn_off` |
| `number` | Control | Number | `set_value` (requires `value`) |
| `select` | Control | String (current option) | `select_option` (requires `value` as option) |
| `button` | Control | — | `press` |
| `update` | Control | Object (`installed_version`/`latest_version`, see §3.2) | `install` / `check` |

---

### 3.2 State Update (`ws_bridge/state`)
Updates states for one or more entities in batch. If a state update arrives before its entity has been declared via `ws_bridge/entity`, the integration buffers it and applies it when the entity is registered.

* **Request**
  ```json
  {
    "id": 3,
    "type": "ws_bridge/state",
    "states": [
      {
        "unique_id": "multisensor_lux",
        "value": 350
      },
      {
        "unique_id": "temp_sensor_01",
        "value": 24.5
      }
    ]
  }
  ```
  - `states` (List, Required): List of entity state updates.
    - `unique_id` (String, Required): The original entity `unique_id` (without the gateway namespace prefix).
    - `value` (Any, Required): New state. Type depends on the platform — a scalar for most, an **object** for platforms whose state isn't a single value (currently `device_tracker` and `update`).
      - Sending the string `"unknown"` (case-insensitive) for any platform will map to Home Assistant's `unavailable` (None) state.
      - For `binary_sensor`, values of `"1"`, `"true"`, `"on"`, `"yes"` (case-insensitive) or boolean `true` are mapped to the On state.
      - For `sensor` with `device_class` of `"timestamp"` or `"date"`, string values are automatically parsed into datetime/date objects.
      - For `device_tracker`, see the object form below.
      - For `update`, see the object form below.
  - `ts` (Number, Optional): Timestamp of the state update (currently accepted by the schema but ignored by the backend).

#### `device_tracker` state (object `value`)

```json
{
  "id": 4,
  "type": "ws_bridge/state",
  "states": [
    {
      "unique_id": "car_location",
      "value": {"latitude": 37.5665, "longitude": 126.9780, "gps_accuracy": 8}
    }
  ]
}
```

- `latitude`, `longitude` (Float, Required together): The position. **Both must be present and numeric** — if either is missing or unparseable, the position is treated as unknown rather than half-applied, since a lone coordinate would place the device somewhere meaningless.
- `gps_accuracy` (Integer, Optional, default `0`): Accuracy radius in meters. Home Assistant uses it when deciding whether the device is inside a zone.
Home Assistant derives the entity state (`home` / `not_home` / a zone name) from the coordinates, so no separate state string is needed. (There is deliberately no field to override this directly — `TrackerEntity.location_name` is deprecated in Home Assistant and scheduled for removal in 2027.7.)

> **Battery**: don't put `battery_level` here. Home Assistant has deprecated `battery_level` on `device_tracker` in favour of a separate battery entity — declare a normal `sensor` with `"device_class": "battery"` instead.

#### `update` state (object `value`)

```json
{
  "id": 5,
  "type": "ws_bridge/state",
  "states": [
    {
      "unique_id": "firmware",
      "value": {
        "installed_version": "1.0.0",
        "latest_version": "1.0.1",
        "in_progress": false,
        "title": "Living Room",
        "summary": "Bug fixes"
      }
    }
  ]
}
```

- `installed_version` (String, Optional): Currently running firmware/app version.
- `latest_version` (String, Optional): Version offered by the manifest. Home Assistant shows an update as available when this differs from `installed_version`.
- `in_progress` (Boolean, Optional, default `false`): `true` while a flash is running.
- `progress` (Number, Optional, 0–100): Percent complete; only meaningful while `in_progress` is `true`.
- `title`, `summary`, `release_url` (String, Optional): Shown on the update card / release-notes dialog.

Omit empty optional keys rather than sending `""`. Sending the string `"unknown"` (or a non-object) clears the version fields.

* **Response**
  ```json
  {
    "id": 3,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

---

### 3.3 Sub-Device Availability (`ws_bridge/availability`)
Updates the online/offline availability status of a sub-device and all of its associated entities.

* **Request**
  ```json
  {
    "id": 4,
    "type": "ws_bridge/availability",
    "device_id": "multisensor_01",
    "online": false
  }
  ```
  - `device_id` (String, Required): The original sub-device ID (without the gateway namespace prefix).
  - `online` (Boolean, Required): `true` for Online (available), `false` for Offline (unavailable).

* **Response**
  ```json
  {
    "id": 4,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

---

### 3.4 Removal (`ws_bridge/remove`)
Permanently **removes** entities, sub-devices, or an entire gateway from Home Assistant. Works even when items are disconnected and `unavailable`.

When a **gateway subentry** is deleted in **Settings → WebSocket Bridge**, or when the client sends **`ws_bridge/remove`** (full gateway), the subentry, devices, and entities for that `gateway_id` are cleaned up automatically.

* **Request (single entity)**
  ```json
  {
    "id": 5,
    "type": "ws_bridge/remove",
    "unique_id": "multisensor_lux"
  }
  ```

* **Request (sub-device and its entities — exact match, default)**
  ```json
  {
    "id": 5,
    "type": "ws_bridge/remove",
    "device_id": "multisensor_01"
  }
  ```

* **Request (sub-device tree — prefix match, e.g. BLE MAC instances)**
  ```json
  {
    "id": 6,
    "type": "ws_bridge/remove",
    "device_id": "jaalee_jht",
    "mode": "prefix"
  }
  ```
  Removes the sub-device whose client `device.id` equals `jaalee_jht` **or** starts with `jaalee_jht_` (e.g. `jaalee_jht_AABBCCDDEEFF`), and all entities bound to those devices.

* **Request (entire gateway — omit both fields)**
  ```json
  {
    "id": 5,
    "type": "ws_bridge/remove"
  }
  ```

  - `unique_id` (String, Optional): Original entity `unique_id`. Takes precedence over `device_id`.
  - `device_id` (String, Optional): Sub-device ID. Removes the device and all entities bound to it.
  - `mode` (String, Optional): Removal scope when `unique_id` or `device_id` is set. Default: `"exact"`.
    - `"exact"`: Only the target whose client id **equals** `device_id` / `unique_id` (legacy behaviour).
    - `"prefix"`: The target **and** any client id that equals `target` or starts with `target_` (e.g. profile `jaalee_jht` plus MAC instances `jaalee_jht_AABBCCDDEEFF`). Use for advertisement sensors with per-MAC `device.id`.
  - Omit `unique_id` and `device_id`: Removes **all** entities, sub-devices, and the gateway device for the currently connected client.

* **Response**
  ```json
  {
    "id": 5,
    "type": "result",
    "success": true,
    "result": null
  }
  ```

---

## 4. Control Commands (Home Assistant → Client)

When a controllable entity (`switch`, `number`, `select`, `button`, `update`) is triggered in HA, a command event is pushed to the client connection registered under `ws_bridge/connect`.

The client should listen for these events, perform the physical action, and then push the updated state back using a `ws_bridge/state` message.

* **Event Message**
  ```json
  {
    "id": 1,
    "type": "event",
    "event": {
      "kind": "command",
      "unique_id": "switch_01",
      "action": "turn_on"
    }
  }
  ```
  - `id`: Matches the `id` of the `ws_bridge/connect` request sent by this client.
  - `event` (Object): Command details.
    - `kind`: Always `"command"`.
    - `unique_id`: The original `unique_id` of the entity (gateway namespace prefix stripped).
    - `action`: The action to execute (`turn_on`, `turn_off`, `press`, `set_value`, `select_option`, `install`, `check`).
    - `value` (Any, Optional): The payload value (e.g., target float for `set_value`, or string option for `select_option`).

### Example with Value
```json
{
  "id": 1,
  "type": "event",
  "event": {
    "kind": "command",
    "unique_id": "target_temp",
    "action": "set_value",
    "value": 26.5
  }
}
```

### `update` commands

- `install` — start installing the currently offered firmware (no `value`). The client should push `in_progress: true` (and `progress` if known) until the flash finishes; a successful flash typically reboots the device.
- `check` — re-fetch the update manifest. Pushed when HA calls `homeassistant.update_entity` on this entity.

---

## 5. Notes
- Recommended entity unique_id pattern: `<device_id>_<key>`.
- Entities that have not been declared via `ws_bridge/entity` will not appear in Home Assistant.
