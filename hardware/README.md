# Matériel

Contraintes des 4 FPGA iCE40HX4K-TQ144 avec les **vrais numéros de
broches**, produites par `hardware/gen/fpga_pins.py` (ne pas modifier les
`.pcf` à la main) :

```
python3 hardware/gen/fpga_pins.py
make -C hdl pnr YOSYS=yowasp-yosys NEXTPNR=yowasp-nextpnr-ice40
```

| FPGA | Carte | E/S utilisées | Fréquence max (broches réelles) |
|---|---|---|---|
| P | PROG | 94 / 107 | 103,3 MHz |
| V | PROG | 80 / 107 | 102,2 MHz |
| C | CHA | 89 / 107 | 107,6 MHz |
| SM | CHA | 92 / 107 | 108,8 MHz |

## Règles de placement des broches

* Signaux du connecteur (via les tampons de niveaux) sur les bancs 3 et 2
  (côtés gauche et bas du boîtier) ; mémoire, liaison RP2350, MODE et LED
  sur les bancs 0 et 1.
* `CLK25` sur l'entrée globale GBIN3 (broche 93).
* Broche 129 réservée à une sortie : la PLL du haut, utilisée par le
  design, réquisitionne son chemin d'entrée (de même la broche 49 pour la
  PLL du bas). Broches SPI 67, 68, 70, 71 réservées à la flash.
* Signaux utilisés **comme horloges** dans le HDL — à placer sur des
  entrées globales (GBIN) : `CLK_12M`, `PCK1B` (FPGA C) ; `PCK2B` (SM) ;
  `SDRMPX`, `SDPMPX` (V).
* SDRAM regroupée sur un même côté du boîtier, `SD_CLK` en sortie DDR
  (SB_IO) avec résistance série.
* Bancs d'E/S en 3,3 V ; VPP de l'iCE40 relié au 3,3 V.

## À faire

1. Relever le brochage et les cotes des cartes AES PROG/CHA sur une
   cartouche réelle (voir `docs/02-signaux-connecteurs.md`).
2. Schémas : alimentations, FPGA + flash SPI, SDRAM, SRAM, tampons de niveaux,
   Pico 2 + microSD (CHA), câble inter-cartes.
3. Routage 4 couches, contacts dorés chanfreinés.
4. `make -C hdl bits` (bitstreams avec les broches réelles).
