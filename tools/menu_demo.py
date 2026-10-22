#!/usr/bin/env python3
"""Vidéo de démonstration du menu SDAES (MP4, ffmpeg requis).

    python3 tools/menu_demo.py [-o sdaes_menu_demo.mp4]

Le vrai binaire du menu (menu/68k/menu_p.bin) tourne dans l'émulateur
68000 des tests (tools/tests/test_menu_emu.py) ; un RP2350 imité répond
avec une carte SD fictive (attente de la carte, liste paginée, dossier,
chargement avec progression). Après la bascule, la ROM de test
(testrom/68k) démarre comme après le reset matériel (le logo du BIOS
n'est pas émulé). Chaque image de la couche fixe (lignes visibles 2 à
29) est dessinée avec la ROM S réelle (build/menu_s.bin, build/test_s.bin),
la touche pressée est rappelée sous l'écran.
"""
import argparse
import os
import struct
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_menu_emu as emu   # noqa: E402

MB = emu.MB
J_UP, J_DOWN, J_LEFT, J_RIGHT, J_A, J_B = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
KEYS = {J_UP: "HAUT", J_DOWN: "BAS", J_LEFT: "GAUCHE", J_RIGHT: "DROITE", J_A: "A", J_B: "B"}
SCALE, STRIP, FPS = 3, 72, 60
LABEL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

GAMES = ["aof", "aof2", "blazstar", "garou", "kof94", "kof95", "kof96", "kof97",
         "kof98", "kof2000", "lastblad", "lastbld2", "magdrop3", "matrim",
         "mslug", "mslug2", "mslug3", "mslugx", "neobombe", "ninjamas", "pulstar",
         "rbff2", "samsho2", "samsho4", "sdaes_test", "shocktro", "sengoku3", "twinspri", "wakuwak7"]


class DemoRP2350(emu.FakeRP2350):
    """Carte SD fictive, réponses différées image par image."""
    TREE = {"/": [(1, "Shoot'em up"), (1, "Puzzle")] + [(0, g) for g in GAMES],
            "/Shoot'em up": [(0, "blazstar"), (0, "pulstar"), (0, "shocktro")],
            "/Puzzle": [(0, "magdrop3"), (0, "neobombe")]}

    def __init__(self, rsp):
        super().__init__(rsp)
        self.boot = 100                 # images avant que la carte SD réponde
        self.loading = None             # (seq, nom, image courante, durée)
        self.w16(MB["MB_RSP_FWVER"], 12)
        for i, v in enumerate((41, 41, 40, 41)):
            self.w16(MB["MB_RSP_FPGAVER"] + 2 * i, v)

    def handle(self, cmd_mem):
        cmd, seq, arg0 = struct.unpack_from(">HHI", cmd_mem, 0)
        if cmd == MB["CMD_PING"] and self.boot > 0:
            return                       # carte SD pas encore prête
        if cmd == MB["CMD_OPEN"] and self.TREE[self.cwd][arg0][0] == 0:
            self.w16(MB["MB_RSP_BUSYSEQ"], seq)
            self.w16(MB["MB_RSP_PROGRESS"], 0)
            self.loading = [seq, self.TREE[self.cwd][arg0][1], 0, 150]
            return
        super().handle(cmd_mem)

    def tick(self):
        self.boot -= 1
        if self.loading:
            seq, name, n, dur = self.loading
            n += 1
            self.loading[2] = n
            self.w16(MB["MB_RSP_PROGRESS"], min(1000, n * 1000 // dur))
            if n >= dur:
                self.loading = None
                self.loaded = name
                self.wstr(MB["MB_RSP_MSG"], name.upper())
                self.w16(MB["MB_RSP_STATUS"], MB["ST_OK"])
                self.w16(MB["MB_RSP_KIND"], MB["KIND_GAME_READY"])
                self.w16(MB["MB_RSP_SEQ"], seq)


class DemoSim(emu.NeoGeoSim):
    """Couche fixe figée à chaque écriture du chien de garde (une par image) :
    l'image filmée ne tombe jamais au milieu d'un rafraîchissement."""
    def __init__(self, rom):
        self.snap = None
        super().__init__(rom)

    def io_w16(self, a, v, byte=0):
        if a == 0x300001:
            self.snap = self.vram[0x7000:0x7500]
        super().io_w16(a, v, byte)


def neo_rgb(v):
    dark = (v >> 15) & 1
    r = (((v >> 8) & 0xF) << 2) | (((v >> 14) & 1) << 1) | (1 - dark)
    g = (((v >> 4) & 0xF) << 2) | (((v >> 13) & 1) << 1) | (1 - dark)
    b = ((v & 0xF) << 2) | (((v >> 12) & 1) << 1) | (1 - dark)
    return tuple(c * 255 // 63 for c in (r, g, b))


class Renderer:
    def __init__(self, sim, srom):
        self.sim = sim
        self.srom = srom
        self.cache = {}
        self.label = ImageFont.truetype(LABEL_FONT, 30)

    def tile(self, code, colors):
        """Tuile 8x8 de la ROM S (format de tools/neotool.py fix_tile)."""
        k = (id(self.srom), code, colors)
        if k not in self.cache:
            im = Image.new("RGBA", (8, 8))
            px = im.load()
            t = self.srom[code * 32: code * 32 + 32]
            for blk, col in enumerate((4, 6, 0, 2)):
                for y in range(8):
                    v = t[blk * 8 + y]
                    for dx, c in ((0, v & 15), (1, v >> 4)):
                        if c:
                            px[col + dx, y] = colors[c] + (255,)
            self.cache[k] = im
        return self.cache[k]

    def frame(self, caption):
        s = self.sim
        im = Image.new("RGB", (320, 224), neo_rgb(s.pal.get(0x400000 + 0xFFF * 2, 0x8000)))
        pals = {}
        for x in range(40):
            for y in range(2, 30):
                v = (s.snap or s.vram[0x7000:0x7500])[x * 32 + y]
                if (v & 0xFF) == 0x20:
                    continue
                p = v >> 12
                if p not in pals:
                    pals[p] = tuple(neo_rgb(s.pal.get(0x400000 + (p * 16 + c) * 2, 0)) for c in range(16))
                g = self.tile(v & 0xFF, pals[p])
                im.paste(g, (x * 8, (y - 2) * 8), g)
        out = Image.new("RGB", (320 * SCALE, 224 * SCALE + STRIP), (24, 24, 28))
        out.paste(im.resize((320 * SCALE, 224 * SCALE), Image.NEAREST), (0, 0))
        if caption:
            d = ImageDraw.Draw(out)
            w = d.textlength(caption, font=self.label)
            d.text(((out.width - w) / 2, 224 * SCALE + 18), caption, font=self.label, fill=(230, 230, 230))
        return out


class Demo:
    def __init__(self, out):
        subprocess.run(["make", "-s", "-C", ROOT, "menu/68k/menu_p.bin", "testrom/68k/test_p.bin",
                        "build/menu_s.bin", "build/test_s.bin"], check=True, stdout=subprocess.DEVNULL)

        def rd(*p):
            return open(os.path.join(ROOT, *p), "rb").read()
        self.test_p, self.test_s = rd("testrom", "68k", "test_p.bin"), rd("build", "test_s.bin")
        self.sim = DemoSim(rd("menu", "68k", "menu_p.bin"))
        self.sim.rp = DemoRP2350(self.sim.rsp)
        self.r = Renderer(self.sim, rd("build", "menu_s.bin"))
        self.caption = ""
        self.done = 0
        w, h = 320 * SCALE, 224 * SCALE + STRIP
        self.ff = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out],
            stdin=subprocess.PIPE)

    def emit(self, img=None):
        self.ff.stdin.write((img or self.r.frame(self.caption)).tobytes())
        self.done += 1

    def frames(self, n, pad=0):
        """n images ; une image = une écriture du chien de garde par le menu."""
        s = self.sim
        s.pad = pad
        for _ in range(n):
            target = s.frames + 1
            while s.frames < target and s.switched is None:
                s.mc.execute(2000)
                if s.doorbell:
                    s.doorbell = False
                    s.rp.handle(s.cmd)
            s.rp.tick()
            self.emit()
        s.pad = 0

    def press(self, key, hold=6, after=30):
        self.caption = f"Manette : {KEYS[key]}"
        self.frames(hold, key)
        self.frames(after)
        self.caption = ""

    def cursor(self):
        """Entrée sous le curseur, lue dans le compteur « n/total » du menu."""
        return int(emu.NeoGeoSim.screen(self.sim)[26].split("/")[0]) - 1

    def start_game(self):
        """Reset matériel après la bascule : les ROM P et S du jeu remplacent
        celles du menu, puis le BIOS appelle USER (requête 2)."""
        s = self.sim
        s.mem.w_block(0, self.test_p)
        s.vram = [0x20] * 0x10000
        s.snap = None
        s.pal = {}
        s.switched = None
        s.mem.w8(0x10FDAE, 2)
        s.mc.cpu.w_pc(0x122)
        s.mc.cpu.w_sp(0x10F300)
        s.mc.cpu.w_sr(0x2700)
        self.r.srom = self.test_s

    def run(self):
        self.caption = "Mise sous tension : le RP2350 lit la carte SD"
        self.frames(150)
        self.caption = ""
        self.frames(60)
        for _ in range(4):
            self.press(J_DOWN, after=18)
        self.press(J_RIGHT, after=50)           # page suivante
        self.press(J_LEFT, after=40)
        for _ in range(4):
            self.press(J_UP, after=14)
        self.press(J_A, after=60)               # dossier "Shoot'em up"
        self.press(J_DOWN, after=20)
        self.press(J_B, after=50)               # retour
        self.press(J_RIGHT, after=30)          # page 2 (entrée 20)
        while self.sim.rp.TREE["/"][self.cursor()][1] != "sdaes_test":
            self.press(J_DOWN, after=12)
        self.frames(30)
        self.caption = "Chargement du jeu dans la SDRAM"
        self.frames(6, J_A)
        while self.sim.switched is None and self.done < 4000:
            self.frames(1)
        self.caption = "Bascule : la cartouche passe en mode jeu"
        last = self.r.frame(self.caption)
        for _ in range(45):
            self.emit(last)
        black = Image.new("RGB", last.size)
        for i in range(20):
            self.emit(Image.blend(last, black, (i + 1) / 20))
        self.caption = "Reset matériel, le BIOS démarre le jeu"
        cap = self.r.frame(self.caption)
        blank = Image.new("RGB", last.size)
        blank.paste(cap.crop((0, 224 * SCALE, cap.width, cap.height)), (0, 224 * SCALE))
        for _ in range(40):
            self.emit(blank)
        self.start_game()
        self.caption = "ROM de test SDAES : le jeu tourne"
        self.frames(150)
        for k in (J_UP, J_DOWN, J_LEFT, J_RIGHT, J_A, J_B):
            self.press(k, hold=14, after=10)
        self.caption = "ROM de test SDAES : le jeu tourne"
        self.frames(120)
        end = self.r.frame("")
        for i in range(30):
            self.emit(Image.blend(end, black, (i + 1) / 30))
        self.ff.stdin.close()
        self.ff.wait()
        print(f"{self.done} images ({self.done / FPS:.1f} s), jeu chargé : {self.sim.rp.loaded}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", default="sdaes_menu_demo.mp4")
    Demo(ap.parse_args().output).run()


if __name__ == "__main__":
    main()
