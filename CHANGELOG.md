# Changelog

## 0.1.0 — 2026-11-11

First version.

- Library: framing and checksums, commands 0x4F (ping), 0x42 (analog), 0x44 (alarms), 0x92 (charge/discharge management), 0x51 (manufacturer), 0x93 (serial); retries; exclusive port lock.
- CLI `pylontech-rs485` with `read`, `info`, `stats`, `raw`, `probe`; JSON output.
- Optional rolling history file with per-cell and pack-spread statistics.
- Tests from frames recorded on a real US3000C; optional hardware test.
