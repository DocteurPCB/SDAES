# 4. Liaison RP2350 ↔ FPGA

Deux bus de liaison de 5 fils (`SCK`, `IO[3:0]`) : un pour la carte PROG
(FPGA P et V), un pour la carte CHA (FPGA C et SM), avec une sélection
`CS_N` par FPGA. Le RP2350 est maître. Mode 0 : le maître change les données
SCK bas, le FPGA échantillonne au front montant. Octets transmis en deux
quartets, **poids fort d'abord**. Le FPGA sur-échantillonne la liaison à
100 MHz (SCK ≤ 20 MHz) ; seul le FPGA sélectionné pilote les lignes IO.

En lecture, le FPGA présente le quartet suivant ~40 ns après chaque front
montant ; le maître lit au front montant suivant (le firmware lit à ~5 MHz).

## Trames

| Commande | Octets envoyés | Réponse |
|---|---|---|
| `0x01` REG_WR | reg, val[31:24], val[23:16], val[15:8], val[7:0] | — |
| `0x02` REG_RD | reg, 1 octet de retournement | val (4 octets, MSB d'abord) |
| `0x10` MEM_WR | espace, adr (4 octets), données… | — (adresse auto-incrémentée) |
| `0x11` MEM_RD | espace, adr (4 octets), 1 octet de retournement | données… (boîte aux lettres) |

Les écritures mémoire ne sont acceptées qu'en **mode menu**. Les octets sont
regroupés en mots de 16 bits (octet d'adresse paire en bits 7:0) puis
écrits en SDRAM par une petite FIFO.

## Espaces mémoire

| Espace | FPGA P | FPGA V | FPGA C | FPGA SM |
|---|---|---|---|---|
| 0 | SDRAM P (mots petit-boutistes) | SDRAM V (octets) | SDRAM C | SRAM : S en 0x00000, M1 en 0x80000 |
| 2 | boîte aux lettres (ordre 68000) | — | — | BRAM police du menu |
| 3 | BRAM programme du menu (ordre 68000) | — | — | BRAM pilote Z80 du menu |
| 4 | table SMA (64 x 4 octets, grand-boutiste) | — | — | — |

## Registres

Communs aux 4 FPGA :

| Reg | Accès | Contenu |
|---|---|---|
| 0x00 | L | identifiant : `NGP2`, `NGV2`, `NGC2`, `NGS2` |
| 0x01 | L/E | CTRL : bit0 ARM, bit1 FORCE (debug), bit3 BANK_EN (P) |
| 0x02 | L | STATUS : bit0 mémoire prête ; chargeur au repos = bit2 (P) / bit1 (V, C, SM) ; mode jeu = bit3 (P) / bit2 (V, C, SM) |
| 0x10 | E | adresse de lecture de diagnostic (mots de 16 bits ; octets pour SM) |
| 0x11 | L | donnée de diagnostic |
| 0x12-0x14 | L | compteurs d'activité (P : /ROMOE, /PORTOE, anticipations réussies ; V : ADPCM-A, ADPCM-B ; C : PCK1B ; SM : PCK2B, Z80) |

Spécifiques : P : 0x03 masque P (mots), 0x04 cycles d'attente
{/PWAIT1, /PWAIT0, /ROMWAIT} (défaut 0b111 = pleine vitesse), 0x08 base P2 courante (mots), 0x09
acquittement de `LK_IRQ` ; protections (`hdl/prog/p_mapper.v`) : 0x0A mode
(bits 1:0 : 0 std, 1 SMA, 2 PVC ; bit 8 superposition), 0x0B registre de
banque SMA, 0x0C permutation des bits, 0x0D/0x0E adresse (bit 31 = actif) et
valeur de protection, 0x0F/0x15 adresses du générateur, 0x16 graine, 0x17
déclencheur, 0x18 codes {activation, retrait}, 0x19 adresse et 0x1A valeurs
de la superposition. Les adresses sont des index de mot A[19:1].
V : 0x04/0x05 base/masque V1, 0x06/0x07 base/masque V2. C : 0x03 masque C (mots de 32 bits). SM : 0x04 masque S,
0x05 masque M1, 0x06 banques de couche fixe NEO-CMC (bits 1-0 : 0, 1, 2 ; lecture bits 13-8 : dernière colonne reconnue).

## Débit

Avec SCK = 18,75 MHz : 9,4 Mo/s. Le firmware lit la carte SD pendant que le
bloc précédent part en DMA (double tampon de 32 Ko). Un jeu de 40 Mo se
charge en ~5 s, un très gros jeu (~90 Mo) en ~10-12 s, la carte SD (SDIO
4 bits à 25 MHz) étant le facteur limitant.
