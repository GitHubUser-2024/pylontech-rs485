"""Command line interface: ``pylontech-rs485 --device DEV <command>``. Output is JSON."""

import argparse
import json
import os
import sys
import time

from . import __version__, history
from . import protocol as P
from .battery import DEFAULT_ADDRESS, DEFAULT_BAUD, Battery, NoResponse
from .port import BAUD_RATES, PortBusy, SerialPort

EXIT_NO_RESPONSE = 2
EXIT_PROTOCOL = 3
EXIT_PORT = 4


def _dump(obj, args):
    json.dump(obj, sys.stdout, indent=2 if args.pretty else None, sort_keys=False)
    sys.stdout.write("\n")


def cmd_read(bat, args):
    data = bat.read_all()
    if args.history:
        samples = history.add(history.load(args.history), data["timestamp"],
                              data["analog"]["cells_mv"], args.window_days * 86400)
        history.save(args.history, samples)
        data["history"] = history.stats(samples)
    _dump(data, args)


def cmd_info(bat, args):
    _dump(bat.info(), args)


def cmd_stats(args):
    if not args.history:
        sys.exit("stats needs --history FILE")
    _dump(history.stats(history.load(args.history)), args)


def cmd_raw(bat, args):
    cid2 = int(args.cid2, 16)
    info = args.info if args.info is not None else "%02X" % bat.address
    reply = bat.raw(cid2, info)
    out = {"request": P.build_frame(bat.address, cid2, info).decode().strip(),
           "reply": reply.decode("ascii", "replace").strip()}
    try:
        out["parsed"] = P.parse_frame(reply)
    except P.ProtocolError as e:
        out["error"] = str(e)
    _dump(out, args)


def cmd_probe(args):
    """Try baud rates x addresses with the protocol-version ping; report who answers."""
    bauds = [int(b) for b in args.bauds.split(",")]
    addresses = range(args.first_address, args.last_address + 1)
    found = []
    for baud in bauds:
        with SerialPort(args.device, baud) as port:
            for adr in addresses:
                reply = port.transact(P.build_frame(adr, P.CMD_PROTOCOL_VERSION, ""), 0.6)
                entry = {"baud": baud, "address": adr}
                if not reply:
                    continue
                try:
                    f = P.parse_frame(reply)
                    entry.update(valid=True, protocol_version="%d.%d" % (f["ver"] >> 4, f["ver"] & 0xF))
                except P.ProtocolError as e:
                    entry.update(valid=False, error=str(e), reply=reply.hex())
                found.append(entry)
                time.sleep(0.05)
    _dump({"responses": found, "hint": None if any(e.get("valid") for e in found) else
           "no valid reply: check wiring (A/B), that the adapter has an RS485 transceiver, "
           "the battery port (RS485, not CAN/console) and its DIP switches"}, args)


def build_parser():
    p = argparse.ArgumentParser(
        prog="pylontech-rs485",
        description="Read a Pylontech battery over RS485 (Pylontech ASCII protocol). Output is JSON.")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    p.add_argument("-d", "--device", default=os.environ.get("PYLONTECH_DEVICE"),
                   help="serial device, e.g. /dev/serial/by-id/usb-... (env PYLONTECH_DEVICE)")
    p.add_argument("-b", "--baud", type=int, default=int(os.environ.get("PYLONTECH_BAUD", DEFAULT_BAUD)),
                   choices=sorted(BAUD_RATES), help="baud rate (default %d)" % DEFAULT_BAUD)
    p.add_argument("-a", "--address", type=int,
                   default=int(os.environ.get("PYLONTECH_ADDRESS", DEFAULT_ADDRESS)),
                   help="battery address (default %d)" % DEFAULT_ADDRESS)
    p.add_argument("-t", "--timeout", type=float, default=2.0, help="reply timeout in seconds (default 2)")
    p.add_argument("--retries", type=int, default=3, help="attempts per command (default 3)")
    p.add_argument("-p", "--pretty", action="store_true", help="indented JSON")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    r = sub.add_parser("read", help="live values: cells, temperatures, current, voltage, alarms, limits")
    r.add_argument("--history", metavar="FILE", help="append cell voltages to FILE and add window statistics")
    r.add_argument("--window-days", type=float, default=7, help="history window in days (default 7)")

    sub.add_parser("info", help="model, software version, manufacturer, serial number, protocol version")

    s = sub.add_parser("stats", help="statistics from a history file only (no battery access)")
    s.add_argument("--history", metavar="FILE", required=True)

    x = sub.add_parser("raw", help="send one command (hex CID2) and show the raw reply")
    x.add_argument("cid2", help="command code in hex, e.g. 42")
    x.add_argument("info", nargs="?", help="INFO field in hex (default: the address byte)")

    pr = sub.add_parser("probe", help="scan baud rates and addresses for a battery")
    pr.add_argument("--bauds", default="115200,9600", help="comma-separated (default 115200,9600)")
    pr.add_argument("--first-address", type=int, default=0)
    pr.add_argument("--last-address", type=int, default=16)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "stats":
        return cmd_stats(args)
    if not args.device:
        sys.exit("no device given: use --device or set PYLONTECH_DEVICE")
    try:
        if args.command == "probe":
            return cmd_probe(args)
        with Battery(args.device, args.baud, args.address, args.timeout, args.retries) as bat:
            {"read": cmd_read, "info": cmd_info, "raw": cmd_raw}[args.command](bat, args)
    except NoResponse as e:
        print("error: %s" % e, file=sys.stderr)
        return EXIT_NO_RESPONSE
    except P.ProtocolError as e:
        print("error: %s" % e, file=sys.stderr)
        return EXIT_PROTOCOL
    except (PortBusy, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return EXIT_PORT
    return 0


if __name__ == "__main__":
    sys.exit(main())
