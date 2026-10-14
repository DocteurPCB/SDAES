# 2. Signaux des connecteurs et translateurs de niveaux

> **Source.** Le brochage ci-dessous est relevé sur les images de la page
> « AES cartridge pinout » du wiki neogeodev ; les rôles des signaux viennent
> des pages « Signals », « NEO-273 », « NEO-ZMC2 », « P bus » et
> « Wait cycle ». La table complète, contact par contact, est dans
> `hardware/aes_connector.csv` ; les gabarits `hardware/*.pcf` indiquent pour
> chaque port FPGA le contact AES correspondant. **À vérifier avant de
> dessiner le circuit imprimé** : le sens physique de la numérotation
> (position 1 = haut des images du wiki, côté masse) et la face « dessus » /
> « dessous », sur une cartouche réelle.

Chaque carte se connecte à la console par un connecteur de bord (contacts
dorés, chanfreinés) : **2 x 50 contacts au pas de 2,54 mm**, carte de
1,6 mm (100 contacts par carte, 200 pour la cartouche). Alimentation :
+5 V (VCC, 3 contacts par face) et masse (2 contacts à chaque extrémité de
chaque face). Sur l'AES, /ROMOE est au contact 22 de la face dessous de la
carte PROG et 4MB au contact 48 (le wiki signale que certains brochages
publiés intervertissent ces deux signaux).

## Brochage du connecteur AES

Positions 1 à 50, de haut en bas sur les images du wiki. Les signaux
« / » sont actifs à 0.

| Pos. | PROG dessus | PROG dessous | CHA dessus | CHA dessous |
|---|---|---|---|---|
| 1 | GND | GND | GND | GND |
| 2 | GND | GND | GND | GND |
| 3 | /PORTADRS | A1 | 24M | FIXD0 |
| 4 | /SDPOE | A2 | /SDROM | FIXD1 |
| 5 | SDPMPX | A3 | /SDMRD | FIXD2 |
| 6 | SDPA11 | A4 | SDA15 | FIXD3 |
| 7 | SDPA10 | A5 | SDA14 | FIXD4 |
| 8 | SDPA9 | A6 | SDA13 | FIXD5 |
| 9 | SDPA8 | A7 | SDA12 | FIXD6 |
| 10 | SDPAD7 | A8 | SDA11 | FIXD7 |
| 11 | SDPAD6 | A9 | SDA10 | P1 |
| 12 | SDPAD5 | A10 | SDA9 | P3 |
| 13 | SDPAD4 | A11 | SDA8 | P5 |
| 14 | SDPAD3 | A12 | SDA7 | P7 |
| 15 | SDPAD2 | A13 | SDA6 | P9 |
| 16 | SDPAD1 | A14 | SDA5 | P11 |
| 17 | SDPAD0 | A15 | SDA4 | P13 |
| 18 | RESET | A16 | SDA3 | P15 |
| 19 | 68KCLKB | A17 | SDA2 | P17 |
| 20 | /PORTWEL | A18 | SDA1 | P19 |
| 21 | /PORTWEU | A19 | SDA0 | P21 |
| 22 | /PORTOEL | /ROMOE | /SDRD1 | P23 |
| 23 | /PORTOEU | R OUT | /SDRD0 | R OUT |
| 24 | VCC | R IN | VCC | R IN |
| 25 | VCC | VCC | VCC | VCC |
| 26 | VCC | VCC | VCC | VCC |
| 27 | L IN | VCC | L IN | VCC |
| 28 | L OUT | /ROMWAIT | L OUT | NC |
| 29 | /ROMOEL | /PDTACK | P22 | NC |
| 30 | /ROMOEU | /PWAIT0 | P20 | DOTA |
| 31 | /AS | /PWAIT1 | P18 | DOTB |
| 32 | R/W | SDRAD0 | P16 | GAD0 |
| 33 | D15 | SDRAD1 | P14 | GAD1 |
| 34 | D14 | SDRAD2 | P12 | GAD2 |
| 35 | D13 | SDRAD3 | P10 | GAD3 |
| 36 | D12 | SDRAD4 | P8 | GBD0 |
| 37 | D11 | SDRAD5 | P6 | GBD1 |
| 38 | D10 | SDRAD6 | P4 | GBD2 |
| 39 | D9 | SDRAD7 | P2 | GBD3 |
| 40 | D8 | SDRA8 | P0 | SDD0 |
| 41 | D7 | SDRA9 | CA4 | SDD1 |
| 42 | D6 | SDRA20 | LOAD | SDD2 |
| 43 | D5 | SDRA21 | H | SDD3 |
| 44 | D4 | SDRA22 | EVEN | SDD4 |
| 45 | D3 | SDRA23 | 2H1 | SDD5 |
| 46 | D2 | SDRMPX | 12M | SDD6 |
| 47 | D1 | /SDROE | PCK2B | SDD7 |
| 48 | D0 | 4MB | PCK1B | 8M |
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

Translateurs (74LVC16T245, TSSOP-48 ; côté A = 3,3 V FPGA, côté B = 5 V) :

| Groupe | Canaux | DIR | /OE |
|---|---|---|---|
| U1-U2 entrées FPGA P | A1-A19, ROMOE, PORTOEU/L, PORTWEL/U (24, trois moitiés) | fixe B→A | `XLAT_EN_N` (P) |
| U2, 2e moitié : sorties FPGA P | ROMWAIT, PWAIT0, PWAIT1 (3) | fixe A→B | `XLAT_EN_N` (P) |
| U3 bus D | D0-D15 | `D_DIR` (1 = FPGA → console) | `XLAT_EN_N` (P) |
| U4 entrées FPGA V | SDRA8-9, 20-23, SDRMPX, SDROE, SDPA8-11, SDPMPX, SDPOE (14) | fixe B→A | `XLAT_EN_N` (P) |
| U5 bus ADPCM | SDRAD0-7 (moitié 1), SDPAD0-7 (moitié 2) | `RAD_DIR`, `PAD_DIR` | `XLAT_EN_N` (P) |

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

Translateurs :

| Groupe | Canaux | DIR | /OE |
|---|---|---|---|
| U1-U4 entrées | P0-23, PCK1B/2B, CA4, S2H1, 12M, EVEN, LOAD, H, SDA0-15, SDMRD, SDROM, SDRD0 (51) | fixe B→A | `XLAT_EN_N` (C) |
| U5-U6 sorties | GAD, GBD, DOTA, DOTB, FIXD (18) | fixe A→B | `XLAT_EN_N` (C) |
| U7 SDD (74LVC8T245) | SDD0-7 | fixe A→B | `SDD_OE_N` (SM, combinatoire) |

Les sorties des translateurs d'entrée U1-U4 alimentent les deux FPGA (P0-15
vers C et SM).

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
10 kΩ (aucune cartouche commerciale ne l'utilise). Avec les translateurs en
haute impédance (FPGA non configurés), des résistances de 10 kΩ vers 5 V
sur les trois sorties d'attente donnent la pleine vitesse.

## Mise sous tension

`XLAT_EN_N` est tiré à 3,3 V par une résistance de 10 kΩ : tant que les
FPGA ne sont pas configurés (quelques dizaines de ms depuis la flash SPI), **tous les
translateurs sont en haute impédance** et la cartouche est électriquement
absente du bus. Le FPGA P (resp. C) force `XLAT_EN_N` à 0 une fois sa PLL
verrouillée.
