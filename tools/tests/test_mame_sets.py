"""Tests de tools/mame_sets.py : chaque fonction rapide est comparée, sur des
positions tirées au hasard, à une transcription littérale du code de MAME."""
import os
import random
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mame_sets  # noqa: E402
import neotool  # noqa: E402


def bitswap(x, *bits):
    """bitswap<N>(x, ...) de MAME, version naïve."""
    n = len(bits)
    return sum(((x >> b) & 1) << (n - 1 - k) for k, b in enumerate(bits))


def w(b, i):
    return struct.unpack_from("<H", b, 2 * i)[0]


def ramp(nwords, seed=0):
    """Mots tous différents (index mélangé), en petit-boutiste."""
    return b"".join(struct.pack("<H", (i * 40503 + seed) & 0xFFFF) for i in range(nwords))


class MameSetTests(unittest.TestCase):
    rnd = random.Random(42)

    def samples(self, n, count=400):
        return [self.rnd.randrange(n) for _ in range(count)] + [0, n - 1]

    def test_bitswap_table(self):
        bits = (0x17, 0x16, 0x15, 0x14, 0x13, 0x00, 0x01, 0x02, 0x0F, 0x0E, 0x0D, 0x0C,
                0x0B, 0x0A, 0x09, 0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x10, 0x11, 0x12)
        f = mame_sets.bitswap_table(24, bits)
        for x in self.samples(1 << 24):
            self.assertEqual(f(x), bitswap(x, *bits))

    def test_svcboot_px(self):
        p = ramp(0x400000)
        out = mame_sets.svcboot_px_decrypt(p)
        sec = (6, 7, 1, 2, 3, 4, 5, 0)
        dst = b"".join(p[s * 0x100000:(s + 1) * 0x100000] for s in sec)
        for i in self.samples(0x400000):
            ofst = bitswap(i & 0xFF, 7, 6, 1, 0, 3, 2, 5, 4) + (i & 0xFFFF00)
            self.assertEqual(w(out, i), w(dst, ofst))

    def test_svcplus_px(self):
        p = ramp(0x300000, 7)
        out = mame_sets.svcplus_px_decrypt(p)
        step1 = {}
        for i in self.samples(0x300000):
            ofst = bitswap(i & 0xFFFFF, 0x17, 0x16, 0x15, 0x14, 0x13, 0x00, 0x01, 0x02,
                           0x0F, 0x0E, 0x0D, 0x0C, 0x0B, 0x0A, 0x09, 0x08,
                           0x07, 0x06, 0x05, 0x04, 0x03, 0x10, 0x11, 0x12) ^ 0x0F0007
            step1[i] = w(p, ofst + (i & 0xFF00000))
        sec = (0, 3, 2, 5, 4, 1)
        for i, v in step1.items():
            # le mot i de l'étape 1 se retrouve dans le bloc k tel que sec[k] = bloc de i
            k = sec.index(i // 0x80000)
            self.assertEqual(w(out, k * 0x80000 + (i % 0x80000)), v)

    def test_svcsplus_px(self):
        p = ramp(0x400000, 3)
        out = mame_sets.svcsplus_px_decrypt(p)
        sec = (6, 7, 1, 2, 3, 4, 5, 0)
        for i in self.samples(0x400000):
            ofst = bitswap(i & 0x7FFF, 0x0F, 0x00, 0x08, 0x09, 0x0B, 0x0A, 0x0C, 0x0D,
                           0x04, 0x03, 0x01, 0x07, 0x06, 0x02, 0x05, 0x0E)
            ofst += (i & 0x078000) + (sec[(i & 0xF80000) >> 19] << 19)
            self.assertEqual(w(out, i), w(p, ofst))

    def test_svcboot_cx(self):
        c = bytes(self.rnd.randrange(256) for _ in range(0x10000)) * 32      # 2 Mo
        out = mame_sets.svcboot_cx_decrypt(c)
        idx_tbl = (0, 1, 0, 1, 2, 3, 2, 3, 3, 4, 3, 4, 4, 5, 4, 5)
        tbl = ((3, 0, 1, 2), (2, 3, 0, 1), (1, 2, 3, 0), (0, 1, 2, 3), (3, 2, 1, 0), (3, 0, 2, 1))
        for i in self.samples(len(c) // 0x80):
            t = tbl[idx_tbl[(i & 0xF00) >> 8]]
            ofst = bitswap(i & 0xFF, 7, 6, 5, 4, t[3], t[2], t[1], t[0]) + (i & 0xFFFFF00)
            self.assertEqual(out[i * 0x80:(i + 1) * 0x80], c[ofst * 0x80:(ofst + 1) * 0x80])

    def test_kf2k3pl_px(self):
        p = ramp(0x380000, 11)
        out = mame_sets.kf2k3pl_px_decrypt(p)
        for i in self.samples(0x380000):
            if 2 * i in (0xF38AC,):
                continue
            blk, j = i & ~0x7FFFF, i & 0x7FFFF
            src = bitswap(j, 23, 22, 21, 20, 19, *range(19))
            self.assertEqual(w(out, i), w(p, blk + src))
        self.assertEqual(w(out, 0xF38AC // 2), 0x4E75)

    def test_kf2k3upl_px(self):
        p = ramp(0x400000, 5)
        out = mame_sets.kf2k3upl_px_decrypt(p)
        self.assertEqual(out[0x000000:0x0D0000], p[0x700000:0x7D0000])
        self.assertEqual(out[0x100000:0x700000], p[0x000000:0x600000])
        moved = p[0x700000:0x800000]                      # contenu des 1er Mo après déplacement
        for i in range(0x1000):
            ofst = (i & 0xFF00) + bitswap(i & 0xFF, 7, 6, 0, 4, 3, 2, 1, 5)
            self.assertEqual(out[0xFE000 + 2 * i:0xFE002 + 2 * i],
                             moved[0xD0610 + 2 * ofst:0xD0612 + 2 * ofst])

    def test_sx_and_helpers(self):
        s = bytes(range(32))
        self.assertEqual(mame_sets.sx_decrypt(s, 1)[:16], s[8:16] + s[:8])
        self.assertEqual(mame_sets.sx_decrypt(bytes([0x01, 0x20]), 2), bytes([0x20, 0x01]))
        self.assertEqual(mame_sets.halves(b"abcd"), b"cdab")
        self.assertEqual(mame_sets.poke16(bytes(4), 2, 0x4E71), bytes([0, 0, 0x71, 0x4E]))


class MameCommandTests(unittest.TestCase):
    def test_kof2003_bootlegs(self):
        with tempfile.TemporaryDirectory() as d:
            def put(name, data):
                with open(os.path.join(d, name), "wb") as f:
                    f.write(data)
            p1, p2 = ramp(0x200000, 1), ramp(0x200000, 2)
            put("2k3-p1.bin", p1)
            put("2k3-p2.bin", p2)
            put("2k3-s1.bin", bytes(range(256)) * 512)
            put("2k3-m1.bin", b"M" * 0x20000)
            base = os.path.join(d, "kof2003.neo")
            put("c1", b"\x11" * 64)
            put("c2", b"\x22" * 64)
            put("v", b"V" * 128)
            self.assertEqual(neotool.main(["build", "-o", base, "--p", os.path.join(d, "v"),
                                           "--v1", os.path.join(d, "v"),
                                           "--c", os.path.join(d, "c1"), os.path.join(d, "c2"),
                                           "--ngh", "0x271"]), 0)
            out = os.path.join(d, "kf2k3bl.neo")
            # C et V chiffrés comme l'original : --from obligatoire
            self.assertNotEqual(neotool.main(["mame", "kf2k3bl", "--dir", d, "-o", out]), 0)
            self.assertEqual(neotool.main(["mame", "kf2k3bl", "--dir", d, "-o", out, "--from", base]), 0)
            with open(out, "rb") as f:
                data = f.read()
            h = neotool.NeoHeader.unpack(data)
            r = {n: data[o:o + sz] for n, o, sz in h.regions()}
            self.assertEqual(h.ngh, 0x271)
            self.assertEqual(len(r["P"]), 0x800000)       # P de 8 Mo -> mode K3B dans le firmware
            self.assertEqual(r["P"][:0x100000], p2[0x300000:0x400000])
            self.assertEqual(r["P"][0x100000:0x500000], p1)
            self.assertEqual(r["P"][0x500000:0x700000], p2[:0x200000])
            self.assertEqual((r["C"], r["V1"], r["M"]), (b"\x11\x22" * 64, b"V" * 128, b"M" * 0x20000))


if __name__ == "__main__":
    unittest.main()
