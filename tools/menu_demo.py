#!/usr/bin/env python3
"""Vidéo de démonstration du menu SDAES (MP4, ffmpeg requis).

    python3 tools/menu_demo.py [-o sdaes_menu_demo.mp4]

Le vrai binaire du menu (menu/68k/menu_p.bin) tourne dans l'émulateur
68000 des tests (tools/tests/test_menu_emu.py) ; un RP2350 imité répond
avec une carte SD fictive (attente de la carte, liste paginée, dossier,
chargement avec progression). Chaque image de la couche fixe (lignes
visibles 2 à 29) est dessinée avec une police VGA 8x8, la touche pressée
est rappelée sous l'écran.
"""
import argparse
import gzip
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
FONT = "/usr/share/consolefonts/Lat15-VGA8.psf.gz"
LABEL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

GAMES = ["aof", "aof2", "blazstar", "garou", "kof94", "kof95", "kof96", "kof97",
         "kof98", "kof2000", "lastblad", "lastbld2", "magdrop3", "matrim",
         "mslug", "mslug2", "mslug3", "mslugx", "neobombe", "ninjamas", "pulstar",
         "rbff2", "samsho2", "samsho4", "shocktro", "sengoku3", "twinspri", "wakuwak7"]


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


def psf_ascii(path):
    """Police PSF -> {code ASCII: 8 octets} (table Unicode si présente)."""
    raw = open(path, "rb").read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    if raw[:2] == b"\x36\x04":
        mode, size = raw[2], raw[3]
        n, off, uni = (512 if mode & 1 else 256), 4, mode & 2
    else:
        _, _, off, flags, n, size, _, _ = struct.unpack_from("<8I", raw)
        uni = flags & 1
    glyphs = [raw[off + i * size: off + (i + 1) * size] for i in range(n)]
    table = {c: glyphs[c] for c in range(min(n, 128))}
    if uni and raw[:2] == b"\x36\x04":
        p = off + n * size
        for i in range(n):
            while True:
                (u,) = struct.unpack_from("<H", raw, p)
                p += 2
                if u == 0xFFFF:
                    break
                if u == 0xFFFE:
                    continue
                if u < 128:
                    table[u] = glyphs[i]
    return {c: (g[:8] if size == 8 else bytes(g[(y * size) // 8] for y in range(8)))
            for c, g in table.items()}


def neo_rgb(v):
    dark = (v >> 15) & 1
    r = (((v >> 8) & 0xF) << 2) | (((v >> 14) & 1) << 1) | (1 - dark)
    g = (((v >> 4) & 0xF) << 2) | (((v >> 13) & 1) << 1) | (1 - dark)
    b = ((v & 0xF) << 2) | (((v >> 12) & 1) << 1) | (1 - dark)
    return tuple(c * 255 // 63 for c in (r, g, b))


class Renderer:
    def __init__(self, sim):
        self.sim = sim
        self.font = psf_ascii(FONT)
        self.cache = {}
        self.label = ImageFont.truetype(LABEL_FONT, 30)

    def glyph(self, ch, rgb):
        k = (ch, rgb)
        if k not in self.cache:
            im = Image.new("RGB", (8, 8))
            rows = self.font.get(ch, bytes(8))
            px = im.load()
            for y in range(8):
                for x in range(8):
                    if rows[y] & (0x80 >> x):
                        px[x, y] = rgb
            self.cache[k] = im
        return self.cache[k]

    def frame(self, caption):
        s = self.sim
        im = Image.new("RGB", (320, 224), neo_rgb(s.pal.get(0x400000 + 0xFFF * 2, 0x8000)))
        for x in range(40):
            for y in range(2, 30):
                v = s.vram[0x7000 + x * 32 + y]
                ch = v & 0xFF
                if ch in (0, 0x20):
                    continue
                rgb = neo_rgb(s.pal.get(0x400000 + ((v >> 12) * 16 + 1) * 2, 0x7FFF))
                im.paste(self.glyph(ch, rgb), (x * 8, (y - 2) * 8))
        out = Image.new("RGB", (320 * SCALE, 224 * SCALE + STRIP), (24, 24, 28))
        out.paste(im.resize((320 * SCALE, 224 * SCALE), Image.NEAREST), (0, 0))
        if caption:
            d = ImageDraw.Draw(out)
            w = d.textlength(caption, font=self.label)
            d.text(((out.width - w) / 2, 224 * SCALE + 18), caption, font=self.label, fill=(230, 230, 230))
        return out


class Demo:
    def __init__(self, out):
        subprocess.run(["make", "-s", "-C", os.path.join(ROOT, "menu", "68k")], check=True,
                       stdout=subprocess.DEVNULL)
        rom = open(os.path.join(ROOT, "menu", "68k", "menu_p.bin"), "rb").read()
        self.sim = emu.NeoGeoSim(rom)
        self.sim.rp = DemoRP2350(self.sim.rsp)
        self.r = Renderer(self.sim)
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
        for _ in range(16):
            self.press(J_DOWN, hold=4, after=8)
        self.frames(30)
        self.caption = "Chargement du jeu dans la SDRAM"
        self.frames(6, J_A)
        while self.sim.switched is None and self.done < 4000:
            self.frames(1)
        self.caption = "Bascule vers le jeu (code 0x5A5A)"
        last = self.r.frame(self.caption)
        for _ in range(90):
            self.emit(last)
        black = Image.new("RGB", last.size)
        for i in range(30):
            self.emit(Image.blend(last, black, (i + 1) / 30))
        self.ff.stdin.close()
        self.ff.wait()
        print(f"{self.done} images ({self.done / FPS:.1f} s), jeu chargé : {self.sim.rp.loaded}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", default="sdaes_menu_demo.mp4")
    Demo(ap.parse_args().output).run()


if __name__ == "__main__":
    main()
