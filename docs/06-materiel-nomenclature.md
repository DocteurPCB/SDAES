# 6. Matériel et nomenclature

Objectif : **tout souder au fer** (panne fine, flux, tresse). Les boîtiers les
plus fins sont au pas de 0,5 mm (TQFP-144 et TSSOP-48), soudables par la
technique « drag soldering ». Aucun BGA ni QFN.

## Choix des composants

| Fonction | Composant proposé | Boîtier | Qté |
|---|---|---|---|
| FPGA | **Lattice iCE40HX4K-TQ144** (puce HX8K) | TQFP-144, 0,5 mm | 4 |
| Flash de configuration | W25Q32JVSS (SPI) | SOIC-8 208 mil | 4 |
| SDRAM P et V | **W9825G6KH-6** (256 Mbit x16) | TSOP-II 54, 0,8 mm | 2 |
| SDRAM C | **AS4C32M16SB-6** (512 Mbit x16) ou IS42S16320 | TSOP-II 54 | 1 |
| SRAM S + M1 | IS61WV10248EDBLL-10 (1 Mo x 8, 10 ns) | TSOP-II 44 | 1 |
| Tampons console → cartouche | 74LVC16244A (3,3 V, entrées tolérantes au 5 V) | TSSOP-48, 0,5 mm | 7 (PROG 3, CHA 4) |
| Tampons bidirectionnels (D, SDRAD/SDPAD) | 74LVC16245A (3,3 V) | TSSOP-48 | 2 (PROG) |
| Tampons cartouche → console | 74AHCT16244 (5 V) | TSSOP-48 | 2 (CHA) |
| Tampons 5 V (attentes, SDD) | 74AHCT125 / 74AHCT244 | TSSOP-14 / TSSOP-20 | 1 + 1 |
| Commande des /OE 5 V | 74LVC1G07 (drain ouvert) | SOT-23-5 | 2 (une par carte) |
| /OE du bus SDD | 74AHCT1G32 (OU, 5 V) | SOT-23-5 | 1 (CHA) |
| Microcontrôleur | **Raspberry Pi Pico 2** (module RP2350) | module à bords crénelés | 1 |
| Carte SD | support microSD push-push | CMS | 1 |
| Horloges | oscillateur 25 MHz 3,3 V | 3,2 x 2,5 mm | 4 |
| Alimentation par carte | AMS1117-3.3 (5 V → 3,3 V) ; AP2112K-1.2 (3,3 V → 1,2 V, cœurs iCE40) | SOT-223 / SOT-23-5 | 2 + 2 |

Remarques :
* La puce de l'iCE40HX4K-TQ144 est celle du HX8K ; la chaîne libre
  (Yosys + nextpnr + IceStorm) en exploite les 7 680 cellules. Les FPGA V, C
  et SM restent sous la capacité officielle du HX4K (3 520 cellules) ; le
  FPGA P, avec les protections, en utilise 3 539 : il **nécessite la chaîne
  libre** (l'outil Lattice iCEcube2 le refuserait). Piste de repli : retirer
  les compteurs de diagnostic ou la superposition KOF 98.
* Niveaux 5 V : tampons 74LVC en 3,3 V dans le sens console → cartouche et
  pour les bus bidirectionnels, 74AHCT en 5 V vers les puces vidéo et le
  Z80 (détails et raisons : `docs/02-signaux-connecteurs.md`, « Niveaux
  5 V »). Prendre des 74LVC de série « A » (fonction Ioff).
* L'iCE40 HX a besoin de 1,2 V (cœur), 3,3 V (E/S) et d'une tension VPP
  (2,5-3,3 V) ; un seul LDO 1,2 V par carte alimente ses deux FPGA.
* Le module Pico 2 évite de router la flash, le quartz et l'USB du RP2350.

## Estimation de coût (petite série, 10 cartouches, hors boîtier)

| Poste | Prix unitaire estimé |
|---|---|
| 4 x iCE40HX4K-TQ144 | 28-40 € |
| 3 x SDRAM + 1 SRAM | 10-14 € |
| 13 tampons de niveaux + 3 portes logiques | 6-9 € |
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
* Tampons près du connecteur de bord ; résistances de tirage 10 kΩ : vers
  3,3 V sur `XLAT_EN_N`, vers **5 V** sur `OE5_N`.
* Découplage des tampons 5 V sur le 5 V de la console, des 74LVC sur le
  3,3 V.
* Points de test : `PCK1B`, `PCK2B`, `LOAD`, `CA4`, `12M`, `/ROMOE`,
  `SDROE` ; connecteur de programmation SPI par carte.
* Consommation estimée : ~300 mA sous 5 V par carte.

## Fichiers de contraintes

`hardware/*.pcf` listent les ports de chaque FPGA ; les numéros de broches
seront renseignés lors du routage (voir `hardware/README.md`).
