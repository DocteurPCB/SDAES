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
    "P": 32 << 20,       # SDRAM P
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

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
