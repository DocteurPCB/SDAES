#!/usr/bin/env python3
"""Contours des cartes PROG et CHA -> hardware/kicad/{prog,cha}/{prog,cha}.kicad_pcb

Cotes reprises des cartes AES de jwestfall69 (neogeo-diag-aes-prog et
neogeo-diag-aes-cha, fabriquées et testées, domaine public) et recoupées sur
la photo de la carte SNK NEO-AEG PROG-EP du wiki neogeodev (étalon : pas des
contacts) :

  * corps 174,0 x 115 mm (PROG) ou 173,0 x 115 mm (CHA), épaisseur 1,6 mm ;
  * languette de contacts centrée, 129,2 x 19 mm ;
  * deux encoches de 12 x 2,5 mm sur le bord opposé à la languette
    (PROG : de 36 à 48 mm de chaque bord ; CHA : de 5,45 à 17,45 mm) ;
  * deux trous de 10 mm à ±45 mm de l'axe, 11,75 mm au-dessus de
    l'épaulement de la languette (plots de la coque).

Le fichier ne contient que le contour, les trous et le connecteur de bord J1
placé ; « Mettre à jour le PCB depuis le schéma » ajoute le reste.
Nécessite le module Python de KiCad (pcbnew).

    python3 hardware/gen/outline.py
"""
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD = os.path.join(HERE, "..", "kicad")

BODY_H, TAB_W, TAB_H, HOLE_DX, HOLE_DY, HOLE_D = 115.0, 129.2, 19.0, 45.0, 11.75, 10.0
NOTCH_W, NOTCH_D = 12.0, 2.5
PAD_FROM_EDGE = 7.1            # centre des contacts -> bord de la languette
BOARDS = {
    # largeur du corps, distance bord du corps -> encoche
    "prog": (174.0, 36.0),
    "cha": (173.0, 5.45),
}
CX, EDGE_Y = 150.0, 180.0      # milieu du bord de la languette (coordonnées KiCad, mm)


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def outline(width, notch):
    """Polygone du contour, sens horaire, depuis le coin bas gauche de la languette."""
    l, r = CX - width / 2, CX + width / 2
    tl, tr = CX - TAB_W / 2, CX + TAB_W / 2
    sh, top = EDGE_Y - TAB_H, EDGE_Y - TAB_H - BODY_H
    n1, n2 = l + notch, r - notch - NOTCH_W
    return [(tl, EDGE_Y), (tl, sh), (l, sh), (l, top),
            (n1, top), (n1, top + NOTCH_D), (n1 + NOTCH_W, top + NOTCH_D), (n1 + NOTCH_W, top),
            (n2, top), (n2, top + NOTCH_D), (n2 + NOTCH_W, top + NOTCH_D), (n2 + NOTCH_W, top),
            (r, top), (r, sh), (tr, sh), (tr, EDGE_Y)]


def build(name, width, notch):
    b = pcbnew.BOARD()
    b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
    pts = outline(width, notch)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(mm(x1, y1))
        s.SetEnd(mm(x2, y2))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        b.Add(s)
    for dx in (-HOLE_DX, HOLE_DX):
        c = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_CIRCLE)
        c.SetCenter(mm(CX + dx, EDGE_Y - TAB_H - HOLE_DY))
        c.SetEnd(mm(CX + dx + HOLE_D / 2, EDGE_Y - TAB_H - HOLE_DY))
        c.SetLayer(pcbnew.Edge_Cuts)
        c.SetWidth(pcbnew.FromMM(0.1))
        b.Add(c)
    fp = pcbnew.FootprintLoad(os.path.join(KICAD, "sdaes.pretty"), "AES_Edge_2x50_P2.54mm")
    fp.SetFPIDAsString("SDAES:AES_Edge_2x50_P2.54mm")
    fp.SetReference("J1")
    fp.SetValue(f"AES_{name.upper()}")
    fp.SetPosition(mm(CX, EDGE_Y - PAD_FROM_EDGE))
    b.Add(fp)
    out = os.path.join(KICAD, name, f"{name}.kicad_pcb")
    b.Save(out)
    print(f"{out} : {width:g} x {BODY_H + TAB_H:g} mm")


def main():
    for name, (width, notch) in BOARDS.items():
        build(name, width, notch)


if __name__ == "__main__":
    main()
