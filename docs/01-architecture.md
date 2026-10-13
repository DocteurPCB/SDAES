# 1. Architecture

## Objectif

Une cartouche pour Neo Geo **AES** (console de salon) qui lit les jeux au
format `.neo` (le format des cartouches NeoSD, produit par NeoBuilder ou
`tools/neotool.py`) depuis une carte microSD, avec un menu affiché par la
console elle-même.

## Pourquoi un FPGA, et où intervient le Raspberry Pi

Une cartouche Neo Geo n'est pas un simple bus ROM : la console lit **cinq
mémoires en parallèle et en permanence**, chacune avec son propre bus.

| Mémoire | Lue par | Débit / contrainte | Taille max (jeux commerciaux) |
|---|---|---|---|
| P (programme) | 68000 à 12 MHz | réponse en < ~140 ns après /ROMOE | ~9 Mo (avec banques) |
| C (sprites) | LSPC via NEO-ZMC2 | un mot de 32 bits toutes les ~333 ns, en continu | 64 Mo |
| S (couche fixe) | LSPC | un octet toutes les ~333 ns | 128 Ko (512 Ko avec banques) |
| M1 (son) | Z80 à 4 MHz | ~300 ns | 128-512 Ko |
| V (échantillons) | YM2610 (2 bus multiplexés) | quelques centaines de ns | 16 Mo et plus |

Il faut donc environ **150 signaux** de bus à 5 V, des temps de réponse de
l'ordre de 100 ns et jusqu'à ~100 Mo de mémoire rapide.

* Un **Raspberry Pi classique (Zero/3/4/5)** ne convient pas : 28 GPIO
  seulement, Linux introduit des latences de l'ordre de la microseconde, et
  les GPIO ne tiennent pas ces débits sur 150 lignes.
* Un **RP2040/RP2350 (Pico)** seul non plus : 30 à 48 GPIO, 264-520 Ko de RAM.
* Un **FPGA** sait répondre à tous ces bus simultanément, de façon
  déterministe. Les données vivent dans des SDRAM bon marché.

Le Raspberry Pi est utilisé là où il est le plus rentable : un **Raspberry Pi
Pico 2 (RP2350, ~5 €)** gère la carte SD (FAT/exFAT, SDIO 4 bits), le
dialogue avec le menu et le chargement des jeux dans les SDRAM. Cela évite un
processeur logiciel (soft-core) dans le FPGA et un développement complexe.

## Découpage matériel

Une cartouche AES contient **deux circuits imprimés** enfichés dans deux
connecteurs distincts de la console : **PROG** (68000 + son ADPCM) et
**CHA** (graphismes + Z80). SDAES reprend ce découpage : chaque carte a son
propre FPGA et ses propres mémoires ; elles sont reliées par un petit câble
(liaison de chargement + signal de bascule menu/jeu).

```
                ┌───────────────────────── Carte CHA ──────────────────────────┐
 Connecteur     │  translateurs   ┌───────────────┐   2 x SDRAM 32 Mo (C, 32 b) │
 CHA  ◄────────►│  5 V <-> 3,3 V ◄►│ FPGA ECP5-25F │◄► SRAM 1 Mo (S + M1)       │
 (P bus, PCK*,  │                 │  NEO-273      │                             │
  ZMC2, Z80)    │                 │  NEO-ZMC2     │◄──── liaison 4 bits ────┐   │
                │                 │  M1 + banques │                         │   │
                │                 └───────────────┘    ┌───────────────┐    │   │
                │                                      │ Pico 2 RP2350 │────┘   │
                │   microSD (SDIO) ◄──────────────────►│ firmware      │────┐   │
                └──────────────────────────────────────┴───────────────┴────┼───┘
                                                         câble inter-cartes │
                ┌───────────────────────── Carte PROG ──────────────────────┼───┐
 Connecteur     │  translateurs   ┌───────────────┐   SDRAM 32 Mo (P)      │   │
 PROG ◄────────►│  5 V <-> 3,3 V ◄►│ FPGA ECP5-25F │◄► SDRAM 32 Mo (V)      │   │
 (68000,        │                 │ ROM P+banques │                        │   │
  YM2610)       │                 │ NEO-PCM2      │◄── liaison 4 bits ─────┘   │
                │                 │ menu + BAL    │──► MODE (vers CHA)         │
                │                 └───────────────┘                            │
                └──────────────────────────────────────────────────────────────┘
```

## Deux modes de fonctionnement

1. **Mode menu** (à la mise sous tension) : les FPGA présentent à la console
   un petit « jeu » stocké dans leurs mémoires internes (BRAM) : le programme
   68000 du menu, une police pour la couche fixe, un pilote Z80 minimal ; les
   sprites (C) sont transparents. Les SDRAM sont libres : le RP2350 peut y
   écrire un jeu.
2. **Mode jeu** : les FPGA servent les données depuis les SDRAM.

Le menu (68000) et le RP2350 dialoguent par une **boîte aux lettres** de 4 Ko
dans la zone 0x200000 de la carte PROG (voir `docs/05-menu-et-firmware.md`).

## Séquence de lancement d'un jeu

1. Le joueur choisit un fichier `.neo` ; le menu envoie `CMD_OPEN`.
2. Le RP2350 lit le fichier et l'écrit dans les SDRAM (≈ 9 Mo/s par liaison,
   affichage d'une barre de progression), règle les masques d'adresse, puis
   **arme** les deux FPGA.
3. Le menu met le Z80 à l'abri (boucle en RAM), copie une routine de 40 octets
   en RAM de travail et l'exécute : elle écrit `0x5A5A` en `0x2FFFE2`.
4. Le FPGA PROG passe en mode jeu et le signale à la carte CHA (ligne MODE).
5. La routine arrête de nourrir le **chien de garde** : la console se
   réinitialise complètement (68000, Z80, YM2610) et le BIOS démarre le jeu
   comme une cartouche normale. (Secours : saut au point d'entrée du BIOS.)

Retour au menu : bouton de la cartouche (le RP2350 désarme les FPGA, le jeu
plante et le chien de garde redémarre la console sur le menu) ou extinction.
