# Changelog

## 0.3.0 — 2026-11-11

- History statistics: per cell `dev_max_mv` (largest deviation from the pack mean in the window, signed) and `dev_max_ts` (when).

## 0.2.0 — 2026-11-11

- 0x44: status bytes decoded (`alarms.status`): BMS protections, charge / discharge / pre-charge MOSFET, effective charge / discharge current, fully charged, heater, buzzer, per-cell error flags. Active protections and cell errors are added to `alarms.active`. Raw bytes stay in `status_bytes`.
- New `protocol.decode_status()`.

## 0.1.0 — 2026-11-11

First version.

- Library: framing and checksums, commands 0x4F (ping), 0x42 (analog), 0x44 (alarms), 0x92 (charge/discharge management), 0x51 (manufacturer), 0x93 (serial); retries; exclusive port lock.
- CLI `pylontech-rs485` with `read`, `info`, `stats`, `raw`, `probe`; JSON output.
- Optional rolling history file with per-cell and pack-spread statistics.
- Tests from frames recorded on a real US3000C; optional hardware test.
