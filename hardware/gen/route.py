#!/usr/bin/env python3
"""Routage automatique des cartes PROG et CHA avec Freerouting.

    python3 hardware/gen/route.py prog [--passes 60]   # DSN -> Freerouting -> SES -> .kicad_pcb
    python3 hardware/gen/route.py prog --import x.ses  # import d'une session seulement

Étapes : la carte placée (pcb.py) est exportée au format Specctra avec ses
plans internes (masse, +3V3), Freerouting route les pistes et relie les
broches des plans par des vias, la
session est relue ici (le module Python de KiCad 7 ne sait pas l'importer
hors de l'interface) puis les zones sont remplies et la DRC de kicad-cli
est lancée.

Freerouting (>= 2.4, Java 25) : variables FREEROUTING_CP (classpath, par
défaut ./freerouting/lib/*) et JAVA (par défaut java).
"""
import os
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kicad import parse, unq   # noqa: E402

KICAD = os.path.join(HERE, "..", "kicad")


def find(x, key):
    return [e for e in x if isinstance(e, list) and e and e[0] == key]


def export_dsn(pcb, dsn, keep=False):
    """keep : garde les pistes déjà routées (reprise d'un routage)."""
    b = pcbnew.LoadBoard(pcb)
    for t in list(b.GetTracks()):
        if not t.IsLocked() and not keep:
            b.Remove(t)
    if not pcbnew.ExportSpecctraDSN(b, dsn):
        raise SystemExit("export DSN impossible")
    # couches internes = plans d'alimentation : Freerouting n'y route rien
    text = open(dsn).read()
    for layer in ("In1.Cu", "In2.Cu"):
        text = text.replace(f"(layer {layer}\n      (type signal)", f"(layer {layer}\n      (type power)")
    open(dsn, "w").write(text)


def run_freerouting(dsn, ses, passes):
    cp = os.environ.get("FREEROUTING_CP", os.path.join(os.getcwd(), "freerouting", "lib", "*"))
    java = os.environ.get("JAVA", "java")
    # sortie des broches et vias vers les plans : posés par pcb.py ;
    # optimisation finale : trop longue pour ce qu'elle apporte
    cmd = [java, "-cp", cp, "app.freerouting.Freerouting", "--gui.enabled=false",
           "--router.fanout.enabled=false", "--router.optimizer.enabled=false",
           "-de", dsn, "-do", ses, "-mp", str(passes)]
    subprocess.run(cmd, check=True)


def import_ses(pcb, ses):
    """Pistes et vias de la session dans la carte (les anciennes sont retirées)."""
    s = parse(open(ses).read())
    while not find(s, "routes"):              # parse() peut envelopper la session
        s = next(e for e in s if isinstance(e, list) and find(e, "routes") or
                 isinstance(e, list) and e and e[0] == "session")
    routes = find(s, "routes")[0]
    res = find(routes, "resolution")[0]
    unit = {"um": 1e-3, "mm": 1.0, "mil": 0.0254, "inch": 25.4}[res[1]]
    k = unit / float(res[2])                  # unité de la session -> mm
    b = pcbnew.LoadBoard(pcb)
    for t in list(b.GetTracks()):
        if not t.IsLocked():                  # vias vers les plans (pcb.py) : gardés
            b.Remove(t)
    vias = {}
    for ps in find(find(routes, "library_out")[0], "padstack") if find(routes, "library_out") else []:
        name = unq(ps[1])
        shp = find(ps, "shape")[0][1]
        vias[name] = float(shp[2]) * k
    layers = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu}
    ds = b.GetDesignSettings()
    n_tr = n_via = 0

    def pt(x, y):
        return pcbnew.VECTOR2I(pcbnew.FromMM(float(x) * k), pcbnew.FromMM(-float(y) * k))

    for net in find(find(routes, "network_out")[0], "net"):
        ni = b.FindNet(unq(net[1]))
        for w in find(net, "wire"):
            path = find(w, "path")[0]
            layer, width, xy = unq(path[1]), float(path[2]) * k, path[3:]
            for i in range(0, len(xy) - 2, 2):
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pt(xy[i], xy[i + 1]))
                t.SetEnd(pt(xy[i + 2], xy[i + 3]))
                t.SetWidth(pcbnew.FromMM(width))
                t.SetLayer(layers[layer])
                t.SetNet(ni)
                b.Add(t)
                n_tr += 1
        for v in find(net, "via"):
            name = unq(v[1])
            d = vias.get(name)
            if d is None:                      # "Via[0-1]_600:300_um"
                d = float(name.split("_")[1].split(":")[0]) / 1000
            drill = float(name.split(":")[1].split("_")[0]) / 1000
            via = pcbnew.PCB_VIA(b)
            via.SetPosition(pt(v[2], v[3]))
            via.SetWidth(pcbnew.FromMM(d))
            via.SetDrill(pcbnew.FromMM(drill))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)      # vias traversants
            via.SetNet(ni)
            b.Add(via)
            n_via += 1
    patch_planes(b, os.path.basename(pcb).split(".")[0])
    b.Save(pcb)
    # remplissage sur la carte relue, dans un processus à part (un second
    # LoadBoard dans le même processus renvoie un objet inutilisable)
    subprocess.run([sys.executable, "-c",
                    "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(sys.argv[1])", pcb],
                   check=True, capture_output=True)
    print(f"{pcb} : {n_tr} segments, {n_via} vias")


def patch_planes(b, name):
    """Après routage : via vers le plan pour chaque pastille CMS de masse ou
    de +3V3 restée sans connexion, en évitant les pistes routées."""
    import pcb as pcbgen
    pcbgen.outline.BOARDS_W = pcbgen.outline.BOARDS[name][0]
    b.BuildConnectivity()
    conn = b.GetConnectivity()
    todo = set()
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() in pcbgen.PLANES and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                if len(conn.GetConnectedTracks(p)) == 0:
                    todo.add((fp.GetReference(), p.GetNumber(), p.IsOnLayer(pcbnew.F_Cu)))
    if todo:
        ok, ko = pcbgen.plane_vias(b, only=todo, quiet=True)
        print(f"  raccordements aux plans après routage : {ok} ajoutés, {ko} impossibles")
        if ko:
            b.BuildConnectivity()
            conn = b.GetConnectivity()
            for fp in b.GetFootprints():
                for p in fp.Pads():
                    if (fp.GetReference(), p.GetNumber(), p.IsOnLayer(pcbnew.F_Cu)) in todo and \
                            len(conn.GetConnectedTracks(p)) == 0:
                        print(f"    à relier à la main : {fp.GetReference()}.{p.GetNumber()} ({p.GetNetname()})")


def drc(pcb, report):
    """DRC de KiCad (module pcbnew : kicad-cli 7 n'a pas de commande drc)."""
    subprocess.run([sys.executable, "-c",
                    "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                    "pcbnew.WriteDRCReport(b, sys.argv[2], pcbnew.EDA_UNITS_MILLIMETRES, True)", pcb, report],
                   check=True, capture_output=True)
    text = open(report).read()
    for line in text.splitlines():
        if line.startswith("**") and ("Found" in line or "unconnected" in line.lower()):
            print("  " + line.strip("* "))
    return text


def main():
    args = sys.argv[1:]
    name = args[0]
    pcb = os.path.join(KICAD, name, f"{name}.kicad_pcb")
    work = os.environ.get("ROUTE_DIR", os.path.join(KICAD, name))
    dsn, ses = os.path.join(work, f"{name}.dsn"), os.path.join(work, f"{name}.ses")
    if "--patch" in args:                     # carte déjà routée : raccordements seuls
        b = pcbnew.LoadBoard(pcb)
        patch_planes(b, name)
        b.Save(pcb)
        subprocess.run([sys.executable, "-c",
                        "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
                        "pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(sys.argv[1])", pcb],
                       check=True, capture_output=True)
        drc(pcb, os.path.join(work, f"{name}-drc.rpt"))
        return
    if "--import" in args:
        ses = args[args.index("--import") + 1]
    else:
        passes = int(args[args.index("--passes") + 1]) if "--passes" in args else 60
        # --continue : reprise sur la carte déjà routée (liaisons restantes)
        export_dsn(pcb, dsn, keep="--continue" in args)
        run_freerouting(dsn, ses, passes)
    import_ses(pcb, ses)
    drc(pcb, os.path.join(work, f"{name}-drc.rpt"))


if __name__ == "__main__":
    main()
