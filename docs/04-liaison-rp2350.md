# 4. Liaison RP2350 ↔ FPGA

Une liaison par FPGA (6 fils : `SCK`, `CS_N`, `IO[3:0]`), le RP2350 est
maître. Mode 0 : le maître change les données SCK bas, le FPGA échantillonne
au front montant. Octets transmis en deux quartets, **poids fort d'abord**.
Le FPGA sur-échantillonne la liaison à 133 MHz (SCK ≤ 20 MHz).

En lecture, le FPGA présente le quartet suivant ~25 ns après chaque front
montant ; le maître lit au front montant suivant.

## Trames

| Commande | Octets envoyés | Réponse |
|---|---|---|
| `0x01` REG_WR | reg, val[31:24], val[23:16], val[15:8], val[7:0] | — |
| `0x02` REG_RD | reg, 1 octet de retournement | val (4 octets, MSB d'abord) |
| `0x10` MEM_WR | espace, adr (4 octets), données… | — (adresse auto-incrémentée) |
| `0x11` MEM_RD | espace, adr (4 octets), 1 octet de retournement | données… (espaces BRAM) |

Les écritures mémoire ne sont acceptées qu'en **mode menu** (SDRAM libres).
Les octets sont regroupés en mots (16 ou 32 bits, octet d'adresse paire en
bits 7:0) puis écrits en SDRAM par une FIFO.

## Espaces mémoire

| Espace | PROG | CHA |
|---|---|---|
| 0 | SDRAM P (mots petit-boutistes, comme les fichiers) | SDRAM C (mots de 32 bits) |
| 1 | SDRAM V (octets) | SRAM : S en 0x00000, M1 en 0x80000 |
| 2 | boîte aux lettres (grand-boutiste, ordre 68000) | BRAM police du menu (S) |
| 3 | BRAM programme du menu (grand-boutiste) | BRAM pilote Z80 du menu (M1) |

## Registres

Communs :

| Reg | Accès | Contenu |
|---|---|---|
| 0x00 | L | identifiant : `NGP1` (PROG) / `NGC1` (CHA) |
| 0x01 | L/E | CTRL : bit0 ARM, bit1 FORCE (debug, mode jeu immédiat), bit3 BANK_EN (PROG) |
| 0x02 | L | STATUS (voir ci-dessous) |
| 0x10 | E | adresse de lecture de diagnostic (bit31 = SDRAM V sur PROG / SRAM sur CHA) |
| 0x11 | L | donnée de diagnostic |
| 0x12-0x14 | L | compteurs d'activité (PROG : /ROMOE, /PORTOE, ADPCM ; CHA : PCK1B, PCK2B, Z80) |

PROG : 0x03 masque P (mots), 0x04/0x05 base/masque V1, 0x06/0x07 base/masque
V2, 0x08 banque P courante, 0x09 acquittement de `LK_IRQ`.
STATUS PROG : bit0 SDRAM P prête, bit1 SDRAM P+V prêtes, bit2 chargeur au
repos, bit3 SDRAM V prête, bit4 mode jeu, bit5 IRQ, bit6 diag en cours,
bit7 débordement.

CHA : 0x03 masque C (mots 32 bits), 0x04 masque S, 0x05 masque M1.
STATUS CHA : bit0 SDRAM prête, bit1 chargeur au repos, bit2 mode jeu,
bit3 entrée MODE, bit4 débordement, bit5 diag en cours.

## Débit

Avec SCK = 18,75 MHz : 9,4 Mo/s par liaison. Le firmware lit la carte SD
pendant que le bloc précédent part en DMA (double tampon de 32 Ko). Un jeu de
40 Mo se charge en ~5 s, un très gros jeu (~90 Mo) en ~10-12 s, la carte SD
(SDIO 4 bits à 25 MHz, ~10 Mo/s) étant le facteur limitant.
