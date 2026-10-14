"""
Test de bout en bout du firmware RP2350 sur PC : compile src/browser.c et
src/neo_loader.c avec des imitations de FatFs et de la liaison FPGA, charge un
.neo produit par neotool et vérifie les images mémoire et les registres.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FW = os.path.join(ROOT, "firmware", "rp2350")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import neotool  # noqa: E402


@unittest.skipUnless(shutil.which("gcc"), "gcc absent")

def forge_crc32(data, target):
    """4 octets à ajouter à data pour que crc32(data + x) == target."""
    tab = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        tab.append(c)
    rev = {t >> 24: i for i, t in enumerate(tab)}
    c = zlib.crc32(data) ^ 0xFFFFFFFF
    t = target ^ 0xFFFFFFFF
    idx = []
    for _ in range(4):
        i = rev[t >> 24]
        idx.append(i)
        t = ((t ^ tab[i]) << 8) & 0xFFFFFFFF
    out = bytearray()
    for i in reversed(idx):
        b = (c ^ i) & 0xFF
        out.append(b)
        c = (c >> 8) ^ tab[(c ^ b) & 0xFF]
    return bytes(out)

class FirmwareHostTest(unittest.TestCase):
    def test_load_neo(self):
        rnd = random.Random(1234)
        with tempfile.TemporaryDirectory() as d:
            sd = os.path.join(d, "sd")
            out = os.path.join(d, "out")
            os.makedirs(os.path.join(sd, "Jeux"))
            os.makedirs(out)
            with open(os.path.join(sd, "readme.txt"), "w") as f:
                f.write("x")
            with open(os.path.join(sd, "Jeux", "casse.neo"), "wb") as f:
                f.write(b"PAS UN NEO" + bytes(5000))

            def blob(n):
                return bytes(rnd.getrandbits(8) for _ in range(n))
            files = {}
            for name, n in (("p1", 3 << 20), ("s1", 128 << 10), ("m1", 64 << 10),
                            ("v1", 0x123457), ("v2", 0x40000), ("c1", 0x8000), ("c2", 0x8000)):
                files[name] = os.path.join(d, name)
                with open(files[name], "wb") as f:
                    f.write(blob(n))
            neo = os.path.join(sd, "Jeux", "test.neo")
            self.assertEqual(neotool.main([
                "build", "-o", neo, "--p", files["p1"], "--s", files["s1"], "--m", files["m1"],
                "--v1", files["v1"], "--v2", files["v2"], "--c", files["c1"], files["c2"],
                "--name", "SDAES TEST", "--ngh", "0x999"]), 0)

            # jeux protégés (contenu minimal)
            def small_neo(name, ngh, folder="Jeux"):
                pth = os.path.join(sd, folder, name + ".neo")
                with open(os.path.join(d, "p_small"), "wb") as f:
                    f.write(bytes(range(256)) * 16)
                self.assertEqual(neotool.main(["build", "-o", pth, "--p", os.path.join(d, "p_small"),
                                               "--name", name.upper(), "--ngh", hex(ngh)]), 0)
            small_neo("kof99", 0x251)
            # en-tête d'un vrai jeu SMA (zone P de 9 Mo) : refusé avant la lecture
            with open(os.path.join(sd, "Jeux", "kof99.neo"), "r+b") as f:
                f.seek(4)
                f.write((0x900000).to_bytes(4, "little"))
            small_neo("garoup", 0x253)          # prototype sans SMA, même NGH que garou
            small_neo("kof99b", 0x251)
            small_neo("garou", 0x253)
            small_neo("roi98", 0x242)
            def neo_with_p(name, ngh, pdata):
                with open(os.path.join(d, "p_" + name), "wb") as f:
                    f.write(pdata)
                self.assertEqual(neotool.main(["build", "-o", os.path.join(sd, "Jeux", name + ".neo"),
                                               "--p", os.path.join(d, "p_" + name),
                                               "--name", name.upper(), "--ngh", hex(ngh)]), 0)
            # Metal Slug 5 : original PVC (P de 8 Mo), Plus (P1 au CRC de MAME), bootleg
            neo_with_p("mslug5", 0x268, bytes(0x800000))
            p1 = bytes(range(256)) * (0x100000 // 256 - 1) + bytes(252)
            neo_with_p("ms5plus", 0x268, p1 + forge_crc32(p1, 0x106B276F))
            neo_with_p("mslug5b", 0x268, bytes(range(256)) * 16)
            # SVC Chaos et KOF 2003 : versions départagées par la taille de P
            neo_with_p("svcplus", 0x269, bytes(0x600000))
            neo_with_p("kof2003", 0x271, bytes(0x900000))
            neo_with_p("kf2k3bl", 0x271, bytes(0x800000))
            neo_with_p("kf2k3pl", 0x271, bytes(0x700000))
            small_neo("fatfury2", 0x047)
            # Metal Slug X : P1 avec deux séquences andi.w #1,D3 ; bne, dont une
            # à cheval sur deux blocs de 32 Ko (ordre petit-boutiste du .neo)
            msx = bytearray(0x10000)
            for a in (0x1000, 0x7FFC):
                msx[a:a + 8] = bytes([0x43, 0x02, 0x01, 0x00, 0x00, 0x66, 0x34, 0x12])
            with open(os.path.join(d, "p_msx"), "wb") as f:
                f.write(msx)
            self.assertEqual(neotool.main(["build", "-o", os.path.join(sd, "Jeux", "mslugx.neo"),
                                           "--p", os.path.join(d, "p_msx"),
                                           "--name", "MSLUGX", "--ngh", "0x250"]), 0)
            with open(os.path.join(sd, "Jeux", "kof99b.map"), "w") as f:
                f.write("# description de test\n"
                        "mapper = sma\n"
                        "bank_addr = 0x2ffff0\n"
                        "bank_bits = 14 6 8 10 12 5\n"
                        "bank_table = 0x000000 0x100000 0x200000\n"
                        "             0x300000 0x3cc000\n"
                        "prot = 0x2fe446 0x9a37\n"
                        "rng = 0x2ffff8 0x2ffffa\n")
            os.makedirs(os.path.join(sd, "SDAES"), exist_ok=True)
            bits = {}
            for i, n in enumerate(("p", "v", "c", "sm")):
                bits[n] = bytes((j * 7 + i * 31) & 0xFF for j in range(135100 + i))
                with open(os.path.join(sd, "SDAES", f"fpga_{n}.bin"), "wb") as f:
                    f.write(bits[n])
            with open(os.path.join(sd, "SDAES", "MAPPERS.TXT"), "w") as f:
                f.write("[kof98]\nngh = 0x242\n"
                        "overlay = 0x20aaaa 0x0090 0x00f0 0x000100 0x00c2 0x00fd\n"
                        "wait = 1 2\n"
                        "fix_bank = 2\n"
                        "[garou]\nngh = 0x253\nmapper = sma\nbank_addr = 0x2fffc0\n"
                        "bank_bits = 5 9 7 6 14 12\nbank_table = 0x000000 0x100000\n"
                        "prot = 0x2fe446 0x9a37\nrng = 0x2fffcc 0x2ffff0\n")

            exe = os.path.join(d, "fwtest")
            src = os.path.join(FW, "src")
            tst = os.path.join(FW, "test")
            subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                            "-I", tst, "-I", src, "-o", exe,
                            os.path.join(tst, "test_main.c"), os.path.join(tst, "fakes.c"),
                            os.path.join(src, "browser.c"), os.path.join(src, "neo_loader.c"),
                            os.path.join(src, "mapper.c"), os.path.join(src, "fpga_boot.c")],
                           check=True)
            env = dict(os.environ, SDAES_SD=sd, SDAES_OUT=out)
            r = subprocess.run([exe], env=env, capture_output=True, text=True)
            print(r.stdout, r.stderr)
            self.assertEqual(r.returncode, 0)
            self.assertIn("RESULTAT firmware : SUCCES", r.stdout)

            def rd(name):
                with open(os.path.join(out, name), "rb") as f:
                    return f.read()
            with open(neo, "rb") as f:
                data = f.read()
            h = neotool.NeoHeader.unpack(data)
            reg = {n: data[o:o + s] for n, o, s in h.regions()}
            plan = neotool.load_plan(h)

            for n in ("p", "v", "c", "sm"):
                self.assertEqual(rd(f"cfg_{n}.bin"), bits[n], f"bitstream {n}")

            self.assertEqual(rd("prog_p.bin"), reg["P"])
            v = rd("prog_v.bin")
            self.assertEqual(v[:len(reg["V1"])], reg["V1"])
            self.assertEqual(v[plan["v2_base"]:plan["v2_base"] + len(reg["V2"])], reg["V2"])
            self.assertEqual(rd("cha_c.bin"), reg["C"])
            sram = rd("cha_sram.bin")
            self.assertEqual(sram[:len(reg["S"])], reg["S"])
            self.assertEqual(sram[0x80000:0x80000 + len(reg["M"])], reg["M"])

            regs = dict(line.split("=") for line in rd("regs.txt").decode().split())
            regs = {k: int(x) for k, x in regs.items()}
            self.assertEqual(regs["p_mask"], plan["p_mask_words"])
            self.assertEqual(regs["v2_base"], plan["v2_base"])
            self.assertEqual(regs["v1_mask"], plan["v1_mask"])
            self.assertEqual(regs["v2_mask"], plan["v2_mask"])
            self.assertEqual(regs["c_mask"], plan["c_mask_words"])
            self.assertEqual(regs["s_mask"], plan["s_mask"])
            self.assertEqual(regs["m1_mask"], plan["m1_mask"])
            self.assertEqual(regs["prog_ctrl"], 1 | 8)       # armé + banques (P > 2 Mo)
            self.assertEqual(regs["cha_ctrl"], 1)


if __name__ == "__main__":
    unittest.main()
