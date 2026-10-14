#!/usr/bin/env python3
"""Affectation des broches des 4 FPGA iCE40HX4K-TQ144 -> hardware/*.pcf

Règles (hardware/README.md) :
  * signaux du connecteur AES (via les tampons de niveaux) : bancs 3 puis 2
    (côtés gauche et bas du boîtier, vers le connecteur de bord) ;
  * mémoire (SDRAM ou SRAM), liaison RP2350, MODE, LED : bancs 0 et 1 ;
  * signaux utilisés comme horloges dans le HDL : entrées globales GBIN ;
  * broches SPI de configuration : pas de flash, le RP2350 configure chaque
    FPGA en mode esclave par le bus de liaison ; LK_SCK -> 70 (SCK),
    LK_IO[0] -> 68 (SDI), LK_CS_N -> 71 (SS), qui redeviennent ces entrées
    après la configuration ; 67 (SDO) reste libre (connecteur de secours).

Les numéros de broches et les bancs viennent du symbole KiCad
FPGA_Lattice:ICE40HX4K-TQ144. Le résultat est vérifié par nextpnr
(make -C hdl pinpnr).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_pcf  # noqa: E402  (ports des tops, contacts AES)
import json  # noqa: E402

# Affectation optimisée d'après le placement du circuit imprimé
# (hardware/gen/pcb.py --pins) ; prioritaire sur la règle des bancs.
PINS_OPT = os.path.join(HERE, "pins_opt.json")

# broches d'E/S par banc, dans l'ordre du boîtier (sens trigonométrique)
BANK = {
    0: [110, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 124, 125, 128, 129,
        130, 134, 135, 136, 137, 138, 139, 141, 142, 143, 144],
    1: [73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 87, 88, 90, 91, 93, 94, 95, 96,
        97, 98, 99, 101, 102, 104, 105, 106, 107],
    2: [37, 38, 39, 41, 42, 43, 44, 45, 47, 48, 49, 52, 55, 56, 60, 61, 62, 63, 64],
    3: [1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
        28, 29, 31, 32, 33, 34],
}
GBIN = {0: 129, 1: 128, 2: 94, 3: 93, 4: 52, 5: 49, 6: 21, 7: 20}
# Les deux PLL (bas : broche 49, haut : broche 129) réquisitionnent le chemin
# d'entrée d'une broche (nextpnr : « PLL bel ... conflicts with input »).
# La broche 129 est réservée à une sortie : la PLL du haut reste libre.
OUTPUT_ONLY = {129}
# Bus de liaison sur les broches de configuration SPI (mode esclave)
CFG_PINS = {"LK_SCK": 70, "LK_IO[0]": 68, "LK_CS_N": 71}


def bus(name, lo, hi):
    return [f"{name}[{i}]" for i in range(lo, hi + 1)]


# Par FPGA : horloges -> GBIN imposées ; groupe « connecteur » ; groupe « mémoire »
FPGAS = {
    "prog_p": {
        "top": ("hdl/prog/prog_p_top.v", "prog_p_top"),
        "gbin": {"CLK25": 3},
        "conn": bus("A", 1, 19) + ["ROMOE_N", "PORTOEU_N", "PORTOEL_N", "PORTWEL_N", "PORTWEU_N",
                                   "ROMWAIT_N", "PWAIT0_N", "PWAIT1_N", "XLAT_EN_N", "D_DIR"]
                + bus("D", 0, 15),
        "mem": bus("SD_DQ", 0, 15) + ["SD_DQM[0]", "SD_DQM[1]", "SD_WE_N", "SD_CAS_N", "SD_RAS_N",
                                      "SD_CS_N", "SD_BA[0]", "SD_BA[1]"] + bus("SD_A", 0, 12)
               + ["SD_CKE", "SD_CLK"],
    },
    "prog_v": {
        "top": ("hdl/prog/prog_v_top.v", "prog_v_top"),
        "gbin": {"CLK25": 3, "SDRMPX": 7, "SDPMPX": 6},
        "conn": bus("SDRAD", 0, 7) + ["SDRA_L[8]", "SDRA_L[9]"] + bus("SDRA_U", 20, 23)
                + ["SDROE_N", "RAD_DIR"] + bus("SDPAD", 0, 7) + bus("SDPA", 8, 11)
                + ["SDPOE_N", "PAD_DIR"],
        "mem": bus("SD_DQ", 0, 15) + ["SD_DQM[0]", "SD_DQM[1]", "SD_WE_N", "SD_CAS_N", "SD_RAS_N",
                                      "SD_CS_N", "SD_BA[0]", "SD_BA[1]"] + bus("SD_A", 0, 12)
               + ["SD_CKE", "SD_CLK"],
    },
    "cha_c": {
        "top": ("hdl/cha/cha_c_top.v", "cha_c_top"),
        "gbin": {"CLK25": 3, "PCK1B": 7, "CLK_12M": 6},
        "conn": bus("P", 0, 23) + ["CA4", "EVEN", "LOAD", "H"] + bus("GAD", 0, 3) + bus("GBD", 0, 3)
                + ["DOTA", "DOTB", "XLAT_EN_N"],
        "mem": bus("SD_DQ", 0, 15) + ["SD_DQM[0]", "SD_DQM[1]", "SD_WE_N", "SD_CAS_N", "SD_RAS_N",
                                      "SD_CS_N", "SD_BA[0]", "SD_BA[1]"] + bus("SD_A", 0, 12)
               + ["SD_CKE", "SD_CLK"],
    },
    "cha_sm": {
        "top": ("hdl/cha/cha_sm_top.v", "cha_sm_top"),
        "gbin": {"CLK25": 3, "PCK2B": 7},
        "conn": bus("P", 0, 15) + ["S2H1"] + bus("FIXD", 0, 7) + bus("SDA", 0, 15)
                + ["SDMRD_N", "SDROM_N", "SDRD0_N"] + bus("SDD", 0, 7) + ["SDD_OE_N"],
        "mem": bus("SR_D", 0, 7) + bus("SR_A", 0, 19) + ["SR_OE_N", "SR_WE_N"],
    },
}


def assign(name):
    cfg = FPGAS[name]
    top_v, top = cfg["top"]
    plist = gen_pcf.ports(os.path.join(ROOT, top_v), top)
    pnames = [p for _, p in plist]
    dirs = dict((p, d) for d, p in plist)
    pin = {}
    used = set()
    for sig, g in cfg["gbin"].items():
        pin[sig] = GBIN[g]
        used.add(GBIN[g])
    for sig, p in CFG_PINS.items():
        pin[sig] = p
        used.add(p)
    if os.path.exists(PINS_OPT) and not getattr(assign, "raw", False):
        for sig, p in json.load(open(PINS_OPT)).get(name, {}).items():
            if sig in dirs and sig not in pin and p not in used:
                pin[sig] = p
                used.add(p)

    def pour(signals, banks):
        free = [p for b in banks for p in BANK[b] if p not in used]
        for s in signals:
            if s in pin:
                continue
            ok = [p for p in free if dirs[s] == "output" or p not in OUTPUT_ONLY]
            if not ok:
                raise SystemExit(f"{name} : plus de broche libre pour {s}")
            pin[s] = ok[0]
            free.remove(ok[0])
            used.add(pin[s])

    pour(cfg["conn"], [3, 2, 1])
    pour(cfg["mem"], [0, 1])
    rest = [p for p in pnames if p not in pin]
    pour(rest, [1, 0, 2, 3])
    missing = [p for p in pnames if p not in pin]
    extra = [p for p in pin if p not in pnames]
    if missing or extra:
        raise SystemExit(f"{name} : ports manquants {missing} / inconnus {extra}")
    return plist, pin, dirs


def bank_of(p):
    return next(b for b, l in BANK.items() if p in l)


def main():
    for name in FPGAS:
        plist, pin, dirs = assign(name)
        top = FPGAS[name]["top"][1]
        out = os.path.join(ROOT, "hardware", f"{name}.pcf")
        with open(out, "w") as f:
            f.write(f"# Contraintes {top} - iCE40HX4K-TQ144 (puce HX8K, outils libres)\n")
            f.write("# Généré par hardware/gen/fpga_pins.py (ne pas modifier à la main).\n")
            f.write("# « AES ... » = contact du connecteur de cartouche relié à ce port à\n")
            f.write("# travers un tampon de niveaux (hardware/aes_connector.csv).\n")
            for d, p in plist:
                c = gen_pcf.contact(p)
                g = [k for k, v in GBIN.items() if v == pin[p]]
                note = f"{d}, " + ("configuration SPI" if p in CFG_PINS else f"banc {bank_of(pin[p])}") + (f", GBIN{g[0]}" if g else "") \
                    + (f", AES {c}" if c else "")
                f.write(f"set_io {p} {pin[p]}    # {note}\n")
        print(f"{out} : {len(plist)} broches")


if __name__ == "__main__":
    main()
