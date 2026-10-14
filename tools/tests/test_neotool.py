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

    def test_c_align(self):
        big, small = bytes([1] * 8), bytes([2] * 2)
        region = neotool.interleave_c([self.path("a", big), self.path("b", big),
                                       self.path("c", small), self.path("d", small),
                                       self.path("e", big), self.path("f", big)], align=True)
        self.assertEqual(len(region), 16 + 16 + 16)          # paire 2 complétée à 16 octets
        self.assertEqual(region[16:20], bytes([2, 2, 2, 2]))
        self.assertEqual(region[20:32], bytes(12))
        self.assertEqual(region[32], 1)

    def test_descramble_mslug5b(self):
        s, v, c = neotool.descramble("mslug5b", bytes([0x01, 0x20, 0x80]), bytes([0x80, 0x80, 0x01, 0x01]),
                                     b"".join(bytes([k]) * 0x80000 for k in range(4)))
        self.assertEqual(s, bytes([0x20, 0x01, 0x80]))       # bitswap<8>(7,6,0,4,3,2,1,5)
        self.assertEqual(v, bytes([0x80, 0x01, 0x01, 0x04])) # octets impairs : bitswap<8>(3,2,4,1,5,0,6,7)
        self.assertEqual([c[k * 0x80000] for k in range(4)], [0, 2, 1, 3])   # A18/A19 échangées

    def test_descramble_ms5plus_and_from(self):
        base = self.path("base.neo")
        self.assertEqual(neotool.main(["build", "-o", base, "--p", self.path("p", bytes(64)),
                                       "--m", self.path("m", b"MMMM"), "--v1", self.path("v", b"VVVV"),
                                       "--c", self.path("c1", b"ab"), self.path("c2", b"cd"),
                                       "--ngh", "0x268"]), 0)
        s1 = bytes(range(32))
        out = self.path("ms5plus.neo")
        self.assertEqual(neotool.main(["build", "-o", out, "--from", base,
                                       "--p", self.path("pp", bytes([7]) * 64), "--s", self.path("s", s1),
                                       "--descramble", "ms5plus", "--ngh", "0x268"]), 0)
        data = readb(out)
        r = {n: data[o:o + sz] for n, o, sz in neotool.NeoHeader.unpack(data).regions()}
        self.assertEqual(r["S"][:16], s1[8:16] + s1[0:8])     # moitiés de 8 octets échangées
        self.assertEqual((r["P"], r["M"], r["V1"], r["C"]), (bytes([7]) * 64, b"MMMM", b"VVVV", b"acbd"))

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


MAME_SNIPPET_A = """
void sma_prot_device::kof99_bankswitch_w(uint16_t data)
{
	int bankaddress;
	static const int bankoffset[64] =
	{
		0x000000, 0x100000, 0x200000, 0x300000,
		0x3cc000, /* commentaire 0x999999 */ 0x4cc000,
	};

	/* unscramble bank number */
	data =
		(((data>>14)&1)<<0)+
		(((data>> 6)&1)<<1)+
		(((data>> 8)&1)<<2)+
		(((data>>10)&1)<<3)+
		(((data>>12)&1)<<4)+
		(((data>> 5)&1)<<5);

	bankaddress = 0x100000 + bankoffset[data];
}

void sma_prot_device::kof99_install_protection(cpu_device* maincpu, neogeo_banked_cart_device* bankdev)
{
	maincpu->space(AS_PROGRAM).install_write_handler(0x2ffff0, 0x2ffff1, write16_delegate(*this, FUNC(sma_prot_device::kof99_bankswitch_w)));
	maincpu->space(AS_PROGRAM).install_read_handler(0x2fe446, 0x2fe447, read16_delegate(*this, FUNC(sma_prot_device::prot_9a37_r)));
	maincpu->space(AS_PROGRAM).install_read_handler(0x2ffff8, 0x2ffff9, read16_delegate(*this, FUNC(sma_prot_device::sma_random_r)));
	maincpu->space(AS_PROGRAM).install_read_handler(0x2ffffa, 0x2ffffb, read16_delegate(*this, FUNC(sma_prot_device::sma_random_r)));
}
"""

MAME_SNIPPET_B = """
void sma_prot_device::garou_bankswitch_w(uint16_t data)
{
	static const int bankoffset[64] =
	{
		0x000000, 0x100000, 0x200000,
	};
	data = bitswap<6>(data, 12, 14, 6, 7, 9, 5);
	m_bank = 0x100000 + bankoffset[data];
}

void sma_prot_device::garou_install_protection(cpu_device* maincpu, neogeo_banked_cart_device* bankdev)
{
	maincpu->space(AS_PROGRAM).install_write_handler(0x2fffc0, 0x2fffc1, write16_delegate(*this, FUNC(sma_prot_device::garou_bankswitch_w)));
	maincpu->space(AS_PROGRAM).install_read_handler(0x2fffcc, 0x2fffcd, read16_delegate(*this, FUNC(sma_prot_device::sma_random_r)));
}
"""


class MapperTests(TmpDir):
    def test_parse_and_registers(self):
        text = ("[kof98]\nngh = 0x242\noverlay = 0x20aaaa 0x0090 0x00f0 0x000100 0x00c2 0x00fd\nwait = 1 2\nfix_bank = 2\npatch = mslugx\n"
                "[jeu]\nmapper = sma\nbank_addr = 0x2ffff0\nbank_bits = 14 6 8 10 12 5\n"
                "bank_table = 0x0 0x100000\n  0x3cc000\nprot = 0x2fe446 0x9a37\nrng = 0x2ffff8 0x2ffffa\n")
        maps = {m["name"]: m for m in neotool.parse_mappers(text)}
        self.assertEqual(maps["jeu"]["bank_table"], [0, 0x100000, 0x3CC000])
        regs = dict(neotool.mapper_registers(maps["jeu"]))
        self.assertEqual(regs[0x0A], 1)
        self.assertEqual(regs[0x0B], 0x7FFF8)
        self.assertEqual(regs[0x0C], 0x5CA86E)
        self.assertEqual(regs[0x0D], 0x80000000 | 0x7F223)
        self.assertEqual(regs[0x15], 0x80000000 | 0x7FFFD)
        self.assertEqual(regs[0x04], 7)                         # pleine vitesse par défaut
        ovl = dict(neotool.mapper_registers(maps["kof98"]))
        self.assertEqual((ovl[0x0A], ovl[0x17], ovl[0x18], ovl[0x19], ovl[0x1A]),
                         (0x100, 0x5555, 0x009000F0, 0x80, 0x00C200FD))
        self.assertEqual(ovl[0x04], 2)                          # ROM 1 cycle, PORT 2 cycles
        self.assertEqual((maps["kof98"]["fix_bank"], maps["jeu"]["fix_bank"]), (2, None))
        self.assertEqual((maps["kof98"]["patch"], maps["jeu"]["patch"]), ("mslugx", "none"))

    def test_parse_errors(self):
        with self.assertRaises(ValueError):
            neotool.parse_mappers("[x]\nmapper = sma\n")            # table manquante
        with self.assertRaises(ValueError):
            neotool.parse_mappers("[x]\nwait = 2 0\n")               # ROM : 1 cycle au plus
        with self.assertRaises(ValueError):
            neotool.parse_mappers("[x]\nbank_bits = 1 2 3\n")
        with self.assertRaises(ValueError):
            neotool.parse_mappers("[x]\ncle = 1\n")

    def test_extract_sma(self):
        text = neotool.extract_sma(MAME_SNIPPET_A + MAME_SNIPPET_B)
        maps = {m["name"]: m for m in neotool.parse_mappers(text)}
        k = maps["kof99"]
        self.assertEqual(k["ngh"], 0x251)
        self.assertEqual(k["bank_addr"], 0x2FFFF0)
        self.assertEqual(k["bank_bits"], [14, 6, 8, 10, 12, 5])
        self.assertEqual(k["bank_table"], [0, 0x100000, 0x200000, 0x300000, 0x3CC000, 0x4CC000])
        self.assertEqual(k["prot"], (0x2FE446, 0x9A37))
        self.assertEqual(k["rng"], [0x2FFFF8, 0x2FFFFA])
        g = maps["garou"]
        self.assertEqual(g["bank_bits"], [5, 9, 7, 6, 14, 12])   # bitswap : poids fort d'abord
        self.assertEqual(g["bank_addr"], 0x2FFFC0)
        self.assertEqual(g["rng"], [0x2FFFCC])

    def test_cli(self):
        src = self.path("prot_sma.cpp", (MAME_SNIPPET_A + MAME_SNIPPET_B).encode())
        out = self.path("MAPPERS.TXT")
        self.assertEqual(neotool.main(["sma-from-mame", src, "-o", out]), 0)
        self.assertEqual(neotool.main(["mapper", out, "--ngh", "0x251"]), 0)
        mp = self.path("jeu.map", b"mapper = pvc\n")
        self.assertEqual(neotool.main(["mapper", mp]), 0)
