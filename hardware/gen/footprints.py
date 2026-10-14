"""Empreintes et symboles propres à SDAES -> hardware/kicad/sdaes.pretty,
hardware/kicad/sdaes.kicad_sym, tables de bibliothèques des projets."""
import os

from kicad import dump, q

FONT = ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]


def _text(kind, txt, x, y, layer):
    return ["fp_text", kind, q(txt), ["at", f"{x:g}", f"{y:g}"], ["layer", q(layer)], FONT]


def _line(x1, y1, x2, y2, layer, w=0.12):
    return ["fp_line", ["start", f"{x1:g}", f"{y1:g}"], ["end", f"{x2:g}", f"{y2:g}"],
            ["stroke", ["width", f"{w:g}"], ["type", "solid"]], ["layer", q(layer)]]


def _rect(x1, y1, x2, y2, layer, w=0.05):
    return [_line(x1, y1, x2, y1, layer, w), _line(x2, y1, x2, y2, layer, w),
            _line(x2, y2, x1, y2, layer, w), _line(x1, y2, x1, y1, layer, w)]


def _pad(num, x, y, w, h, side="F"):
    return ["pad", q(num), "smd", "rect", ["at", f"{x:g}", f"{y:g}"], ["size", f"{w:g}", f"{h:g}"],
            ["layers", q(f"{side}.Cu"), q(f"{side}.Mask")]]


def aes_edge():
    """Contacts de bord de la cartouche AES : 2 x 50 au pas de 2,54 mm,
    contacts de 1,5 x 10 mm dont le centre est à 7,1 mm du bord de la
    languette (cotes des cartes AES de jwestfall69, neogeo-diag-aes-prog et
    neogeo-diag-aes-cha, fabriquées et testées). T1..T50 = contacts A1..A50
    sur la face composants (« dessus »), B1..B50 sur l'autre face ; vu côté
    composants, languette vers le bas, T1 et B1 sont à droite, l'un derrière
    l'autre (sérigraphie « A1 » des cartes SNK NEO-AEG). Origine : centre de
    la rangée, bord de la languette à y = +7,1 mm."""
    pitch, w, h, edge = 2.54, 1.5, 10.0, 7.1
    fp = ["footprint", q("AES_Edge_2x50_P2.54mm"), ["version", "20221018"], ["generator", "pcbnew"],
          ["layer", q("F.Cu")],
          ["descr", q("Connecteur de bord cartouche Neo Geo AES, 2 x 50 contacts, pas 2,54 mm, "
                      "contacts 1,5 x 10 mm (cotes jwestfall69 neogeo-diag-aes-prog/cha)")],
          ["attr", "smd"],
          _text("reference", "REF**", 0, -7, "F.SilkS"),
          _text("value", "AES_Edge_2x50", 0, -8.5, "F.Fab")]
    for i in range(50):
        x = (24.5 - i) * pitch
        fp.append(_pad(f"T{i + 1}", x, 0, w, h, "F"))
        fp.append(_pad(f"B{i + 1}", x, 0, w, h, "B"))
    fp += _rect(-24.5 * pitch - 1.5, -h / 2 - 0.5, 24.5 * pitch + 1.5, edge, "F.CrtYd")
    fp += [_text("user", "A1", 24.5 * pitch, -h / 2 - 1.5, "F.SilkS"),
           _text("user", "A50", -24.5 * pitch, -h / 2 - 1.5, "F.SilkS")]
    return fp


def pico2():
    """Raspberry Pi Pico 2 soudé en surface par ses demi-trous (fiche Pico 2,
    figure « paste stencil » : pastilles de 3,8 mm, 15,58 mm entre les
    rangées, pas de 2,54 mm). Broche 1 en haut à gauche, port USB en haut."""
    pitch, pw, ph, inner = 2.54, 3.8, 1.6, 15.58
    xc = inner / 2 + pw / 2
    y0 = -9.5 * pitch
    fp = ["footprint", q("RaspberryPi_Pico2_SMD"), ["version", "20221018"], ["generator", "pcbnew"],
          ["layer", q("F.Cu")],
          ["descr", q("Raspberry Pi Pico 2, module 21 x 51 mm soudé par ses demi-trous")],
          ["attr", "smd"],
          _text("reference", "REF**", 0, -27.5, "F.SilkS"),
          _text("value", "RaspberryPi_Pico2", 0, 27.5, "F.Fab")]
    for i in range(20):
        fp.append(_pad(str(i + 1), -xc, y0 + i * pitch, pw, ph))
        fp.append(_pad(str(40 - i), xc, y0 + i * pitch, pw, ph))
    fp += _rect(-10.5, -25.5, 10.5, 25.5, "F.Fab", 0.1)
    fp += _rect(-11.6, -26.5, 11.6, 26.5, "F.CrtYd")
    fp += [_line(-10.5, -25.5, 10.5, -25.5, "F.SilkS"), _text("user", "USB", 0, -24, "F.SilkS"),
           _text("user", "1", -xc - 2.6, y0, "F.SilkS")]
    return fp


def write(outdir, symbols):
    pretty = os.path.join(outdir, "sdaes.pretty")
    os.makedirs(pretty, exist_ok=True)
    for fp in (aes_edge(), pico2()):
        name = fp[1].strip('"')
        with open(os.path.join(pretty, name + ".kicad_mod"), "w") as f:
            f.write(dump(fp) + "\n")
    lib = ["kicad_symbol_lib", ["version", "20220914"], ["generator", "kicad_symbol_editor"]]
    for s in symbols:
        x = list(s.sexpr)
        x[1] = q(s.lib_id.split(":")[1])
        lib.append(x)
    with open(os.path.join(outdir, "sdaes.kicad_sym"), "w") as f:
        f.write(dump(lib) + "\n")
    for proj in ("prog", "cha"):
        d = os.path.join(outdir, proj)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sym-lib-table"), "w") as f:
            f.write('(sym_lib_table\n  (lib (name "SDAES")(type "KiCad")(uri "${KIPRJMOD}/../sdaes.kicad_sym")'
                    '(options "")(descr "Symboles SDAES"))\n)\n')
        with open(os.path.join(d, "fp-lib-table"), "w") as f:
            f.write('(fp_lib_table\n  (lib (name "SDAES")(type "KiCad")(uri "${KIPRJMOD}/../sdaes.pretty")'
                    '(options "")(descr "Empreintes SDAES"))\n)\n')
