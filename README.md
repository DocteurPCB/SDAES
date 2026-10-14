# SDAES — cartouche SD pour Neo Geo AES

Cartouche ouverte pour Neo Geo **AES** qui charge les jeux depuis une carte
microSD, dans l'esprit de la NeoSD : un menu s'affiche sur la console, on
choisit un fichier `.neo`, la cartouche le charge en mémoire et la console
redémarre dessus. **Tous les composants se soudent au fer** : aucun BGA ni
QFN.

> **État : conception + logiciel vérifiés en simulation, pas encore de
> prototype matériel.** Le code FPGA, le menu, le firmware et les outils sont
> écrits et testés automatiquement (voir plus bas) ; les circuits imprimés
> restent à dessiner. Le brochage AES est relevé sur le wiki neogeodev
> (`hardware/aes_connector.csv`) ; son orientation reste à confirmer sur une
> vraie cartouche (`docs/07-validation-et-feuille-de-route.md`).

## Principe

* **4 FPGA Lattice iCE40 en TQFP-144** (un par bus de la console : programme
  68000, son ADPCM, sprites, couche fixe + Z80) répondent en temps réel et
  remplacent les ROM et les puces de cartouche (NEO-273, NEO-ZMC2,
  NEO-PCM2, banques P et Z80). Chaîne de développement libre (Yosys,
  nextpnr).
* **3 SDRAM + 1 SRAM en TSOP** contiennent le jeu (jusqu'à 24 Mo de P,
  32 Mo de V, 64 Mo de C : tous les jeux commerciaux standards).
* Un **Raspberry Pi Pico 2 (RP2350, ~5 €)** lit la carte SD et charge les
  jeux (~9 Mo/s). Un Raspberry Pi « Linux » ne convient pas pour le bus
  lui-même (trop peu de GPIO, latence) : voir `docs/01-architecture.md`.
* Coût matière estimé : **≈ 70-95 € par cartouche** en petite série,
  montage à la main.

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `docs/` | architecture, signaux, timings, liaison, menu/firmware, nomenclature, validation |
| `hdl/` | Verilog des 4 FPGA (`prog/` : P et V, `cha/` : C et SM, `common/`) + bancs de test (`sim/`) |
| `menu/` | menu Neo Geo : programme 68000 (`68k/`) et pilote Z80 (`z80/`) |
| `firmware/rp2350/` | firmware du Pico 2 (SDK Pico + FatFs SDIO) et test sur PC |
| `protocol/` | protocole menu ↔ RP2350, partagé |
| `tools/` | `neotool.py` (.neo, police, BRAM, code de sécurité, bootlegs avec `mame_sets.py`), tests |
| `hardware/` | brochage du connecteur AES (`aes_connector.csv`), gabarits de contraintes FPGA (`.pcf`), futurs projets KiCad |

## Construire et tester

Dépendances (Ubuntu/Debian) : `iverilog`, `gcc-m68k-linux-gnu`, `z80asm`,
`console-setup-linux` (police), Python 3 ; facultatif : `yosys` +
`nextpnr-ice40` (ou `pip install yowasp-yosys yowasp-nextpnr-ice40`),
`pip install machine68k` (émulation du menu).

```
make                               # menu + fichiers d'init BRAM (hdl/build/*.hex)
make SECURITY_FROM=un_jeu.neo      # idem, avec le code de sécurité requis par le BIOS
make test                          # tous les tests (Python + simulations HDL)
make -C hdl lint pnr YOSYS=yowasp-yosys NEXTPNR=yowasp-nextpnr-ice40   # synthèse + placement-routage des 4 FPGA
python3 tools/neotool.py info jeu.neo
```

Résultats actuels de `make test` :

* 18 tests Python : outils (dont descriptions de protections), firmware sur PC (chargement complet d'un `.neo`
  et comparaison des images mémoire), menu 68000 exécuté dans un émulateur ;
* simulations HDL au niveau carte : `tb_prog` (FPGA P + V) et `tb_cha`
  (FPGA C + SM) en SUCCÈS ; lecture du programme 68000 en 79 ns (126 ns au
  pire cas) pour une limite estimée à ~125-150 ns ;
* placement-routage des 4 FPGA à 101-114 MHz pour 100 MHz visés.

## Documentation

1. [Architecture](docs/01-architecture.md)
2. [Signaux et translateurs](docs/02-signaux-connecteurs.md)
3. [Mémoires et timings](docs/03-memoire-et-timings.md)
4. [Liaison RP2350 ↔ FPGA](docs/04-liaison-rp2350.md)
5. [Menu et firmware](docs/05-menu-et-firmware.md)
6. [Matériel et nomenclature](docs/06-materiel-nomenclature.md)
7. [Validation et feuille de route](docs/07-validation-et-feuille-de-route.md)
8. [Cartouches protégées](docs/08-cartouches-protegees.md)

## Avertissements

* Aucun BIOS, ROM ou code SNK n'est inclus. Le code de sécurité exigé par le
  BIOS est recopié, à la construction, depuis un jeu que vous possédez.
* Protections : SMA (KOF 99, Garou, Metal Slug 3, KOF 2000), PVC (Metal
  Slug 5, SVC Chaos, KOF 2003), KOF 98, PRO-CT0 (Fatal Fury 2, Super
  Sidekicks), Metal Slug X (P1 corrigée au chargement), Metal Slug 5 Plus
  et les bootlegs de Metal Slug 5, SVC Chaos et KOF 2003 sont pris en
  charge (`neotool mame` fabrique leurs `.neo`)
  ([détails](docs/08-cartouches-protegees.md)) ; les tables SMA s'extraient
  du source de MAME avec `neotool.py sma-from-mame`. Banques de couche fixe
  NEO-CMC : KOF 2000, SVC, KOF 2003, Metal Slug 3/4 ; approchées pour Garou.
