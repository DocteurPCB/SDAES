# 2. Signaux des connecteurs et tampons de niveaux

> **Source.** Le brochage ci-dessous est relevé sur les images de la page
> « AES cartridge pinout » du wiki neogeodev ; les rôles des signaux viennent
> des pages « Signals », « NEO-273 », « NEO-ZMC2 », « P bus » et
> « Wait cycle ». La table complète, contact par contact, est dans
> `hardware/aes_connector.csv` ; les gabarits `hardware/*.pcf` indiquent pour
> chaque port FPGA le contact AES correspondant. **Numérotation et sens
> physique** recoupés avec les cartes AES de jwestfall69
> (`neogeo-diag-aes-prog`, `neogeo-diag-aes-cha`, fabriquées et testées,
> domaine public ; cartes de test du Z80 : seules leur mécanique et la
> position des contacts servent de référence, pas leurs choix électriques) :
> A1..A50 sur la face composants (« dessus »), B1..B50 sur
> l'autre ; vu côté composants, languette vers le bas, A1 et B1 sont à
> droite, l'un derrière l'autre (sérigraphie « A1 » des cartes SNK NEO-AEG).
> Les images du wiki montrent la face A dans l'ordre inverse (A50 en haut).

Chaque carte se connecte à la console par un connecteur de bord (contacts
dorés, chanfreinés) : **2 x 50 contacts au pas de 2,54 mm**, carte de
1,6 mm (100 contacts par carte, 200 pour la cartouche). Alimentation :
+5 V (VCC, 3 contacts par face) et masse (2 contacts à chaque extrémité de
chaque face). Sur l'AES, /ROMOE est au contact 22 de la face dessous de la
carte PROG et 4MB au contact 48 (le wiki signale que certains brochages
publiés intervertissent ces deux signaux).

## Brochage du connecteur AES

Positions 1 à 50 = numéros A/B officiels (repères T1..T50 / B1..B50 des
schémas). Les signaux
« / » sont actifs à 0.

| Pos. | PROG A (dessus) | PROG B (dessous) | CHA A (dessus) | CHA B (dessous) |
|---|---|---|---|---|
| 1 | GND | GND | GND | GND |
| 2 | GND | GND | GND | GND |
| 3 | D0 | A1 | PCK1B | FIXD0 |
| 4 | D1 | A2 | PCK2B | FIXD1 |
| 5 | D2 | A3 | 12M | FIXD2 |
| 6 | D3 | A4 | 2H1 | FIXD3 |
| 7 | D4 | A5 | EVEN | FIXD4 |
| 8 | D5 | A6 | H | FIXD5 |
| 9 | D6 | A7 | LOAD | FIXD6 |
| 10 | D7 | A8 | CA4 | FIXD7 |
| 11 | D8 | A9 | P0 | P1 |
| 12 | D9 | A10 | P2 | P3 |
| 13 | D10 | A11 | P4 | P5 |
| 14 | D11 | A12 | P6 | P7 |
| 15 | D12 | A13 | P8 | P9 |
| 16 | D13 | A14 | P10 | P11 |
| 17 | D14 | A15 | P12 | P13 |
| 18 | D15 | A16 | P14 | P15 |
| 19 | R/W | A17 | P16 | P17 |
| 20 | /AS | A18 | P18 | P19 |
| 21 | /ROMOEU | A19 | P20 | P21 |
| 22 | /ROMOEL | /ROMOE | P22 | P23 |
| 23 | L OUT | R OUT | L OUT | R OUT |
| 24 | L IN | R IN | L IN | R IN |
| 25 | VCC | VCC | VCC | VCC |
| 26 | VCC | VCC | VCC | VCC |
| 27 | VCC | VCC | VCC | VCC |
| 28 | /PORTOEU | /ROMWAIT | /SDRD0 | NC |
| 29 | /PORTOEL | /PDTACK | /SDRD1 | NC |
| 30 | /PORTWEU | /PWAIT0 | SDA0 | DOTA |
| 31 | /PORTWEL | /PWAIT1 | SDA1 | DOTB |
| 32 | 68KCLKB | SDRAD0 | SDA2 | GAD0 |
| 33 | RESET | SDRAD1 | SDA3 | GAD1 |
| 34 | SDPAD0 | SDRAD2 | SDA4 | GAD2 |
| 35 | SDPAD1 | SDRAD3 | SDA5 | GAD3 |
| 36 | SDPAD2 | SDRAD4 | SDA6 | GBD0 |
| 37 | SDPAD3 | SDRAD5 | SDA7 | GBD1 |
| 38 | SDPAD4 | SDRAD6 | SDA8 | GBD2 |
| 39 | SDPAD5 | SDRAD7 | SDA9 | GBD3 |
| 40 | SDPAD6 | SDRA8 | SDA10 | SDD0 |
| 41 | SDPAD7 | SDRA9 | SDA11 | SDD1 |
| 42 | SDPA8 | SDRA20 | SDA12 | SDD2 |
| 43 | SDPA9 | SDRA21 | SDA13 | SDD3 |
| 44 | SDPA10 | SDRA22 | SDA14 | SDD4 |
| 45 | SDPA11 | SDRA23 | SDA15 | SDD5 |
| 46 | SDPMPX | SDRMPX | /SDMRD | SDD6 |
| 47 | /SDPOE | /SDROE | /SDROM | SDD7 |
| 48 | /PORTADRS | 4MB | 24M | 8M |
| 49 | GND | GND | GND | GND |
| 50 | GND | GND | GND | GND |

Contacts non utilisés par SDAES : /PORTADRS, /AS, R/W, RESET, 68KCLKB,
/ROMOEU, /ROMOEL (on utilise /ROMOE combiné), /PDTACK (résistance de tirage
à 5 V, cf. plus bas), 24M, 8M, 4MB, SDRD1, boucles audio L/R (utilisées
seulement par la révision NEO-AES de la console : à relier entre elles
comme sur une cartouche d'origine, **à vérifier**).

## Carte PROG

| Signal (nom FPGA) | FPGA | Sens | Rôle |
|---|---|---|---|
| `A[19:1]` | P | console → cartouche | adresse 68000 (mots) |
| `D[15:0]` | P | bidirectionnel | données 68000 ; la cartouche pilote en lecture |
| `ROMOE_N` | P | → | lecture zone 0x000000-0x0FFFFF (P1), deux octets |
| `PORTOEU_N`, `PORTOEL_N` | P | → | lecture octet pair / impair en zone 0x200000-0x2FFFFF (P2 / banques) ; le FPGA les combine (le mot entier est toujours présenté) |
| `PORTWEL_N`, `PORTWEU_N` | P | → | écriture octet bas / haut en zone 0x2xxxxx |
| `ROMWAIT_N`, `PWAIT0_N`, `PWAIT1_N` | P | cartouche → console | cycles d'attente 68000 (registre 0x04 du FPGA P, clé `wait` des fichiers de protection ; à 1 = pleine vitesse, valeur par défaut) |
| `SDRAD[7:0]` | V | bidirectionnel | ADPCM-A : adresse multiplexée puis donnée |
| `SDRA_L[9:8]`, `SDRA_U[23:20]` | V | → | ADPCM-A : adresse (8-9 multiplexés) |
| `SDRMPX`, `SDROE_N` | V | → | ADPCM-A : strobe de multiplexage, lecture |
| `SDPAD[7:0]` | V | bidirectionnel | ADPCM-B : adresse multiplexée puis donnée |
| `SDPA[11:8]` | V | → | ADPCM-B : adresse (multiplexée) |
| `SDPMPX`, `SDPOE_N` | V | → | ADPCM-B : strobe, lecture |

Tampons de niveaux (voir « Niveaux 5 V » plus bas) :

| Repère | Composant | Canaux | Sens | /OE |
|---|---|---|---|---|
| U1-U2 | 74LVC16244A (3,3 V) | A1-A19, ROMOE, PORTOEU/L, PORTWEL/U (24) | console → FPGA P | `XLAT_EN_N` |
| U3 | 74LVC16244A (3,3 V) | SDRA8-9, 20-23, SDRMPX, SDROE, SDPA8-11, SDPMPX, SDPOE (14) | console → FPGA V | `XLAT_EN_N` |
| U4 | 74LVC16245A (3,3 V) | D0-D15 | `D_DIR` (1 = FPGA → console) | `XLAT_EN_N` |
| U5 | 74LVC16245A (3,3 V) | SDRAD0-7 (moitié 1), SDPAD0-7 (moitié 2) | `RAD_DIR`, `PAD_DIR` | `XLAT_EN_N` |
| U6 | 74AHCT125 (5 V) | ROMWAIT, PWAIT0, PWAIT1 | FPGA P → console | `OE5_N` |

## Carte CHA

| Signal (nom FPGA) | FPGA | Sens | Rôle |
|---|---|---|---|
| `P[23:0]` | C (et `P[15:0]` vers SM) | → | bus P du LSPC (adresses sprites/fixe) |
| `PCK1B` | C | → | verrouillage de l'adresse C (front montant) |
| `CA4` | C | → | bit A4 de la ROM C (demi-tuile), hors bus P |
| `CLK_12M`, `EVEN`, `LOAD`, `H` | C | → | horloge et commandes du sérialiseur ZMC2 (LOAD et pixels au front descendant de 12M) |
| `GAD[3:0]`, `GBD[3:0]`, `DOTA`, `DOTB` | C | cartouche → console | pixels de sprites |
| `PCK2B`, `S2H1` | SM | → | verrou de l'adresse S (front montant), bit A3 de la ROM S (contact « 2H1 ») |
| `FIXD[7:0]` | SM | ← | donnée de la couche fixe |
| `SDA[15:0]` | SM | → | adresse Z80 |
| `SDMRD_N`, `SDROM_N`, `SDRD0_N` | SM | → | lecture mémoire, sélection M1, ports de banques |
| `SDD[7:0]` | SM | ← | donnée Z80 (pilotée seulement en lecture M1) |

Tampons de niveaux :

| Repère | Composant | Canaux | Sens | /OE |
|---|---|---|---|---|
| U1-U4 | 74LVC16244A (3,3 V) | P0-23, PCK1B/2B, CA4, 2H1, 12M, EVEN, LOAD, H, SDA0-15, SDMRD, SDROM, SDRD0 (51) | console → FPGA C et SM | `XLAT_EN_N` |
| U5-U6 | 74AHCT16244 (5 V) | GAD, GBD, DOTA, DOTB, FIXD (18) | FPGA C et SM → console | `OE5_N` |
| U7 | 74AHCT244 (5 V) | SDD0-7 | FPGA SM → Z80 | `SDD_OE5_N` |

Les sorties de U1-U4 alimentent les deux FPGA (P0-15 vers C et SM).
`SDD_OE5_N` = `SDD_OE_N` OU `OE5_N` (porte 74AHCT1G32 en 5 V) :
`SDD_OE_N` vient directement du FPGA SM (combinatoire, rapide : le bus Z80
doit être relâché sans retard), `OE5_N` garantit la haute impédance à la
mise sous tension (voir « Mise sous tension »).

## Câble inter-cartes (12 contacts)

| Contact | Signal | Sens |
|---|---|---|
| 1 | `PROG_SCK` | RP2350 → FPGA P et V |
| 2-5 | `PROG_IO0..3` | bidirectionnel (bus partagé P/V) |
| 6 | `CS_P` | RP2350 → P |
| 7 | `CS_V` | RP2350 → V |
| 8 | `LK_IRQ` | P → RP2350 |
| 9 | `MODE` | FPGA P → FPGA C et SM |
| 10 | `CDONE_PROG` | CDONE de P et V (drain ouvert, ET câblé) |
| 11-12 | GND | |

Longueur courte (< 10 cm) ; résistances série de 33 Ω côté émetteur sur
SCK et IO. Chaque carte est alimentée par son propre connecteur.

## /PDTACK et cycles d'attente

Sur une cartouche d'origine, /ROMWAIT, /PWAIT0, /PWAIT1 et /PDTACK sont
reliés à 5 V ou à la masse pour régler les cycles d'attente du 68000
(page « Wait cycle » du wiki). SDAES pilote les trois premiers depuis le
FPGA P (pleine vitesse par défaut ; quelques jeux ont besoin d'attente pour
espacer leurs accès VRAM) et tire /PDTACK à 5 V par une résistance de
10 kΩ (aucune cartouche commerciale ne l'utilise). Avec les tampons en
haute impédance (FPGA non configurés), des résistances de 10 kΩ vers 5 V
sur les trois sorties d'attente donnent la pleine vitesse.

## Niveaux 5 V

La console ne connaît que le 5 V, et une partie de ses signaux sort de
logique TTL dont le niveau haut peut ne pas dépasser 2,7-3,4 V (par
exemple PCK1B et PCK2B, issus d'inverseurs 74AS04 d'après le wiki
neogeodev). Aucune broche de FPGA ne touche le connecteur, et les
tampons sont choisis selon le sens :

* **console → cartouche : 74LVC16244A / 74LVC16245A alimentés en 3,3 V.**
  Entrées tolérantes au 5 V (5,5 V max), seuil TTL (niveau haut reconnu
  dès 2,0 V), sorties 3,3 V vers les FPGA. Un translateur double tension
  (74LVC16T245) aurait un seuil de 0,7 x 5 V = 3,5 V côté console : trop
  haut pour des sorties TTL. Ce composant n'est donc plus utilisé.
* **cartouche → console, puces vidéo SNK (pixels, couche fixe), attentes
  et Z80 : 74AHCT alimentés en 5 V.** Leurs entrées TTL acceptent le 3,3 V
  des FPGA et leurs sorties montent à 5 V, ce qui convient quel que soit
  le seuil des puces de la console (à confirmer sur matériel pour les
  puces SNK).
* **bus bidirectionnels D (68000) et SDRAD/SDPAD (YM2610) : 74LVC16245A en
  3,3 V.** Dans le sens cartouche → console, le niveau haut est de 3,3 V :
  suffisant pour les entrées TTL du 68000 et du YM2610 (niveau haut à
  partir de 2,0 V ; à confirmer pour le YM2610). Hors lecture, leurs
  sorties sont en haute impédance et supportent le 5 V du bus.

## Mise sous tension

Deux signaux de validation, tirés vers l'état « désactivé » par des
résistances de 10 kΩ :

* `XLAT_EN_N` (tampons 74LVC, 3,3 V) : tiré à 3,3 V. Tant que le 3,3 V
  n'est pas établi, ces tampons non alimentés restent en haute impédance
  (fonction Ioff des 74LVC...A) ; ensuite, la résistance les garde
  désactivés.
* `OE5_N` (tampons 74AHCT, 5 V) : tiré à **5 V**. Ces tampons sont
  alimentés dès la mise sous tension de la console : tirer leur /OE au
  3,3 V les activerait pendant la montée du régulateur. Le FPGA commande
  `OE5_N` à travers un 74LVC1G07 (drain ouvert, sortie tolérante au 5 V,
  alimenté en 3,3 V) : non alimenté ou au repos, il laisse la résistance
  tenir `OE5_N` à 5 V. `OE5_N` ne change qu'une fois, après la
  configuration : la lenteur du drain ouvert (résistance de tirage) est
  sans conséquence. `SDD_OE5_N` (carte CHA) = `SDD_OE_N` OU `OE5_N`.

Tant que les FPGA ne sont pas configurés (quelques dizaines de ms depuis la
flash SPI), **tous les tampons sont en haute impédance** et la cartouche
est électriquement absente du bus. Le FPGA P (resp. C) force `XLAT_EN_N`
à 0 une fois sa PLL verrouillée ; `OE5_N` suit `XLAT_EN_N` (même broche
du FPGA, à travers le 74LVC1G07). La cartouche ne doit pas être branchée
console allumée.
