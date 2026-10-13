# 6. Matériel et nomenclature

## Choix des composants

| Fonction | Composant proposé | Justification |
|---|---|---|
| FPGA (x2) | Lattice **ECP5 LFE5U-25F-6BG256C** | ~200 E/S, 56 BRAM, chaîne libre (Yosys + nextpnr), bon prix. Le 12F (même boîtier) suffit pour CHA mais pas pour PROG (BRAM du menu). |
| Flash de configuration (x2) | W25Q32JV (SPI) | démarrage du FPGA en ~30 ms |
| SDRAM (x4) | **W9825G6KH-6** (32 Mo, x16, 166 MHz) | très répandue et bon marché ; une seule référence partout |
| SRAM (CHA) | IS61WV10248EDBLL-10 (1 Mo x 8, 10 ns) | S et M1, accès simultanés fixe/Z80 sans rafraîchissement |
| Translateurs | 74LVC16T245 (x10), 74LVC8T245 (x1) | double alimentation 3,3 V / 5 V, sens commandable |
| Microcontrôleur | **Raspberry Pi Pico 2** (module, RP2350) | SD + FAT + menu pour ~5 € ; module = pas de conception RF/flash/USB |
| Carte SD | support microSD push-push | accessible par une ouverture du boîtier |
| Horloges | oscillateurs 25 MHz 3,3 V (x2) | PLL interne → 133 MHz |
| Alimentation (par carte) | buck 5 V → 3,3 V 1 A, LDO 2,5 V (VCCAUX), buck/LDO 1,1 V (cœur ECP5) | |

## Estimation de coût (petite série, 10 cartouches, hors boîtier)

| Poste | Prix unitaire estimé |
|---|---|
| 2 x ECP5-25F | 24-30 € |
| 4 x SDRAM | 6-10 € |
| SRAM 1 Mo | 3-4 € |
| 11 translateurs | 5-8 € |
| Pico 2 | 5 € |
| flash, oscillateurs, régulateurs, passifs, support SD, câble | 8-12 € |
| 2 circuits imprimés 4 couches, contacts dorés chanfreinés | 8-15 € |
| assemblage BGA (sous-traité) | 15-30 € |
| **Total** | **≈ 75-115 €** |

Les prix varient selon les distributeurs et les quantités ; à recalculer au
moment de la commande.

## Circuit imprimé

* **4 couches minimum** (BGA 256 au pas de 0,8 mm) : signal / masse /
  alimentations / signal.
* Contacts de bord **dorés (ENIG dur) et chanfreinés**, épaisseur à mesurer
  sur une cartouche AES réelle (≈ 1,6 mm), contour et position des
  détrompeurs relevés sur une carte d'origine.
* SDRAM au plus près du FPGA, longueurs de pistes appariées (± 5 mm) sur
  DQ/adresses, horloge SDRAM avec résistance série 22-33 Ω.
* Découplage soigné : 100 nF par broche d'alimentation + vrac 10 µF.
* Translateurs près du connecteur de bord ; résistance de tirage 10 kΩ vers
  3,3 V sur `XLAT_EN_N` (cartouche isolée tant que le FPGA démarre).
* Points de test : `PCK1B`, `PCK2B`, `LOAD`, `CA4`, `12M`, `/ROMOE`,
  `SDROE` + connecteur JTAG pour chaque FPGA.
* Consommation estimée : ~400 mA sous 5 V par carte.

## Fichiers de contraintes

`hardware/cha_pins.lpf` et `hardware/prog_pins.lpf` listent les ports des
FPGA avec les standards d'E/S ; les numéros de billes (`LOCATE`) seront
renseignés lors du routage.
