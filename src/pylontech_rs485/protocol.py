"""Pylontech RS485 protocol (ASCII framing, "protocol 3.5" family): framing and decoding.

Pure functions only, no I/O, so everything here can be tested without hardware.

Frame layout (all fields are ASCII hex, except SOI and EOI)::

    ~  VER  ADR  CID1  CID2/RTN  LENGTH  INFO  CHKSUM  \\r
       2    2    2     2         4       n     4

* VER is ``20`` and CID1 is ``46`` (battery) on the batteries this was tested with.
* In a request the fifth field is the command (CID2); in a response it is the
  return code (RTN, ``00`` = OK).
* LENGTH = 4-bit checksum nibble (LCHKSUM) + 12-bit length of INFO in ASCII chars.
  LCHKSUM is the two's complement (mod 16) of the sum of the three length nibbles.
* CHKSUM is the two's complement (mod 65536) of the sum of the ASCII codes of all
  characters between ``~`` and CHKSUM.
"""

VER = 0x20
CID1_BATTERY = 0x46

# Command codes (CID2) implemented here
CMD_PROTOCOL_VERSION = 0x4F
CMD_ANALOG = 0x42
CMD_ALARM = 0x44
CMD_MANAGEMENT = 0x92
CMD_MANUFACTURER = 0x51
CMD_SERIAL = 0x93

RTN_CODES = {
    0x00: "OK",
    0x01: "VER error",
    0x02: "CHKSUM error",
    0x03: "LCHKSUM error",
    0x04: "CID2 invalid",
    0x05: "command format error",
    0x06: "invalid data",
    0x90: "ADR error",
    0x91: "communication error",
}

# Temperature probe labels for a 15-cell module (US3000C); other layouts get generic labels.
TEMP_LABELS_15 = ["bms", "cells_1_4", "cells_5_8", "cells_9_12", "cells_13_15"]

ALARM_STATES = {0x00: "normal", 0x01: "below lower limit", 0x02: "above upper limit", 0xF0: "other fault"}


class ProtocolError(Exception):
    """Malformed frame, checksum mismatch or a non-OK return code."""


class ReturnCodeError(ProtocolError):
    def __init__(self, rtn):
        self.rtn = rtn
        super().__init__("battery returned RTN 0x%02X (%s)" % (rtn, RTN_CODES.get(rtn, "unknown")))


def checksum(body):
    """CHKSUM of a frame body (str between '~' and CHKSUM)."""
    return (~sum(body.encode("ascii")) + 1) & 0xFFFF


def length_field(info_len):
    """LENGTH field value for an INFO of `info_len` ASCII characters."""
    if not 0 <= info_len <= 0xFFF:
        raise ValueError("INFO too long")
    nibbles = (info_len & 0xF) + ((info_len >> 4) & 0xF) + ((info_len >> 8) & 0xF)
    lchk = (~nibbles + 1) & 0xF
    return (lchk << 12) | info_len


def build_frame(address, cid2, info="", cid1=CID1_BATTERY, ver=VER):
    """Build a request frame. `info` is the INFO field as an ASCII hex string."""
    info = info.upper()
    body = "%02X%02X%02X%02X%04X%s" % (ver, address, cid1, cid2, length_field(len(info)), info)
    return ("~%s%04X\r" % (body, checksum(body))).encode("ascii")


def parse_frame(raw):
    """Parse a response frame. Returns a dict with ver, address, cid1, rtn, info (hex str).

    Raises ProtocolError on framing/checksum errors and ReturnCodeError if RTN != 0.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("ascii")
        except UnicodeDecodeError:
            raise ProtocolError("non-ASCII bytes in frame: %r" % raw[:60])
    s = raw.strip()
    if not s.startswith("~") or len(s) < 17:
        raise ProtocolError("not a frame: %r" % raw[:60])
    body, chk = s[1:-4], s[-4:]
    try:
        if int(chk, 16) != checksum(body):
            raise ProtocolError("CHKSUM mismatch: got %s, expected %04X" % (chk, checksum(body)))
        ver, adr, cid1, rtn = (int(body[i:i + 2], 16) for i in (0, 2, 4, 6))
        length = int(body[8:12], 16)
    except ValueError:
        raise ProtocolError("non-hex characters in frame: %r" % s[:60])
    info_len = length & 0xFFF
    if length_field(info_len) != length:
        raise ProtocolError("LCHKSUM mismatch in LENGTH %04X" % length)
    info = body[12:]
    if len(info) != info_len:
        raise ProtocolError("INFO length %d does not match LENGTH %d" % (len(info), info_len))
    if rtn != 0:
        raise ReturnCodeError(rtn)
    return {"ver": ver, "address": adr, "cid1": cid1, "rtn": rtn, "info": info}


class _Reader:
    """Sequential reader over an INFO hex string."""

    def __init__(self, info):
        self.h, self.i = info, 0

    def remaining(self):
        return (len(self.h) - self.i) // 2

    def u(self, n, signed=False):
        if self.i + 2 * n > len(self.h):
            raise ProtocolError("INFO too short")
        v = int(self.h[self.i:self.i + 2 * n], 16)
        self.i += 2 * n
        if signed and v >= 1 << (8 * n - 1):
            v -= 1 << (8 * n)
        return v

    def raw(self, n):
        if self.i + 2 * n > len(self.h):
            raise ProtocolError("INFO too short")
        b = bytes.fromhex(self.h[self.i:self.i + 2 * n])
        self.i += 2 * n
        return b


def _temp_labels(n_cells, n_temps):
    if n_cells == 15 and n_temps == len(TEMP_LABELS_15):
        return TEMP_LABELS_15
    return ["t%d" % (i + 1) for i in range(n_temps)]


def _kelvin10(v):
    return round((v - 2731) / 10.0, 1)


def decode_analog(info):
    """Decode the INFO of a 0x42 (analog values) response.

    Units: cell / pack voltages in mV and V, current in A (positive = charging),
    temperatures in degC, capacities in Ah.
    """
    r = _Reader(info)
    data_flag = r.u(1)
    address = r.u(1)
    cells = [r.u(2) for _ in range(r.u(1))]
    temps_raw = [r.u(2) for _ in range(r.u(1))]
    current = r.u(2, signed=True) / 10.0
    voltage = r.u(2) / 1000.0
    remaining = r.u(2)
    user_defined = r.u(1)
    full = r.u(2)
    cycles = r.u(2)
    if user_defined == 4:  # 3-byte capacities follow (needed above 65 Ah)
        remaining = r.u(3)
        full = r.u(3)
    labels = _temp_labels(len(cells), len(temps_raw))
    lo, hi = min(cells), max(cells)
    return {
        "address": address,
        "data_flag": data_flag,
        "cells_mv": cells,
        "cell_min_mv": lo,
        "cell_max_mv": hi,
        "cell_min_index": cells.index(lo) + 1,
        "cell_max_index": cells.index(hi) + 1,
        "cell_spread_mv": hi - lo,
        "temperatures_c": {lbl: _kelvin10(v) for lbl, v in zip(labels, temps_raw)},
        "current_a": current,
        "voltage_v": voltage,
        "power_w": round(voltage * current, 1),
        "remaining_ah": remaining / 1000.0,
        "full_ah": full / 1000.0,
        "soc_pct": round(100.0 * remaining / full, 1) if full else None,
        "cycles": cycles,
    }


def _alarm_state(v):
    return ALARM_STATES.get(v, "unknown 0x%02X" % v)


# Status bytes that follow the pack-level states in a 0x44 reply (Pylontech RS485
# protocol 3.3/3.5, "Status 1".."Status 5"). Bit -> name.
STATUS1_PROTECTIONS = {
    0: "module over voltage",
    1: "cell under voltage",
    2: "charge over current",
    4: "discharge over current",
    5: "discharge over temperature",
    6: "charge over temperature",
    7: "module under voltage",
}
STATUS2_BITS = {0: "precharge_mosfet", 1: "charge_mosfet", 2: "discharge_mosfet", 3: "using_battery_power"}
STATUS3_BITS = {0: "buzzer", 3: "fully_charged", 5: "heater", 6: "discharge_current", 7: "charge_current"}


def decode_status(status_bytes):
    """Decode the trailing status bytes of a 0x44 reply.

    ``status_bytes`` is the list after the three pack-level states. Missing bytes
    count as 0; bytes after Status 5 are returned unchanged in ``extra``.

    * ``protections``: active protections from Status 1 (empty = none)
    * ``charge_mosfet`` / ``discharge_mosfet`` / ``precharge_mosfet`` /
      ``using_battery_power``: Status 2 bits
    * ``charge_current`` / ``discharge_current``: Status 3 "effective current" bits
      (the BMS sees a real charge / discharge current), plus ``fully_charged``,
      ``heater``, ``buzzer``
    * ``cell_errors``: cell numbers flagged in Status 4 (cells 1-8) and Status 5 (9-16)
    """
    b = list(status_bytes) + [0] * max(0, 5 - len(status_bytes))
    s1, s2, s3, s4, s5 = b[:5]
    out = {"protections": [name for bit, name in sorted(STATUS1_PROTECTIONS.items()) if s1 >> bit & 1]}
    out.update({name: bool(s2 >> bit & 1) for bit, name in STATUS2_BITS.items()})
    out.update({name: bool(s3 >> bit & 1) for bit, name in STATUS3_BITS.items()})
    out["cell_errors"] = [i + 1 for i in range(8) if s4 >> i & 1] + [i + 9 for i in range(8) if s5 >> i & 1]
    out["extra"] = b[5:]
    return out


def decode_alarm(info):
    """Decode the INFO of a 0x44 (alarm info) response.

    Returns per-cell / per-temperature states, the three pack-level states, the
    decoded status bytes (``status``, see :func:`decode_status`; raw in
    ``status_bytes``) and a list of active alarms (empty = all normal). Active
    protections and cell errors from the status bytes are listed as alarms too.
    """
    r = _Reader(info)
    data_flag = r.u(1)
    address = r.u(1)
    cells = [r.u(1) for _ in range(r.u(1))]
    temps = [r.u(1) for _ in range(r.u(1))]
    labels = _temp_labels(len(cells), len(temps))
    pack = {}
    for key in ("charge_current", "pack_voltage", "discharge_current"):
        pack[key] = r.u(1) if r.remaining() else 0
    status = list(r.raw(r.remaining()))
    active = ["cell %d %s" % (i + 1, _alarm_state(v)) for i, v in enumerate(cells) if v]
    active += ["temperature %s %s" % (labels[i], _alarm_state(v)) for i, v in enumerate(temps) if v]
    active += ["%s %s" % (k.replace("_", " "), _alarm_state(v)) for k, v in pack.items() if v]
    st = decode_status(status)
    active += ["protection: %s" % name for name in st["protections"]]
    active += ["cell %d error" % c for c in st["cell_errors"]]
    return {
        "address": address,
        "data_flag": data_flag,
        "cells": [_alarm_state(v) for v in cells],
        "temperatures": {lbl: _alarm_state(v) for lbl, v in zip(labels, temps)},
        "charge_current": _alarm_state(pack["charge_current"]),
        "pack_voltage": _alarm_state(pack["pack_voltage"]),
        "discharge_current": _alarm_state(pack["discharge_current"]),
        "active": active,
        "status": st,
        "status_bytes": status,
    }


def decode_management(info):
    """Decode the INFO of a 0x92 (charge / discharge management) response."""
    r = _Reader(info)
    address = r.u(1)
    out = {
        "address": address,
        "charge_voltage_limit_v": r.u(2) / 1000.0,
        "discharge_voltage_limit_v": r.u(2) / 1000.0,
        "charge_current_limit_a": r.u(2, signed=True) / 10.0,
        "discharge_current_limit_a": abs(r.u(2, signed=True)) / 10.0,
    }
    flags = r.u(1)
    out.update({
        "flags": flags,
        "charge_enabled": bool(flags & 0x80),
        "discharge_enabled": bool(flags & 0x40),
        "charge_immediately": bool(flags & 0x20),
        "charge_immediately_2": bool(flags & 0x10),
        "full_charge_request": bool(flags & 0x08),
    })
    return out


def _text(b):
    return b.decode("ascii", "replace").strip("\x00 ")


def decode_manufacturer(info):
    """Decode the INFO of a 0x51 (manufacturer info) response."""
    r = _Reader(info)
    model = _text(r.raw(10))
    sw = r.raw(2)
    manufacturer = _text(r.raw(min(20, r.remaining())))
    return {"model": model, "software_version": "%d.%d" % (sw[0], sw[1]),
            "manufacturer": manufacturer.rstrip("-")}


def decode_serial(info):
    """Decode the INFO of a 0x93 (serial number) response."""
    r = _Reader(info)
    address = r.u(1)
    return {"address": address, "serial": _text(r.raw(r.remaining()))}
