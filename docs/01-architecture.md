# 1. Architecture

## Objectif

Une cartouche pour Neo Geo **AES** qui lit les jeux au format `.neo` (le
format des cartouches NeoSD, produit par NeoBuilder ou `tools/neotool.py`)
depuis une carte microSD, avec un menu affiché par la console elle-même,
**entièrement soudable à la main** (aucun boîtier BGA ni QFN sur les
circuits imprimés).

## Pourquoi des FPGA, et où intervient le Raspberry Pi

Une cartouche Neo Geo n'est pas un simple bus ROM : la console lit **cinq
mémoires en parallèle et en permanence**, chacune avec son propre bus.

| Mémoire | Lue par | Contrainte | Taille max (jeux commerciaux) |
|---|---|---|---|
| P (programme) | 68000 à 12 MHz | réponse en ~125-150 ns après /ROMOE | ~9 Mo (avec banques) |
| C (sprites) | LSPC via NEO-ZMC2 | un mot de 32 bits toutes les ~333 ns | 64 Mo |
| S (couche fixe) | LSPC | un octet toutes les ~333 ns | 128 Ko |
| M1 (son) | Z80 à 4 MHz | ~300 ns | 128-512 Ko |
| V (échantillons) | YM2610 (2 bus multiplexés) | quelques centaines de ns | 16 Mo et plus |

Soit environ **150 signaux à 5 V**, des réponses en ~100 ns et jusqu'à
~100 Mo de mémoire rapide. Un Raspberry Pi « Linux » (28 GPIO, latences de
l'ordre de la microseconde) ou un RP2350 seul (48 GPIO, 520 Ko de RAM) ne
peuvent pas servir ces bus. Il faut de la logique programmable et de la
SDRAM.

Le Raspberry Pi est utilisé là où il est rentable : un **Raspberry Pi Pico 2
(RP2350, ~5 €)** gère la carte SD (FAT/exFAT, SDIO 4 bits), le dialogue
avec le menu et le chargement des jeux.

## Pourquoi quatre FPGA

Les FPGA soudables à la main (boîtier TQFP-144, pas de 0,5 mm) offrent au
plus ~95-107 entrées/sorties. Il en faudrait ~175 pour une carte entière.
SDAES utilise donc **un FPGA par bus de la console** :

| FPGA | Carte | Rôle (puces d'origine remplacées) | Mémoire |
|---|---|---|---|
| **P** | PROG | ROM P + registre de banque ; menu ; boîte aux lettres ; commande MODE | SDRAM 32 Mo (TSOP-54) |
| **V** | PROG | ROM V + NEO-PCM2 (démultiplexage ADPCM-A/B) | SDRAM 32 Mo (TSOP-54) |
| **C** | CHA | ROM C + NEO-273 (verrou PCK1B) + sérialiseur NEO-ZMC2 | SDRAM 64 Mo (TSOP-54) |
| **SM** | CHA | ROM S + NEO-273 (verrou PCK2B) + ROM M1 + banques Z80 | SRAM 1 Mo (TSOP-44) |

FPGA retenu : **Lattice iCE40 (puce HX8K) en TQFP-144**, vendu sous la
référence iCE40HX4K-TQ144. Chaîne de développement libre (Yosys, nextpnr,
IceStorm) ; chaque conception utilise moins de 2 400 cellules logiques et
tient même dans la capacité officielle du HX4K (3 520).

```
                ┌──────────────────────── Carte CHA ─────────────────────────┐
 Connecteur     │ translateurs  ┌──────────┐  SDRAM 64 Mo (C)                   │
 CHA  ◄────────►│ 5 V <-> 3,3 V ◄►│ FPGA C   │◄►                                 │
 (P bus, PCK*,  │               └──────────┘                                    │
  ZMC2, Z80)    │               ┌──────────┐  SRAM 1 Mo (S + M1)                │
                │              ◄►│ FPGA SM  │◄►                                 │
                │               └──────────┘                                    │
                │        bus de liaison CHA ▲         ┌───────────────┐          │
                │                           └─────────│ Pico 2 RP2350 │          │
                │   microSD (SDIO) ◄────────────────► │ firmware      │──┐       │
                └─────────────────────────────────────┴───────────────┴──┼───────┘
                                                      câble inter-cartes │
                ┌──────────────────────── Carte PROG ────────────────────┼───────┐
 Connecteur     │ translateurs  ┌──────────┐  SDRAM 32 Mo (P)            │       │
 PROG ◄────────►│ 5 V <-> 3,3 V ◄►│ FPGA P   │◄►      ◄── bus de liaison ─┘       │
 (68000,        │               └──────────┘──► MODE (vers V, C, SM)            │
  YM2610)       │               ┌──────────┐  SDRAM 32 Mo (V)                    │
                │              ◄►│ FPGA V   │◄►                                  │
                │               └──────────┘                                    │
                └───────────────────────────────────────────────────────────────┘
```

## Deux modes de fonctionnement

1. **Mode menu** (à la mise sous tension) : les FPGA présentent à la console
   un petit « jeu » stocké dans leurs mémoires internes : programme 68000 du
   menu (FPGA P), police de la couche fixe et pilote Z80 minimal (FPGA SM) ;
   les sprites sont transparents. Les SDRAM/SRAM sont libres pour le
   chargement.
2. **Mode jeu** : les FPGA servent les données depuis les SDRAM/SRAM.

Le menu (68000) et le RP2350 dialoguent par une **boîte aux lettres** de 4 Ko
dans la zone 0x200000 du FPGA P (voir `docs/05-menu-et-firmware.md`).

## Séquence de lancement d'un jeu

1. Le joueur choisit un fichier `.neo` ; le menu envoie `CMD_OPEN`.
2. Le RP2350 lit le fichier et l'écrit dans les mémoires des quatre FPGA
   (~9 Mo/s, barre de progression), règle les masques d'adresse, puis
   **arme** les FPGA.
3. Le menu met le Z80 à l'abri (boucle en RAM), copie une routine de 40 octets
   en RAM de travail et l'exécute : elle écrit `0x5A5A` en `0x2FFFE2`.
4. Le FPGA P passe en mode jeu et le signale aux trois autres (ligne MODE).
5. La routine arrête de nourrir le **chien de garde** : la console se
   réinitialise complètement (68000, Z80, YM2610) et le BIOS démarre le jeu
   comme une cartouche normale. (Secours : saut au point d'entrée du BIOS.)

Retour au menu : bouton de la cartouche (le RP2350 désarme les FPGA, le jeu
plante et le chien de garde redémarre la console sur le menu) ou extinction.
