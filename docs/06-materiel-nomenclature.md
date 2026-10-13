# 6. Matériel et nomenclature

Objectif : **tout souder au fer** (panne fine, flux, tresse). Les boîtiers les
plus fins sont au pas de 0,5 mm (TQFP-144 et TSSOP-48), soudables par la
technique « drag soldering ». Aucun BGA ni QFN.

## Choix des composants

| Fonction | Composant proposé | Boîtier | Qté |
|---|---|---|---|
| FPGA | **Lattice iCE40HX4K-TQ144** (puce HX8K) | TQFP-144, 0,5 mm | 4 |
| Flash de configuration | W25Q16JV (SPI) | SOIC-8 | 4 |
| SDRAM P et V | **W9825G6KH-6** (256 Mbit x16) | TSOP-II 54, 0,8 mm | 2 |
| SDRAM C | **AS4C32M16SB-6** (512 Mbit x16) ou IS42S16320 | TSOP-II 54 | 1 |
| SRAM S + M1 | IS61WV10248EDBLL-10 (1 Mo x 8, 10 ns) | TSOP-II 44 | 1 |
| Translateurs | 74LVC16T245 | TSSOP-48, 0,5 mm | 11 |
| Translateur SDD | 74LVC8T245 | TSSOP-24 | 1 |
| Microcontrôleur | **Raspberry Pi Pico 2** (module RP2350) | module à bords crénelés | 1 |
| Carte SD | support microSD push-push | CMS | 1 |
| Horloges | oscillateur 25 MHz 3,3 V | 3,2 x 2,5 mm | 4 |
| Alimentation par carte | régulateur 5 V → 3,3 V 1 A (buck ou LDO SOT-223) ; LDO 1,2 V (cœurs iCE40) | SOT-223 / SOT-23-5 | 2 + 2 |

Remarques :
* La puce de l'iCE40HX4K-TQ144 est celle du HX8K ; la chaîne libre peut
  utiliser 7 680 cellules, mais SDAES n'en utilise que 2 317 au plus, donc
  la capacité officielle (3 520) suffit.
* L'iCE40 HX a besoin de 1,2 V (cœur), 3,3 V (E/S) et d'une tension VPP
  (2,5-3,3 V) ; un seul LDO 1,2 V par carte alimente ses deux FPGA.
* Le module Pico 2 évite de router la flash, le quartz et l'USB du RP2350.

## Estimation de coût (petite série, 10 cartouches, hors boîtier)

| Poste | Prix unitaire estimé |
|---|---|
| 4 x iCE40HX4K-TQ144 | 28-40 € |
| 3 x SDRAM + 1 SRAM | 10-14 € |
| 12 translateurs | 5-8 € |
| Pico 2 | 5 € |
| flash, oscillateurs, régulateurs, passifs, support SD, câble | 10-14 € |
| 2 circuits imprimés 4 couches, contacts dorés chanfreinés | 8-15 € |
| **Total (montage à la main)** | **≈ 70-95 €** |

Les prix varient selon les distributeurs et les quantités ; à recalculer au
moment de la commande.

## Circuit imprimé

* **4 couches recommandées** (SDRAM à 100 MHz) : signal / masse /
  alimentations / signal. Une version 2 couches est envisageable mais
  risquée pour les SDRAM.
* Contacts de bord **dorés (ENIG dur) et chanfreinés**, épaisseur à mesurer
  sur une cartouche AES réelle (≈ 1,6 mm), contour et détrompeurs relevés sur
  une carte d'origine.
* Chaque SDRAM au plus près de son FPGA, longueurs appariées (± 5 mm) ;
  horloge SDRAM avec résistance série 22-33 Ω.
* Découplage : 100 nF par broche d'alimentation + 10 µF par rail et par FPGA.
* Translateurs près du connecteur de bord ; résistance de tirage 10 kΩ vers
  3,3 V sur `XLAT_EN_N`.
* Points de test : `PCK1B`, `PCK2B`, `LOAD`, `CA4`, `12M`, `/ROMOE`,
  `SDROE` ; connecteur de programmation SPI par carte.
* Consommation estimée : ~300 mA sous 5 V par carte.

## Fichiers de contraintes

`hardware/*.pcf` listent les ports de chaque FPGA ; les numéros de broches
seront renseignés lors du routage (voir `hardware/README.md`).
