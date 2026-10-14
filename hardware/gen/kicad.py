"""Écriture de schémas KiCad 7 à partir d'une description Python du circuit.

Principe : chaque composant est posé sur une grille ; à l'extrémité de chaque
broche on pose une étiquette globale portant le nom du signal (ou un symbole
« non connecté »). La connectivité vient donc uniquement des noms, ce qui
rend le schéma vérifiable : `kicad-cli sch export netlist` doit redonner
exactement la netlist décrite (voir check_netlist).
"""
import os
import re
import uuid as _uuid

KICAD_SYM = "/usr/share/kicad/symbols"
GRID = 2.54


def uid():
    return str(_uuid.uuid4())


# ---------------------------------------------------------------------------
# S-expressions

def parse(text):
    tokens = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text)
    stack = [[]]
    for t in tokens:
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t)
    return stack[0]


def dump(x, ind=0):
    if not isinstance(x, list):
        return x
    if all(not isinstance(e, list) for e in x):
        return "(" + " ".join(x) + ")"
    # l'ordre des éléments est conservé (KiCad y est sensible, ex. pin_names)
    out = "("
    for i, e in enumerate(x):
        if isinstance(e, list):
            out += "\n" + "  " * (ind + 1) + dump(e, ind + 1)
        else:
            out += ("" if i == 0 else " ") + e
    return out + ")"


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def unq(s):
    return s[1:-1].replace('\\"', '"').replace("\\\\", "\\") if s.startswith('"') else s


def find(x, key):
    return [e for e in x if isinstance(e, list) and e and e[0] == key]


# ---------------------------------------------------------------------------
# symboles

class Pin:
    def __init__(self, number, name, unit, x, y, angle, etype):
        self.number, self.name, self.unit = number, name, unit
        self.x, self.y, self.angle, self.etype = x, y, angle, etype


class Symbol:
    """Symbole de bibliothèque : définition S-expr (pour lib_symbols) et broches."""

    def __init__(self, lib_id, sexpr, pins, units):
        self.lib_id, self.sexpr, self.pins, self.units = lib_id, sexpr, pins, units

    def pins_of_unit(self, unit):
        return [p for p in self.pins if p.unit in (0, unit)]

    def pin(self, number):
        r = [p for p in self.pins if p.number == str(number)]
        if not r:
            raise KeyError(f"{self.lib_id} : pas de broche {number}")
        return r[0]


_LIBS = {}


def _lib(name):
    if name not in _LIBS:
        with open(os.path.join(KICAD_SYM, name + ".kicad_sym")) as f:
            _LIBS[name] = parse(f.read())[0]
    return _LIBS[name]


def _pins_from(sym):
    pins = []
    base = unq(sym[1])
    for sub in find(sym, "symbol"):
        m = re.match(r"(.*)_(\d+)_(\d+)$", unq(sub[1]))
        unit = int(m.group(2))
        for p in find(sub, "pin"):
            at = find(p, "at")[0]
            name = unq(find(p, "name")[0][1])
            num = unq(find(p, "number")[0][1])
            pins.append(Pin(num, name, unit, float(at[1]), float(at[2]),
                            int(float(at[3])) if len(at) > 3 else 0, p[1]))
    return pins


def _unhide_pins(x):
    """Rend visibles les broches cachées (sinon KiCad les relie implicitement
    à un réseau global portant leur nom, ex. VCC)."""
    if isinstance(x, list):
        if x and x[0] == "pin":
            while "hide" in x:
                x.remove("hide")
        for e in x:
            _unhide_pins(e)


def kicad_symbol(lib, name):
    """Symbole de la bibliothèque officielle KiCad (les symboles dérivés
    « extends » sont aplatis)."""
    libx = _lib(lib)
    syms = {unq(s[1]): s for s in find(libx, "symbol")}
    sym = syms[name]
    ext = find(sym, "extends")
    if ext:
        parent = syms[unq(ext[0][1])]
        body = [e for e in parent if not (isinstance(e, list) and e[0] == "property")]
        props = find(sym, "property")
        pname = unq(parent[1])
        subs = []
        for e in body[2:]:
            if isinstance(e, list) and e[0] == "symbol":
                e = [e[0], q(unq(e[1]).replace(pname, name, 1))] + e[2:]
            subs.append(e)
        sym = ["symbol", q(name)] + props + subs
    sym = [e for e in sym]           # copie superficielle
    import copy
    sym = copy.deepcopy(sym)
    _unhide_pins(sym)
    pins = _pins_from(sym)
    units = sorted({p.unit for p in pins if p.unit > 0}) or [1]
    sym[1] = q(f"{lib}:{name}")
    return Symbol(f"{lib}:{name}", sym, pins, units)


def box_symbol(lib_id, left, right, ref="U", width=20.32, top=None, bottom=None):
    """Symbole rectangulaire. left/right : listes de (numéro, nom, type) ou None
    (espace), de haut en bas. Type KiCad : input, output, bidirectional,
    power_in, passive, no_connect, tri_state, open_collector."""
    top = top or []
    bottom = bottom or []
    n = max(len(left), len(right), 1)
    h = (n + 1) * GRID
    y0 = (n // 2) * GRID                      # y du premier rang (lib : y vers le haut)
    pins, defs = [], []
    name = lib_id.split(":")[1]

    def add(num, nm, etype, x, y, angle):
        pins.append(Pin(str(num), nm, 1, x, y, angle, etype))
        defs.append(["pin", etype, "line", ["at", f"{x:g}", f"{y:g}", str(angle)], ["length", "2.54"],
                     ["name", q(nm), ["effects", ["font", ["size", "1.27", "1.27"]]]],
                     ["number", q(num), ["effects", ["font", ["size", "1.27", "1.27"]]]]])

    hw = width / 2
    for i, e in enumerate(left):
        if e:
            add(e[0], e[1], e[2], -hw - 2.54, y0 - i * GRID, 0)
    for i, e in enumerate(right):
        if e:
            add(e[0], e[1], e[2], hw + 2.54, y0 - i * GRID, 180)
    ytop, ybot = y0 + GRID, y0 - n * GRID
    for i, e in enumerate(top):
        if e:
            add(e[0], e[1], e[2], -hw + GRID * (i + 1), ytop + 2.54, 270)
    for i, e in enumerate(bottom):
        if e:
            add(e[0], e[1], e[2], -hw + GRID * (i + 1), ybot - 2.54, 90)
    font = ["effects", ["font", ["size", "1.27", "1.27"]]]
    sym = ["symbol", q(lib_id), ["pin_names", ["offset", "1.016"]], ["in_bom", "yes"], ["on_board", "yes"],
           ["property", q("Reference"), q(ref), ["at", "0", f"{ytop + 1.27:g}", "0"], font],
           ["property", q("Value"), q(name), ["at", "0", f"{ybot - 1.27:g}", "0"], font],
           ["property", q("Footprint"), q(""), ["at", "0", "0", "0"], ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]],
           ["property", q("Datasheet"), q(""), ["at", "0", "0", "0"], ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]],
           ["symbol", q(f"{name}_0_1"),
            ["rectangle", ["start", f"{-hw:g}", f"{ytop:g}"], ["end", f"{hw:g}", f"{ybot:g}"],
             ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]],
           ["symbol", q(f"{name}_1_1")] + defs]
    return Symbol(lib_id, sym, pins, [1])


# ---------------------------------------------------------------------------
# circuit

class Part:
    def __init__(self, ref, sym, value, footprint, nets, datasheet="", dnp=False):
        """nets : {numéro de broche : réseau} ; broche absente = non connectée."""
        self.ref, self.sym, self.value, self.footprint = ref, sym, value, footprint
        self.nets = {str(k): v for k, v in nets.items()}
        self.datasheet, self.dnp = datasheet, dnp
        for k in list(self.nets):
            p = sym.pin(k)                   # vérifie que la broche existe
            # broches empilées (même unité, même position) : KiCad les relie
            for o in sym.pins:
                if o.number != p.number and o.unit == p.unit and (o.x, o.y) == (p.x, p.y):
                    if self.nets.get(o.number, self.nets[k]) != self.nets[k]:
                        raise ValueError(f"{ref} : broches empilées {k} et {o.number} sur deux réseaux")
                    self.nets[o.number] = self.nets[k]


class Sheet:
    def __init__(self, name, filename):
        self.name, self.filename, self.parts = name, filename, []
        self.uuid = uid()

    def add(self, part):
        self.parts.append(part)
        return part


class Board:
    def __init__(self, name, title):
        self.name, self.title, self.sheets = name, title, []
        self.root_uuid = uid()

    def sheet(self, name, filename):
        s = Sheet(name, filename)
        self.sheets.append(s)
        return s

    def parts(self):
        return [p for s in self.sheets for p in s.parts]

    def netlist(self):
        """{réseau : {(ref, broche)}} décrit."""
        nets = {}
        for p in self.parts():
            for pin, n in p.nets.items():
                nets.setdefault(n, set()).add((p.ref, pin))
        return nets


# ---------------------------------------------------------------------------
# écriture

FONT = ["effects", ["font", ["size", "1.27", "1.27"]]]


def _symbol_extent(sym, unit):
    ps = sym.pins_of_unit(unit)
    if not ps:
        return (-10, -10, 10, 10)
    xs = [p.x for p in ps]
    ys = [-p.y for p in ps]
    return (min(xs) - 25, min(ys) - 8, max(xs) + 25, max(ys) + 8)


def _snap(v):
    return round(v / GRID) * GRID


def write_board(board, outdir, project):
    os.makedirs(outdir, exist_ok=True)
    root = os.path.join(outdir, project + ".kicad_sch")
    pages = []
    for i, sh in enumerate(board.sheets):
        _write_sheet(board, sh, os.path.join(outdir, sh.filename), project, i + 2)
        pages.append(sh)
    # feuille racine : un symbole de feuille par bloc
    items = []
    for i, sh in enumerate(pages):
        x, y = 25.4 + (i % 4) * 63.5, 30.48 + (i // 4) * 38.1
        items.append(["sheet", ["at", f"{x:g}", f"{y:g}"], ["size", "50.8", "25.4"], ["fields_autoplaced"],
                      ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0000"]],
                      ["uuid", sh.uuid],
                      ["property", q("Sheetname"), q(sh.name), ["at", f"{x:g}", f"{y - 0.7:g}", "0"],
                       ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
                      ["property", q("Sheetfile"), q(sh.filename), ["at", f"{x:g}", f"{y + 26:g}", "0"],
                       ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"], "hide"]],
                      ["instances", ["project", q(project), ["path", q("/" + board.root_uuid), ["page", q(str(i + 2))]]]]])
    doc = ["kicad_sch", ["version", "20230121"], ["generator", "eeschema"], ["uuid", board.root_uuid],
           ["paper", "A4"],
           ["title_block", ["title", q(board.title)], ["comment", "1", q("Généré par hardware/gen (ne pas modifier à la main)")]],
           ["lib_symbols"]] + items + [["sheet_instances", ["path", q("/"), ["page", q("1")]]]]
    with open(root, "w") as f:
        f.write(dump(doc) + "\n")
    with open(os.path.join(outdir, project + ".kicad_pro"), "w") as f:
        f.write('{\n  "meta": {"filename": "%s.kicad_pro", "version": 1},\n'
                '  "sheets": [["%s", ""]]\n}\n' % (project, board.root_uuid))
    return root


def _write_sheet(board, sh, path, project, page):
    syms = {}
    items = []
    x, y, rowh = 30.48, 30.48, 0
    maxw = 760
    for p in sh.parts:
        syms[p.sym.lib_id] = p.sym
        for unit in p.sym.units:
            x0, y0, x1, y1 = _symbol_extent(p.sym, unit)
            w, h = x1 - x0, y1 - y0
            if x + w > maxw:
                x, y, rowh = 30.48, y + rowh + 10, 0
            sx, sy = _snap(x - x0), _snap(y - y0)
            x += w + 5
            rowh = max(rowh, h)
            u = uid()
            pins = p.sym.pins_of_unit(unit)
            ent = ["symbol", ["lib_id", q(p.sym.lib_id)], ["at", f"{sx:g}", f"{sy:g}", "0"], ["unit", str(unit)],
                   ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "yes" if p.dnp else "no"], ["uuid", u],
                   ["property", q("Reference"), q(p.ref), ["at", f"{sx:g}", f"{sy + y0 - 2:g}", "0"], FONT],
                   ["property", q("Value"), q(p.value), ["at", f"{sx:g}", f"{sy + y1 + 2:g}", "0"], FONT],
                   ["property", q("Footprint"), q(p.footprint), ["at", f"{sx:g}", f"{sy:g}", "0"],
                    ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]],
                   ["property", q("Datasheet"), q(p.datasheet or "~"), ["at", f"{sx:g}", f"{sy:g}", "0"],
                    ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]]]
            seen = set()
            for pin in pins:
                if pin.number in seen:
                    continue
                seen.add(pin.number)
                ent.append(["pin", q(pin.number), ["uuid", uid()]])
            ent.append(["instances", ["project", q(project),
                        ["path", q(f"/{board.root_uuid}/{sh.uuid}"), ["reference", q(p.ref)], ["unit", str(unit)]]]])
            items.append(ent)
            for pin in pins:
                px, py = sx + pin.x, sy - pin.y
                net = p.nets.get(pin.number)
                if net is None:
                    items.append(["no_connect", ["at", f"{px:g}", f"{py:g}"], ["uuid", uid()]])
                    continue
                # l'étiquette part vers l'extérieur du composant
                ang = {0: 180, 180: 0, 90: 270, 270: 90}[pin.angle % 360]
                just = "right" if ang in (180, 270) else "left"
                items.append(["global_label", q(net), ["shape", "passive"], ["at", f"{px:g}", f"{py:g}", str(ang)],
                              ["fields_autoplaced"],
                              ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]],
                              ["uuid", uid()],
                              ["property", q("Intersheetrefs"), q("${INTERSHEET_REFS}"),
                               ["at", f"{px:g}", f"{py:g}", "0"],
                               ["effects", ["font", ["size", "1.27", "1.27"]], "hide"]]])
    paper = "A0" if y > 500 else ("A1" if y > 300 or maxw > 420 else "A2")
    doc = ["kicad_sch", ["version", "20230121"], ["generator", "eeschema"], ["uuid", uid()], ["paper", paper],
           ["title_block", ["title", q(f"{board.title} - {sh.name}")]],
           ["lib_symbols"] + [s.sexpr for s in syms.values()]] + items + \
          [["sheet_instances", ["path", q("/"), ["page", q(str(page))]]]]
    with open(path, "w") as f:
        f.write(dump(doc) + "\n")


# ---------------------------------------------------------------------------
# vérification

def read_netlist(path):
    """Netlist KiCad (format kicadsexpr) -> {réseau : {(ref, broche)}}."""
    x = parse(open(path).read())[0]
    nets = {}
    for n in find(find(x, "nets")[0], "net"):
        name = unq(find(n, "name")[0][1]).lstrip("/")
        nodes = {(unq(find(nd, "ref")[0][1]), unq(find(nd, "pin")[0][1])) for nd in find(n, "node")}
        nets[name] = nodes
    return nets


def check_netlist(board, path):
    """Compare la netlist exportée par KiCad à la description ; renvoie la
    liste des différences (vide = identique)."""
    want = board.netlist()
    got = {k: v for k, v in read_netlist(path).items() if not k.startswith("unconnected-")}
    errs = []
    for n, nodes in want.items():
        if got.get(n) != nodes:
            errs.append(f"{n} : attendu {sorted(nodes)}, KiCad {sorted(got.get(n, []))}")
    for n in got:
        if n not in want and not n.startswith("Net-("):
            errs.append(f"réseau inattendu {n} : {sorted(got[n])}")
        elif n.startswith("Net-("):
            errs.append(f"réseau sans nom {n} : {sorted(got[n])}")
    return errs
