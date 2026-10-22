"""
Exécute le binaire réel du menu 68000 (menu/68k) dans un émulateur 68000
(paquet Python "machine68k") avec une Neo Geo minimale simulée :
VRAM de la couche fixe, manette, palette, boîte aux lettres SDAES et un
RP2350 imité en Python. Vérifie l'écran affiché, la navigation et la
séquence de lancement (parking Z80, routine en RAM, code 0x5A5A).
"""
import os
import shutil
import struct
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "protocol"))

try:
    import machine68k as m68k
except ImportError:          # pragma: no cover
    m68k = None

# constantes du protocole (protocol/sdaes_mailbox.h)
MB = {}
with open(os.path.join(ROOT, "protocol", "sdaes_mailbox.h")) as f:
    for line in f:
        p = line.split()
        if len(p) >= 3 and p[0] == "#define":
            try:
                MB[p[1]] = int(p[2].rstrip("UL"), 0)
            except ValueError:
                pass

J_UP, J_DOWN, J_A, J_B = 0x01, 0x02, 0x10, 0x20


class FakeRP2350:
    """Imitation du firmware, côté protocole uniquement."""
    TREE = {"/": [(1, "Jeux"), (0, "aof"), (0, "kof98")],
            "/Jeux": [(0, "mslug")]}

    def __init__(self, rsp):
        self.rsp = rsp
        self.cwd = "/"
        self.loaded = None
        self.slow = False

    def w16(self, off, v):
        struct.pack_into(">H", self.rsp, off, v)

    def wstr(self, off, s):
        b = s.encode()[:63] + b"\0"
        self.rsp[off:off + len(b)] = b

    def handle(self, cmd_mem):
        cmd, seq, arg0 = struct.unpack_from(">HHI", cmd_mem, 0)
        self.w16(MB["MB_RSP_BUSYSEQ"], seq)
        kind, status = MB["KIND_NONE"], MB["ST_OK"]
        ents = self.TREE[self.cwd]
        if cmd == MB["CMD_LIST"]:
            page = ents[arg0:arg0 + MB["MB_PAGE_SIZE"]]
            for i, (t, n) in enumerate(page):
                off = MB["MB_RSP_ENTRIES"] + i * MB["MB_ENTRY_SIZE"]
                self.rsp[off] = t
                self.wstr(off + 1, n)
            self.w16(MB["MB_RSP_COUNT"], len(page))
            self.w16(MB["MB_RSP_TOTAL"], len(ents))
            self.wstr(MB["MB_RSP_PATH"], self.cwd)
            kind = MB["KIND_LIST"]
        elif cmd == MB["CMD_OPEN"]:
            t, n = ents[arg0]
            if t == 1:
                self.cwd = "/" + n
                kind = MB["KIND_DIR_CHANGED"]
            elif self.slow:                     # chargement long : réponse jamais publiée
                self.w16(MB["MB_RSP_PROGRESS"], 400)
                return
            else:
                self.loaded = n
                self.w16(MB["MB_RSP_PROGRESS"], 1000)
                self.wstr(MB["MB_RSP_MSG"], n.upper())
                kind = MB["KIND_GAME_READY"]
        elif cmd == MB["CMD_PARENT"]:
            self.cwd = "/"
            kind = MB["KIND_DIR_CHANGED"]
        elif cmd != MB["CMD_PING"]:
            status = MB["ST_ERR_ARG"]
        self.w16(MB["MB_RSP_STATUS"], status)
        self.w16(MB["MB_RSP_KIND"], kind)
        self.w16(MB["MB_RSP_SEQ"], seq)


class NeoGeoSim:
    def __init__(self, rom):
        self.mc = m68k.Machine(m68k.CPUType.M68000, 2048)   # 0x000000-0x1FFFFF
        self.mem = self.mc.mem
        self.mem.w_block(0, rom)
        self.vram = [0] * 0x10000
        self.vaddr, self.vmod = 0, 1
        self.pal = {}
        self.cmd = bytearray(0x100)
        self.rsp = bytearray(0x1000)
        self.rp = FakeRP2350(self.rsp)
        self.doorbell = False
        self.frames = 0
        self.pad = 0
        self.sound = []
        self.switched = None
        self.map(0x200000, 16, self.port_r16, self.port_w16)
        self.map(0x300000, 1, self.io_r16, self.io_w16)
        self.map(0x320000, 1, self.io_r16, self.io_w16)
        self.map(0x380000, 1, self.io_r16, self.io_w16)
        self.map(0x3A0000, 1, self.io_r16, self.io_w16)
        self.map(0x3C0000, 1, self.io_r16, self.io_w16)
        self.map(0x400000, 1, self.pal_r16, self.pal_w16)
        cpu = self.mc.cpu
        self.mem.w8(0x10FDAE, 2)          # BIOS_USER_REQUEST : titre
        cpu.w_pc(0x122)                   # point d'entrée USER de l'en-tête
        cpu.w_sp(0x10F300)
        cpu.w_sr(0x2700)

    def map(self, base, pages, r16, w16):
        def r8(a):
            v = r16(a & ~1)
            return (v & 0xFF) if a & 1 else (v >> 8)

        def w8(a, v):
            w16(a, v, byte=(a & 1) + 1)

        def r32(a):
            return (r16(a) << 16) | r16(a + 2)

        def w32(a, v):
            w16(a, v >> 16)
            w16(a + 2, v & 0xFFFF)
        self.mem.set_special_range_read_funcs(base, pages, r8, r16, r32)
        self.mem.set_special_range_write_funcs(base, pages, w8, lambda a, v: w16(a, v), w32)

    # zone 0x2xxxxx : boîte aux lettres + registres SDAES
    def port_r16(self, a):
        off = a - 0x200000
        if off == 0xFFFE0:
            return 0x0003 if self.doorbell else 0x0002
        return struct.unpack_from(">H", self.rsp, off & 0xFFE)[0]

    def port_w16(self, a, v, byte=0):
        off = a - 0x200000
        if off == 0xFFFE0:
            self.doorbell = True
        elif off == 0xFFFE2:
            if v == 0x5A5A:
                self.switched = self.mc.cpu.r_pc()
                self.mc.abort_execute()
        elif off < 0x100:
            if byte == 0:
                struct.pack_into(">H", self.cmd, off, v)
            else:
                self.cmd[off + byte - 1] = v & 0xFF

    def io_r16(self, a):
        if (a & ~1) == 0x300000:
            return ((~self.pad & 0xFF) << 8) | 0xFF
        return 0xFFFF

    def io_w16(self, a, v, byte=0):
        if a == 0x300001:
            self.frames += 1                 # chien de garde : une fois par "image"
        elif a & ~1 == 0x320000:
            self.sound.append(v & 0xFF)
        elif a == 0x3C0000:
            self.vaddr = v
        elif a == 0x3C0004:
            self.vmod = v
        elif a == 0x3C0002:
            self.vram[self.vaddr & 0xFFFF] = v
            self.vaddr = (self.vaddr + self.vmod) & 0xFFFF

    def pal_r16(self, a):
        return self.pal.get(a, 0)

    def pal_w16(self, a, v, byte=0):
        self.pal[a] = v

    def run_frames(self, n, pad=0):
        target = self.frames + n
        self.pad = pad
        budget = 2000 * (n + 10)                          # ~40 M cycles par image : bloqué
        while self.frames < target and self.switched is None:
            budget -= 1
            if budget < 0:
                raise RuntimeError(f"68000 bloqué en 0x{self.mc.cpu.r_pc():X}")
            self.mc.execute(20000)
            if self.doorbell:
                self.doorbell = False
                self.rp.handle(self.cmd)
        self.pad = 0

    def press(self, key):
        self.run_frames(3, key)
        self.run_frames(3)

    def screen(self):
        rows = []
        for y in range(32):
            rows.append("".join(chr(self.vram[0x7000 + x * 32 + y] & 0xFF or 0x20) for x in range(40)).rstrip())
        return rows


@unittest.skipUnless(m68k, "paquet machine68k absent (pip install machine68k)")
@unittest.skipUnless(shutil.which("m68k-linux-gnu-gcc"), "gcc-m68k-linux-gnu absent")
class MenuEmulationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["make", "-s", "-C", os.path.join(ROOT, "menu", "68k")], check=True)
        with open(os.path.join(ROOT, "menu", "68k", "menu_p.bin"), "rb") as f:
            cls.rom = f.read()

    def test_navigation_and_launch(self):
        sim = NeoGeoSim(self.rom)
        sim.run_frames(20)
        scr = sim.screen()
        print("\n".join(scr[:12]))
        self.assertIn("SDAES  -  NEO GEO SD", scr[2])
        self.assertEqual(scr[4].strip(), "/")
        self.assertTrue(scr[6].startswith(" >/Jeux"), scr[6])
        self.assertIn("aof", scr[7])
        self.assertIn("kof98", scr[8])
        self.assertIn("1/3", scr[26].replace(" ", ""))
        self.assertIn("A:LANCER", scr[27])
        # une Neo Geo n'affiche que les lignes 2 à 29 de la couche fixe
        for y in (0, 1, 30, 31):
            self.assertEqual(scr[y], "", f"ligne {y} invisible utilisée : {scr[y]!r}")
        self.assertEqual(sim.pal.get(0x400002), 0x7FFF)        # palette 0, couleur 1 : blanc

        # entre dans le dossier puis revient
        sim.press(J_A)
        sim.run_frames(5)
        scr = sim.screen()
        self.assertEqual(scr[4].strip(), "/Jeux")
        self.assertIn("mslug", scr[6])
        sim.press(J_B)
        sim.run_frames(5)
        self.assertIn("aof", sim.screen()[7])

        # descend sur "aof" et lance
        sim.press(J_DOWN)
        self.assertTrue(sim.screen()[7].startswith(" > aof"), sim.screen()[7])
        sim.press(J_A)
        sim.run_frames(40)
        self.assertEqual(sim.rp.loaded, "aof")
        self.assertIn(0x7F, sim.sound)                          # Z80 mis à l'abri
        self.assertIsNotNone(sim.switched, "pas de demande de bascule")
        self.assertTrue(0x101000 <= sim.switched < 0x101100,
                        f"bascule exécutée depuis 0x{sim.switched:X}, pas depuis la RAM")
        self.assertIn("AOF", "\n".join(sim.screen()))

    def test_messages_visible(self):
        """CHARGEMENT... et la barre de progression restent dans les lignes 2..29."""
        sim = NeoGeoSim(self.rom)
        sim.run_frames(20)
        sim.press(J_DOWN)
        sim.rp.slow = True                      # chargement en cours, pas de réponse
        sim.run_frames(3, J_A)
        sim.run_frames(10)
        scr = sim.screen()
        self.assertIn("CHARGEMENT", scr[28])
        self.assertIn("#", scr[16])
        for y in (0, 1, 30, 31):
            self.assertEqual(scr[y], "", f"ligne {y} invisible utilisée : {scr[y]!r}")



@unittest.skipUnless(m68k, "paquet machine68k absent (pip install machine68k)")
@unittest.skipUnless(shutil.which("m68k-linux-gnu-gcc"), "gcc-m68k-linux-gnu absent")
class TestRomEmulationTest(unittest.TestCase):
    """ROM de test (testrom/68k) : démarrage par le BIOS, contrôles affichés."""

    @classmethod
    def setUpClass(cls):
        subprocess.run(["make", "-s", "-C", os.path.join(ROOT, "testrom", "68k")], check=True,
                       stdout=subprocess.DEVNULL)
        with open(os.path.join(ROOT, "testrom", "68k", "test_p.bin"), "rb") as f:
            cls.rom = f.read()

    def boot(self, rom):
        sim = NeoGeoSim(rom)
        sim.run_frames(30)
        return sim

    def test_checks_pass(self):
        sim = self.boot(self.rom)
        scr = sim.screen()
        self.assertIn("ROM DE TEST", scr[3])
        self.assertTrue(scr[11].rstrip().endswith("OK"), scr[11])
        self.assertTrue(scr[13].rstrip().endswith("OK"), scr[13])
        n1 = int(scr[16].split()[1])
        sim.run_frames(10)
        self.assertGreater(int(sim.screen()[16].split()[1]), n1)
        # manette : la touche pressée change de palette (2 = allumée, 3 = éteinte)
        a = 0x7000 + (14 + 4 * 3) * 32 + 21                  # colonne du « A »
        self.assertEqual(sim.vram[a] >> 12, 3)
        sim.run_frames(2, J_A)
        sim.pad = J_A
        sim.run_frames(1, J_A)
        self.assertEqual(sim.vram[a] >> 12, 2)

    def test_corrupted_rom_detected(self):
        rom = bytearray(self.rom)
        i = rom.index(b"LE JEU A DEMARRE")                   # texte : le code reste intact
        rom[i] ^= 0x01                                       # un bit de la ROM P faux
        scr = self.boot(bytes(rom)).screen()
        self.assertIn("ERREUR", scr[11])


if __name__ == "__main__":
    unittest.main()
