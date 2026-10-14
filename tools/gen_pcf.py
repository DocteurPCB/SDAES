#!/usr/bin/env python3
"""Génère un gabarit de contraintes iCE40 (.pcf) à partir des ports d'un top
Verilog. Les numéros de broches restent à compléter lors du routage du
circuit imprimé (lignes commentées "set_io NOM ?")."""
import csv
import os
import re
import sys

# Contact du connecteur AES correspondant à un port FPGA (via les translateurs)
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

src, top, out = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src) as f:
    text = f.read()
start = text.index(f"module {top}")
body = text[start:text.index(");", start)]
ports = []
for m in re.finditer(r"\b(input|output|inout)\s+wire\s*(\[(\d+):(\d+)\])?\s*([^;\n]+)", body):
    names = [n.strip() for n in m.group(5).split("//")[0].split(",") if n.strip()]
    for n in names:
        if m.group(2):
            hi, lo = int(m.group(3)), int(m.group(4))
            ports += [(m.group(1), f"{n}[{i}]") for i in range(lo, hi + 1)]
        else:
            ports.append((m.group(1), n))
with open(out, "w") as f:
    f.write(f"# Contraintes {top} - iCE40HX4K-TQ144 (puce HX8K, outils libres)\n")
    f.write("# Gabarit généré par tools/gen_pcf.py : compléter les numéros de broches.\n")
    f.write("# CLK25 sur une entrée globale (GBIN) ; voir hardware/README.md pour les\n")
    f.write("# signaux utilisés comme horloges. « AES ... » = contact du connecteur de\n")
    f.write("# cartouche relié à ce port à travers un translateur (hardware/aes_connector.csv).\n")
    for d, p in ports:
        c = contact(p)
        f.write(f"# set_io {p} ?    # {d}" + (f", AES {c}" if c else "") + "\n")
print(f"{out} : {len(ports)} broches")
