# pylontech-rs485

Read a **Pylontech** LiFePO₄ battery over its **RS485** port using Pylontech's own ASCII protocol: every cell voltage, temperatures, current, voltage, capacity, cycles, alarms and the BMS charge/discharge limits.

- **Python 3, standard library only.** No pyserial, no other packages. Runs on any Linux (or other POSIX) machine: a server, a Raspberry Pi, a laptop.
- **No dependency on any home-automation system.** It is a library plus a command-line tool that prints JSON; feed that into whatever you like.
- Only hardware needed: the battery and a **USB-RS485 adapter**.

Released into the public domain under [The Unlicense](LICENSE): do whatever you want with it.

**Home Assistant users:** the custom integration [ha-pylontech-rs485](https://github.com/GitHubUser-2024/ha-pylontech-rs485) (install via HACS, set up in the UI) and the MQTT publisher [pylontech-ha](https://github.com/GitHubUser-2024/pylontech-ha) are both built on this library.

## Tested hardware

| | |
|---|---|
| Battery | Pylontech **US3000C** (15 cells, 74 Ah), BMS software 2.2, single module |
| Adapter | USB-RS485 dongle with **CH340** USB chip (`1a86:7523`) and an RS485 transceiver |
| Host | Linux, Python 3.11 and 3.13 |

Other Pylontech low-voltage modules that speak the same protocol (US2000C, US5000, …) will probably work. Reports welcome; they are not tested here.

## Wiring

Use the battery's **RS485** port (labelled `RS485` or `B/RS485`), not `CAN` and not `CONSOLE`. The CAN port can stay connected to your inverter/GX device at the same time.

| RJ45 pin (battery RS485 port) | Signal | Colour in a standard patch cable (T568A and T568B) |
|---|---|---|
| 7 | RS485 **A** (D+) | white-brown |
| 8 | RS485 **B** (D−) | brown |
| others | leave unconnected | |

The simplest cable is a straight patch cable cut in half: connect white-brown to the adapter's A terminal and brown to B. If the battery does not answer, swap A and B (adapter labelling varies) and try again.

Finding pin 1 on an RJ45 **plug**: gold contacts facing you, clip at the back, cable hanging down → pin 1 is on the left, pin 8 on the right. Looking **into the socket** with the clip slot at the bottom → pin 1 is on the right.

Never connect the CONSOLE port's pins 4/5 (wake-up voltage on some modules).

**DIP switches** (US3000C): switch 1 sets the RS485 baud rate, OFF = **115200** (default), ON = 9600; restart the battery after changing it. Leave the others as they are.

### Buying an adapter: it must have a transceiver

Some cables sold as "RS485 cable for US2000C/US3000C/US5000" contain **only a USB-to-UART chip** (for example a Prolific PL2303GC) and **no RS485 transceiver**. They cannot work: the battery never answers and you only see one to three garbage bytes after each request. A real adapter has a second chip next to the terminals (MAX485, SP485, SN75176, MAX3485 or similar), or the listing says so. Adapters with screw terminals make it easy to swap A/B.

## Install

```bash
git clone <this repo> && cd pylontech-rs485
pip install .                 # installs the `pylontech-rs485` command
# or without installing:
PYTHONPATH=src python3 -m pylontech_rs485 --help
```

Your user needs read/write access to the serial device (usually group `dialout`).

Use the stable path under `/dev/serial/by-id/` rather than `/dev/ttyUSB0`, which can change.

## Command line

```bash
export PYLONTECH_DEVICE=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0

pylontech-rs485 probe                       # which baud rate / address answers?
pylontech-rs485 --pretty info               # model, software, manufacturer, serial, protocol version
pylontech-rs485 --pretty read               # live values
pylontech-rs485 read --history cells.json   # live values + rolling 7-day cell statistics
pylontech-rs485 stats --history cells.json  # statistics only, no battery access
pylontech-rs485 raw 42                      # one command, raw reply (debugging)
```

Global options: `--device/-d` (or `PYLONTECH_DEVICE`), `--baud/-b` (default 115200, or `PYLONTECH_BAUD`), `--address/-a` (default 2, or `PYLONTECH_ADDRESS`), `--timeout/-t` seconds (default 2), `--retries` (default 3), `--pretty/-p`.

Exit codes: `0` OK, `2` no reply from the battery, `3` protocol error (bad frame, checksum, error code from the battery), `4` serial port error (missing device, permission, locked by another process).

The port is locked with `flock` while in use, so two runs (e.g. a cron job and a manual call) never interleave on the bus; the second one waits up to 10 s.

### `read` output

```json
{
  "timestamp": 1794389055,
  "address": 2,
  "analog": {
    "cells_mv": [3314, 3313, 3314, 3314, 3314, 3314, 3314, 3313, 3313, 3313, 3314, 3314, 3314, 3314, 3314],
    "cell_min_mv": 3313, "cell_max_mv": 3314, "cell_min_index": 2, "cell_max_index": 1, "cell_spread_mv": 1,
    "temperatures_c": {"bms": 18.8, "cells_1_4": 15.9, "cells_5_8": 15.7, "cells_9_12": 15.4, "cells_13_15": 17.1},
    "current_a": 0.7, "voltage_v": 49.706, "power_w": 34.8,
    "remaining_ah": 21.127, "full_ah": 74.0, "soc_pct": 28.6, "cycles": 799,
    "address": 2, "data_flag": 0
  },
  "alarms": {
    "cells": ["normal", "..."], "temperatures": {"bms": "normal", "...": "..."},
    "charge_current": "normal", "pack_voltage": "normal", "discharge_current": "normal",
    "active": [],
    "status": {
      "protections": [], "precharge_mosfet": false, "charge_mosfet": true, "discharge_mosfet": true,
      "using_battery_power": true, "buzzer": false, "fully_charged": false, "heater": false,
      "discharge_current": false, "charge_current": true, "cell_errors": [], "extra": [0]
    },
    "status_bytes": [0, 14, 128, 0, 0, 0], "address": 2, "data_flag": 0
  },
  "management": {
    "charge_voltage_limit_v": 53.25, "discharge_voltage_limit_v": 45.0,
    "charge_current_limit_a": 37.0, "discharge_current_limit_a": 37.0,
    "charge_enabled": true, "discharge_enabled": true, "charge_immediately": false,
    "charge_immediately_2": false, "full_charge_request": false, "flags": 192, "address": 2
  }
}
```

Notes:

- `current_a` is positive while charging, negative while discharging.
- `soc_pct` is `remaining_ah / full_ah` as reported over RS485. An inverter or GX device that reads SOC over CAN may show a slightly different number.
- Temperatures are labelled for a 15-cell module (BMS board + four cell groups); other layouts get `t1`, `t2`, ….
- `alarms.active` lists everything not normal, as readable text; empty means all clear. Active BMS protections and cell errors from the status bytes are included (`protection: …`, `cell N error`).
- `alarms.status` decodes the status bytes (raw in `status_bytes`):

  | Byte | Bits |
  |---|---|
  | Status 1 | protections: 0 module over voltage, 1 cell under voltage, 2 charge over current, 4 discharge over current, 5 discharge over temperature, 6 charge over temperature, 7 module under voltage |
  | Status 2 | 0 pre-charge MOSFET, 1 charge MOSFET, 2 discharge MOSFET, 3 running on battery power |
  | Status 3 | 0 buzzer, 3 fully charged, 5 heater, 6 effective discharge current, 7 effective charge current |
  | Status 4 / 5 | cell error, cells 1–8 / 9–16 |

  Bit meanings follow the Pylontech RS485 protocol document. Checked on a US3000C: `00 0E 80` while charging (both MOSFETs on, charge current flowing). Further bytes (the US3000C sends one more `00`) end up in `extra`.

### History and statistics

With `--history FILE`, each `read` appends the cell voltages to a small JSON file (`[[timestamp, [mV, …]], …]`), drops samples older than the window (`--window-days`, default 7) and adds a `history` block:

- per cell: `now_mv`, `min_mv`, `max_mv`, `avg_mv` over the window, and the **deviation from the pack mean** of the same sample, now (`dev_now_mv`), averaged (`dev_avg_mv`) and the **largest** one in the window (`dev_max_mv`, signed, with its time `dev_max_ts`). The average hides short sags or peaks; the max shows which cell drifts furthest;
- pack: `spread_now_mv` (highest − lowest cell), `spread_avg_mv`, `spread_min_mv`, `spread_max_mv`, plus `samples` and `span_days`.

Min/max per cell mostly follow the state of charge. The deviation columns are the ones that show imbalance between cells. Run it from cron or a systemd timer, e.g. every 10 minutes (about 1000 samples per week).

## Library

```python
from pylontech_rs485 import Battery, history

with Battery("/dev/serial/by-id/usb-...", baud=115200, address=2) as bat:
    print(bat.info())            # model, software_version, manufacturer, serial, protocol_version
    data = bat.read_all()        # analog + alarms + management
    cells = data["analog"]["cells_mv"]

samples = history.add(history.load("cells.json"), data["timestamp"], cells)
history.save("cells.json", samples)
print(history.stats(samples))
```

Individual calls: `bat.analog()`, `bat.alarms()`, `bat.management()`, `bat.manufacturer()`, `bat.serial_number()`, `bat.protocol_version()`, `bat.command(cid2, info)` (validated INFO hex), `bat.raw(cid2, info)` (raw bytes). Pure framing/decoding without I/O is in `pylontech_rs485.protocol`.

Errors: `NoResponse` (nothing received), `ProtocolError` (bad frame), `ReturnCodeError` (battery replied with an error code; not retried), `port.PortBusy`, and normal `OSError` for device problems.

## Protocol notes

ASCII frames, 8N1:

```
~  VER  ADR  CID1  CID2/RTN  LENGTH  INFO  CHKSUM  \r
```

All fields are ASCII hex. `VER` = `20`, `CID1` = `46` (battery), `ADR` = battery address (**2** for a single module on the tested battery). In a request the fifth field is the command (CID2), in a reply the return code (RTN, `00` = OK). `LENGTH` = 4-bit LCHKSUM + 12-bit INFO length in characters; LCHKSUM = two's complement (mod 16) of the sum of the three length nibbles. `CHKSUM` = two's complement (mod 65536) of the sum of all ASCII codes between `~` and the checksum.

Example: analog values of the battery at address 2 = `~20024642E00202FD33\r`.

| CID2 | Request INFO | Reply |
|---|---|---|
| `4F` | — | protocol version (in VER); used as a ping |
| `42` | address | data flag, address, cell count + mV per cell, temperature count + values in 0.1 K (°C = (raw − 2731) / 10), current (signed, **0.1 A**), voltage (mV), remaining capacity (mAh), user-defined byte, full capacity, cycles; if the user-defined byte is `04`, 3-byte remaining and full capacities (mAh) follow and replace the 2-byte ones |
| `44` | address | per-cell and per-temperature state (`00` normal, `01` low, `02` high, `F0` fault), charge current / pack voltage / discharge current state, then status bytes 1–5 (decoded, see above) |
| `92` | address | charge voltage limit, discharge voltage limit (mV), charge / discharge current limit (signed, 0.1 A), flags: `80` charge enabled, `40` discharge enabled, `20` charge immediately, `10` charge immediately 2, `08` full charge request |
| `51` | — | model (10 bytes ASCII), software version (2 bytes), manufacturer (20 bytes ASCII) |
| `93` | address | address + serial number (ASCII) |

The current scale (0.1 A) was checked against an external shunt.

**No Modbus.** The US3000C's RS485 port speaks only this protocol; there is no Modbus mode to enable.

## Troubleshooting

1. `pylontech-rs485 probe` — if nothing answers at any baud rate/address:
2. Check the adapter really has an RS485 transceiver (see above).
3. Swap A and B.
4. Check you are in the RS485 port, and DIP switch 1 matches the baud rate.
5. A few garbage bytes after each request and nothing else = the battery is not answering (the garbage is the adapter switching direction).

`raw` shows exactly what was sent and received.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

Tests use frames recorded from a real US3000C (`tests/frames.py`; the serial number was replaced with a dummy) and need no hardware. `tests/test_hardware.py` runs against a real battery when `PYLONTECH_DEVICE` is set.
