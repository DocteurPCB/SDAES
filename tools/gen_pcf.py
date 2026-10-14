#!/usr/bin/env python3
"""Ports des tops Verilog et contacts AES correspondants (utilisé par
hardware/gen/fpga_pins.py) ; en ligne de commande, produit un gabarit .pcf
sans numéros de broches."""
import csv
import os
import re
import sys

# Contact du connecteur AES correspondant à un port FPGA (via les tampons de niveaux)
CONN = {}
with open(os.path.join(os.path.dirname(__file__), "..", "hardware", "aes_connector.csv")) as f:
    for r in csv.reader(l for l in f if not l.startswith("#")):
        if r[0] != "carte":
            CONN[r[3]] = f"{r[0]} {r[1]} {r[2]}"


def contact(port):
    n = re.sub(r"_N$", "", port.split("[")[0])
    n = {"S2H1": "2H1", "CLK_12M": "12M", "SDRA_L": "SDRA", "SDRA_U": "SDRA"}.get(n, n)
    if "[" in port:
        n += port.split("[")[1].rstrip("]")
    return CONN.get(n)


def ports(src, top):
    """Ports du top Verilog `top` du fichier `src`, bus éclatés : [(sens, nom)]."""
    with open(src) as f:
        text = f.read()
    start = text.index(f"module {top}")
    body = text[start:text.index(");", start)]
    out = []
    for m in re.finditer(r"\b(input|output|inout)\s+wire\s*(\[(\d+):(\d+)\])?\s*([^;\n]+)", body):
        names = [n.strip() for n in m.group(5).split("//")[0].split(",") if n.strip()]
        for n in names:
            if m.group(2):
                hi, lo = int(m.group(3)), int(m.group(4))
                out += [(m.group(1), f"{n}[{i}]") for i in range(lo, hi + 1)]
            else:
                out.append((m.group(1), n))
    return out


if __name__ == "__main__":
    src, top, out = sys.argv[1], sys.argv[2], sys.argv[3]
    plist = ports(src, top)
    with open(out, "w") as f:
        f.write(f"# Contraintes {top} - iCE40HX4K-TQ144 : gabarit sans numéros de broches\n")
        f.write("# (les .pcf du dépôt sont produits par hardware/gen/fpga_pins.py).\n")
        for d, p in plist:
            c = contact(p)
            f.write(f"# set_io {p} ?    # {d}" + (f", AES {c}" if c else "") + "\n")
    print(f"{out} : {len(plist)} broches")
