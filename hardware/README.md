# Matériel

Ce dossier accueillera les projets KiCad des deux cartes (PROG et CHA).
Pour l'instant il contient les gabarits de contraintes FPGA, générés à partir
des tops Verilog :

```
python3 tools/gen_lpf.py hdl/cha/cha_top.v  cha_top  hardware/cha_pins.lpf
python3 tools/gen_lpf.py hdl/prog/prog_top.v prog_top hardware/prog_pins.lpf
```

| Carte | E/S FPGA utilisées | Disponibles (LFE5U-25F, BG256) |
|---|---|---|
| CHA | 176 | 197 |
| PROG | 161 | 197 |

## Règles de placement des broches

* `CLK25` sur une entrée d'horloge primaire (PCLK) proche de la PLL.
* Signaux utilisés **comme horloges** dans le HDL — à placer sur des
  broches PCLK : `CLK_12M`, `PCK1B`, `PCK2B` (CHA) ; `SDRMPX`, `SDPMPX`
  (PROG).
* Un banc d'E/S par SDRAM si possible ; `SD_CLK`/`PS_CLK`/`VS_CLK` en
  sortie DDR (ODDRX1F) avec résistance série.
* Tous les bancs en VCCIO = 3,3 V.

## À faire

1. Relever le brochage et les cotes des cartes AES PROG/CHA sur une
   cartouche réelle (voir `docs/02-signaux-connecteurs.md`).
2. Schémas : alimentations, FPGA + flash + JTAG, SDRAM, SRAM,
   translateurs, Pico 2 + microSD (CHA), câble inter-cartes.
3. Routage 4 couches, contacts dorés chanfreinés.
4. Compléter les `LOCATE` des fichiers `.lpf`.
