#!/usr/bin/env python3
"""Description des cartes PROG et CHA de SDAES -> schémas KiCad.

    python3 hardware/gen/boards.py          # écrit hardware/kicad/{prog,cha}/
    python3 hardware/gen/boards.py --check  # + vérifie la netlist exportée par kicad-cli
    python3 hardware/gen/boards.py --pdf    # + PDF des schémas (hardware/kicad/sdaes_*.pdf)

Conventions de noms de réseaux :
  * AES_xxx  : côté console (5 V), nom du contact (hardware/aes_connector.csv)
  * xxx      : même signal côté FPGA (3,3 V), après le tampon de niveaux
  * P_, V_, C_, SM_ : signaux locaux d'un FPGA (mémoire, horloge, flash...)
Les broches des FPGA viennent de hardware/*.pcf (hardware/gen/fpga_pins.py).
Sources des brochages hors bibliothèque KiCad : fiches TI (SN74LVC16244A,
SN74AHCT16244), ISSI (IS61WV10248EDBLL), Raspberry Pi (Pico 2).
"""
import csv
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
import kicad as k  # noqa: E402

# ---------------------------------------------------------------------------
# empreintes

FP = {
    "fpga": "Package_QFP:TQFP-144_20x20mm_P0.5mm",
    "tssop48": "Package_SO:TSSOP-48_6.1x12.5mm_P0.5mm",
    "tssop20": "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
    "tssop14": "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    "sot23-5": "Package_TO_SOT_SMD:SOT-23-5",
    "sot223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    "sdram": "Package_SO:TSOP-II-54_22.2x10.16mm_P0.8mm",
    "sram": "Package_SO:TSOP-II-44_10.16x18.41mm_P0.8mm",
    "flash": "Package_SO:SOIC-8_5.23x5.23mm_P1.27mm",
    "osc": "Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm_HandSoldering",
    "r": "Resistor_SMD:R_0603_1608Metric",
    "c": "Capacitor_SMD:C_0603_1608Metric",
    "c10u": "Capacitor_SMD:C_0805_2012Metric",
    "c22u": "Capacitor_SMD:C_1206_3216Metric",
    "led": "LED_SMD:LED_0603_1608Metric",
    "hdr2x3": "Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical",
    "hdr2x6": "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical",
    "sd": "Connector_Card:microSD_HC_Wuerth_693072010801",
    "sw": "Button_Switch_SMD:SW_SPST_TL3342",
    "schottky": "Diode_SMD:D_SOD-123",
    "edge": "SDAES:AES_Edge_2x50_P2.54mm",
    "pico": "SDAES:RaspberryPi_Pico2_SMD",
}

# ---------------------------------------------------------------------------
# symboles

R = k.kicad_symbol("Device", "R")
C = k.kicad_symbol("Device", "C")
LED = k.kicad_symbol("Device", "LED")
DSCH = k.kicad_symbol("Device", "D_Schottky")
SW = k.kicad_symbol("Switch", "SW_Push")
ICE40 = k.kicad_symbol("FPGA_Lattice", "ICE40HX4K-TQ144")
SDRAM = k.kicad_symbol("Memory_RAM", "MT48LC16M16A2TG")
FLASH = k.kicad_symbol("Memory_Flash", "W25Q32JVSS")
OSC = k.kicad_symbol("Oscillator", "ASE-xxxMHz")
LDO33 = k.kicad_symbol("Regulator_Linear", "AMS1117-3.3")
LDO12 = k.kicad_symbol("Regulator_Linear", "AP2112K-1.2")
MSD = k.kicad_symbol("Connector", "Micro_SD_Card")
X245 = k.kicad_symbol("74xx", "MC74LCX16245DT")        # brochage 16245 standard (= SN74LVC16245A)
X244_8 = k.kicad_symbol("74xx", "74AHCT244")
X125 = k.kicad_symbol("74xx", "74LS125")               # brochage 125 standard (74AHCT125)
G07 = k.kicad_symbol("74xGxx", "74LVC1G07")
G32 = k.kicad_symbol("74xGxx", "74AHCT1G32")
HDR6 = k.kicad_symbol("Connector_Generic", "Conn_02x03_Odd_Even")
HDR12 = k.kicad_symbol("Connector_Generic", "Conn_02x06_Odd_Even")

# 16244 (SN74LVC16244A / SN74AHCT16244, TSSOP-48) : brochage de la fiche TI
_244 = {1: "1OE", 2: "1Y1", 3: "1Y2", 5: "1Y3", 6: "1Y4", 8: "2Y1", 9: "2Y2", 11: "2Y3", 12: "2Y4",
        13: "3Y1", 14: "3Y2", 16: "3Y3", 17: "3Y4", 19: "4Y1", 20: "4Y2", 22: "4Y3", 23: "4Y4",
        24: "4OE", 25: "3OE", 26: "4A4", 27: "4A3", 29: "4A2", 30: "4A1", 32: "3A4", 33: "3A3",
        35: "3A2", 36: "3A1", 37: "2A4", 38: "2A3", 40: "2A2", 41: "2A1", 43: "1A4", 44: "1A3",
        46: "1A2", 47: "1A1", 48: "2OE"}
_244_GND = [4, 10, 15, 21, 28, 34, 39, 45]
_244_VCC = [7, 18, 31, 42]


def _x16244():
    left = [(n, _244[n], "input") for g in (1, 2, 3, 4) for n in sorted(_244) if _244[n].startswith(f"{g}A")]
    left = sorted(left, key=lambda e: e[1])
    right = sorted([(n, _244[n], "tri_state") for n in _244 if "Y" in _244[n]], key=lambda e: e[1])
    left += [None] + [(n, _244[n], "input") for n in (1, 48, 25, 24)]
    right += [None] + [(n, "VCC", "power_in") for n in _244_VCC]
    bottom = [(n, "GND", "power_in") for n in _244_GND]
    return k.box_symbol("SDAES:x16244", left, right, width=20.32, bottom=bottom)


X16244 = _x16244()

# SRAM IS61WV10248EDBLL, TSOP-II 44 (fiche ISSI Rev. B, « PIN CONFIGURATION »)
_SRAM = {1: "NC", 2: "NC", 3: "A0", 4: "A1", 5: "A2", 6: "A3", 7: "A4", 8: "~{CE}", 9: "IO0", 10: "IO1",
         11: "VDD", 12: "GND", 13: "IO2", 14: "IO3", 15: "~{WE}", 16: "A5", 17: "A6", 18: "A7", 19: "A8",
         20: "A9", 21: "NC", 22: "NC", 23: "NC", 24: "NC", 25: "A19", 26: "A10", 27: "A11", 28: "A12",
         29: "A13", 30: "A14", 31: "IO4", 32: "IO5", 33: "VDD", 34: "GND", 35: "IO6", 36: "IO7",
         37: "~{OE}", 38: "A15", 39: "A16", 40: "A17", 41: "A18", 42: "NC", 43: "NC", 44: "NC"}


def _sram():
    a = sorted([(n, v) for n, v in _SRAM.items() if re.fullmatch(r"A\d+", v)], key=lambda e: int(e[1][1:]))
    io = sorted([(n, v) for n, v in _SRAM.items() if v.startswith("IO")], key=lambda e: e[1])
    left = [(n, v, "input") for n, v in a] + [None] + [(8, "~{CE}", "input"), (37, "~{OE}", "input"),
                                                      (15, "~{WE}", "input")]
    right = [(n, v, "bidirectional") for n, v in io] + [None, (11, "VDD", "power_in"), (33, "VDD", "power_in"),
                                                        (12, "GND", "power_in"), (34, "GND", "power_in")]
    right += [None] + [(n, "NC", "no_connect") for n, v in sorted(_SRAM.items()) if v == "NC"]
    return k.box_symbol("SDAES:IS61WV10248", left, right, width=22.86)


SRAM = _sram()


def _pico():
    """Raspberry Pi Pico 2 (40 broches, fiche Raspberry Pi « Pico 2 pinout »)."""
    left_names = ["GP0", "GP1", "GND", "GP2", "GP3", "GP4", "GP5", "GND", "GP6", "GP7", "GP8", "GP9",
                  "GND", "GP10", "GP11", "GP12", "GP13", "GND", "GP14", "GP15"]
    right_names = ["VBUS", "VSYS", "GND", "3V3_EN", "3V3_OUT", "ADC_VREF", "GP28", "AGND", "GP27", "GP26",
                   "RUN", "GP22", "GND", "GP21", "GP20", "GP19", "GP18", "GND", "GP17", "GP16"]
    left = [(i + 1, n, "power_in" if "GND" in n else "bidirectional") for i, n in enumerate(left_names)]
    right = [(40 - i, n, "power_in" if n in ("GND", "AGND", "VSYS") else
              "power_out" if n == "3V3_OUT" else "bidirectional") for i, n in enumerate(right_names)]
    return k.box_symbol("SDAES:RaspberryPi_Pico2", left, right, ref="A", width=25.4)


PICO = _pico()

# connecteur de bord AES (hardware/aes_connector.csv) ; broches T1..T50 (dessus),
# B1..B50 (dessous)
EDGE = {}
with open(os.path.join(ROOT, "hardware", "aes_connector.csv")) as f:
    for r in csv.reader(l for l in f if not l.startswith("#")):
        if r[0] != "carte":
            EDGE.setdefault(r[0], {})[("T" if r[1] == "dessus" else "B") + r[2]] = r[3]


def _edge(board):
    def etype(n):
        return "power_in" if n in ("VCC", "GND") else "passive"
    left = [(f"T{i}", EDGE[board][f"T{i}"], etype(EDGE[board][f"T{i}"])) for i in range(1, 51)]
    right = [(f"B{i}", EDGE[board][f"B{i}"], etype(EDGE[board][f"B{i}"])) for i in range(1, 51)]
    return k.box_symbol(f"SDAES:AES_{board}", left, right, ref="J", width=30.48)


def edge_x(board, net):
    """Abscisse (mm, axe de la languette = 0, A1 à droite vu côté composants)
    du contact AES d'un réseau AES_xxx : sert à ordonner les canaux des
    tampons comme les contacts, pour un routage sans croisement."""
    sig = net[4:] if net.startswith("AES_") else net
    pins = [p for p, s in EDGE[board].items() if s == sig]
    if not pins:
        raise KeyError(f"{board} : contact {sig} inconnu")
    return (25.5 - int(pins[0][1:])) * 2.54


def by_edge(board, pairs, i):
    """Trie des couples (réseau console, réseau FPGA) selon le contact AES de
    l'élément i."""
    return sorted(pairs, key=lambda c: edge_x(board, c[i]))


def pin_of(sym, name):
    r = [p.number for p in sym.pins if p.name == name]
    if len(r) != 1:
        raise KeyError(f"{sym.lib_id} : broche {name} ({len(r)})")
    return r[0]


def read_pcf(name):
    pins = {}
    for line in open(os.path.join(ROOT, "hardware", f"{name}.pcf")):
        m = re.match(r"set_io\s+(\S+)\s+(\d+)", line)
        if m:
            pins[m.group(1)] = int(m.group(2))
    return pins


# ---------------------------------------------------------------------------
# blocs réutilisables

class Refs:
    def __init__(self):
        self.n = {}

    def __call__(self, prefix):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return f"{prefix}{self.n[prefix]}"


def res(sh, ref, value, a, b):
    sh.add(k.Part(ref("R"), R, value, FP["r"], {1: a, 2: b}))


def cap(sh, ref, value, a, b="GND"):
    fp = FP["c"] if value in ("100n", "1u") else FP["c10u"] if value == "10u" else FP["c22u"]
    sh.add(k.Part(ref("C"), C, value, fp, {1: a, 2: b}))


def decouple(sh, ref, net, n100, bulk=None):
    for _ in range(n100):
        cap(sh, ref, "100n", net)
    if bulk:
        cap(sh, ref, bulk, net)


def power(sh, ref, edge_ref):
    """5 V du connecteur -> 3,3 V (AMS1117) et 1,2 V (AP2112K)."""
    cap(sh, ref, "22u", "+5V")
    cap(sh, ref, "100n", "+5V")
    sh.add(k.Part(ref("U"), LDO33, "AMS1117-3.3", FP["sot223"], {1: "GND", 2: "+3V3", 3: "+5V"}))
    cap(sh, ref, "22u", "+3V3")
    cap(sh, ref, "100n", "+3V3")
    sh.add(k.Part(ref("U"), LDO12, "AP2112K-1.2", FP["sot23-5"], {1: "+3V3", 2: "GND", 3: "+3V3", 5: "+1V2"}))
    cap(sh, ref, "10u", "+1V2")
    cap(sh, ref, "1u", "+3V3")


def fpga(sh, ref, tag, pcf_name, portmap):
    """FPGA iCE40 + flash SPI + oscillateur 25 MHz + filtres PLL + connecteur de
    programmation + tirages CDONE/CRESET. portmap : port du top -> réseau."""
    pins = read_pcf(pcf_name)
    nets = {}
    for port, p in pins.items():
        net = portmap(port)
        if net:
            nets[p] = net
    nets.update({27: "+1V2", 123: "+3V3", 89: "+3V3", 46: "+3V3", 6: "+3V3", 72: "+3V3", 108: "+3V3",
                 5: "GND", 53: "GND", 127: "GND",
                 54: f"{tag}_VCCPLL0", 126: f"{tag}_VCCPLL1",
                 65: "CDONE", 66: f"{tag}_CRESET_N", 67: f"{tag}_FL_DI", 68: f"{tag}_FL_DO",
                 70: f"{tag}_FL_SCK", 71: f"{tag}_FL_CS_N"})
    u = sh.add(k.Part(ref("U"), ICE40, "iCE40HX4K-TQ144", FP["fpga"], nets))
    # alimentations : 100 nF par broche, vrac
    decouple(sh, ref, "+1V2", 4, "10u")
    decouple(sh, ref, "+3V3", 9, "10u")
    for pll in ("VCCPLL0", "VCCPLL1"):          # filtre RC de la PLL (Lattice)
        res(sh, ref, "100", "+1V2", f"{tag}_{pll}")
        cap(sh, ref, "10u", f"{tag}_{pll}")
        cap(sh, ref, "100n", f"{tag}_{pll}")
    res(sh, ref, "10k", "+3V3", f"{tag}_CRESET_N")
    sh.add(k.Part(ref("U"), FLASH, "W25Q32JVSS", FP["flash"],
                  {1: f"{tag}_FL_CS_N", 2: f"{tag}_FL_DO", 3: f"{tag}_FL_WP_N", 4: "GND",
                   5: f"{tag}_FL_DI", 6: f"{tag}_FL_SCK", 7: f"{tag}_FL_HOLD_N", 8: "+3V3"}))
    cap(sh, ref, "100n", "+3V3")
    res(sh, ref, "10k", "+3V3", f"{tag}_FL_CS_N")
    res(sh, ref, "10k", "+3V3", f"{tag}_FL_WP_N")
    res(sh, ref, "10k", "+3V3", f"{tag}_FL_HOLD_N")
    # programmation de la flash (iceprog) : FPGA tenu en reset par CRESET
    sh.add(k.Part(ref("J"), HDR6, f"PROG {tag}", FP["hdr2x3"],
                  {1: f"{tag}_FL_SCK", 2: f"{tag}_FL_CS_N", 3: f"{tag}_FL_DI", 4: f"{tag}_FL_DO",
                   5: f"{tag}_CRESET_N", 6: "GND"}))
    sh.add(k.Part(ref("X"), OSC, "25 MHz 3,3 V", FP["osc"],
                  {1: "+3V3", 2: "GND", 3: f"{tag}_CLK25", 4: "+3V3"}))
    cap(sh, ref, "100n", "+3V3")
    if "LED" in pins:
        res(sh, ref, "470", f"{tag}_LED", f"{tag}_LED_K")
        sh.add(k.Part(ref("D"), LED, "LED", FP["led"], {2: f"{tag}_LED_K", 1: "GND"}))
    return u


def sdram(sh, ref, tag, value):
    nets = {}
    for p in SDRAM.pins:
        n = p.name
        if re.fullmatch(r"A\d+", n):
            nets[p.number] = f"{tag}_SD_A{n[1:]}"
        elif re.fullmatch(r"DQ\d+", n):
            nets[p.number] = f"{tag}_SD_DQ{n[2:]}"
        elif re.fullmatch(r"BA\d", n):
            nets[p.number] = f"{tag}_SD_BA{n[2]}"
    nets.update({pin_of(SDRAM, "DQML"): f"{tag}_SD_DQM0", pin_of(SDRAM, "DQMH"): f"{tag}_SD_DQM1",
                 pin_of(SDRAM, "~{WE}"): f"{tag}_SD_WE_N", pin_of(SDRAM, "~{CAS}"): f"{tag}_SD_CAS_N",
                 pin_of(SDRAM, "~{RAS}"): f"{tag}_SD_RAS_N", pin_of(SDRAM, "~{CS}"): f"{tag}_SD_CS_N",
                 pin_of(SDRAM, "CKE"): f"{tag}_SD_CKE", pin_of(SDRAM, "CLK"): f"{tag}_SD_CLK_R"})
    for p in SDRAM.pins:
        if p.name in ("VDD", "VDDQ"):
            nets[p.number] = "+3V3"
        elif p.name in ("VSS", "VSSQ"):
            nets[p.number] = "GND"
    sh.add(k.Part(ref("U"), SDRAM, value, FP["sdram"], nets))
    res(sh, ref, "33", f"{tag}_SD_CLK", f"{tag}_SD_CLK_R")      # résistance série d'horloge
    decouple(sh, ref, "+3V3", 7, "10u")


def sdram_port(tag):
    def f(port):
        m = re.fullmatch(r"SD_(A|DQ|BA|DQM)\[(\d+)\]", port)
        if m:
            return f"{tag}_SD_{m.group(1)}{m.group(2)}"
        if port.startswith("SD_"):
            return f"{tag}_{port}"
        return None
    return f


def x16244(sh, ref, chans, oe, vcc, value):
    """chans : jusqu'à 16 (entrée A, sortie Y) ; canaux libres : entrée à la masse."""
    nets = {}
    slots = [(f"{g}A{i}", f"{g}Y{i}") for g in (1, 2, 3, 4) for i in (1, 2, 3, 4)]
    num = {v: n for n, v in _244.items()}
    for (a, y), ch in zip(slots, list(chans) + [None] * (16 - len(chans))):
        if ch is None:
            nets[num[a]] = "GND"
        else:
            nets[num[a]], nets[num[y]] = ch
    for g in ("1OE", "2OE", "3OE", "4OE"):
        nets[num[g]] = oe
    for n in _244_VCC:
        nets[n] = vcc
    for n in _244_GND:
        nets[n] = "GND"
    sh.add(k.Part(ref("U"), X16244, value, FP["tssop48"], nets))
    decouple(sh, ref, vcc, 2)


def x16245(sh, ref, a_nets, b_nets, dir1, dir2, oe):
    """A = côté FPGA (3,3 V), B = côté console ; T/R = 1 : A -> B."""
    nets = {}
    for i in range(16):
        nets[pin_of(X245, f"A{i}")] = a_nets[i]
        nets[pin_of(X245, f"B{i}")] = b_nets[i]
    nets.update({pin_of(X245, "T/~{R}1"): dir1, pin_of(X245, "T/~{R}2"): dir2,
                 pin_of(X245, "~{OE1}"): oe, pin_of(X245, "~{OE2}"): oe})
    for p in X245.pins:
        if p.name == "VCC":
            nets[p.number] = "+3V3"
        elif p.name == "GND":
            nets[p.number] = "GND"
    sh.add(k.Part(ref("U"), X245, "74LVC16245A", FP["tssop48"], nets))
    decouple(sh, ref, "+3V3", 2)


def edge(sh, ref, board, used):
    """Connecteur de bord : contact -> AES_<signal> si utilisé, VCC/GND."""
    sym = _edge(board)
    nets = {}
    for pin, sig in EDGE[board].items():
        if sig == "VCC":
            nets[pin] = "+5V"
        elif sig == "GND":
            nets[pin] = "GND"
        elif sig in used:
            nets[pin] = f"AES_{sig}"
    sh.add(k.Part(ref("J"), sym, f"AES {board}", FP["edge"], nets))
    # boucles audio (révision NEO-AES de la console) : reliées par des 0 ohm
    for a, b in (("L_IN", "L_OUT"), ("R_IN", "R_OUT")):
        res(sh, ref, "0", f"AES_{a}", f"AES_{b}")


CABLE = {1: "PROG_SCK", 2: "PROG_IO0", 3: "PROG_IO1", 4: "PROG_IO2", 5: "PROG_IO3", 6: "CS_P",
         7: "CS_V", 8: "LK_IRQ", 9: "MODE", 10: "CDONE", 11: "GND", 12: "GND"}


# ---------------------------------------------------------------------------
# carte PROG

def prog_board():
    b = k.Board("prog", "SDAES - carte PROG (programme 68000 + son ADPCM)")
    ref = Refs()
    used = {"A%d" % i for i in range(1, 20)} | {"D%d" % i for i in range(16)} | \
        {"ROMOE", "PORTOEU", "PORTOEL", "PORTWEL", "PORTWEU", "ROMWAIT", "PWAIT0", "PWAIT1", "PDTACK",
         "SDRMPX", "SDROE", "SDPMPX", "SDPOE", "SDRA8", "SDRA9", "SDRA20", "SDRA21", "SDRA22", "SDRA23",
         "SDPA8", "SDPA9", "SDPA10", "SDPA11", "L_IN", "L_OUT", "R_IN", "R_OUT"} | \
        {f"SDRAD{i}" for i in range(8)} | {f"SDPAD{i}" for i in range(8)}

    sh = b.sheet("Connecteur et alimentations", "power.kicad_sch")
    edge(sh, ref, "PROG", used)
    power(sh, ref, None)
    # attentes : pleine vitesse tant que les tampons sont en haute impédance
    for s in ("ROMWAIT", "PWAIT0", "PWAIT1", "PDTACK"):
        res(sh, ref, "10k", "+5V", f"AES_{s}")
    res(sh, ref, "10k", "+3V3", "CDONE")
    sh.add(k.Part(ref("J"), HDR12, "Câble PROG-CHA", FP["hdr2x6"], CABLE))

    sh = b.sheet("Tampons de niveaux", "buffers.kicad_sch")
    ins = [(f"AES_A{i}", f"A{i}") for i in range(1, 20)] + \
          [(f"AES_{s}", f"{s}_N") for s in ("ROMOE", "PORTOEU", "PORTOEL", "PORTWEL", "PORTWEU")] + \
          [(f"AES_SDRA{i}", f"SDRA{i}") for i in (8, 9, 20, 21, 22, 23)] + \
          [("AES_SDRMPX", "SDRMPX"), ("AES_SDROE", "SDROE_N")] + \
          [(f"AES_SDPA{i}", f"SDPA{i}") for i in (8, 9, 10, 11)] + \
          [("AES_SDPMPX", "SDPMPX"), ("AES_SDPOE", "SDPOE_N")]
    ins = by_edge("PROG", ins, 0)
    for i in range(0, len(ins), 16):
        x16244(sh, ref, ins[i:i + 16], "XLAT_EN_N", "+3V3", "74LVC16244A")
    dd = by_edge("PROG", [(f"D{i}", f"AES_D{i}") for i in range(16)], 1)
    x16245(sh, ref, [a for a, _ in dd], [b for _, b in dd], "D_DIR", "D_DIR", "XLAT_EN_N")
    # canaux 0-7 (sens RAD_DIR) et 8-15 (PAD_DIR) : tri dans chaque groupe
    rad = by_edge("PROG", [(f"SDRAD{i}", f"AES_SDRAD{i}") for i in range(8)], 1)
    pad = by_edge("PROG", [(f"SDPAD{i}", f"AES_SDPAD{i}") for i in range(8)], 1)
    x16245(sh, ref, [a for a, _ in rad + pad], [b for _, b in rad + pad], "RAD_DIR", "PAD_DIR", "XLAT_EN_N")
    # sorties 5 V : attentes (74AHCT125), /OE commandé par 74LVC1G07 à drain ouvert
    sh.add(k.Part(ref("U"), X125, "74AHCT125", FP["tssop14"],
                  {1: "OE5_N", 2: "ROMWAIT_N", 3: "AES_ROMWAIT", 4: "OE5_N", 5: "PWAIT0_N", 6: "AES_PWAIT0",
                   10: "OE5_N", 9: "PWAIT1_N", 8: "AES_PWAIT1", 13: "+5V", 12: "GND",
                   7: "GND", 14: "+5V"}))
    cap(sh, ref, "100n", "+5V")
    sh.add(k.Part(ref("U"), G07, "74LVC1G07", FP["sot23-5"], {2: "XLAT_EN_N", 3: "GND", 4: "OE5_N", 5: "+3V3"}))
    cap(sh, ref, "100n", "+3V3")
    res(sh, ref, "10k", "+3V3", "XLAT_EN_N")
    res(sh, ref, "10k", "+5V", "OE5_N")

    def pmap(port):
        m = re.fullmatch(r"(A|D)\[(\d+)\]", port)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        m = re.fullmatch(r"LK_IO\[(\d)\]", port)
        if m:
            return f"PROG_IO{m.group(1)}"
        fixed = {"LK_SCK": "PROG_SCK", "LK_CS_N": "CS_P", "LK_IRQ": "LK_IRQ", "MODE": "MODE",
                 "CLK25": "P_CLK25", "LED": "P_LED"}
        return fixed.get(port) or sdram_port("P")(port) or port

    def vmap(port):
        m = re.fullmatch(r"(SDRAD|SDPAD|SDPA)\[(\d+)\]", port)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        m = re.fullmatch(r"SDRA_[LU]\[(\d+)\]", port)
        if m:
            return f"SDRA{m.group(1)}"
        m = re.fullmatch(r"LK_IO\[(\d)\]", port)
        if m:
            return f"PROG_IO{m.group(1)}"
        fixed = {"LK_SCK": "PROG_SCK", "LK_CS_N": "CS_V", "MODE": "MODE", "CLK25": "V_CLK25", "LED": "V_LED"}
        return fixed.get(port) or sdram_port("V")(port) or port

    sh = b.sheet("FPGA P", "fpga_p.kicad_sch")
    fpga(sh, ref, "P", "prog_p", pmap)
    sh = b.sheet("SDRAM P", "sdram_p.kicad_sch")
    sdram(sh, ref, "P", "W9825G6KH-6")
    sh = b.sheet("FPGA V", "fpga_v.kicad_sch")
    fpga(sh, ref, "V", "prog_v", vmap)
    sh = b.sheet("SDRAM V", "sdram_v.kicad_sch")
    sdram(sh, ref, "V", "W9825G6KH-6")
    return b


# ---------------------------------------------------------------------------
# carte CHA

def cha_board():
    b = k.Board("cha", "SDAES - carte CHA (sprites, couche fixe, Z80, RP2350)")
    ref = Refs()
    used = {f"P{i}" for i in range(24)} | {f"FIXD{i}" for i in range(8)} | {f"SDA{i}" for i in range(16)} | \
        {f"SDD{i}" for i in range(8)} | {f"GAD{i}" for i in range(4)} | {f"GBD{i}" for i in range(4)} | \
        {"PCK1B", "PCK2B", "CA4", "2H1", "12M", "EVEN", "LOAD", "H", "DOTA", "DOTB", "SDMRD", "SDROM",
         "SDRD0", "L_IN", "L_OUT", "R_IN", "R_OUT"}

    sh = b.sheet("Connecteur et alimentations", "power.kicad_sch")
    edge(sh, ref, "CHA", used)
    power(sh, ref, None)

    sh = b.sheet("Tampons de niveaux", "buffers.kicad_sch")
    ins = [(f"AES_P{i}", f"P{i}") for i in range(24)] + \
          [("AES_PCK1B", "PCK1B"), ("AES_PCK2B", "PCK2B"), ("AES_CA4", "CA4"), ("AES_2H1", "2H1"),
           ("AES_12M", "12M"), ("AES_EVEN", "EVEN"), ("AES_LOAD", "LOAD"), ("AES_H", "H")] + \
          [(f"AES_SDA{i}", f"SDA{i}") for i in range(16)] + \
          [("AES_SDMRD", "SDMRD_N"), ("AES_SDROM", "SDROM_N"), ("AES_SDRD0", "SDRD0_N")]
    ins = by_edge("CHA", ins, 0)
    for i in range(0, len(ins), 16):
        x16244(sh, ref, ins[i:i + 16], "XLAT_EN_N", "+3V3", "74LVC16244A")
    outs = [(f"GAD{i}", f"AES_GAD{i}") for i in range(4)] + [(f"GBD{i}", f"AES_GBD{i}") for i in range(4)] + \
           [("DOTA", "AES_DOTA"), ("DOTB", "AES_DOTB")] + [(f"FIXD{i}", f"AES_FIXD{i}") for i in range(8)]
    outs = by_edge("CHA", outs, 1)
    x16244(sh, ref, outs[:16], "OE5_N", "+5V", "74AHCT16244")
    x16244(sh, ref, outs[16:], "OE5_N", "+5V", "74AHCT16244")
    # bus de données Z80 : 74AHCT244, /OE = SDD_OE_N OU OE5_N
    n244 = {pin_of(X244_8, f"{g}A{i}"): f"SDD{(g - 1) * 4 + i}" for g in (1, 2) for i in range(4)}
    n244.update({pin_of(X244_8, f"{g}Y{i}"): f"AES_SDD{(g - 1) * 4 + i}" for g in (1, 2) for i in range(4)})
    n244.update({pin_of(X244_8, "1OE"): "SDD_OE5_N", pin_of(X244_8, "2OE"): "SDD_OE5_N",
                 pin_of(X244_8, "VCC"): "+5V", pin_of(X244_8, "GND"): "GND"})
    sh.add(k.Part(ref("U"), X244_8, "74AHCT244", FP["tssop20"], n244))
    cap(sh, ref, "100n", "+5V")
    sh.add(k.Part(ref("U"), G32, "74AHCT1G32", FP["sot23-5"],
                  {1: "SDD_OE_N", 2: "OE5_N", 3: "GND", 4: "SDD_OE5_N", 5: "+5V"}))
    cap(sh, ref, "100n", "+5V")
    sh.add(k.Part(ref("U"), G07, "74LVC1G07", FP["sot23-5"], {2: "XLAT_EN_N", 3: "GND", 4: "OE5_N", 5: "+3V3"}))
    cap(sh, ref, "100n", "+3V3")
    res(sh, ref, "10k", "+3V3", "XLAT_EN_N")
    res(sh, ref, "10k", "+5V", "OE5_N")

    def cmap(port):
        m = re.fullmatch(r"(P|GAD|GBD)\[(\d+)\]", port)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        m = re.fullmatch(r"LK_IO\[(\d)\]", port)
        if m:
            return f"CHA_IO{m.group(1)}"
        fixed = {"CLK_12M": "12M", "LK_SCK": "CHA_SCK", "LK_CS_N": "CS_C", "MODE": "MODE",
                 "CLK25": "C_CLK25", "LED": "C_LED"}
        return fixed.get(port) or sdram_port("C")(port) or port

    def smap(port):
        m = re.fullmatch(r"(P|FIXD|SDA|SDD|SR_A|SR_D)\[(\d+)\]", port)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        m = re.fullmatch(r"LK_IO\[(\d)\]", port)
        if m:
            return f"CHA_IO{m.group(1)}"
        fixed = {"S2H1": "2H1", "LK_SCK": "CHA_SCK", "LK_CS_N": "CS_SM", "MODE": "MODE", "CLK25": "SM_CLK25"}
        return fixed.get(port) or port

    sh = b.sheet("FPGA C", "fpga_c.kicad_sch")
    fpga(sh, ref, "C", "cha_c", cmap)
    sh = b.sheet("SDRAM C", "sdram_c.kicad_sch")
    sdram(sh, ref, "C", "AS4C32M16SB-6TIN")
    sh = b.sheet("FPGA SM", "fpga_sm.kicad_sch")
    fpga(sh, ref, "SM", "cha_sm", smap)
    sh = b.sheet("SRAM S + M1", "sram.kicad_sch")
    nets = {}
    for n, v in _SRAM.items():
        if re.fullmatch(r"A\d+", v):
            nets[n] = f"SR_A{v[1:]}"
        elif v.startswith("IO"):
            nets[n] = f"SR_D{v[2:]}"
    nets.update({8: "GND", 37: "SR_OE_N", 15: "SR_WE_N", 11: "+3V3", 33: "+3V3", 12: "GND", 34: "GND"})
    sh.add(k.Part(ref("U"), SRAM, "IS61WV10248EDBLL-10TLI", FP["sram"], nets))
    decouple(sh, ref, "+3V3", 2, "10u")

    sh = b.sheet("RP2350, carte SD, câble", "mcu.kicad_sch")
    pico = {i: "GND" for i in (3, 8, 13, 18, 23, 28, 33, 38)}
    gp = {2: "SD_CLK", 3: "SD_CMD", 4: "SD_D0", 5: "SD_D1", 6: "SD_D2", 7: "SD_D3",
          8: "PROG_SCK_MCU", 9: "PROG_IO0_MCU", 10: "PROG_IO1_MCU", 11: "PROG_IO2_MCU", 12: "PROG_IO3_MCU",
          13: "CS_P", 14: "CS_V", 15: "CHA_SCK_MCU", 16: "CHA_IO0_MCU", 17: "CHA_IO1_MCU",
          18: "CHA_IO2_MCU", 19: "CHA_IO3_MCU", 20: "CS_C", 21: "CS_SM", 22: "LK_IRQ",
          26: "CDONE", 27: "BUTTON_N"}
    for g, net in gp.items():
        pico[pin_of(PICO, f"GP{g}")] = net
    pico[pin_of(PICO, "VSYS")] = "PICO_VSYS"
    sh.add(k.Part(ref("A"), PICO, "Raspberry Pi Pico 2", FP["pico"], pico))
    # VSYS depuis le 5 V de la console, par une diode Schottky (fiche Pico 2)
    sh.add(k.Part(ref("D"), DSCH, "SS14 / BAT60A", FP["schottky"], {2: "+5V", 1: "PICO_VSYS"}))
    # résistances série côté émetteur sur les deux bus de liaison
    for bus in ("PROG", "CHA"):
        res(sh, ref, "33", f"{bus}_SCK_MCU", f"{bus}_SCK")
        for i in range(4):
            res(sh, ref, "33", f"{bus}_IO{i}_MCU", f"{bus}_IO{i}")
    res(sh, ref, "10k", "+3V3", "CDONE")
    sh.add(k.Part(ref("SW"), SW, "Retour menu", FP["sw"], {1: "BUTTON_N", 2: "GND"}))
    sh.add(k.Part(ref("J"), MSD, "microSD", FP["sd"],
                  {1: "SD_D2", 2: "SD_D3", 3: "SD_CMD", 4: "+3V3", 5: "SD_CLK", 6: "GND",
                   7: "SD_D0", 8: "SD_D1", 9: "GND"}))
    for s in ("SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3"):
        res(sh, ref, "10k", "+3V3", s)
    cap(sh, ref, "10u", "+3V3")
    cap(sh, ref, "100n", "+3V3")
    sh.add(k.Part(ref("J"), HDR12, "Câble PROG-CHA", FP["hdr2x6"], CABLE))
    return b


# ---------------------------------------------------------------------------

def main():
    import footprints
    out = os.path.join(ROOT, "hardware", "kicad")
    footprints.write(out, [X16244, SRAM, PICO, _edge("PROG"), _edge("CHA")])
    ok = True
    for board in (prog_board(), cha_board()):
        d = os.path.join(out, board.name)
        root = k.write_board(board, d, board.name)
        parts = board.parts()
        print(f"{board.name} : {len(parts)} composants, {len(board.netlist())} réseaux -> {root}")
        if "--check" in sys.argv:
            net = os.path.join(d, board.name + ".net")
            subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", net, root],
                           check=True, capture_output=True)
            errs = k.check_netlist(board, net)
            os.remove(net)
            for e in errs[:40]:
                print("   ERREUR", e)
            print(f"   netlist KiCad : {'IDENTIQUE à la description' if not errs else f'{len(errs)} différence(s)'}")
            ok = ok and not errs
        if "--pdf" in sys.argv:
            pdf = os.path.join(out, f"sdaes_{board.name}.pdf")
            subprocess.run(["kicad-cli", "sch", "export", "pdf", "-o", pdf, root], check=True, capture_output=True)
            print(f"   PDF : {pdf}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
