# SDAES — cartouche SD pour Neo Geo AES

Cartouche ouverte pour Neo Geo **AES** qui charge les jeux depuis une carte
microSD, dans l'esprit de la NeoSD : un menu s'affiche sur la console, on
choisit un fichier `.neo`, la cartouche le charge en mémoire et la console
redémarre dessus.

> **État : conception + logiciel vérifiés en simulation, pas encore de
> prototype matériel.** Le code FPGA, le menu, le firmware et les outils sont
> écrits et testés automatiquement (voir plus bas) ; les circuits imprimés
> restent à dessiner et plusieurs détails du brochage AES doivent être
> confirmés sur une vraie cartouche
> (`docs/07-validation-et-feuille-de-route.md`).

## Principe

* **2 FPGA Lattice ECP5** (un par carte, comme les cartes PROG et CHA d'une
  cartouche d'origine) répondent aux bus de la console en temps réel et
  remplacent les ROM et les puces de cartouche (NEO-273, NEO-ZMC2,
  NEO-PCM2, banques P et Z80).
* **4 SDRAM de 32 Mo + 1 SRAM** contiennent le jeu (jusqu'à 32 Mo de P,
  32 Mo de V, 64 Mo de C : tous les jeux commerciaux standards).
* Un **Raspberry Pi Pico 2 (RP2350, ~5 €)** lit la carte SD et charge les
  jeux (~9 Mo/s par liaison). Un Raspberry Pi « Linux » ne convient pas pour
  le bus lui-même (trop peu de GPIO, latence) : voir `docs/01-architecture.md`.
* Coût matière estimé : **≈ 75-115 € par cartouche** en petite série.

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `docs/` | architecture, signaux, timings, liaison, menu/firmware, nomenclature, validation |
| `hdl/` | Verilog des FPGA (`cha/`, `prog/`, `common/`) + bancs de test (`sim/`) |
| `menu/` | menu Neo Geo : programme 68000 (`68k/`) et pilote Z80 (`z80/`) |
| `firmware/rp2350/` | firmware du Pico 2 (SDK Pico + FatFs SDIO) et test sur PC |
| `protocol/` | protocole menu ↔ RP2350, partagé |
| `tools/` | `neotool.py` (.neo, police, BRAM, code de sécurité), tests |
| `hardware/` | gabarits de contraintes FPGA, futurs projets KiCad |

## Construire et tester

Dépendances (Ubuntu/Debian) : `iverilog`, `gcc-m68k-linux-gnu`, `z80asm`,
`console-setup-linux` (police), Python 3 ; facultatif : `yosys` (ou
`pip install yowasp-yosys`), `pip install machine68k` (émulation du menu).

```
make                               # menu + fichiers d'init BRAM (hdl/build/*.hex)
make SECURITY_FROM=un_jeu.neo      # idem, avec le code de sécurité requis par le BIOS
make test                          # tous les tests (Python + simulations HDL)
make -C hdl lint YOSYS=yowasp-yosys   # synthèse ECP5 des deux FPGA
python3 tools/neotool.py info jeu.neo
```

Résultats actuels de `make test` :

* 14 tests Python : outils, firmware sur PC (chargement complet d'un `.neo`
  et comparaison des images mémoire), menu 68000 exécuté dans un émulateur ;
* simulations HDL : `tb_cha` et `tb_prog` en SUCCÈS, avec latences
  simulées de 53 à 95 ns pour des contraintes de ~140 à 300 ns.

## Documentation

1. [Architecture](docs/01-architecture.md)
2. [Signaux et translateurs](docs/02-signaux-connecteurs.md)
3. [Mémoires et timings](docs/03-memoire-et-timings.md)
4. [Liaison RP2350 ↔ FPGA](docs/04-liaison-rp2350.md)
5. [Menu et firmware](docs/05-menu-et-firmware.md)
6. [Matériel et nomenclature](docs/06-materiel-nomenclature.md)
7. [Validation et feuille de route](docs/07-validation-et-feuille-de-route.md)

## Avertissements

* Aucun BIOS, ROM ou code SNK n'est inclus. Le code de sécurité exigé par le
  BIOS est recopié, à la construction, depuis un jeu que vous possédez.
* Les jeux à protection matérielle spécifique (SMA, PVC, banques de fixe
  CMC50) ne sont pas encore pris en charge.
