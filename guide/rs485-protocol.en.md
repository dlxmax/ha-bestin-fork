[한국어](rs485-protocol.md)

# BESTIN RS-485 protocol primer

How the frames the wallpad exchanges with the home's devices over RS-485 look and how the exchange works. Everything here was seen on one wallpad (two EW11 adapters); other models may differ.

## 1. Buses

The wallpad has several independent RS-485 buses (9600 baud, 8N1). Device addresses are per bus, so the same address (`0x31`) is a different device on different buses. An EW11 adapter exposes a bus over TCP (port `8899`) and sends every received byte to all connected clients, so with two clients each also sees the other's traffic.

| Bus | Devices | Address (header) |
|---|---|---|
| Control | heating controller | `28` |
| | gas valves 1, 2 | `31`, `32` (10-byte) |
| | ventilation | `61` (10-byte) |
| Energy | lights and outlets | `31` (variable length) |
| | standby cut-off units | `41`–`43` |
| | HEMS (meters) | `D1` |

Other buses (smart switches, elevator call, …) exist but are not handled here.

## 2. Frames

Every frame starts with `02` and ends with a checksum byte. There are two shapes.

**Variable length**: `02 <header> <length> <command> <sequence> <data…> <checksum>`. The length is the whole frame in bytes, start and checksum included.

**Fixed 10 bytes** (gas valve `31`/`32`, ventilation `61`, door lock `41`): `02 <header> <command> <sequence> <5 data bytes> <checksum>`. There is no length byte; the byte after the header is the command.

```
variable : 02 41 08 91 6b 01 16 a2                 (cut-off unit reply)
fixed    : 02 32 00 52 00 00 00 00 00 66           (gas valve 2 status poll)
```

- **Checksum**: `c = 3`, then for every byte except the last `c = ((c ^ byte) + 1) & 0xFF`; the result is the last byte.
- **Request and reply**: the wallpad sends a request and the device answers. The reply command is the request command plus `0x80` (`11`→`91`, `01`→`81`, `21`→`A1`, `22`→`A2`, `42`→`C2`; in the fixed shape `00`→`80`, `02`→`82`), and the reply echoes the request's sequence byte.
- **Sequence**: a byte that changes with every command the wallpad sends; the integration checks that the reply to a command carries the same one.
- **Polling**: the wallpad polls constantly (heating summary about once a second, device info every 5 minutes, outside temperature every 30 minutes). A device only speaks when polled, so listening is enough to follow state.

### Finding frame boundaries

The stream has no frame markers. Find `02`, check that the next byte is a known header, then read the length: 10 bytes for headers `31`/`32`/`41` when the next byte is one of `00 01 02 80 81 82`, and for `61`/`17`; otherwise the third byte is the length. `02` also occurs inside data, so when a candidate has a bad length or checksum, drop one byte and look again. Fixed-length devices must be recognised by header first: read as a length, the `80` of a gas valve reply would swallow the frames after it.

## 3. By device

### Heating controller (`28`, control bus)

One thermostat per room (5 on this wallpad, rooms 1–5).

| Cmd | Direction | Content |
|---|---|---|
| `11` → `91` | one room | the poll is 7 bytes `02 28 07 11 <seq> <room> <checksum>`; the reply is 16 bytes: byte 5 room, 6 flags (bit 0 on, bit 4 valve open = heating now), 7 setpoint (bits 0–5 whole °C, bit 6 = +0.5), 8–9 current temperature × 10, big-endian |
| `12` | set | 14 bytes: byte 5 room, 6 = `01` on / `02` off, 7 = setpoint (same encoding) |
| `21` → `A1` | all rooms | clock + 4 bytes per room (mode and valve, setpoint, current temperature 2 bytes), about once a second |
| `22` → `A2` | set all | the one seen carried only the clock (10:02); the reply has `A1`'s layout |
| `01` → `81` | device info | 18-byte device info: room count, feature flags, setpoint range, vendor, firmware |
| `42` → `C2` | outside temperature | the wallpad sends the outside temperature (`42`), the controller answers with it and the AI mode (`C2`) |

```
02 28 10 91 12 04 01 56 00 e9 00 25 00 00 00 26   room 4, on, setpoint 22.5 °C, now 23.3 °C
```

A `91` is a thermostat state only when its length byte is `10` (16 bytes); reading another `28` frame (such as the 18-byte `81`) as one gives nonsense.

#### Device info `01` → `81`

The wallpad asks every 5 minutes (`01`) and the controller answers with 18 bytes. It is a **fixed spec sheet**, not a measurement, so the values never change. Control bus (`28`) only.

```
02 28 12 81 12 | 05 1d 03 05 28 10 0e 04 16 01 01 06 | 9d
```

| Byte | Name | Example | Meaning |
|---|---|---|---|
| 3 | command | `81` | device info reply (request is `01`) |
| 5 | rooms | `05` | room count (1–8) |
| 6 | flags 1 | `1d` | bit0 half-degree step, bit1 outing, bit2 sleep, bit3 reservation, bit4 pause (top 3 bits must be 0) |
| 7 | flags 2 | `03` | bit0 AI, bit1 outside temperature, bit2 **boiler**, bit3 leak (top 4 bits must be 0) |
| 8 | min temp | `05` | minimum setpoint °C (5–20) |
| 9 | max temp | `28` | maximum setpoint °C (21–50) |
| 10 | vendor | `10` | vendor code (1 or more) |
| 11–13 | firmware date | `0e 04 16` | year (2000 + value), month, day (hex `16` = day 22) → 2014-04-22 |
| 14 | firmware build number | `01` | |
| 15–16 | protocol version (main.sub) | `01 06` | 1.6 |

The example reads as: 5 rooms; 0.5° steps, sleep, reservation and pause supported, outing not; AI and outside temperature supported, **no boiler**, no leak sensor; setpoint range 5–40 °C; vendor 16. It is not a boiler temperature: no boiler request appears on this wallpad bus and the boiler bit in flags 2 is off. Its length is not `10` (16 bytes), so it must not be read as a thermostat `91`.

#### Outside temperature `42` → `C2`

Every 30 minutes (at :02 and :32) the wallpad sends the outside temperature (`42`) and the controller answers with the outside temperature and the AI mode (`C2`).

```
02 28 0b 42 70 | 01 02 00 00 00 | 1b          wallpad → heating  (payload: flag 1, 2 °C, mode 0 = unchanged)
02 28 0a c2 70 | 02 01 32 23    | 88          heating → wallpad
```

| Byte | Meaning |
|---|---|
| 5 | outside temperature: bits 0–5 whole °C (max 60), bit 6 = +0.5, bit 7 = negative |
| 6 | AI mode: 1 = on, 2 = off |
| 7–8 | unknown bytes (`32 23`, identical in every frame seen) |

The wallpad never **changes** AI mode: every `42` request seen carries "unchanged" (`0`) in the AI slot. The temperature is not a sensor value but the current temperature from the weather information the complex's server pushes to the wallpad (forwarded only when the publish date is today, and only the temperature, so it differs a little from a weather sensor). What AI mode actually does is unconfirmed.

### Gas valve (`31`, `32`, fixed 10 bytes)

One header per valve (`31` first, `32` second). Only two commands: status poll `00` and close `02`. No open command is known; over the bus the valve can only be closed.

```
poll  : 02 32 00 52 00 00 00 00 00 66
reply : 02 32 80 52 80 01 00 00 00 67    byte 5: 0 closed, 1 open, 2 operating
```

### Ventilation (`61`, fixed 10 bytes)

| Cmd | Bytes 5, 6 | Meaning |
|---|---|---|
| `00` | — | status poll |
| `01` | `<on 0/1> 01` | on, off |
| `03` | `00 <speed 1–3>` | speed |
| `07` | `<10 or 00> …` | natural ventilation on, off |

In the reply `80`, byte 5: bit 0 on, bit 4 natural ventilation; byte 6: speed.

### Lights and outlets (`31`, variable length, energy bus)

Polled per room (`02 31 07 11 <seq> <room> <checksum>`). The reply is 30 bytes: byte 5 room (low nibble), 6 light bitmask (bit N = light N), 7 outlet bits 0–1 plus bit 4 = standby cut, 8–11 two cut-off thresholds × 10, 12–13 `dcvalue` × 10 (meaning unconfirmed), then from byte 14 two bytes per outlet of power consumption × 10. Room 1 has 4 lights and 3 outlets, the other rooms 2 and 2.

Control command (13 bytes, command `01`): byte 5 room, 6 = `(1 << light) | 80` for on or `1 << light` for off, 7 outlet bits, 8 standby cut (`83` on / `03` off), 11 = `04` (light on) or `09 << outlet` (outlet on), `00` for off.

### Standby cut-off units (`41`–`43`, energy bus)

Poll `02 4x 07 11 <seq> <circuits> <checksum>`, reply `02 4x <length> 91 <seq> <circuits> <one status byte per circuit> <checksum>` (status byte: bits 0–1 mode, 2–3 cut off or not, 4–5 cut-off value status, 6–7 overload). The same header `41` in the fixed 10-byte shape (`02 41 00 …`) is a door lock.

Example status frame (`02 41 08 91 6b 01 16 a2`): byte 5 = circuit count, 6… = one status byte per circuit.

| Bits | Value | Meaning |
|---|---|---|
| 0–1 | `1` / `2` | mode true or false; it looks like the unit's automatic cut-off mode switch but is unconfirmed. All units seen report false |
| 2–3 | `4` / `8` | not cut / cut off (circuit power is cut) |
| 4–5 | `0` / `16` or `32` | "cut-off value status"; it looks like "a cut-off threshold is set" but is unconfirmed, and the threshold itself is not in this frame |
| 6–7 | `0` / `64` | ok / overload error |

Example: `0x16` = `0001 0110` → mode false, not cut, cut-off value status true, no overload. All three units on the wallpad we checked report this.

### HEMS meters (`D1`, energy bus)

The poll `D1 … 02` is answered by a 48-byte `82`. Each meter has a 4-byte total and a 2-byte live value, both BCD (read the hex digits as decimal). Totals: bytes 8–11 electricity, 16–19 water, 24–27 hot water, 32–35 gas, 40–43 heat; live values are two bytes starting at 13, 21, 29, 37, 45 (same order, 8 bytes apart). A 34-byte variant (no hot water or heat) has the water total at 17–19 (3 bytes) and gas at 25–28.

## 4. Other gateway shapes

The integration also has light and outlet code for the `Gen2` (headers `30`–`3F`) and `AIO` (headers `50`–`5F`, `17`) shapes. They do not appear on this wallpad, so they are not described here; the code (`parse_state_gen2`, `parse_state_aio` in `controller.py`) is the reference.

## 5. Frame list

Every frame seen on the two EW11 adapters of one wallpad. Keys are `header/length(decimal)/command` (the same as `packet_types` in the diagnostics).

**Control bus (EW11 #1)**

| Key | Direction | Meaning |
|---|---|---|
| `28/7/11` | wallpad → heating | room status poll |
| `28/16/91` | heating → wallpad | one room's state: mode, setpoint, current temperature |
| `28/6/21` | wallpad → heating | all-room summary poll (about 1/s) |
| `28/29/A1` | heating → wallpad | clock + every room's mode, valve, setpoint and current temperature (5 rooms = 29 bytes); repeats `91` |
| `28/13/22` | wallpad → heating | set-all-rooms command; the one seen carried only the clock (10:02), no mode or setpoint |
| `28/29/A2` | heating → wallpad | reply to `22`, same layout as `A1` |
| `28/6/01` | wallpad → heating | device-info poll (every 5 min) |
| `28/18/81` | heating → wallpad | device info |
| `28/11/42` | wallpad → heating | outside temperature hand-over |
| `28/10/C2` | heating → wallpad | reply to `42`: outside temperature, AI mode |
| `31/10/00`, `32/10/00` | wallpad → gas valve 1, 2 | status poll |
| `31/10/80`, `32/10/80` | gas valve → wallpad | valve state |
| `61/10/00` | wallpad → ventilation | status poll |
| `61/10/80` | ventilation → wallpad | ventilation state |

**Energy bus (EW11 #2)**

| Key | Direction | Meaning |
|---|---|---|
| `31/7/11` | wallpad → lights and outlets | status poll |
| `31/30/91` | lights and outlets → wallpad | lights and outlets (30 bytes) |
| `41/7/11`, `42/7/11`, `43/7/11` | wallpad → cut-off unit | status poll |
| `41/8/91`, `42/8/91`, `43/8/91` | cut-off unit → wallpad | standby cut-off unit state |
| `D1/7/02` | wallpad → HEMS | usage poll |
| `D1/48/82` | HEMS → wallpad | electric, water, hot water, gas and heat totals and live values |

The headers in this table are the ones seen on one wallpad. The integration's framer (`hub.py`) only recognises `0x17`, `0x28`, `0x31`, `0x32`, `0x41`–`0x43`, `0x61`, `0xD1`, AIO `0x50`–`0x5F` and Gen2 `0x30`–`0x3F`.

## 6. What is not known

- Bytes 10–14 of the heating `91`, parts of each room entry in `A1`, and bytes 7–8 of the `C2` reply (`32 23`) have no known meaning; their values were never seen to change.
- The `mode` and `cutvalue` bits of the cut-off units are inferred.
- If a frame is not understood, open an issue with the `packet_types` keys whose `ignored` is above 0 in the diagnostics.
