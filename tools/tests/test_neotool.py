"""Tests de neotool.py : python3 -m unittest discover -s tools/tests"""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import neotool  # noqa: E402
from neotool import readb  # noqa: E402


def readt(path):
    with open(path) as f:
        return f.read()


class TmpDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name, data=None):
        p = os.path.join(self.d, name)
        if data is not None:
            with open(p, "wb") as f:
                f.write(data)
        return p


class HeaderTests(unittest.TestCase):
    def test_layout(self):
        h = neotool.NeoHeader(1, 2, 3, 4, 5, 6, 1999, 9, 0, 0x251, "KOF", "SNK")
        raw = h.pack()
        self.assertEqual(len(raw), 4096)
        self.assertEqual(raw[:4], b"NEO\x01")
        self.assertEqual(struct.unpack_from("<6I", raw, 4), (1, 2, 3, 4, 5, 6))
        self.assertEqual(struct.unpack_from("<I", raw, 0x28)[0], 0x251)
        self.assertEqual(raw[0x2C:0x2F], b"KOF")
        self.assertEqual(raw[0x4D:0x50], b"SNK")
        back = neotool.NeoHeader.unpack(raw)
        self.assertEqual((back.name, back.manu, back.ngh, back.csize), ("KOF", "SNK", 0x251, 6))

    def test_bad_magic(self):
        with self.assertRaises(ValueError):
            neotool.NeoHeader.unpack(b"XXXX" + bytes(4092))

    def test_masks(self):
        self.assertEqual(neotool.mask_for(0x100000), 0xFFFFF)
        self.assertEqual(neotool.mask_for(0x100001), 0x1FFFFF)
        self.assertEqual(neotool.mask_for(0), 0)

    def test_plan(self):
        h = neotool.NeoHeader(psize=5 << 20, ssize=128 << 10, msize=128 << 10,
                              v1size=0x300001, v2size=0x80000, csize=32 << 20)
        plan = neotool.load_plan(h)
        self.assertEqual(plan["errors"], [])
        self.assertTrue(plan["bank_enable"])
        self.assertEqual(plan["p_mask_words"], (8 << 20) // 2 - 1)
        self.assertEqual(plan["v2_base"], 0x310000)          # aligné sur 64 Ko
        self.assertEqual(plan["c_mask_words"], (32 << 20) // 4 - 1)
        big = neotool.NeoHeader(csize=128 << 20)
        self.assertIn("C trop grand", neotool.load_plan(big)["errors"])


class BuildTests(TmpDir):
    def test_build_and_interleave(self):
        c1 = bytes(range(0, 16))
        c2 = bytes(range(100, 116))
        c3 = bytes([0xAA] * 16)
        c4 = bytes([0xBB] * 16)
        p1 = bytes(range(32))
        args = ["build", "-o", self.path("t.neo"),
                "--p", self.path("p1", p1),
                "--c", self.path("c1", c1), self.path("c2", c2), self.path("c3", c3), self.path("c4", c4),
                "--name", "TEST", "--ngh", "0x123"]
        self.assertEqual(neotool.main(args), 0)
        data = readb(self.path("t.neo"))
        h = neotool.NeoHeader.unpack(data)
        self.assertEqual(h.psize, 32)
        self.assertEqual(h.csize, 64)
        regions = {n: data[o:o + s] for n, o, s in h.regions()}
        self.assertEqual(regions["P"], p1)
        c = regions["C"]
        self.assertEqual(c[0:4], bytes([0, 100, 1, 101]))     # c1[0] c2[0] c1[1] c2[1]
        self.assertEqual(c[32:36], bytes([0xAA, 0xBB, 0xAA, 0xBB]))

    def test_c_must_be_pairs(self):
        with self.assertRaises(ValueError):
            neotool.interleave_c([self.path("c1", b"12")])

    def test_cr_mapping_matches_fpga(self):
        """Le FPGA réordonne un mot SDRAM {v3,v2,v1,v0} en CR = {v3,v1,v2,v0}.
        Vérifie que CR[7:0]=plan0 (c1 bas), CR[15:8]=plan1 (c1 haut),
        CR[23:16]=plan2 (c2 bas), CR[31:24]=plan3 (c2 haut)."""
        c1 = bytes([0x01, 0x02])   # mot c1 = 0x0201 (plan0=01, plan1=02)
        c2 = bytes([0x04, 0x08])   # mot c2 = 0x0804 (plan2=04, plan3=08)
        region = neotool.interleave_c([self.path("c1", c1), self.path("c2", c2)])
        w = struct.unpack("<I", region)[0]
        cr = (w & 0xFF000000) | ((w & 0xFF00) << 8) | ((w >> 8) & 0xFF00) | (w & 0xFF)
        self.assertEqual(cr, 0x08040201)


class FontTests(TmpDir):
    def test_fix_tile_layout(self):
        # pixel allumé en colonne 0 de la ligne 0 -> octet 16, quartet bas
        t = neotool.fix_tile([0x80] + [0] * 7)
        self.assertEqual(t[16], 0x01)
        self.assertEqual(sum(t), 1)
        # colonne 5 de la ligne 3 -> bloc colonnes 4-5 (octet 0+3), quartet haut
        t = neotool.fix_tile([0, 0, 0, 0x04, 0, 0, 0, 0])
        self.assertEqual(t[3], 0x10)
        # colonne 7 -> bloc 6-7 (octet 8+y), quartet haut
        t = neotool.fix_tile([0x01] + [0] * 7)
        self.assertEqual(t[8], 0x10)

    def test_psf1(self):
        glyphs = bytes(256 * 8)
        glyphs = bytearray(glyphs)
        glyphs[ord("A") * 8:ord("A") * 8 + 8] = bytes([0x18, 0x24, 0x42, 0x7E, 0x42, 0x42, 0x42, 0])
        psf = b"\x36\x04\x00\x08" + bytes(glyphs)
        out = self.path("s.bin")
        self.assertEqual(neotool.main(["font", self.path("f.psf", psf), "-o", out]), 0)
        rom = readb(out)
        self.assertEqual(len(rom), 8192)
        self.assertEqual(rom[ord("A") * 32:ord("A") * 32 + 32], neotool.fix_tile([0x18, 0x24, 0x42, 0x7E, 0x42, 0x42, 0x42, 0]))


class SecurityAndHexTests(TmpDir):
    def test_security_copy(self):
        prog = bytearray(0x1000)
        struct.pack_into(">I", prog, 0x182, 0x186)
        prog[0x186:0x400] = bytes((i * 7) & 0xFF for i in range(0x400 - 0x186))
        p_le = neotool.swap16(bytes(prog))
        h = neotool.NeoHeader(psize=len(p_le))
        game = self.path("g.neo", h.pack() + p_le)
        menu = self.path("m.bin", bytes(0x800))
        out = self.path("o.bin")
        self.assertEqual(neotool.main(["security", menu, game, "-o", out]), 0)
        res = readb(out)
        self.assertEqual(res[0x186:0x400], bytes(prog[0x186:0x400]))
        self.assertEqual(res[:0x186], bytes(0x186))

    def test_bramhex16(self):
        src = self.path("m.bin", bytes([0x4E, 0x45, 0x4F, 0x2D]))
        hi, lo = self.path("hi.hex"), self.path("lo.hex")
        self.assertEqual(neotool.main(["bramhex16", src, "--hi", hi, "--lo", lo, "--size", "8"]), 0)
        self.assertEqual(readt(hi).split(), ["4e", "4f", "00", "00"])
        self.assertEqual(readt(lo).split(), ["45", "2d", "00", "00"])

    def test_bramhex_overflow(self):
        src = self.path("x.bin", bytes(10))
        self.assertEqual(neotool.main(["bramhex", src, "-o", self.path("x.hex"), "--size", "8"]), 2)


if __name__ == "__main__":
    unittest.main()
