#!/usr/bin/env python3
"""Génère un gabarit de contraintes iCE40 (.pcf) à partir des ports d'un top
Verilog. Les numéros de broches restent à compléter lors du routage du
circuit imprimé (lignes commentées "set_io NOM ?")."""
import re
import sys

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
    f.write("# signaux utilisés comme horloges.\n")
    for d, p in ports:
        f.write(f"# set_io {p} ?    # {d}\n")
print(f"{out} : {len(ports)} broches")
