#!/usr/bin/env python3
"""
neotool.py - outils SDAES (format .neo, images du menu, fichiers d'init BRAM)

Commandes :
  info      FICHIER.neo                     affiche l'en-tête et le plan mémoire
  build     -o JEU.neo --p ... --c ...      assemble un .neo depuis des ROM séparées
  font      POLICE.psf[.gz] -o menu_s.bin   génère la ROM S du menu (police 8x8)
  security  MENU.bin JEU.neo -o MENU.bin    recopie le code de sécurité d'un jeu
  bramhex   FICHIER.bin -o X.hex --size N   fichier $readmemh 8 bits
  bramhex16 MENU.bin --hi H.hex --lo L.hex  sépare un binaire 68000 en octets pairs/impairs
  mapper    FICHIER.map|MAPPERS.TXT [--game NOM] [--ngh N]
                                            vérifie une description de protection
                                            et affiche les registres du FPGA P
  sma-from-mame SOURCE.cpp -o MAPPERS.TXT  extrait les tables SMA du source MAME

Conventions de stockage (identiques au firmware et au FPGA) :
  P  : mots de 16 bits petit-boutistes (ordre des fichiers .p1 de MAME)
  S  : octets dans l'ordre de la ROM
  M  : octets dans l'ordre de la ROM
  V1 : ADPCM-A, V2 : ADPCM-B (V2 vide = partagé avec V1)
  C  : ROM impaire (c1, c3...) et paire (c2, c4...) entrelacées octet par
       octet, paire par paire (c1[0] c2[0] c1[1] c2[1] ...)
"""
import argparse
import gzip
import os
import struct
import sys

HEADER_SIZE = 4096


def readb(path):
    with open(path, "rb") as f:
        return f.read()
NEO_MAGIC = b"NEO\x01"

# limites matérielles de SDAES (voir docs/03-memoire-et-timings.md)
LIMITS = {
    "P": 24 << 20,       # SDRAM P : 25 Mo moins la RAM de protection PVC
    "S": 512 << 10,      # SRAM 0x00000-0x7FFFF
    "M": 512 << 10,      # SRAM 0x80000-0xFFFFF
    "V": 32 << 20,       # SDRAM V (V1 + V2)
    "C": 64 << 20,       # 2 x SDRAM en 32 bits
}

GENRES = ["Other", "Action", "BeatEmUp", "Sports", "Driving", "Platformer",
          "Mahjong", "Shooter", "Quiz", "Fighting", "Puzzle"]


# ---------------------------------------------------------------------------
# Format .neo
# ---------------------------------------------------------------------------
class NeoHeader:
    FMT = "<4s6I4I33s17s"   # magic, P S M V1 V2 C, année genre capture NGH, nom, éditeur

    def __init__(self, psize=0, ssize=0, msize=0, v1size=0, v2size=0, csize=0,
                 year=0, genre=0, screenshot=0, ngh=0, name="", manu=""):
        self.psize, self.ssize, self.msize = psize, ssize, msize
        self.v1size, self.v2size, self.csize = v1size, v2size, csize
        self.year, self.genre, self.screenshot, self.ngh = year, genre, screenshot, ngh
        self.name, self.manu = name, manu

    def pack(self):
        raw = struct.pack(self.FMT, NEO_MAGIC, self.psize, self.ssize, self.msize,
                          self.v1size, self.v2size, self.csize,
                          self.year, self.genre, self.screenshot, self.ngh,
                          self.name.encode("latin-1")[:32], self.manu.encode("latin-1")[:16])
        return raw + b"\x00" * (HEADER_SIZE - len(raw))

    @classmethod
    def unpack(cls, data):
        if len(data) < HEADER_SIZE:
            raise ValueError("fichier trop court pour un en-tête .neo")
        f = struct.unpack_from(cls.FMT, data)
        if f[0] != NEO_MAGIC:
            raise ValueError("signature .neo absente (attendu 'NEO' + version 1)")
        h = cls(*f[1:11])
        h.name = f[11].split(b"\x00")[0].decode("latin-1")
        h.manu = f[12].split(b"\x00")[0].decode("latin-1")
        return h

    def regions(self):
        """liste (nom, décalage dans le fichier, taille)"""
        out, off = [], HEADER_SIZE
        for name, size in (("P", self.psize), ("S", self.ssize), ("M", self.msize),
                           ("V1", self.v1size), ("V2", self.v2size), ("C", self.csize)):
            out.append((name, off, size))
            off += size
        return out


def mask_for(size):
    """masque d'adresse (puissance de 2 supérieure - 1)"""
    if size <= 1:
        return 0
    return (1 << (size - 1).bit_length()) - 1


def load_plan(h):
    """Plan de chargement identique au firmware (firmware/rp2350/src/neo.c)."""
    errors = []
    if h.psize > LIMITS["P"]:
        errors.append("P trop grand")
    if h.ssize > LIMITS["S"]:
        errors.append("S trop grand")
    if h.msize > LIMITS["M"]:
        errors.append("M1 trop grand")
    v2_base = (h.v1size + 0xFFFF) & ~0xFFFF if h.v2size else 0
    if v2_base + h.v2size > LIMITS["V"] or h.v1size > LIMITS["V"]:
        errors.append("V trop grand")
    if h.csize > LIMITS["C"]:
        errors.append("C trop grand")
    if h.csize % 4:
        errors.append("taille C non multiple de 4")
    return {
        "p_mask_words": mask_for(h.psize) >> 1,
        "s_mask": mask_for(h.ssize),
        "m1_mask": mask_for(h.msize),
        "v1_base": 0, "v1_mask": mask_for(h.v1size),
        "v2_base": v2_base if h.v2size else 0,
        "v2_mask": mask_for(h.v2size if h.v2size else h.v1size),
        "c_mask_words": mask_for(h.csize) >> 2,
        "bank_enable": h.psize > (2 << 20),
        "errors": errors,
    }


def cmd_info(args):
    with open(args.file, "rb") as f:
        data = f.read(HEADER_SIZE)
        size = os.fstat(f.fileno()).st_size
    h = NeoHeader.unpack(data)
    print(f"Nom      : {h.name}")
    print(f"Éditeur  : {h.manu}")
    print(f"Année    : {h.year}   NGH : {h.ngh:04X}   Genre : "
          f"{GENRES[h.genre] if h.genre < len(GENRES) else h.genre}")
    for name, off, sz in h.regions():
        print(f"  {name:2s} : {sz:>10d} octets ({sz / 1048576:6.2f} Mo) @ 0x{off:08X}")
    expected = HEADER_SIZE + h.psize + h.ssize + h.msize + h.v1size + h.v2size + h.csize
    if size != expected:
        print(f"ATTENTION : taille du fichier {size} != {expected} attendue")
    plan = load_plan(h)
    print("Plan SDAES :")
    for k, v in plan.items():
        if k != "errors":
            print(f"  {k:13s} = {v:#x}" if isinstance(v, int) and not isinstance(v, bool) else f"  {k:13s} = {v}")
    for e in plan["errors"]:
        print(f"  ERREUR : {e}")
    return 1 if plan["errors"] else 0


# ---------------------------------------------------------------------------
# Construction d'un .neo
# ---------------------------------------------------------------------------
def read_all(paths):
    out = b""
    for p in paths or []:
        with open(p, "rb") as f:
            out += f.read()
    return out


def interleave_c(paths):
    """c1,c2,c3,c4... -> (c1|c2 entrelacés) + (c3|c4 entrelacés) + ..."""
    if not paths:
        return b""
    if len(paths) % 2:
        raise ValueError("les ROM C vont par paires (c1 c2, c3 c4, ...)")
    out = bytearray()
    for i in range(0, len(paths), 2):
        odd = readb(paths[i])
        even = readb(paths[i + 1])
        if len(odd) != len(even):
            raise ValueError(f"{paths[i]} et {paths[i + 1]} n'ont pas la même taille")
        pair = bytearray(len(odd) * 2)
        pair[0::2] = odd
        pair[1::2] = even
        out += pair
    return bytes(out)


def cmd_build(args):
    p = read_all(args.p)
    if args.p_swap:
        p = swap16(p)
    s, m = read_all(args.s), read_all(args.m)
    v1, v2 = read_all(args.v1), read_all(args.v2)
    c = interleave_c(args.c)
    h = NeoHeader(len(p), len(s), len(m), len(v1), len(v2), len(c),
                  args.year, args.genre, 0, args.ngh, args.name, args.manu)
    with open(args.output, "wb") as f:
        f.write(h.pack())
        for blob in (p, s, m, v1, v2, c):
            f.write(blob)
    print(f"{args.output} : P={len(p)} S={len(s)} M={len(m)} V1={len(v1)} V2={len(v2)} C={len(c)}")
    return 0


def swap16(b):
    a = bytearray(b)
    a[0::2], a[1::2] = b[1::2], b[0::2]
    return bytes(a)


# ---------------------------------------------------------------------------
# Police du menu -> ROM S
# ---------------------------------------------------------------------------
def read_psf(path):
    """retourne (largeur, hauteur, [glyphes bytes])"""
    raw = readb(path)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    if raw[:2] == b"\x36\x04":                      # PSF1
        mode, charsize = raw[2], raw[3]
        n = 512 if mode & 1 else 256
        glyphs = [raw[4 + i * charsize: 4 + (i + 1) * charsize] for i in range(n)]
        return 8, charsize, glyphs
    if raw[:4] == b"\x72\xb5\x4a\x86":              # PSF2
        _, _, hsize, _, n, charsize, h, w = struct.unpack_from("<8I", raw)
        glyphs = [raw[hsize + i * charsize: hsize + (i + 1) * charsize] for i in range(n)]
        return w, h, glyphs
    raise ValueError("format de police non reconnu (PSF1/PSF2 attendus)")


def fix_tile(rows, color=1):
    """
    Tuile de la couche fixe : 8x8 pixels, 4 bits/pixel, 32 octets.
    Octet = 2 pixels (pixel de gauche dans le quartet bas). Ordre des octets :
    colonnes 4-5 (lignes 0..7), 6-7, 0-1, 2-3.
    """
    out = bytearray(32)
    for blk, col in enumerate((4, 6, 0, 2)):
        for y in range(8):
            r = rows[y] if y < len(rows) else 0
            left = color if r & (0x80 >> col) else 0
            right = color if r & (0x80 >> (col + 1)) else 0
            out[blk * 8 + y] = left | (right << 4)
    return bytes(out)


def cmd_font(args):
    w, h, glyphs = read_psf(args.font)
    if w != 8:
        raise ValueError("police de 8 pixels de large requise")
    rom = bytearray()
    for code in range(256):
        g = glyphs[code] if code < len(glyphs) else b""
        rows = list(g[:8]) if h == 8 else [g[(y * h) // 8] for y in range(8)]
        rom += fix_tile(rows)
    with open(args.output, "wb") as f:
        f.write(rom)
    print(f"{args.output} : {len(rom)} octets (256 tuiles)")
    return 0


# ---------------------------------------------------------------------------
# Code de sécurité
# ---------------------------------------------------------------------------
SEC_START, SEC_END = 0x186, 0x400


def cmd_security(args):
    menu = bytearray(readb(args.menu))
    with open(args.game, "rb") as f:
        h = NeoHeader.unpack(f.read(HEADER_SIZE))
        p = f.read(min(h.psize, 0x1000))
    p = swap16(p)                       # fichier petit-boutiste -> ordre 68000
    ptr = struct.unpack_from(">I", p, 0x182)[0]
    if ptr != SEC_START:
        raise ValueError(f"pointeur de sécurité inattendu 0x{ptr:X} (0x186 attendu)")
    if len(menu) < SEC_END:
        raise ValueError("binaire du menu trop court")
    menu[SEC_START:SEC_END] = p[SEC_START:SEC_END]
    with open(args.output, "wb") as f:
        f.write(menu)
    print(f"{args.output} : code de sécurité recopié depuis {h.name!r}")
    return 0


# ---------------------------------------------------------------------------
# Fichiers d'initialisation BRAM
# ---------------------------------------------------------------------------
def write_hex(path, data, size):
    if len(data) > size:
        raise ValueError(f"{len(data)} octets ne tiennent pas dans {size}")
    data = data + b"\x00" * (size - len(data))
    with open(path, "w") as f:
        for b in data:
            f.write(f"{b:02x}\n")


def cmd_bramhex(args):
    write_hex(args.output, readb(args.file), args.size)
    return 0


def cmd_bramhex16(args):
    data = readb(args.file)
    if len(data) % 2:
        data += b"\x00"
    write_hex(args.hi, data[0::2], args.size // 2)
    write_hex(args.lo, data[1::2], args.size // 2)
    return 0


# ---------------------------------------------------------------------------
# Protections (format .map / MAPPERS.TXT, cf. firmware/rp2350/src/mapper.c)
# ---------------------------------------------------------------------------
PORT_BASE = 0x200000
MAP_MODES = {"std": 0, "sma": 1, "pvc": 2, "ct0": 3}


def _nums(text):
    out = []
    for tok in text.replace(",", " ").split():
        try:
            out.append(int(tok, 0))
        except ValueError:
            raise ValueError(f"nombre invalide : {tok}")
    return out


def default_mapper(name=""):
    return {"name": name, "ngh": 0, "mode": 0, "bank_addr": 0, "bank_bits": list(range(6)),
            "bank_table": [], "prot": None, "rng": [], "rng_seed": 0x2345, "overlay": None,
            "wait": (0, 0), "fix_bank": None, "patch": "none"}


def parse_mappers(text, whole_file=False, name=""):
    """Retourne la liste des descriptions (une seule si whole_file)."""
    sections, cur, in_table = [], (default_mapper(name) if whole_file else None), False
    for raw in text.splitlines():
        line = raw.split("#")[0].split(";")[0].strip()
        if not line:
            continue
        if line.startswith("["):
            if whole_file:
                raise ValueError("section interdite dans un fichier .map")
            if cur:
                sections.append(cur)
            cur = default_mapper(line.strip("[]").strip())
            in_table = False
            continue
        if cur is None:
            raise ValueError("clé hors section")
        if "=" not in line:
            if in_table:
                cur["bank_table"] += _nums(line)
                continue
            raise ValueError(f"ligne invalide : {line}")
        key, val = (x.strip() for x in line.split("=", 1))
        in_table = False
        v = _nums(val) if key not in ("mapper", "patch") else None
        if key == "ngh":
            cur["ngh"] = v[0]
        elif key == "mapper":
            if val not in MAP_MODES:
                raise ValueError(f"mapper inconnu : {val}")
            cur["mode"] = MAP_MODES[val]
        elif key == "bank_addr":
            cur["bank_addr"] = v[0]
        elif key == "bank_bits":
            if len(v) != 6 or max(v) > 15:
                raise ValueError("bank_bits : 6 numéros de bit (0-15)")
            cur["bank_bits"] = v
        elif key == "bank_table":
            cur["bank_table"] = v
            in_table = True
        elif key == "prot":
            cur["prot"] = (v[0], v[1])
        elif key == "rng":
            cur["rng"] = v[:2]
        elif key == "rng_seed":
            cur["rng_seed"] = v[0]
        elif key == "overlay":
            if len(v) != 6:
                raise ValueError("overlay : 6 valeurs")
            cur["overlay"] = v
        elif key == "patch":
            if val not in ("none", "mslugx"):
                raise ValueError(f"correctif inconnu : {val}")
            cur["patch"] = val
        elif key == "fix_bank":
            if len(v) != 1 or v[0] > 2:
                raise ValueError("fix_bank : 0, 1 (type Garou) ou 2 (type KOF 2000)")
            cur["fix_bank"] = v[0]
        elif key == "wait":
            if len(v) != 2 or v[0] > 1 or v[1] > 2:
                raise ValueError("wait : attente zone ROM (0-1) et zone PORT (0-2)")
            cur["wait"] = tuple(v)
        else:
            raise ValueError(f"clé inconnue : {key}")
    if cur:
        sections.append(cur)
    for m in sections:
        if len(m["bank_table"]) > 64:
            raise ValueError(f"{m['name']} : plus de 64 entrées dans bank_table")
        if m["mode"] == 1 and not m["bank_table"]:
            raise ValueError(f"{m['name']} : bank_table manquante")
    return sections


def mapper_registers(m):
    """Registres du FPGA P, identiques à mapper_registers() du firmware."""
    def idx(a):
        return ((a - PORT_BASE) >> 1) & 0x7FFFF
    regs = [(0x0A, m["mode"] | (0x100 if m["overlay"] else 0))]
    # {PWAIT1, PWAIT0, ROMWAIT}, actifs à 0 : 0 = pleine vitesse
    rom_w, port_w = m["wait"]
    regs.append((0x04, ((0x3, 0x2, 0x1)[port_w] << 1) | (0 if rom_w else 1)))
    if m["mode"] == 1:
        perm = sum((b & 0xF) << (4 * i) for i, b in enumerate(m["bank_bits"]))
        regs += [(0x0B, idx(m["bank_addr"])), (0x0C, perm),
                 (0x0D, (0x80000000 | idx(m["prot"][0])) if m["prot"] else 0),
                 (0x0E, (m["prot"][1] if m["prot"] else 0) & 0xFFFF)]
        rng = m["rng"] + [0, 0]
        regs += [(0x0F, (0x80000000 | idx(rng[0])) if rng[0] else 0),
                 (0x15, (0x80000000 | idx(rng[1])) if rng[1] else 0),
                 (0x16, m["rng_seed"])]
    if m["overlay"]:
        t, on, off, addr, v0, v1 = m["overlay"]
        regs += [(0x17, idx(t)), (0x18, ((on & 0xFFFF) << 16) | (off & 0xFFFF)),
                 (0x19, (addr >> 1) & 0x7FFFF), (0x1A, ((v0 & 0xFFFF) << 16) | (v1 & 0xFFFF))]
    return regs


def cmd_mapper(args):
    text = readb(args.file).decode("latin-1")
    whole = not args.file.upper().endswith(".TXT")
    maps = parse_mappers(text, whole_file=whole, name=args.game or "")
    if args.game or args.ngh is not None:
        sel = [m for m in maps if args.game and m["name"].lower() == args.game.lower()]
        sel = sel or [m for m in maps if args.ngh is not None and m["ngh"] == args.ngh]
        maps = sel[:1]
    if not maps:
        print("aucune description correspondante")
        return 1
    for m in maps:
        kind = [k for k, v in MAP_MODES.items() if v == m["mode"]][0]
        print(f"[{m['name']}] ngh=0x{m['ngh']:X} mapper={kind} "
              f"table={len(m['bank_table'])} superposition={'oui' if m['overlay'] else 'non'} "
              f"couche_fixe={'auto' if m['fix_bank'] is None else m['fix_bank']}")
        for reg, val in mapper_registers(m):
            print(f"   reg 0x{reg:02X} = 0x{val:08X}")
    return 0


# Jeux SMA connus : nom de fonction MAME -> NGH (à vérifier sur votre .neo)
SMA_NGH = {"kof99": 0x251, "garou": 0x253, "garouh": 0x253, "mslug3": 0x256, "kof2000": 0x257}


def extract_sma(src):
    """
    Extrait du source MAME de la protection SMA (prot_sma.cpp ou sma_prot.cpp)
    les tables de banques, la permutation des bits et les adresses installées.
    Reconnaît les deux écritures de la permutation utilisées par MAME :
    (((data>>N)&1)<<M) et bitswap<6>(data, b5, b4, b3, b2, b1, b0).
    """
    import re
    games = {}
    for fm in re.finditer(r"(\w+)_bankswitch_w\s*\([^)]*\)\s*\{(.*?)\n\}", src, re.S):
        name, body = fm.group(1), fm.group(2)
        tm = re.search(r"bankoffset\s*\[\s*\d*\s*\]\s*=\s*\{(.*?)\}", body, re.S)
        if not tm:
            continue
        table = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", re.sub(r"/\*.*?\*/", "", tm.group(1), flags=re.S))]
        bits = [None] * 6
        bs = re.search(r"bitswap\s*<\s*6\s*>\s*\(\s*data\s*,([^)]*)\)", body)
        if bs:
            lst = [int(x) for x in bs.group(1).split(",")]
            for i in range(6):
                bits[i] = lst[5 - i]
        else:
            for srcbit, dst in re.findall(r"\(\s*\(\s*data\s*>>\s*(\d+)\s*\)\s*&\s*1\s*\)\s*<<\s*(\d+)", body):
                bits[int(dst)] = int(srcbit)
        if None in bits:
            raise ValueError(f"{name} : permutation des bits non reconnue")
        games[name] = {"table": table, "bits": bits, "bank_addr": None, "prot": None, "rng": []}
    for im in re.finditer(r"(\w+)_install_protection\s*\([^)]*\)\s*\{(.*?)\n\}", src, re.S):
        name, body = im.group(1), im.group(2)
        if name not in games:
            continue
        g = games[name]
        for hm in re.finditer(r"install_(read|write)_handler\s*\(\s*(0x[0-9a-fA-F]+)[^;]*?(\w+)\s*\)+\s*;", body, re.S):
            addr, func = int(hm.group(2), 16), hm.group(3)
            if "bankswitch" in func:
                g["bank_addr"] = addr
            elif "9a37" in func:
                g["prot"] = (addr, 0x9A37)
            elif "random" in func:
                g["rng"].append(addr)
    out = []
    for name, g in games.items():
        if g["bank_addr"] is None:
            raise ValueError(f"{name} : adresse du registre de banque introuvable")
        lines = [f"[{name}]"]
        if name in SMA_NGH:
            lines.append(f"ngh = 0x{SMA_NGH[name]:X}")
        lines += ["mapper = sma", f"bank_addr = 0x{g['bank_addr']:06x}",
                  "bank_bits = " + " ".join(str(b) for b in g["bits"])]
        tbl = [f"0x{v:06x}" for v in g["table"]]
        lines.append("bank_table = " + " ".join(tbl[:8]))
        for i in range(8, len(tbl), 8):
            lines.append("             " + " ".join(tbl[i:i + 8]))
        if g["prot"]:
            lines.append(f"prot = 0x{g['prot'][0]:06x} 0x{g['prot'][1]:04x}")
        if g["rng"]:
            lines.append("rng = " + " ".join(f"0x{a:06x}" for a in g["rng"][:2]))
        out.append("\n".join(lines))
    return "# Généré par tools/neotool.py sma-from-mame\n\n" + "\n\n".join(out) + "\n"


def cmd_sma_from_mame(args):
    text = extract_sma(readb(args.source).decode("latin-1"))
    parse_mappers(text)          # vérification
    with open(args.output, "w") as f:
        f.write(text)
    print(f"{args.output} : {text.count('[')} jeu(x)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info")
    s.add_argument("file")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("build")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--p", nargs="+", help="p1 p2 ... (ordre de la région 68000)")
    s.add_argument("--p-swap", action="store_true", help="inverse les octets de P (dumps grand-boutistes)")
    s.add_argument("--s", nargs="+")
    s.add_argument("--m", nargs="+")
    s.add_argument("--v1", nargs="+")
    s.add_argument("--v2", nargs="+")
    s.add_argument("--c", nargs="+", help="c1 c2 c3 c4 ... (par paires)")
    s.add_argument("--name", default="")
    s.add_argument("--manu", default="")
    s.add_argument("--year", type=int, default=0)
    s.add_argument("--genre", type=int, default=0)
    s.add_argument("--ngh", type=lambda x: int(x, 0), default=0)
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("font")
    s.add_argument("font")
    s.add_argument("-o", "--output", required=True)
    s.set_defaults(fn=cmd_font)

    s = sub.add_parser("security")
    s.add_argument("menu")
    s.add_argument("game")
    s.add_argument("-o", "--output", required=True)
    s.set_defaults(fn=cmd_security)

    s = sub.add_parser("bramhex")
    s.add_argument("file")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--size", type=lambda x: int(x, 0), required=True)
    s.set_defaults(fn=cmd_bramhex)

    s = sub.add_parser("bramhex16")
    s.add_argument("file")
    s.add_argument("--hi", required=True)
    s.add_argument("--lo", required=True)
    s.add_argument("--size", type=lambda x: int(x, 0), default=32768)
    s.set_defaults(fn=cmd_bramhex16)

    s = sub.add_parser("mapper")
    s.add_argument("file")
    s.add_argument("--game")
    s.add_argument("--ngh", type=lambda x: int(x, 0))
    s.set_defaults(fn=cmd_mapper)

    s = sub.add_parser("sma-from-mame")
    s.add_argument("source")
    s.add_argument("-o", "--output", required=True)
    s.set_defaults(fn=cmd_sma_from_mame)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
