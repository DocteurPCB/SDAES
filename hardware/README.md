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

## Schémas KiCad (cartes PROG et CHA)

Les schémas sont **générés** à partir d'une description Python des deux
cartes (`hardware/gen/boards.py`), puis vérifiés par KiCad :

```
sudo apt-get install kicad kicad-symbols kicad-footprints     # KiCad 7
python3 hardware/gen/boards.py --check --pdf
```

* `hardware/kicad/prog/`, `hardware/kicad/cha/` : projets KiCad (une
  feuille par bloc : connecteur et alimentations, tampons de niveaux,
  FPGA, mémoires, RP2350 et carte SD).
* `hardware/kicad/sdaes_prog.pdf`, `sdaes_cha.pdf` : schémas en PDF.
* `hardware/kicad/sdaes.kicad_sym`, `sdaes.pretty` : symboles et empreintes
  propres au projet (connecteur de bord AES, Pico 2, 16244, SRAM).
* `--check` réexporte la netlist avec `kicad-cli` et la compare à la
  description : elle doit être **identique** (aucun réseau oublié ni
  ajouté). Aucun réseau ne doit toucher une seule broche.

Chaque broche porte une étiquette globale au nom de son signal (pas de
fils) : `AES_xxx` côté console (5 V), `xxx` côté FPGA, `P_`, `V_`, `C_`,
`SM_` pour les signaux locaux d'un FPGA. Les broches des FPGA viennent des
`.pcf` ci-dessus. Brochages hors bibliothèque KiCad relevés dans les fiches
TI (SN74LVC16244A, SN74AHCT16244 : identiques), ISSI (IS61WV10248EDBLL) et
Raspberry Pi (Pico 2).

| Carte | Composants | Réseaux |
|---|---|---|
| PROG | 124 | 274 |
| CHA | 138 | 293 |

Par FPGA : flash SPI W25Q32JV (+ connecteur 2 x 3 pour `iceprog`, le FPGA
tenu en reset par CRESET), oscillateur 25 MHz, filtre RC des deux PLL
(100 Ω, 10 µF, 100 nF), découplage 100 nF par broche d'alimentation, LED.
Alimentations par carte : AMS1117-3.3 (5 V → 3,3 V) et AP2112K-1.2
(3,3 V → 1,2 V).

### Contours et connecteur de bord

`python3 hardware/gen/outline.py` (module Python de KiCad) écrit
`hardware/kicad/{prog,cha}/{prog,cha}.kicad_pcb` : contour, deux trous de
10 mm pour les plots de la coque et connecteur J1 placé. Cotes reprises des
cartes AES de jwestfall69 (`neogeo-diag-aes-prog`, `neogeo-diag-aes-cha`,
fabriquées et testées, domaine public ; ce sont des cartes de test du Z80,
reprises pour leur mécanique seulement), identiques à 0,01 mm près, et
recoupées sur la photo de la carte SNK NEO-AEG PROG-EP du wiki :

| | PROG | CHA |
|---|---|---|
| Corps | 174,0 x 115 mm | 173,0 x 115 mm |
| Languette (centrée) | 129,2 x 19 mm | 129,2 x 19 mm |
| Encoches 12 x 2,5 mm (bord supérieur) | à 36 mm de chaque bord | à 5,45 mm de chaque bord |
| Trous Ø 10 mm | ±45 mm de l'axe, 11,75 mm au-dessus de l'épaulement | idem |

Contacts : 1,5 x 10 mm au pas de 2,54 mm, centre à 7,1 mm du bord ; A1..A50
(repères T) sur la face composants, B1..B50 sur l'autre ; vu côté
composants, languette en bas, A1 et B1 à droite. Fabrication : 1,6 mm,
finition ENIG, contacts dorés chanfreinés à 45°. La carte CHA se loge
derrière la carte PROG : hauteur des composants limitée (jwestfall69 :
un support DIP ordinaire + EPROM est trop haut, un support bas passe).

**À vérifier avant le routage** : boucles audio L/R reliées par
des résistances de 0 Ω (révision NEO-AES de la console), valeurs du filtre
PLL (note Lattice sur l'iCE40), courant réel des régulateurs.

## À faire

1. ~~Brochage et cotes des cartes AES PROG/CHA~~ (fait, voir plus haut).
2. ~~Schémas~~, ~~contours~~ (faits).
3. Routage 4 couches, contacts dorés chanfreinés.
4. `make -C hdl bits` (bitstreams avec les broches réelles).
