#!/usr/bin/env python3
"""Génère un gabarit de contraintes ECP5 (.lpf) à partir des ports d'un top Verilog.
Les sites (LOCATE) restent à compléter lors du routage du circuit imprimé."""
import re
import sys

src, top, out = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(src).read()
body = text[text.index(f"module {top}"):text.index(");", text.index(f"module {top}"))]
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
    f.write(f"# Contraintes {top} - LFE5U-25F-6BG256C - gabarit généré par tools/gen_lpf.py\n")
    f.write("# Compléter les sites (billes) lors du routage. 25 MHz sur une entrée d'horloge.\n")
    f.write('FREQUENCY PORT "CLK25" 25 MHZ;\n')
    if top == "cha_top":
        f.write('FREQUENCY PORT "CLK_12M" 12 MHZ;\n')
    for d, p in ports:
        f.write(f'# LOCATE COMP "{p}" SITE "?";\n')
        extra = " SLEWRATE=FAST" if d != "input" else ""
        f.write(f'IOBUF PORT "{p}" IO_TYPE=LVCMOS33{extra};\n')
print(f"{out} : {len(ports)} broches")
