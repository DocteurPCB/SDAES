#!/usr/bin/env python3
"""Termine les liaisons laissées par Freerouting (petit routeur A* sur grille).

    python3 hardware/gen/finish.py prog|cha [--report fichier_drc.rpt]

Lit les « unconnected_items » d'un rapport DRC KiCad (route.py le produit),
puis relie chaque paire d'éléments par une piste de 0,127 mm sur les faces
externes, avec vias (0,6 / 0,3 mm) si besoin. Grille de 0,1 mm, déplacements
à 45°, obstacles = tout le cuivre des autres réseaux gonflé de l'isolement
(0,127 mm), zones interdites autour des trous, bord de carte. Les liaisons
sont faites l'une après l'autre ; une liaison impossible est signalée.
"""
import heapq
import math
import os
import re
import subprocess
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import outline  # noqa: E402

KICAD = os.path.join(HERE, "..", "kicad")
RES = float(os.environ.get("FINISH_RES", "0.1"))      # pas de la grille (mm)
TRACK_W = float(os.environ.get("FINISH_W", "0.127"))  # 0,1 mm admis en dernier recours
CLR = 0.127 + float(os.environ.get("FINISH_MARGIN", "0.03"))   # isolement + marge de discrétisation
VIA_D, VIA_DRILL = 0.6, 0.3
HOLE_CLR = 0.25                # perçage à perçage
VIA_COST = 20                  # coût d'un via, en pas de grille
MARGIN = float(os.environ.get("FINISH_WINDOW", "40"))   # fenêtre de recherche autour des extrémités (mm)
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)


def mm(v):
    return pcbnew.ToMM(v)


def read_unconnected(report):
    """[(net, [(type, x, y, couche), (type, x, y, couche)])] depuis un rapport DRC."""
    out = []
    lines = open(report).read().splitlines()
    for i, l in enumerate(lines):
        if not l.startswith("[unconnected_items]"):
            continue
        items = []
        for k in (i + 2, i + 3):
            m = re.match(r"\s+@\(([-\d.]+) mm, ([-\d.]+) mm\): (\w+).*?\[([^\]]+)\].* on ([A-Za-z0-9.]+)", lines[k])
            if m:
                items.append((m.group(3), float(m.group(1)), float(m.group(2)), m.group(5), m.group(4)))
        if len(items) == 2 and items[0][4] == items[1][4]:
            out.append((items[0][4], items))
    return out


class Grid:
    def __init__(self, b, x0, y0, x1, y1):
        self.b = b
        self.x0, self.y0 = x0, y0
        self.nx = int((x1 - x0) / RES) + 1
        self.ny = int((y1 - y0) / RES) + 1
        xs = x0 + np.arange(self.nx) * RES
        ys = y0 + np.arange(self.ny) * RES
        self.X, self.Y = np.meshgrid(xs, ys)

    def cell(self, x, y):
        return int(round((y - self.y0) / RES)), int(round((x - self.x0) / RES))

    def xy(self, iy, ix):
        return float(self.x0 + int(ix) * RES), float(self.y0 + int(iy) * RES)

    def region(self, x0, y0, x1, y1):
        """Tranche de grille couvrant un rectangle (mm), ou None."""
        i0 = max(0, int((y0 - self.y0) / RES) - 1)
        i1 = min(self.ny, int((y1 - self.y0) / RES) + 2)
        j0 = max(0, int((x0 - self.x0) / RES) - 1)
        j1 = min(self.nx, int((x1 - self.x0) / RES) + 2)
        if i0 >= i1 or j0 >= j1:
            return None
        return slice(i0, i1), slice(j0, j1)

    def mark_rect(self, m, r, infl):
        s = self.region(r[0] - infl, r[1] - infl, r[2] + infl, r[3] + infl)
        if s is None:
            return
        X, Y = self.X[s], self.Y[s]
        d = np.hypot(np.maximum(np.maximum(r[0] - X, 0), X - r[2]), np.maximum(np.maximum(r[1] - Y, 0), Y - r[3]))
        m[s] |= d <= infl + 1e-9

    def mark_seg(self, m, x1, y1, x2, y2, infl):
        s = self.region(min(x1, x2) - infl, min(y1, y2) - infl, max(x1, x2) + infl, max(y1, y2) + infl)
        if s is None:
            return
        X, Y = self.X[s], self.Y[s]
        dx, dy = x2 - x1, y2 - y1
        L = dx * dx + dy * dy
        t = np.zeros_like(X) if L == 0 else np.clip(((X - x1) * dx + (Y - y1) * dy) / L, 0, 1)
        m[s] |= np.hypot(X - x1 - t * dx, Y - y1 - t * dy) <= infl + 1e-9

    def mark_circle(self, m, x, y, infl):
        self.mark_rect(m, (x, y, x, y), infl)


def inside_board(G, name):
    """Masque des cellules dans le contour (corps + languette), hors bord."""
    w = outline.BOARDS[name][0]
    cx, ey = outline.CX, outline.EDGE_Y
    sh = ey - outline.TAB_H
    top = sh - outline.BODY_H
    m = (np.abs(G.X - cx) < w / 2 - 0.5) & (G.Y > top + 3.0) & (G.Y < sh - 0.5)
    m |= (np.abs(G.X - cx) < outline.TAB_W / 2 - 0.5) & (G.Y >= sh - 0.5) & (G.Y < ey - 10.6)
    return m


def build_maps(G, b, net, name):
    """obst[l] : cellules interdites à une piste du réseau net sur la couche l ;
    via_bad : cellules où un via est impossible ; mine[l] : cuivre du réseau."""
    infl_t = TRACK_W / 2 + CLR
    infl_v = VIA_D / 2 + CLR
    obst = {l: np.zeros(G.X.shape, bool) for l in LAYERS}
    via_bad = np.zeros(G.X.shape, bool)
    mine = {l: np.zeros(G.X.shape, bool) for l in LAYERS}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            r = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
            if G.region(*r) is None and G.region(r[0] - 2, r[1] - 2, r[2] + 2, r[3] + 2) is None:
                continue
            same = p.GetNetname() == net and net != ""
            for l in LAYERS:
                if p.IsOnLayer(l):
                    if same:
                        G.mark_rect(mine[l], r, 0.0)
                    else:
                        G.mark_rect(obst[l], r, infl_t)
            if not same or p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                G.mark_rect(via_bad, r, infl_v if not same else VIA_D / 2 + HOLE_CLR)
    for t in b.GetTracks():
        same = t.GetNetname() == net
        if t.GetClass() == "PCB_VIA":
            x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
            r = mm(t.GetWidth()) / 2
            for l in LAYERS:
                if same:
                    G.mark_circle(mine[l], x, y, r)
                else:
                    G.mark_circle(obst[l], x, y, r + infl_t)
            G.mark_circle(via_bad, x, y, r + (infl_v if not same else VIA_D / 2 + HOLE_CLR))
        else:
            l = t.GetLayer()
            if l not in LAYERS:
                continue
            x1, y1, x2, y2 = mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)
            w = mm(t.GetWidth()) / 2
            if same:
                G.mark_seg(mine[l], x1, y1, x2, y2, w)
            else:
                G.mark_seg(obst[l], x1, y1, x2, y2, w + infl_t)
                G.mark_seg(via_bad, x1, y1, x2, y2, w + infl_v)
    # zones interdites (trous de la coque, entretoises)
    for z in b.Zones():
        if not z.GetIsRuleArea():
            continue
        bb = z.GetBoundingBox()
        cx, cy = mm(bb.GetCenter().x), mm(bb.GetCenter().y)
        rad = mm(bb.GetWidth()) / 2
        for l in LAYERS:
            G.mark_circle(obst[l], cx, cy, rad + infl_t)
        G.mark_circle(via_bad, cx, cy, rad + infl_v)
    ok = inside_board(G, name)
    for l in LAYERS:
        obst[l] |= ~ok
        obst[l] &= ~mine[l]          # son propre cuivre est toujours franchissable
    via_bad |= ~ok
    return obst, via_bad, mine


def item_cells(G, b, it, net):
    """Cellules (couche, iy, ix) d'un élément du rapport DRC."""
    kind, x, y, layer = it[0], it[1], it[2], it[3]
    lay = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    out = set()
    m = np.zeros(G.X.shape, bool)
    if kind == "Pad":
        for fp in b.GetFootprints():
            for p in fp.Pads():
                v = p.GetPosition()
                if p.GetNetname() == net and abs(mm(v.x) - x) < 0.01 and abs(mm(v.y) - y) < 0.01:
                    bb = p.GetBoundingBox()
                    G.mark_rect(m, (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())), 0.0)
                    ls = [l for l in LAYERS if p.IsOnLayer(l)]
                    for iy, ix in zip(*np.nonzero(m)):
                        for l in ls:
                            out.add((l, iy, ix))
                    return out, (x, y)
    best = None
    for t in b.GetTracks():
        if t.GetNetname() != net:
            continue
        if t.GetClass() == "PCB_VIA":
            vx, vy = mm(t.GetPosition().x), mm(t.GetPosition().y)
            d = math.hypot(vx - x, vy - y)
            if kind == "Via" and (best is None or d < best[0]):
                best = (d, t)
        elif kind == "Track":
            x1, y1, x2, y2 = mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)
            d = min(math.hypot(x1 - x, y1 - y), math.hypot(x2 - x, y2 - y))
            if t.GetLayer() == lay.get(layer) and (best is None or d < best[0]):
                best = (d, t)
    if best is None:
        return out, (x, y)
    t = best[1]
    if t.GetClass() == "PCB_VIA":
        vx, vy = mm(t.GetPosition().x), mm(t.GetPosition().y)
        G.mark_circle(m, vx, vy, max(mm(t.GetWidth()) / 2, RES * 0.75))
        for iy, ix in zip(*np.nonzero(m)):
            for l in LAYERS:
                out.add((l, iy, ix))
        return out, (vx, vy)
    x1, y1, x2, y2 = mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)
    G.mark_seg(m, x1, y1, x2, y2, max(mm(t.GetWidth()) / 2, RES * 0.75))
    for iy, ix in zip(*np.nonzero(m)):
        out.add((t.GetLayer(), iy, ix))
    return out, (x1, y1)


def astar(G, obst, via_bad, src, dst):
    goal_pt = np.mean([[iy, ix] for _, iy, ix in dst], axis=0)
    dsts = set(dst)
    moves = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
             (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]

    def h(iy, ix):
        return math.hypot(iy - goal_pt[0], ix - goal_pt[1]) * 0.9

    openq, came, g = [], {}, {}
    for s in src:
        g[s] = 0.0
        heapq.heappush(openq, (h(s[1], s[2]), 0.0, s))
    seen = set()
    while openq:
        f, gc, cur = heapq.heappop(openq)
        if cur in seen:
            continue
        seen.add(cur)
        if cur in dsts:
            path = [cur]
            while path[-1] in came:
                path.append(came[path[-1]])
            return path[::-1]
        l, iy, ix = cur
        nb = []
        for dy, dx, c in moves:
            ny, nx = iy + dy, ix + dx
            if 0 <= ny < G.ny and 0 <= nx < G.nx and not obst[l][ny, nx]:
                if dy and dx and (obst[l][iy, nx] or obst[l][ny, ix]):
                    continue                    # pas de coin coupé
                nb.append(((l, ny, nx), c))
        if not via_bad[iy, ix]:
            o = LAYERS[1] if l == LAYERS[0] else LAYERS[0]
            if not obst[o][iy, ix]:
                nb.append(((o, iy, ix), VIA_COST))
        for n, c in nb:
            ng = gc + c
            if ng < g.get(n, 1e18):
                g[n] = ng
                came[n] = cur
                heapq.heappush(openq, (ng + h(n[1], n[2]), ng, n))
    return None


def emit(b, G, path, net, start_xy, end_xy):
    """Pistes et vias le long du chemin (points alignés fusionnés)."""
    ni = b.FindNet(net)
    pts = [(l, G.xy(iy, ix)) for l, iy, ix in path]
    segs, vias = [], []
    run = [pts[0]]
    for p in pts[1:]:
        if p[0] != run[-1][0]:
            vias.append(p[1])
            segs.append(run)
            run = [p]
        else:
            run.append(p)
    segs.append(run)
    n_t = 0
    for run in segs:
        layer = run[0][0]
        xy = [q[1] for q in run]
        # fusion des points alignés
        simp = [xy[0]]
        for i in range(1, len(xy) - 1):
            ax, ay = simp[-1]
            bx, by = xy[i]
            cx, cy = xy[i + 1]
            if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-6:
                simp.append(xy[i])
        simp.append(xy[-1])
        for (x1, y1), (x2, y2) in zip(simp, simp[1:]):
            if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
            t.SetWidth(pcbnew.FromMM(TRACK_W))
            t.SetLayer(layer)
            t.SetNet(ni)
            b.Add(t)
            n_t += 1
    for x, y in vias:
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(VIA_D))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(ni)
        b.Add(v)
    return n_t, len(vias)


def pad_count(b):
    n = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname():
                n[p.GetNetname()] = n.get(p.GetNetname(), 0) + 1
    return n


def blockers(b, items, net, counts):
    """Réseaux à deux pastilles dont les pistes passent à moins de 1 mm des
    extrémités d'une liaison bloquée (candidats à l'arrachage)."""
    out = set()
    for it in items:
        x, y = it[1], it[2]
        for t in b.GetTracks():
            n = t.GetNetname()
            if n == net or t.IsLocked() or t.GetClass() == "PCB_VIA" or counts.get(n, 0) != 2:
                continue
            x1, y1, x2, y2 = mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)
            dx, dy = x2 - x1, y2 - y1
            L = dx * dx + dy * dy
            u = 0 if L == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L))
            if math.hypot(x - x1 - u * dx, y - y1 - u * dy) < 1.6:
                out.add(n)
    return out


def route_pairs(b, name, todo, order):
    """Relie les paires dans l'ordre de priorité ; renvoie les échecs."""
    todo = sorted(todo, key=lambda t: (order.index(t[0]) if t[0] in order else len(order)))
    fails = []
    for net, items in todo:
        (a, bpt) = items
        x0 = min(a[1], bpt[1]) - MARGIN
        x1 = max(a[1], bpt[1]) + MARGIN
        y0 = min(a[2], bpt[2]) - MARGIN
        y1 = max(a[2], bpt[2]) + MARGIN
        G = Grid(b, x0, y0, x1, y1)
        obst, via_bad, _ = build_maps(G, b, net, name)
        src, sxy = item_cells(G, b, a, net)
        dst, dxy = item_cells(G, b, bpt, net)
        path = astar(G, obst, via_bad, sorted(src), dst) if src and dst else None
        if path is None:
            print(f"    {net} : bloqué")
            fails.append((net, items))
            continue
        n_t, n_v = emit(b, G, path, net, sxy, dxy)
        print(f"    {net} : relié ({n_t} segments, {n_v} vias)")
    return fails


def one_round(name, report, state_file, rip_ok=True):
    """Un tour (processus à part : après Save, la carte chargée devient
    inutilisable dans le même processus)."""
    import json
    import route
    pcb = os.path.join(KICAD, name, f"{name}.kicad_pcb")
    order = json.load(open(state_file)) if os.path.exists(state_file) else []
    todo = read_unconnected(report)
    print(f"  {len(todo)} liaisons")
    if not todo:
        return
    b = pcbnew.LoadBoard(pcb)
    fails = route_pairs(b, name, todo, order)
    if fails and rip_ok:
        counts = pad_count(b)
        rip = set()
        for net, items in fails:
            if net not in order:
                order.insert(0, net)
            rip |= blockers(b, items, net, counts) - set(order)
        for t in list(b.GetTracks()):
            if t.GetNetname() in rip and not t.IsLocked():
                b.Remove(t)
        if rip:
            print(f"    arrachés : {' '.join(sorted(rip))}")
    json.dump(order, open(state_file, "w"))
    b.Save(pcb)
    subprocess.run([sys.executable, "-c",
                    "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(sys.argv[1])", pcb],
                   check=True, capture_output=True)
    route.drc(pcb, report)


def finish(name, report, rounds=6):
    """Premier tour sans arrachage, puis tours avec arrachage ; on garde la
    meilleure carte (le moins de liaisons restantes), jamais une pire."""
    import shutil
    pcb = os.path.join(KICAD, name, f"{name}.kicad_pcb")
    state = report + ".ordre.json"
    best_pcb, best_rpt = pcb + ".meilleure", report + ".meilleure"
    if os.path.exists(state):
        os.remove(state)
    best = len(read_unconnected(report))
    shutil.copy(pcb, best_pcb)
    shutil.copy(report, best_rpt)
    for k in range(rounds):
        if not read_unconnected(report):
            break
        print(f"  tour {k + 1}{' (sans arrachage)' if k == 0 else ''}")
        cmd = [sys.executable, os.path.abspath(__file__), name, "--report", report, "--one-round", state]
        if k == 0:
            cmd.append("--no-rip")
        subprocess.run(cmd, check=True)
        n = len(read_unconnected(report))
        if n < best:
            best = n
            shutil.copy(pcb, best_pcb)
            shutil.copy(report, best_rpt)
    shutil.copy(best_pcb, pcb)
    shutil.copy(best_rpt, report)
    os.remove(best_pcb)
    os.remove(best_rpt)
    print(f"{pcb} : {best} liaison(s) restante(s)")
    for net, items in read_unconnected(report):
        print(f"    reste : {net} ({items[0][0]} {items[0][1]:.2f},{items[0][2]:.2f} -> "
              f"{items[1][0]} {items[1][1]:.2f},{items[1][2]:.2f})")


def main():
    args = sys.argv[1:]
    name = args[0]
    work = os.environ.get("ROUTE_DIR", os.path.join(KICAD, name))
    report = args[args.index("--report") + 1] if "--report" in args else os.path.join(work, f"{name}-drc.rpt")
    if "--one-round" in args:
        one_round(name, report, args[args.index("--one-round") + 1], rip_ok="--no-rip" not in args)
    else:
        finish(name, report)


if __name__ == "__main__":
    main()
