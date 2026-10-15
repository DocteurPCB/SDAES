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
        "U12": (110, 98, 0), "U13": (110, 62, None),        # FPGA V et sa SDRAM
        "U10": (190, 98, 0), "U11": (190, 62, None),        # FPGA P et sa SDRAM
        "A1": (150, 93, 0),                                    # Pico 2, au milieu
        "J5": (150, 55, 0),                                    # microSD, ouverture vers le haut
        "SW1": (128, 50, 0),                                   # bouton retour menu
        "J2": (172, 52, 0),                                    # câble PROG-CHA (même place sur CHA)
    },
    "cha": {
        "J1": (CX, EDGE_Y - outline.PAD_FROM_EDGE, 0),
        "U9": (93, ROW, None), "U3": (108, ROW, None), "U7": (124, ROW, None), "U4": (141, ROW, None),
        "U5": (158, ROW, None), "U6": (175, ROW, None), "U8": (192, ROW, None),
        "U10": (207, ROW, None), "U11": (216, ROW, None),
        "U1": (150, 150, 0), "U2": (138, 150, None),
        "U14": (112, 98, 0), "U15": (100, 64, None),        # FPGA SM et SRAM
        "U12": (192, 98, 0), "U13": (192, 62, None),        # FPGA C et SDRAM
        "J4": (172, 52, 0),                                    # câble PROG-CHA (même place sur PROG)
    },
}
# 9 trous d'entretoise M3 reliant les deux cartes : mêmes coordonnées sur
# PROG et CHA (repère commun : axe de la languette), hors composants.
STANDOFFS = [(70, 55), (230, 55), (70, 100), (230, 100), (70, 150), (230, 150),
             (130, 75), (170, 75), (150, 124)]
STANDOFF_FP = "MountingHole:MountingHole_3.2mm_M3"
STANDOFF_KEEP = 3.5            # rayon sans composant ni cuivre autour (mm)
MARGIN = 0.3       # écart minimal entre deux composants (mm)
POWER = {"GND", "+3V3", "+1V2", "+5V"}


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
    for hx, hy in STANDOFFS:
        k = STANDOFF_KEEP
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
        for i, (x, y) in enumerate(STANDOFFS):
            fp = load_fp(STANDOFF_FP)
            fp.SetReference(f"H{i + 1}")
            fp.SetValue("Entretoise M3")
            fp.SetBoardOnly(True)
            fp.SetExcludedFromBOM(True)
            fp.SetPosition(mm(x, y))
            self.board.Add(fp)

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
        vals = {p.ref: p.value for p in self.parts}
        for ref, pcf in FPGA_REF[self.name].items():
            if not vals.get(ref, "").startswith("iCE40"):
                raise SystemExit(f"{self.name} : {ref} n'est pas un FPGA ({vals.get(ref)}) : table PLACE à revoir")
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
            sides = self.sides(self.fps[a.ref])
            for o in self.taken:
                if overlap(r, o[1]) and sides & o[2]:
                    print(f"  ATTENTION : {a.ref} chevauche {o[0]}")
            self.taken.append((a.ref, r, sides))
        # satellites : près de la broche de l'ancre qui partage un réseau
        for a, sats in groups:
            used_pads = {}
            big = len(self.fps[a.ref].Pads()) >= 14 and a.ref.startswith("U")
            for s in sats:
                fp = self.add(s, 0, 0, 0)
                target = self.target(a, s, used_pads)
                bottom = big and s.ref.startswith("C") and set(s.nets.values()) <= POWER
                if bottom:
                    # découplage sous le boîtier, face arrière : la face
                    # composants reste libre pour la sortie des broches
                    c = self.fps[a.ref].GetPosition()
                    cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
                    dx, dy = cx - target[0], cy - target[1]
                    dist = math.hypot(dx, dy) or 1
                    pull = min(4.0, 0.6 * dist)
                    target = (target[0] + dx / dist * pull, target[1] + dy / dist * pull)
                self.drop(fp, target, a, bottom)
        return missing

    @staticmethod
    def sides(fp):
        """Faces occupées : traversant = les deux."""
        if any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in fp.Pads()):
            return {"F", "B"}
        return {"B"} if fp.IsFlipped() else {"F"}

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

    def drop(self, fp, target, anchor, bottom=False):
        """Pose `fp` à l'emplacement libre le plus proche de `target` (spirale
        sur une grille de 0,5 mm), tourné pour pointer vers l'ancre."""
        ax, ay = (pcbnew.ToMM(v) for v in (self.fps[anchor.ref].GetPosition().x,
                                           self.fps[anchor.ref].GetPosition().y))
        tx, ty = target
        horiz = abs(tx - ax) < abs(ty - ay)       # broche en haut/bas de l'ancre
        fp.SetOrientationDegrees(90 if horiz else 0)
        if bottom:
            fp.Flip(fp.GetPosition(), False)
        sides = self.sides(fp)
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
                if allowed(r) and not any(overlap(r, o[1]) and sides & o[2] for o in self.taken):
                    self.taken.append((fp.GetReference(), r, sides))
                    return
        raise SystemExit(f"pas de place pour {fp.GetReference()}")

    # -- plans, règles ----------------------------------------------------
    def finish(self):
        b = self.board
        b.SetCopperLayerCount(4)
        ds = b.GetDesignSettings()
        nc = ds.m_NetSettings.m_DefaultNetClass
        # 0,127 mm (5 mil) : minimum courant des fabricants en 4 couches
        nc.SetTrackWidth(pcbnew.FromMM(0.127))
        nc.SetClearance(pcbnew.FromMM(0.127))
        nc.SetViaDiameter(pcbnew.FromMM(0.6))
        nc.SetViaDrill(pcbnew.FromMM(0.3))
        ds.m_TrackMinWidth = pcbnew.FromMM(0.09)        # rétrécissement à l'entrée des broches
        ds.m_ViasMinSize = pcbnew.FromMM(0.45)
        ds.m_MinThroughDrill = pcbnew.FromMM(0.3)
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
            tw, ty = outline.TAB_W / 2 - 0.5, EDGE_Y - 10.6     # languette, au-dessus des contacts
            for x, y in ((CX - w / 2 + 0.5, TOP + 0.5), (CX + w / 2 - 0.5, TOP + 0.5),
                         (CX + w / 2 - 0.5, SHOULDER - 0.5), (CX + tw, SHOULDER - 0.5),
                         (CX + tw, ty), (CX - tw, ty),
                         (CX - tw, SHOULDER - 0.5), (CX - w / 2 + 0.5, SHOULDER - 0.5)):
                ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
            b.Add(z)

        # sous le Pico 2 : ni piste ni via sur la face composants (pastilles
        # de test nues sous le module) ; les signaux passent par la face arrière
        if "A1" in self.fps:
            c = self.fps["A1"].GetPosition()
            px, py = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
            k = pcbnew.ZONE(b)
            k.SetIsRuleArea(True)
            k.SetDoNotAllowTracks(True)
            k.SetDoNotAllowVias(True)
            k.SetDoNotAllowCopperPour(False)
            k.SetDoNotAllowPads(False)
            k.SetDoNotAllowFootprints(False)
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.F_Cu)
            k.SetLayerSet(ls)
            ol = k.Outline()
            ol.NewOutline()
            for x, y in ((px - 7.3, py - 25.0), (px + 7.3, py - 25.0), (px + 7.3, py + 25.0), (px - 7.3, py + 25.0)):
                ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
            b.Add(k)
        # zones interdites (pistes, vias, plans) autour des trous
        for (x, y), r in [(h, outline.HOLE_D / 2 + 0.5) for h in HOLES] + \
                         [(h, STANDOFF_KEEP) for h in STANDOFFS]:
            k = pcbnew.ZONE(b)
            k.SetIsRuleArea(True)
            k.SetDoNotAllowTracks(True)
            k.SetDoNotAllowVias(True)
            k.SetDoNotAllowCopperPour(True)
            k.SetDoNotAllowPads(False)
            k.SetDoNotAllowFootprints(False)
            ls = pcbnew.LSET()
            for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
                ls.AddLayer(l)
            k.SetLayerSet(ls)
            ol = k.Outline()
            ol.NewOutline()
            for i in range(24):
                a = 2 * math.pi * i / 24
                ol.Append(pcbnew.FromMM(x + r * math.cos(a)), pcbnew.FromMM(y + r * math.sin(a)))
            b.Add(k)

    def fanout_planes(self):
        plane_vias(self.board)

    def save(self):
        out = os.path.join(KICAD, self.name, f"{self.name}.kicad_pcb")
        self.board.Save(out)
        # remplissage des zones sur la carte relue (carte construite en
        # mémoire : le remplisseur de KiCad 7 y plante)
        b = pcbnew.LoadBoard(out)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(out)
        set_netclasses(os.path.join(KICAD, self.name, f"{self.name}.kicad_pro"))
        outline.fab_setup(out)
        return out


# classes de réseaux d'alimentation routés en pistes (masse et +3V3 : plans)
NETCLASSES = [("Alim5V", 0.5, 0.15, ["+5V", "PICO_VSYS"]), ("Coeur", 0.3, 0.15, ["+1V2"])]


def set_netclasses(pro):
    """Classes et affectations écrites dans le .kicad_pro (le module pcbnew
    ne les enregistre pas) ; l'export Specctra les reprend."""
    import json
    d = json.load(open(pro))
    ns = d.setdefault("net_settings", {})
    names = [n for n, *_ in NETCLASSES]
    classes = [c for c in ns.get("classes", []) if c.get("name") not in names + ["Alim"]]
    base = next((c for c in classes if c.get("name") == "Default"), {})
    pats = []
    for name, w, clr, nets in NETCLASSES:
        c = dict(base)
        c.update({"name": name, "track_width": w, "clearance": clr, "via_diameter": 0.6, "via_drill": 0.3})
        classes.append(c)
        pats += [{"netclass": name, "pattern": n} for n in nets]
    ns["classes"] = classes
    ns["netclass_patterns"] = pats
    json.dump(d, open(pro, "w"), indent=2)


def plane_vias(b, only=None, quiet=False):
    """Via de raccordement aux plans internes pour chaque pastille CMS de
    masse ou de +3V3, posé avant le routage (Freerouting en oubliait).
    Circuits intégrés : via vers l'intérieur, sous le boîtier entre les
    rangées de broches, pour laisser libres les couloirs de sortie des
    signaux ; passifs : dans le prolongement de la pastille. Via et piste
    de raccordement respectent l'isolement de 0,127 mm."""
    via_d, via_drill, clr = 0.6, 0.3, 0.127 + 0.02
    pads = []      # (x0, y0, x1, y1, réseau, pastille)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            pads.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()),
                         pcbnew.ToMM(bb.GetBottom()), p.GetNetname(), p))
    vias = []      # (x, y, réseau)
    tracks = []    # (x1, y1, x2, y2, largeur, réseau)
    for t in b.GetTracks():               # cuivre déjà présent (après routage)
        if t.GetClass() == "PCB_VIA":
            vias.append((pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y), t.GetNetname()))
        else:
            tracks.append((pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y),
                           pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y),
                           pcbnew.ToMM(t.GetWidth()), t.GetNetname()))

    def d_rect(x, y, r):
        return math.hypot(max(r[0] - x, 0, x - r[2]), max(r[1] - y, 0, y - r[3]))

    def d_seg(x, y, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L))
        return math.hypot(x - x1 - t * dx, y - y1 - t * dy)

    def point_ok(x, y, rad, net, pad):
        """Un disque de rayon rad (bord du cuivre) en (x, y) est-il à
        l'écart des autres réseaux ?"""
        for x0, y0, x1, y1, n, p in pads:
            if p is pad or n == net:
                continue
            if d_rect(x, y, (x0, y0, x1, y1)) < rad + clr:
                return False
        for vx, vy, n in vias:
            if n != net and math.hypot(x - vx, y - vy) < rad + via_d / 2 + clr:
                return False
        for x1, y1, x2, y2, w, n in tracks:
            if n != net and d_seg(x, y, x1, y1, x2, y2) < rad + w / 2 + clr:
                return False
        return True

    def via_ok(x, y, net, pad):
        r = via_d / 2 + clr
        in_tab = (abs(x - CX) < outline.TAB_W / 2 - 1 and SHOULDER - 1 < y < EDGE_Y - 10.8)
        if not allowed((x - r, y - r, x + r, y + r)) and not in_tab:
            return False
        for hx, hy in HOLES + STANDOFFS:
            if math.hypot(x - hx, y - hy) < 6.5:
                return False
        for vx, vy, n in vias:            # perçages : écart même entre vias d'un réseau
            if math.hypot(x - vx, y - vy) < via_d + 0.2:
                return False
        # Freerouting refuse un via sur une pastille CMS, même de son
        # réseau (« attach off ») : écart à toutes les pastilles
        for x0, y0, x1, y1, n, p in pads:
            if d_rect(x, y, (x0, y0, x1, y1)) < via_d / 2 + clr:
                return False
        return point_ok(x, y, via_d / 2, net, pad)

    def track_ok(x1, y1, x2, y2, w, net, pad):
        L = math.hypot(x2 - x1, y2 - y1)
        n = max(2, int(L / 0.05))
        return all(point_ok(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n, w / 2, net, pad)
                   for k in range(n + 1))

    n_ok = n_ko = 0
    for fp in b.GetFootprints():
        c = fp.GetPosition()
        cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
        lib = fp.GetFPIDAsString().split(":")[0]
        inward_ok = lib in ("Package_QFP", "Package_SO")     # corps sans pastille dessous
        is_edge = fp.GetReference() == "J1"
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in PLANES or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if only is not None and (fp.GetReference(), p.GetNumber(), p.IsOnLayer(pcbnew.F_Cu)) not in only:
                continue
            layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu     # face de la pastille
            v = p.GetPosition()
            px, py = pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)
            bb = p.GetBoundingBox()
            half = max(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) / 2
            # axe de la pastille (sa grande dimension), orienté vers
            # l'extérieur du composant
            if pcbnew.ToMM(bb.GetHeight()) > pcbnew.ToMM(bb.GetWidth()):
                a0 = math.pi / 2 if py >= cy else -math.pi / 2
            else:
                a0 = 0.0 if px >= cx else math.pi
            if is_edge:
                a0, dirs = -math.pi / 2, (0,)          # contacts : vers l'intérieur de la carte
            elif inward_ok:
                dirs = (math.pi, 0)                    # sous le boîtier d'abord
            else:
                dirs = (0, math.pi / 2, -math.pi / 2)
            w = 0.25 if half < 0.6 else 0.3
            done = False
            dirs = tuple(dirs) + tuple(d for d in (math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2,
                                                   3 * math.pi / 4, -3 * math.pi / 4, math.pi)
                                       if d not in dirs and not is_edge)
            for da in dirs:
                for dist in (half + via_d / 2 + 0.2, half + via_d / 2 + 0.5, half + 1.3, half + 2.0, half + 3.0):
                    a = a0 + da
                    x, y = px + dist * math.cos(a), py + dist * math.sin(a)
                    if not via_ok(x, y, net, p) or not track_ok(px, py, x, y, w, net, p):
                        continue
                    via = pcbnew.PCB_VIA(b)
                    via.SetPosition(mm(x, y))
                    via.SetWidth(pcbnew.FromMM(via_d))
                    via.SetDrill(pcbnew.FromMM(via_drill))
                    via.SetNet(p.GetNet())
                    via.SetLocked(True)
                    b.Add(via)
                    t = pcbnew.PCB_TRACK(b)
                    t.SetStart(v)
                    t.SetEnd(mm(x, y))
                    t.SetWidth(pcbnew.FromMM(w))
                    t.SetLayer(layer)
                    t.SetNet(p.GetNet())
                    t.SetLocked(True)
                    b.Add(t)
                    vias.append((x, y, net))
                    tracks.append((px, py, x, y, w, net))
                    done = True
                    break
                if done:
                    break
            n_ok += done
            n_ko += not done
            if not done and not quiet:
                print(f"  sans via : {fp.GetReference()}.{p.GetNumber()} ({net})")
    if not quiet:
        print(f"  vias vers les plans : {n_ok} posés, {n_ko} sans place")
    return n_ok, n_ko


# FPGA de chaque carte : référence -> nom du gabarit .pcf (fpga_pins.FPGAS)
FPGA_REF = {"prog": {"U10": "prog_p", "U12": "prog_v"}, "cha": {"U12": "cha_c", "U14": "cha_sm"}}
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
        fixed = set(cfg["gbin"]) | set(fpga_pins.CFG_PINS)
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
    L.fanout_planes()
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
