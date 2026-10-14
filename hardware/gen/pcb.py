#!/usr/bin/env python3
"""Circuits imprimés PROG et CHA : composants placés -> hardware/kicad/{prog,cha}/{prog,cha}.kicad_pcb

Part du contour (outline.py) et de la description des cartes (boards.py) :
chaque composant reçoit son empreinte et ses réseaux, sans passer par
l'interface de KiCad. Placement :

  * « ancres » (circuits intégrés, connecteurs, module Pico) : position fixée
    par la table PLACE ci-dessous (flux du signal : contacts en bas, tampons
    de niveaux juste au-dessus, FPGA, mémoires en haut) ; l'orientation, si
    elle n'est pas imposée, est celle qui raccourcit le plus les liaisons ;
  * composants passifs : chacun suit l'ancre qui le précède dans la
    description (découplage après son circuit, etc.) et se place au plus
    près de la broche de l'ancre avec laquelle il partage un réseau.

Circuit 4 couches : signaux sur les faces externes, In1 = plan de masse
continu, In2 = plan +3V3 ; +5V et +1V2 routés en pistes larges.
Nécessite le module Python de KiCad (pcbnew).

    python3 hardware/gen/pcb.py [prog|cha]
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boards    # noqa: E402
import outline   # noqa: E402

KICAD = os.path.join(HERE, "..", "kicad")
SYSLIB = "/usr/share/kicad/footprints"
CX, EDGE_Y = outline.CX, outline.EDGE_Y
SHOULDER = EDGE_Y - outline.TAB_H                     # haut de la languette
TOP = SHOULDER - outline.BODY_H                       # bord supérieur
HOLES = [(CX + dx, SHOULDER - outline.HOLE_DY) for dx in (-outline.HOLE_DX, outline.HOLE_DX)]
PLANES = {"GND": (pcbnew.In1_Cu,), "+3V3": (pcbnew.In2_Cu,)}    # plans internes

# Ancres : référence -> (x, y, rotation en degrés ou None = automatique).
# Repère : axe de la languette x = 150, bord des contacts y = 180, haut de
# la carte y = 46 ; trous de la coque en (105, 149,25) et (195, 149,25).
ROW = 135.0        # rangée des tampons, au-dessus des trous
PLACE = {
    "prog": {
        "J1": (CX, EDGE_Y - outline.PAD_FROM_EDGE, 0),
        # tampons, dans l'ordre des contacts qu'ils desservent
        "U3": (101, ROW, None), "U7": (118, ROW, None), "U8": (134, ROW, None), "U9": (144, ROW, None),
        "U4": (160, ROW, None), "U6": (177, ROW, None), "U5": (194, ROW, None),
        "U1": (150, 150, 0), "U2": (138, 150, None),          # régulateurs, près des contacts VCC
        "U13": (110, 98, 0), "U15": (110, 62, None),        # FPGA V et sa SDRAM
        "U10": (190, 98, 0), "U12": (190, 62, None),        # FPGA P et sa SDRAM
        "J2": (150, 52, 0),                                    # câble PROG-CHA
    },
    "cha": {
        "J1": (CX, EDGE_Y - outline.PAD_FROM_EDGE, 0),
        "U9": (93, ROW, None), "U3": (108, ROW, None), "U7": (124, ROW, None), "U4": (141, ROW, None),
        "U5": (158, ROW, None), "U6": (175, ROW, None), "U8": (192, ROW, None),
        "U10": (207, ROW, None), "U11": (216, ROW, None),
        "U1": (150, 150, 0), "U2": (138, 150, None),
        "U15": (112, 98, 0), "U17": (100, 64, None),        # FPGA SM et SRAM
        "U12": (192, 98, 0), "U14": (192, 62, None),        # FPGA C et SDRAM
        "A1": (150, 90, 0),                                    # Pico 2, au milieu
        "J4": (150, 55, 180),                                  # microSD, ouverture vers le haut
        "SW1": (128, 50, 0),                                   # bouton retour menu
        "J5": (172, 52, 0),                                    # câble PROG-CHA
    },
}
MARGIN = 0.3       # écart minimal entre deux composants (mm)


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def load_fp(lib_id):
    lib, name = lib_id.split(":")
    path = os.path.join(KICAD, "sdaes.pretty") if lib == "SDAES" else os.path.join(SYSLIB, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"empreinte introuvable : {lib_id}")
    fp.SetFPIDAsString(lib_id)
    return fp


def bbox(fp, margin=MARGIN):
    """Rectangle occupé (mm) : boîte de l'empreinte sans les textes."""
    b = fp.GetBoundingBox(False, False)
    return (pcbnew.ToMM(b.GetLeft()) - margin, pcbnew.ToMM(b.GetTop()) - margin,
            pcbnew.ToMM(b.GetRight()) + margin, pcbnew.ToMM(b.GetBottom()) + margin)


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def allowed(r, is_edge=False):
    """Dans le corps de la carte, hors trous de la coque et hors languette."""
    x0, y0, x1, y1 = r
    if x0 < CX - outline.BOARDS_W / 2 + 1 or x1 > CX + outline.BOARDS_W / 2 - 1:
        return False
    if y0 < TOP + 3.5 or (y1 > SHOULDER - 0.5 and not is_edge):
        return False
    for hx, hy in HOLES:
        k = outline.HOLE_D / 2 + 1.5
        if overlap(r, (hx - k, hy - k, hx + k, hy + k)):
            return False
    return True


class Layout:
    def __init__(self, name):
        self.name = name
        self.desc = {"prog": boards.prog_board, "cha": boards.cha_board}[name]()
        outline.BOARDS_W = outline.BOARDS[name][0]
        self.board = outline.make(name)
        self.fps = {}
        self.parts = self.desc.parts()
        self.nets = self.desc.netlist()
        for n in sorted(self.nets):
            self.board.Add(pcbnew.NETINFO_ITEM(self.board, n))
        self.edge_fp = None
        for f in self.board.GetFootprints():          # J1 déjà placé par outline
            self.edge_fp = f
        self.taken = []

    # -- composants -------------------------------------------------------
    def add(self, part, x, y, rot):
        if part.ref == "J1":
            fp = self.edge_fp
        else:
            fp = load_fp(part.footprint)
            fp.SetReference(part.ref)
            fp.SetValue(part.value)
            self.board.Add(fp)
            fp.SetPosition(mm(x, y))
            fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            n = part.nets.get(pad.GetNumber())
            if n:
                pad.SetNet(self.board.FindNet(n))
        self.fps[part.ref] = fp
        return fp

    def pad_xy(self, ref, num=None, net=None):
        out = []
        for p in self.fps[ref].Pads():
            if (num is None or p.GetNumber() == num) and (net is None or p.GetNetname() == net):
                v = p.GetPosition()
                out.append((pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)))
        return out

    def hpwl(self, refs):
        """Demi-périmètre des réseaux de signal touchant `refs` (composants placés)."""
        tot = 0.0
        seen = set()
        for r in refs:
            for p in self.fps[r].Pads():
                n = p.GetNetname()
                if not n or n in PLANES or n in seen:
                    continue
                seen.add(n)
                pts = [xy for rr, _ in self.nets[n] if rr in self.fps for xy in self.pad_xy(rr, net=n)]
                if len(pts) > 1:
                    xs, ys = [a for a, _ in pts], [b for _, b in pts]
                    tot += max(xs) - min(xs) + max(ys) - min(ys)
        return tot

    # -- placement --------------------------------------------------------
    def place(self):
        table = PLACE[self.name]
        groups, cur = [], None
        for p in self.parts:
            if p.ref in table:
                cur = (p, [])
                groups.append(cur)
            elif cur is None:
                raise SystemExit(f"{p.ref} avant toute ancre")
            else:
                cur[1].append(p)
        missing = [p.ref for p in self.parts if p.ref[0] in "UJA" and p.ref not in table
                   and not p.ref.startswith("J") and p.ref[0] != "A"]
        anchors = [g[0] for g in groups]
        # ancres non reconnues (en-têtes, oscillateurs...) : traitées comme satellites
        for a in anchors:
            x, y, rot = table[a.ref]
            self.add(a, x, y, rot or 0)
        # orientation automatique, deux passes
        for _ in range(2):
            for a in anchors:
                if table[a.ref][2] is not None:
                    continue
                fp = self.fps[a.ref]
                best = None
                for rot in (0, 90, 180, 270):
                    fp.SetOrientationDegrees(rot)
                    c = self.hpwl([a.ref])
                    if best is None or c < best[0]:
                        best = (c, rot)
                fp.SetOrientationDegrees(best[1])
        for a in anchors:
            r = bbox(self.fps[a.ref])
            if a.ref != "J1" and not allowed(r):
                print(f"  ATTENTION : {a.ref} sort de la zone autorisée {tuple(round(v, 1) for v in r)}")
            for o in self.taken:
                if overlap(r, o[1]):
                    print(f"  ATTENTION : {a.ref} chevauche {o[0]}")
            self.taken.append((a.ref, r))
        # satellites : près de la broche de l'ancre qui partage un réseau
        for a, sats in groups:
            used_pads = {}
            for s in sats:
                fp = self.add(s, 0, 0, 0)
                target = self.target(a, s, used_pads)
                self.drop(fp, target, a)
        return missing

    def target(self, anchor, sat, used):
        """Point visé pour un satellite : broche de l'ancre de même réseau (hors
        masse) la moins utilisée, sinon broche d'un autre composant déjà placé."""
        nets = [n for n in sat.nets.values() if n != "GND"]
        best = None
        for n in nets:
            for xy in self.pad_xy(anchor.ref, net=n):
                k = used.get(xy, 0)
                if best is None or k < best[0]:
                    best = (k, xy)
        if best:
            used[best[1]] = best[0] + 1
            return best[1]
        for n in nets:
            pts = [xy for rr, _ in self.nets.get(n, ()) if rr in self.fps and rr != sat.ref
                   for xy in self.pad_xy(rr, net=n)]
            if pts:
                return pts[0]
        x, y = self.fps[anchor.ref].GetPosition().x, self.fps[anchor.ref].GetPosition().y
        return pcbnew.ToMM(x), pcbnew.ToMM(y)

    def drop(self, fp, target, anchor):
        """Pose `fp` à l'emplacement libre le plus proche de `target` (spirale
        sur une grille de 0,5 mm), tourné pour pointer vers l'ancre."""
        ax, ay = (pcbnew.ToMM(v) for v in (self.fps[anchor.ref].GetPosition().x,
                                           self.fps[anchor.ref].GetPosition().y))
        tx, ty = target
        horiz = abs(tx - ax) < abs(ty - ay)       # broche en haut/bas de l'ancre
        fp.SetOrientationDegrees(90 if horiz else 0)
        for rad in range(0, 80):
            cands = []
            for i in range(-rad, rad + 1):
                for j in (-rad, rad):
                    cands += [(i, j), (j, i)]
            cands.sort(key=lambda c: c[0] ** 2 + c[1] ** 2)
            for i, j in cands:
                x, y = tx + i * 0.5, ty + j * 0.5
                fp.SetPosition(mm(x, y))
                r = bbox(fp)
                if allowed(r) and not any(overlap(r, o[1]) for o in self.taken):
                    self.taken.append((fp.GetReference(), r))
                    return
        raise SystemExit(f"pas de place pour {fp.GetReference()}")

    # -- plans, règles ----------------------------------------------------
    def finish(self):
        b = self.board
        b.SetCopperLayerCount(4)
        ds = b.GetDesignSettings()
        nc = ds.m_NetSettings.m_DefaultNetClass
        nc.SetTrackWidth(pcbnew.FromMM(0.15))
        nc.SetClearance(pcbnew.FromMM(0.15))
        nc.SetViaDiameter(pcbnew.FromMM(0.6))
        nc.SetViaDrill(pcbnew.FromMM(0.3))
        ds.m_TrackMinWidth = pcbnew.FromMM(0.127)
        ds.m_ViasMinSize = pcbnew.FromMM(0.45)
        ds.m_MinThroughDrill = pcbnew.FromMM(0.3)
        pw = pcbnew.NETCLASS("Alim")
        pw.SetTrackWidth(pcbnew.FromMM(0.5))
        pw.SetClearance(pcbnew.FromMM(0.2))
        pw.SetViaDiameter(pcbnew.FromMM(0.8))
        pw.SetViaDrill(pcbnew.FromMM(0.4))
        ds.m_NetSettings.m_NetClasses["Alim"] = pw
        for n in ("+5V", "+1V2", "GND", "+3V3"):
            ds.m_NetSettings.m_NetClassPatternAssignments.append(
                (pcbnew.EDA_COMBINED_MATCHER(n, pcbnew.CTX_NETCLASS), "Alim")) \
                if hasattr(ds.m_NetSettings, "m_NetClassPatternAssignments") else None
        w = outline.BOARDS[self.name][0]
        for net, layer in ((n, l) for n, ls in PLANES.items() for l in ls):
            z = pcbnew.ZONE(b)
            z.SetLayer(layer)
            z.SetNet(b.FindNet(net))
            z.SetLocalClearance(pcbnew.FromMM(0.3))
            z.SetMinThickness(pcbnew.FromMM(0.25))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
            ol = z.Outline()
            ol.NewOutline()
            for x, y in ((CX - w / 2 + 0.5, TOP + 0.5), (CX + w / 2 - 0.5, TOP + 0.5),
                         (CX + w / 2 - 0.5, SHOULDER - 0.5), (CX - w / 2 + 0.5, SHOULDER - 0.5)):
                ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
            b.Add(z)

    def save(self):
        out = os.path.join(KICAD, self.name, f"{self.name}.kicad_pcb")
        self.board.Save(out)
        # remplissage des zones sur la carte relue (carte construite en
        # mémoire : le remplisseur de KiCad 7 y plante)
        b = pcbnew.LoadBoard(out)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(out)
        return out


# FPGA de chaque carte : référence -> nom du gabarit .pcf (fpga_pins.FPGAS)
FPGA_REF = {"prog": {"U10": "prog_p", "U13": "prog_v"}, "cha": {"U12": "cha_c", "U15": "cha_sm"}}
PINS_OPT = os.path.join(HERE, "pins_opt.json")


def _angle(cx, cy, x, y):
    return math.atan2(y - cy, x - cx)


def _adiff(a, b):
    d = abs(a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


def match_cyclic(sig, pins, bad):
    """Affectation qui conserve l'ordre circulaire : sig et pins sont des
    listes (angle, nom) triées par angle ; bad(s, p) interdit un couple.
    Minimise la somme des carrés des écarts d'angle (programmation
    dynamique pour chaque point de départ de la liste des broches)."""
    n, m = len(sig), len(pins)
    best = None
    inf = float("inf")
    for off in range(m):
        pp = pins[off:] + pins[:off]
        # dp[j] = coût minimal des i premiers signaux sur les j premières broches
        prev = [0.0] * (m + 1)
        choice = []
        for i in range(n):
            cur = [inf] * (m + 1)
            ch = [None] * (m + 1)
            for j in range(i + 1, m - (n - i - 1) + 1):
                take = inf if bad(sig[i][1], pp[j - 1][1]) else prev[j - 1] + _adiff(sig[i][0], pp[j - 1][0]) ** 2
                if take < cur[j - 1]:
                    cur[j], ch[j] = take, True
                else:
                    cur[j], ch[j] = cur[j - 1], False
            prev = cur
            choice.append(ch)
        if best is None or prev[m] < best[0]:
            # reconstruction
            res, j = {}, m
            for i in range(n - 1, -1, -1):
                while not choice[i][j]:
                    j -= 1
                res[sig[i][1]] = pp[j - 1][1]
                j -= 1
            best = (prev[m], res)
    return best[1]


def optimise_pins(L):
    """Réaffecte les broches des FPGA selon le placement (pins_opt.json)."""
    import json
    import fpga_pins
    opt = json.load(open(PINS_OPT)) if os.path.exists(PINS_OPT) else {}
    for ref, pcf in FPGA_REF[L.name].items():
        cfg = fpga_pins.FPGAS[pcf]
        plist, cur, dirs = fpga_pins.assign(pcf)
        fixed = set(cfg["gbin"])
        part = [p for p in L.parts if p.ref == ref][0]
        fp = L.fps[ref]
        c = fp.GetPosition()
        cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
        pad_xy = {int(p.GetNumber()): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
                  for p in fp.Pads() if p.GetNumber().isdigit()}
        free = sorted({p for b in fpga_pins.BANK.values() for p in b} - {fpga_pins.GBIN[g] for g in cfg["gbin"].values()})
        sig = []
        for _, port in plist:
            if port in fixed:
                continue
            net = part.nets.get(str(cur[port]))
            pts = [xy for rr, _ in L.nets.get(net, ()) if rr != ref and rr in L.fps
                   for xy in L.pad_xy(rr, net=net)]
            if not pts:
                continue
            tx, ty = sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts)
            sig.append((_angle(cx, cy, tx, ty), port))
        pins = [(_angle(cx, cy, *pad_xy[p]), p) for p in free]
        sig.sort()
        pins.sort()
        res = match_cyclic(sig, pins, lambda s, p: dirs[s] != "output" and p in fpga_pins.OUTPUT_ONLY)
        opt[pcf] = {s: p for s, p in sorted(res.items())}
        moved = sum(1 for s, p in res.items() if cur[s] != p)
        print(f"  {ref} ({pcf}) : {len(res)} signaux, {moved} broches changées")
    with open(PINS_OPT, "w") as f:
        json.dump(opt, f, indent=1, sort_keys=True)
        f.write("\n")


def build(name):
    L = Layout(name)
    L.place()
    L.finish()
    out = L.save()
    print(f"{out} : {len(L.fps)} composants, longueur estimée des liaisons {L.hpwl(list(L.fps)):.0f} mm")
    return L


def main():
    args = sys.argv[1:]
    pins = "--pins" in args
    for name in [a for a in args if not a.startswith("-")] or ("prog", "cha"):
        L = build(name)
        if pins:
            optimise_pins(L)


if __name__ == "__main__":
    main()
