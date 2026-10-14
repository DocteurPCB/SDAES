"""Fabrication de .neo pour des bootlegs, à partir des fichiers ROM de MAME.

Chaque recette reproduit l'agencement des régions de MAME (ROM_LOAD,
ROM_CONTINUE...) et les fonctions de remise en ordre de MAME
(src/devices/bus/neogeo/prot_misc.cpp, prot_kof2k3bl.cpp, boot_*.cpp).
Les régions sont dans l'ordre des fichiers .neo : mots 68000 petit-boutistes
pour P (comme les fichiers .p1 et la région de MAME sur un PC), C avec c1/c2
entrelacés octet par octet.

Les données encore chiffrées comme sur l'original (C et V des bootlegs de
KOF 2003, C/M1/V de Metal Slug 5 Plus) sont reprises d'un .neo déchiffré de
l'original (option --from).
"""
import os
import sys
from array import array


# ---------------------------------------------------------------------------
# outils

def bitswap_table(nbits, bits):
    """Fonction x -> bitswap<nbits>(x, bits...) de MAME (bits[0] = bit de
    poids fort du résultat), calculée par octets pour aller vite."""
    assert len(bits) == nbits
    tabs = []
    for byte in range((nbits + 7) // 8):
        t = []
        for v in range(256):
            x = v << (8 * byte)
            r = 0
            for k, b in enumerate(bits):
                if (x >> b) & 1:
                    r |= 1 << (nbits - 1 - k)
            t.append(r)
        tabs.append(t)

    def f(x):
        r = 0
        for byte, t in enumerate(tabs):
            r |= t[(x >> (8 * byte)) & 0xFF]
        return r
    return f


def words(b):
    """Mots 16 bits petit-boutistes -> array('H')."""
    a = array("H")
    a.frombytes(bytes(b))
    if sys.byteorder == "big":
        a.byteswap()
    return a


def wbytes(a):
    a = array("H", a)
    if sys.byteorder == "big":
        a.byteswap()
    return a.tobytes()


def swap16(b):
    a = bytearray(b)
    a[0::2], a[1::2] = b[1::2], b[0::2]
    return bytes(a)


def halves(b):
    """ROM_LOAD(nom, taille/2...) + ROM_CONTINUE(0) : moitiés échangées."""
    h = len(b) // 2
    return b[h:] + b[:h]


def blocks(b, sec, size=0x100000):
    """Blocs réordonnés : bloc i du résultat = bloc sec[i] de b."""
    return b"".join(b[s * size:(s + 1) * size] for s in sec)


def poke16(b, addr, value):
    b = bytearray(b)
    b[addr] = value & 0xFF
    b[addr + 1] = value >> 8
    return bytes(b)


def interleave_pairs(files, align=False):
    pairs = []
    for odd, even in zip(files[0::2], files[1::2]):
        if len(odd) != len(even):
            raise ValueError("les deux ROM C d'une paire n'ont pas la même taille")
        p = bytearray(len(odd) * 2)
        p[0::2] = odd
        p[1::2] = even
        pairs.append(bytes(p))
    size = max(len(p) for p in pairs) if align else 0
    out = b""
    for k, p in enumerate(pairs):
        out += p
        if align and k + 1 < len(pairs):
            out += bytes(size - len(p))
    return out


# ---------------------------------------------------------------------------
# fonctions de MAME (prot_misc.cpp, prot_kof2k3bl.cpp)

def sx_decrypt(s, value):
    if value == 1:
        out = bytearray(s)
        for i in range(0, len(s) - 15, 16):
            out[i:i + 8] = s[i + 8:i + 16]
            out[i + 8:i + 16] = s[i:i + 8]
        return bytes(out)
    f = bitswap_table(8, (7, 6, 0, 4, 3, 2, 1, 5))
    return bytes(s).translate(bytes(f(v) for v in range(256)))


def svcboot_px_decrypt(p):
    dst = words(blocks(p, (6, 7, 1, 2, 3, 4, 5, 0)[:len(p) // 0x100000]))
    f = bitswap_table(8, (7, 6, 1, 0, 3, 2, 5, 4))
    lo = [f(v) for v in range(256)]
    return wbytes(dst[(i & ~0xFF) | lo[i & 0xFF]] for i in range(len(dst)))


def svcboot_cx_decrypt(c):
    idx_tbl = (0, 1, 0, 1, 2, 3, 2, 3, 3, 4, 3, 4, 4, 5, 4, 5)
    sw4 = ((3, 0, 1, 2), (2, 3, 0, 1), (1, 2, 3, 0), (0, 1, 2, 3), (3, 2, 1, 0), (3, 0, 2, 1))
    fs = []
    for t in sw4:
        f = bitswap_table(8, (7, 6, 5, 4, t[3], t[2], t[1], t[0]))
        fs.append([f(v) for v in range(256)])
    mv = memoryview(bytes(c))
    out = []
    for i in range(len(c) // 0x80):
        ofst = (i & 0xFFFFF00) | fs[idx_tbl[(i & 0xF00) >> 8]][i & 0xFF]
        out.append(mv[ofst * 0x80:(ofst + 1) * 0x80])
    return b"".join(out)


def svcplus_px_decrypt(p):
    f = bitswap_table(24, (0x17, 0x16, 0x15, 0x14, 0x13, 0x00, 0x01, 0x02,
                           0x0F, 0x0E, 0x0D, 0x0C, 0x0B, 0x0A, 0x09, 0x08,
                           0x07, 0x06, 0x05, 0x04, 0x03, 0x10, 0x11, 0x12))
    perm = [f(i) ^ 0x0F0007 for i in range(0x100000)]
    src = words(p)
    dst = wbytes(src[(i & 0xFF00000) + perm[i & 0xFFFFF]] for i in range(len(src)))
    return blocks(dst, (0, 3, 2, 5, 4, 1))


def svcplus_px_hack(p):
    return poke16(p, 0x0F8016, 0x33C1)


def svcplusa_px_decrypt(p):
    return blocks(p, (1, 2, 3, 4, 5, 0))


def svcsplus_px_decrypt(p):
    sec = (6, 7, 1, 2, 3, 4, 5, 0)
    f = bitswap_table(16, (0x0F, 0x00, 0x08, 0x09, 0x0B, 0x0A, 0x0C, 0x0D,
                           0x04, 0x03, 0x01, 0x07, 0x06, 0x02, 0x05, 0x0E))
    perm = [f(i) for i in range(0x8000)]
    src = words(p)
    return wbytes(src[perm[i & 0x7FFF] + (i & 0x78000) + (sec[(i & 0xF80000) >> 19] << 19)]
                  for i in range(len(src)))


def svcsplus_px_hack(p):
    for a, v in ((0x9E90, 0x000F), (0x9E92, 0xC9C0), (0xA10C, 0x4EB9), (0xA10E, 0x000E), (0xA110, 0x9750)):
        p = poke16(p, a, v)
    return p


def kf2k3pl_px_decrypt(p):
    f = bitswap_table(24, (23, 22, 21, 20, 19) + tuple(range(19)))
    perm = [f(j) for j in range(0x80000)]
    src = words(p)
    out = array("H")
    for blk in range(0, 0x700000 // 2, 0x80000):
        t = src[blk:blk + 0x80000]
        out.extend(t[perm[j]] for j in range(0x80000))
    out.extend(src[len(out):])
    return poke16(wbytes(out), 0xF38AC, 0x4E75)        # « patched by Altera protection chip »


def kf2k3upl_px_decrypt(p):
    b = bytearray(p)
    b[0x100000:0x700000] = p[0x000000:0x600000]
    b[0x000000:0x100000] = p[0x700000:0x800000]
    f = bitswap_table(8, (7, 6, 0, 4, 3, 2, 1, 5))
    src = bytes(b[0xD0610:0xD0610 + 0x2000])
    for i in range(0x1000):
        ofst = (i & 0xFF00) + f(i & 0xFF)
        b[0xFE000 + 2 * i:0xFE000 + 2 * i + 2] = src[2 * ofst:2 * ofst + 2]
    return bytes(b)


def mslug5b_vx_decrypt(v):
    f = bitswap_table(8, (3, 2, 4, 1, 5, 0, 6, 7))
    v = bytearray(v)
    v[1::2] = bytes(v[1::2]).translate(bytes(f(x) for x in range(256)))
    return bytes(v)


def mslug5b_cx_decrypt(c):
    c = bytearray(c)
    blk = 0x80000
    for i in range(1, 128, 4):
        a, b = i * blk, (i + 1) * blk
        if b + blk <= len(c):
            c[a:a + blk], c[b:b + blk] = c[b:b + blk], c[a:a + blk]
    return bytes(c)


# ---------------------------------------------------------------------------
# recettes : chaque fonction reçoit read(nom) et base (régions d'un .neo
# déchiffré de l'original, ou None) et rend un dict de régions

def _svc_common(read):
    return {
        "M": halves(read("svc-m1.bin")),
        "V1": b"".join(swap16(read(n)) for n in ("svc-v2.bin", "svc-v1.bin", "svc-v4.bin", "svc-v3.bin")),
        "V2": b"",
        "C": svcboot_cx_decrypt(interleave_pairs([read(f"svc-c{k}.bin") for k in range(1, 9)])),
    }


def _need(base, what):
    if base is None:
        raise ValueError(f"{what} : donner un .neo déchiffré de l'original avec --from")
    return base


def r_svcboot(read, base):
    r = _svc_common(read)
    r.update(P=svcboot_px_decrypt(read("svc-p1.bin")), S=halves(read("svc-s1.bin")))
    return r


def r_svcplus(read, base):
    r = _svc_common(read)
    p = read("svc-p1p.bin") + read("svc-p2p.bin") + read("svc-p3p.bin")
    r.update(P=svcplus_px_hack(svcplus_px_decrypt(p)), S=sx_decrypt(read("svc-s1p.bin"), 1))
    return r


def r_svcplusa(read, base):
    r = _svc_common(read)
    p = read("svc-p1pl.bin") + read("svc-p2pl.bin")
    r.update(P=svcplus_px_hack(svcplusa_px_decrypt(p)), S=halves(read("svc-s1pl.bin")))
    return r


def r_svcsplus(read, base):
    r = _svc_common(read)
    p = read("svc-p1sp.bin") + read("svc-p2sp.bin")
    r.update(P=svcsplus_px_hack(svcsplus_px_decrypt(p)), S=sx_decrypt(read("svc-s1sp.bin"), 2))
    return r


def _k3_common(read, base, s):
    b = _need(base, "C et V de KOF 2003 (chiffrés comme l'original)")
    return {"S": s, "M": read("2k3-m1.bin"), "V1": b["V1"], "V2": b["V2"], "C": b["C"]}


def r_kf2k3bl(read, base):
    p1, p2 = read("2k3-p1.bin"), read("2k3-p2.bin")
    # p1 en 0x100000 ; p2 : 2 Mo en 0x500000, puis deux fois 1 Mo en 0x000000
    p = p2[0x300000:0x400000] + p1 + p2[0x000000:0x200000] + bytes(0x100000)
    r = _k3_common(read, base, sx_decrypt(read("2k3-s1.bin"), 1))
    r["P"] = p
    return r


def r_kf2k3bla(read, base):
    p = read("2k3-p1bl.bin") + read("2k3-p3bl.bin") + read("2k3-p2bl.bin")
    r = _k3_common(read, base, sx_decrypt(read("2k3-s1.bin"), 1))
    r["P"] = kf2k3pl_px_decrypt(p)
    return r


def r_kf2k3pl(read, base):
    p = read("2k3-p1pl.bin") + read("2k3-p3bl.bin") + read("2k3-p2bl.bin")
    r = _k3_common(read, base, sx_decrypt(read("2k3-s1pl.bin"), 1))
    r["P"] = kf2k3pl_px_decrypt(p)
    return r


def r_kf2k3upl(read, base):
    r = _k3_common(read, base, sx_decrypt(read("2k3-s1up.bin"), 2))
    r["P"] = kf2k3upl_px_decrypt(read("2k3-p1up.bin"))
    return r


def r_ms5plus(read, base):
    b = _need(base, "C, M1 et V de Metal Slug 5 (chiffrés comme l'original)")
    p = read("ms5-p1p.bin") + read("ms5-p2p.bin") + read("ms5-p3p.bin")
    return {"P": p, "S": sx_decrypt(read("ms5-s1p.bin"), 1), "M": b["M"],
            "V1": b["V1"], "V2": b["V2"], "C": b["C"]}


def r_mslug5b(read, base):
    c = interleave_pairs([read(f"ms5b-c{k}.bin") for k in range(1, 9)], align=True)
    return {"P": read("ms5b-p1.bin") + read("ms5b-p2.bin"),
            "S": sx_decrypt(read("ms5b-s1.bin"), 2),
            "M": read("ms5b-m1.bin"),
            "V1": mslug5b_vx_decrypt(b"".join(read(f"ms5b-v{k}.bin") for k in range(1, 5))),
            "V2": b"",
            "C": mslug5b_cx_decrypt(c)}


# nom MAME -> (recette, NGH, nom affiché)
SETS = {
    "svcboot":  (r_svcboot,  0x269, "SVC CHAOS (BOOTLEG)"),
    "svcplus":  (r_svcplus,  0x269, "SVC CHAOS PLUS"),
    "svcplusa": (r_svcplusa, 0x269, "SVC CHAOS PLUS (SET 2)"),
    "svcsplus": (r_svcsplus, 0x269, "SVC CHAOS SUPER PLUS"),
    "kf2k3bl":  (r_kf2k3bl,  0x271, "KOF 2003 (BOOTLEG)"),
    "kf2k3bla": (r_kf2k3bla, 0x271, "KOF 2003 (BOOTLEG 2)"),
    "kf2k3pl":  (r_kf2k3pl,  0x271, "KOF 2004 PLUS / HERO"),
    "kf2k3upl": (r_kf2k3upl, 0x271, "KOF 2004 ULTRA PLUS"),
    "ms5plus":  (r_ms5plus,  0x268, "METAL SLUG 5 PLUS"),
    "mslug5b":  (r_mslug5b,  0x268, "METAL SLUG 5 (BOOTLEG)"),
}


def build_regions(name, rom_dir, base=None):
    """Régions du .neo du jeu MAME `name`, fichiers lus dans rom_dir."""
    if name not in SETS:
        raise ValueError(f"jeu inconnu : {name} (connus : {', '.join(sorted(SETS))})")

    def read(fn):
        path = os.path.join(rom_dir, fn)
        if not os.path.exists(path):
            raise ValueError(f"fichier manquant : {path}")
        with open(path, "rb") as f:
            return f.read()
    recipe, ngh, title = SETS[name]
    return recipe(read, base), ngh, title
