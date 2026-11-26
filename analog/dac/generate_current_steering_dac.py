#!/usr/bin/env python3
"""Generate the routed, binary-weighted GF180 variant-D current-steering DAC.

Run inside IIC-OSIC-TOOLS with KLayout's Python module available:
    python3 generate_current_steering_dac.py current_steering_dac.spice

Regenerate the SPICE netlist from xschem after modifying the schematic.
The SPICE input must contain the current_steering_dac cell and its 20 ports.
The GDS excludes the testbench bias source, output loads and digital stimulus.
The dedicated VSS return uses Metal5 and requires the five-metal stack.
"""

from argparse import ArgumentParser
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
import re

import klayout.db as db


TOP = "current_steering_dac"
# Minimum finger width supported by this layout's centered diffusion contacts.
MIN_FINGER_WIDTH = 0.40
LAYER = {
    "active": (22, 0), "poly": (30, 0), "pplus": (31, 0), "nplus": (32, 0),
    "contact": (33, 0), "m1": (34, 0), "v1": (35, 0), "m2": (36, 0),
    "v2": (38, 0), "v3": (40, 0), "v4": (41, 0),
    "m3": (42, 0), "m4": (46, 0), "m5": (81, 0),
    "m3_label": (42, 10), "m4_label": (46, 10), "m5_label": (81, 10),
}
COMMON = ("voutp", "voutn", "vb", "vss")
VSS_BUS_Y = -9


@dataclass(frozen=True)
class Mos:
    name: str
    drain: str
    gate: str
    source: str
    body: str
    length: float
    width: float
    multiplicity: int = 1


def grid_units(value):
    units = Decimal(str(value)) / Decimal("0.005")
    if not units.is_finite() or units <= 0 or units != units.to_integral_value():
        raise ValueError(f"{value} is not a positive multiple of 0.005 µm")
    return int(units)


def spice_um(token):
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)([un]?)", token)
    if not match:
        raise ValueError(f"Expected a numeric SPICE dimension, got {token!r}")
    number, suffix = match.groups()
    value = Decimal(number) * {"": 1000000, "u": 1, "n": Decimal("0.001")}[suffix]
    grid_units(value)
    return float(value)


def read_dac(path):
    # xschem comments out the subcircuit declaration for a standalone sheet.
    lines = re.sub(r"\n\s*\+", " ", path.read_text().lower()).splitlines()
    for start, line in enumerate(lines):
        header = re.match(r"^(?:\*\*)?\.subckt\s+current_steering_dac\s+(.+)$", line.strip())
        if header:
            break
    else:
        raise ValueError(f"Could not find a {TOP} subcircuit in {path}")
    ports = header[1].split()
    bit_ports = {f"d{i}{suffix}" for i in range(8) for suffix in ("", "b")}
    if len(ports) != 20 or set(ports) != bit_ports.union(COMMON):
        raise ValueError("Expected voutp/voutn, vb/vss and all 16 true/complement bit ports")

    devices = []
    for line in lines[start + 1:]:
        line = line.strip()
        if line.startswith((".ends", "**.ends", "**** begin user architecture code")):
            break
        if not line or line.startswith("*"):
            continue
        fields = line.split()
        if len(fields) < 6 or not fields[0].startswith("xm") or fields[5] != "nfet_03v3":
            raise ValueError(f"Unsupported core element: {line}")
        params = dict(re.findall(r"\b(l|w|nf|m)\s*=\s*(\S+)", " ".join(fields[6:])))
        if params.get("nf", "1") != "1":
            raise ValueError(f"{fields[0]}: expected nf=1 in the schematic")
        multiplicity = int(params.get("m", "1"))
        if multiplicity < 1:
            raise ValueError(f"{fields[0]}: m must be a positive integer")
        length, width = (spice_um(params[key]) for key in ("l", "w"))
        if length < 0.28 or width < MIN_FINGER_WIDTH:
            raise ValueError(f"{fields[0]}: generator requires L >= 0.28 and W >= 0.40 µm")
        devices.append(Mos(fields[0], *fields[1:5], length, width, multiplicity))

    groups = []
    consumed = set()
    for bit in range(8):
        gate = f"d{bit}"
        sides = [[dev for dev in devices if dev.gate == pin] for pin in (gate, gate + "b")]
        if any(not side for side in sides):
            raise ValueError(f"Expected both steering sides for bit {bit}")
        tail_net = sides[0][0].source
        tails = [dev for dev in devices if dev.drain == tail_net and dev.gate == "vb"]
        if (any(dev.drain != out or dev.source != tail_net
                for side, out in zip(sides, ("voutp", "voutn")) for dev in side)
                or tail_net in ports or not tails or any(dev.source != "vss" for dev in tails)):
            raise ValueError(f"Unexpected switch or tail connections for bit {bit}")
        group = [*sides[0], *sides[1], *tails]
        names = {dev.name for dev in group}
        if consumed & names or len(group) != len(names) or any(dev.body != "vss" for dev in group):
            raise ValueError(f"Duplicate instance or invalid body connection in bit {bit}")
        consumed.update(names)
        groups.append(group)
    if len(consumed) != len(devices):
        raise ValueError("Unexpected devices outside the eight supported branches")
    return ports, groups


def layout_rows(groups, pack_parallel):
    rows = []
    for group in groups:
        widths = {}
        for dev in group:
            key = ((dev.drain, dev.gate, dev.source, dev.body, dev.length)
                   if pack_parallel else dev.name)
            representative, width_units = widths.get(key, (dev, 0))
            widths[key] = (representative, width_units + dev.multiplicity * grid_units(dev.width))
        rows.append([replace(dev, width=width_units / 200, multiplicity=1)
                     for dev, width_units in widths.values()])
    return rows


def finger_widths(width, maximum):
    total, limit = grid_units(width), grid_units(maximum)
    count = (total + limit - 1) // limit
    base, remainder = divmod(total, count)
    if base < grid_units(MIN_FINGER_WIDTH):
        raise ValueError("Finger width would be below the supported minimum")
    return [(base + (i < remainder)) * 0.005 for i in range(count)]


class Layout:
    def __init__(self):
        self.layout = db.Layout()
        self.layout.dbu = 0.001
        self.layers = {name: self.layout.layer(*pair) for name, pair in LAYER.items()}
        self.top = self.layout.create_cell(TOP)

    @staticmethod
    def coord(value):
        return round(value / 0.005) * 5

    def box(self, layer, x1, y1, x2, y2):
        box = db.Box(*(self.coord(value) for value in (x1, y1, x2, y2)))
        self.top.shapes(self.layers[layer]).insert(box)

    def wire(self, layer, x1, y1, x2, y2, width):
        half = width / 2
        self.box(layer, min(x1, x2) - half, min(y1, y2) - half,
                 max(x1, x2) + half, max(y1, y2) + half)

    def cut(self, layer, x, y):
        size = 0.22 if layer == "contact" else 0.26
        # Snap the center first so a half-grid input cannot change cut size.
        x, y = self.coord(x) / 1000, self.coord(y) / 1000
        self.wire(layer, x, y, x, y, size)

    def label(self, metal, name, x, y):
        text = db.Text(name, db.Trans(self.coord(x), self.coord(y)))
        self.top.shapes(self.layers[metal + "_label"]).insert(text)

    def transistor(self, x, y, length, width, rails, grounded_source):
        drain_y, gate_y, source_y = rails
        right = x + length + 3
        gate_x = x + 1.5 + length / 2
        self.box("active", x, y, right, y + width)
        self.box("nplus", x - 0.35, y - 0.35, right + 0.35, y + width + 0.35)
        self.box("poly", x + 1.5, gate_y, x + 1.5 + length, y + width + 0.65)
        self.wire("poly", gate_x, gate_y, gate_x, gate_y, 0.66)
        self.cut("contact", gate_x, gate_y)
        self.wire("m1", gate_x, gate_y, gate_x, gate_y, 0.70)
        self.cut("v1", gate_x, gate_y)
        for contact_x, bus_y in ((x + 0.65, drain_y), (right - 0.65, source_y)):
            count = int((width - 0.45 + 1e-8) / 0.48) + 1
            count = max(1, count)
            first = y + (width - (count - 1) * 0.48) / 2
            last = first + (count - 1) * 0.48
            for i in range(count):
                self.cut("contact", contact_x, first + i * 0.48)
            if grounded_source and bus_y == source_y:
                # Lift each tail-source contact stripe directly into the ground plate.
                for metal in ("m1", "m2", "m3"):
                    self.wire(metal, contact_x, first, contact_x, last, 0.90)
                via_count = 1 + int((last - first) / 0.60)
                via_start = (first + last - (via_count - 1) * 0.60) / 2
                for i in range(via_count):
                    for via in ("v1", "v2", "v3"):
                        self.cut(via, contact_x, via_start + i * 0.60)
                continue
            self.wire("m1", contact_x, min(first, bus_y), contact_x,
                      max(last, bus_y), 0.70)
            self.cut("v1", contact_x, bus_y)

    def branch(self, x, bit, devices, maximum, bus_y):
        tail_net = devices[0].source
        pins = (f"d{bit}", f"d{bit}b")
        lanes = {net: x + 2 + 2 * i for i, net in enumerate((*COMMON, *pins, tail_net))}
        stops = {net: [] for net in lanes}
        for net in bus_y:
            self.cut("v3", lanes[net], bus_y[net])
            stops[net].append(bus_y[net])
        for net in pins:
            self.label("m3", net, lanes[net], 1)
            stops[net].append(1)

        y = 8
        right = x + 18
        for dev in devices:
            widths = finger_widths(dev.width, maximum)
            active_x = x + 18
            active_top = y + max(widths)
            rails = (y - 1.5, y - 3.5, active_top + 1.5)
            for width in widths:
                self.transistor(active_x, y, dev.length, width, rails, dev.source == "vss")
                last_x = active_x + dev.length + 3
                active_x = last_x + 1.5
            right = max(right, last_x)
            for node, rail_y in zip((dev.drain, dev.gate, dev.source), rails):
                if node == "vss":
                    continue
                self.wire("m2", lanes[node], rail_y, last_x, rail_y, 0.85)
                self.cut("v2", lanes[node], rail_y)
                stops[node].append(rail_y)

            tap_y = active_top + 4.0
            tap_start = x + 18
            self.box("active", tap_start, tap_y - 0.5, last_x, tap_y + 0.5)
            self.box("pplus", tap_start - 0.35, tap_y - 0.85, last_x + 0.35, tap_y + 0.85)
            for index in range(int((last_x - tap_start - 1.0) / 0.48) + 1):
                self.cut("contact", tap_start + 0.5 + index * 0.48, tap_y)
            self.wire("m1", tap_start + 0.35, tap_y, last_x - 0.35, tap_y, 0.70)
            self.cut("v1", tap_start + 0.55, tap_y)
            self.wire("m2", lanes["vss"], tap_y, tap_start + 0.55, tap_y, 0.85)
            self.cut("v2", lanes["vss"], tap_y)
            self.cut("v3", lanes["vss"], tap_y)
            stops["vss"].append(tap_y)
            if dev.source == "vss":
                self.box("m4", lanes["vss"], y - 0.75, last_x, active_top + 0.75)
            y = tap_y + 7.0

        for net, positions in stops.items():
            self.wire("m3", lanes[net], min(positions), lanes[net], max(positions), 1.0)
        ground_x = lanes["vss"]
        self.wire("m4", ground_x, VSS_BUS_Y, ground_x, max(stops["vss"]), 10.0)
        for i in range(-3, 4):
            for j in range(-3, 4):
                self.cut("v4", ground_x + i * 0.65, VSS_BUS_Y + j * 0.65)
        return right + 4

    def generate(self, groups, maximum):
        tallest = max(sum(11 + max(finger_widths(dev.width, maximum)) for dev in group)
                      for group in groups)
        bus_y = {net: 12 + tallest + 5 * index for index, net in enumerate(COMMON[:-1])}
        x = 0
        for bit, group in enumerate(groups):
            x = self.branch(x, bit, group, maximum, bus_y)
        for net, y in bus_y.items():
            self.wire("m4", 1, y, x - 3, y, 2.4)
            self.label("m4", net, 1, y)
        self.wire("m5", 1, VSS_BUS_Y, x - 3, VSS_BUS_Y, 16.0)
        self.label("m5", "vss", x / 2, VSS_BUS_Y)


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("netlist", type=Path)
    cli.add_argument("--output-dir", type=Path)
    cli.add_argument("--max-finger-width", type=float, default=8.0, metavar="UM")
    cli.add_argument("--pack-parallel", action="store_true",
                     help="place identical-length devices on the same four nets in one row")
    args = cli.parse_args()
    output = args.output_dir or args.netlist.parent
    try:
        ports, groups = read_dac(args.netlist)
        devices = [dev for group in groups for dev in group]
        layout = Layout()
        rows = layout_rows(groups, args.pack_parallel)
        layout.generate(rows, args.max_finger_width)
        output.mkdir(parents=True, exist_ok=True)
        gds = output / f"{TOP}.gds"
        layout.layout.write(str(gds))
        reference = output / f"{TOP}_lvs.spice"
        lines = ["** GF180 KLayout LVS reference generated from the xschem netlist",
                 f".subckt {TOP} {' '.join(ports)}"]
        for dev in devices:
            # Expose the schematic multiplier as explicit parallel devices for LVS.
            for index in range(dev.multiplicity):
                suffix = f"_p{index + 1}" if dev.multiplicity > 1 else ""
                lines.append(f"{dev.name[1:]}{suffix} {dev.drain} {dev.gate} {dev.source} {dev.body} "
                             f"nfet_03v3 L={dev.length:g}u W={dev.width:g}u")
        reference.write_text("\n".join([*lines, f".ends {TOP}", ""]))
    except (OSError, ValueError, KeyError) as exc:
        cli.error(str(exc))
    size = layout.top.bbox()
    fingers = sum(len(finger_widths(row.width, args.max_finger_width))
                  for group in rows for row in group)
    print(f"{len(devices)} schematic NMOS instances ({sum(d.multiplicity for d in devices)} "
          f"including multiplicity), {fingers} drawn fingers, {len(ports)} ports")
    print(f"Bounding box: {size.width()/1000:g} × {size.height()/1000:g} µm")
    print(gds)
    print(reference)


if __name__ == "__main__":
    main()
