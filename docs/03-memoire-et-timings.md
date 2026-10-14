# 3. Mémoires, correspondances d'adresses et timings

## Plan mémoire

| Contenu | FPGA | Composant | Taille max |
|---|---|---|---|
| P | P | SDRAM 256 Mbit x16 (W9825G6KH-6) | 24 Mo (+ 8 Ko de RAM PVC) |
| V1 (ADPCM-A) + V2 (ADPCM-B) | V | SDRAM 256 Mbit x16 | 32 Mo au total |
| C | C | SDRAM 512 Mbit x16 (AS4C32M16SB-6) | 64 Mo |
| S | SM | SRAM 1 Mo x 8, 0x00000 | 512 Ko |
| M1 | SM | SRAM, 0x80000 | 512 Ko |
| menu P (8 Ko) + boîte aux lettres (4 Ko) | P | BRAM | — |
| police S (8 Ko) + pilote Z80 (2 Ko) | SM | BRAM | — |

Chaque région a un **masque d'adresse** (puissance de 2 supérieure − 1) :
les jeux dont la taille n'est pas une puissance de 2 sont répliqués comme
sur une vraie cartouche.

## Correspondances d'adresses

Les points issus de la rétro-ingénierie publique sont regroupés dans les
sections « CARTOGRAPHIE » de `hdl/cha/cha_c_core.v` et
`hdl/cha/cha_sm_core.v`, pour être corrigés en un seul endroit.

* **P** : 0x000000-0x0FFFFF → mots 0x000000-0x07FFFF ; 0x200000-0x2FFFFF →
  mots `base P2` + A. La base P2 vaut 0x100000 octets au départ et change
  selon le schéma de la cartouche : banques de 1 Mo (standard, écriture dans
  0x2FFFF0-0x2FFFFF), table SMA ou registre PVC, voir
  `docs/08-cartouches-protegees.md`.
  **Placement SDRAM** : P1 seul dans la banque SDRAM 0, la zone banquée dans
  les banques 1-3. Les deux candidats d'une adresse 68000 (P1 ou P2) sont
  ainsi dans deux banques différentes et se lisent en parallèle.
* **C** : mot de 32 bits = `{tuile[19:0], CA4, ligne[3:0]}` avec tuile[15:0]
  = P[15:0], ligne = P[19:16], tuile[19:16] = P[23:20] (verrou PCK1B, front
  montant). Conforme aux pages « NEO-273 » et « P bus » du wiki neogeodev
  (P15..P0 = A20..A5, P19..P16 = A3..A0, P23..P20 = A24..A21 ; CA4 = A4,
  hors bus P). En
  SDRAM x16, les deux moitiés (CA4 = 0/1) sont 4 mots de 16 bits de la même
  ligne, lus en une seule activation.
* **Bus CR du ZMC2** : CR[7:0] = plan 0, CR[15:8] = plan 1 (ROM C impaire),
  CR[23:16] = plan 2, CR[31:24] = plan 3 (ROM C paire). Le `.neo` stocke
  c1/c2 entrelacés octet par octet ; le FPGA réordonne `{v3,v2,v1,v0}` →
  `{v3,v1,v2,v0}`.
* **S** : octet = `{P[11:0], P15, 2H1, P[14:12]}`, soit tuile sur 12 bits,
  demi-tuile, colonne (2H1 = A3, hors bus P), ligne sur 3 bits (verrou
  PCK2B, front montant ; d'après les pages « NEO-273 » et « P bus » du
  wiki).
* **ZMC2** : LOAD verrouille le mot C au front descendant de 12M, les pixels
  changent aussi au front descendant (page « NEO-ZMC2 »).
* **Recoupements avec du Verilog existant** : le NEO-273 de SNKVerilog
  (Furrtek, dépôt neogeodev) donne exactement les correspondances C et S
  ci-dessus ; le sérialiseur ZMC2 du cœur MiSTer NeoGeo (Kyuusaku) est
  identique à `hdl/cha/zmc2_dot.v` (décalages, table EVEN/H) et cadencé au
  front descendant de 12M.
* **M1** : fenêtres Z80 0x0000-0x7FFF fixe, 0x8000/16 Ko, 0xC000/8 Ko,
  0xE000/4 Ko, 0xF000/2 Ko ; banque = registre B lors d'un `IN (C)` sur les
  ports 0x0B/0x0A/0x09/0x08. Valeurs initiales 2/6/0x0E/0x1E (identité).
* **ADPCM** : front montant de *MPX = partie basse de l'adresse, front
  descendant = partie haute (rôle du NEO-PCM2).

## Lecture anticipée du programme (FPGA P)

À 100 MHz, une lecture SDRAM classique déclenchée par /ROMOE prendrait
~110 ns, trop près de la limite. Le FPGA P lance donc la lecture **dès que
l'adresse 68000 change** (le 68000 la pose ~40-70 ns avant /ROMOE), et lit
**les deux candidats en parallèle** (zone P1 et zone banquée P2, dans deux
banques SDRAM). Quand /ROMOE ou /PORTOE arrive, la donnée est en général
déjà prête. Le rafraîchissement SDRAM n'est déclenché que juste après une
lecture terminée (le cycle 68000 suivant est loin).

## Budgets de temps

Horloge système 100 MHz, SDRAM CL2, horloge SDRAM = horloge système
inversée, donnée lue capturée sur le front descendant. Résultats de
**simulation** (`make -C hdl sim`, modèle SDRAM tAC 5,4 ns / tOH 2,7 ns) :

| Accès | Contrainte (estimée) | SDAES, simulé |
|---|---|---|
| 68000 : /OE → donnée, code (adresse 40 ns avant /OE) | ~125-150 ns | **79 ns** (100 % d'anticipations réussies, rafraîchissements compris) |
| 68000 : alternance code P1 / données P2 | idem | **88 ns** |
| 68000 : pire cas (adresse en même temps que /OE) | idem | **126 ns** |
| PCK1B → deux mots C prêts | avant le LOAD suivant (~300 ns) | **125 ns** |
| PCK2B → deux octets S prêts | ~300 ns | **140 ns** (dont 20 ns pour la banque CMC) |
| Z80 : lecture M1 | ~300 ns | **70 ns** |
| ADPCM : /SDROE → donnée | plusieurs centaines de ns | **98 ns** |

S'y ajoutent les délais des translateurs (~4-6 ns par traversée) et des
pistes. `RD_LAT` et la phase de l'horloge SDRAM sont paramétrables.

## Placement-routage (nextpnr, broches non affectées)

| FPGA | Cellules logiques | BRAM | E/S | Fréquence max |
|---|---|---|---|---|
| P (avec protections) | 3 751 | 28 / 32 | 94 | 103 MHz |
| V | 1 881 | 0 | 80 | 101 MHz |
| C | 1 785 | 0 | 89 | 107 MHz |
| SM (avec banques CMC) | 1 621 | 20 / 32 | 92 | 114 MHz |

La marge à 100 MHz est faible (1 à 18 %) et dépend de la graine de
placement ; l'affectation réelle des broches la fera varier. Si besoin, la
PLL peut être réglée à 90 MHz : les latences augmentent d'environ 10 % et
restent dans les budgets ci-dessus, sauf le pire cas 68000 (~140 ns), qui
devient limite.

## Points à valider en priorité sur matériel

1. Correspondances C et S (conformes au wiki, à confirmer à l'analyseur).
2. Sens du sérialiseur ZMC2 (ordre des pixels, rôle de EVEN et H).
3. Fronts de démultiplexage ADPCM.
4. Délai réel entre l'adresse 68000 et /ROMOE (efficacité de l'anticipation).
5. Marge réelle entre PCK1B et LOAD.
6. Réinitialisation par le chien de garde sur AES.
