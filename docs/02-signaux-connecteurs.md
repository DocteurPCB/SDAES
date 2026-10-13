# 2. Signaux des connecteurs et translateurs de niveaux

> **Important.** Les noms et rôles des signaux ci-dessous proviennent de la
> rétro-ingénierie publique des puces que SDAES remplace (NEO-273, NEO-ZMC2,
> NEO-PCM2, ROM). Les **numéros de contacts** du connecteur AES ne sont pas
> reproduits ici : ils doivent être relevés sur une cartouche réelle et
> recoupés avec le wiki neogeodev (pages « Cartridge pinout » AES PROG/CHA)
> avant de dessiner le circuit imprimé. Les fichiers `hardware/*.pcf`
> contiennent les noms de signaux, pas encore les numéros de broches FPGA.

Chaque carte se connecte à la console par un connecteur de bord (contacts
dorés, chanfreinés). Alimentation : +5 V et masse par le connecteur.

## Carte PROG

| Signal (nom FPGA) | FPGA | Sens | Rôle |
|---|---|---|---|
| `A[19:1]` | P | console → cartouche | adresse 68000 (mots) |
| `D[15:0]` | P | bidirectionnel | données 68000 ; la cartouche pilote en lecture |
| `ROMOE_N` | P | → | lecture zone 0x000000-0x0FFFFF (P1) |
| `PORTOE_N` | P | → | lecture zone 0x200000-0x2FFFFF (P2 / banques) |
| `PORTWEL_N`, `PORTWEU_N` | P | → | écriture octet bas / haut en zone 0x2xxxxx |
| `SDRAD[7:0]` | V | bidirectionnel | ADPCM-A : adresse multiplexée puis donnée |
| `SDRA_L[9:8]`, `SDRA_U[23:20]` | V | → | ADPCM-A : adresse (8-9 multiplexés) |
| `SDRMPX`, `SDROE_N` | V | → | ADPCM-A : strobe de multiplexage, lecture |
| `SDPAD[7:0]` | V | bidirectionnel | ADPCM-B : adresse multiplexée puis donnée |
| `SDPA[11:8]` | V | → | ADPCM-B : adresse (multiplexée) |
| `SDPMPX`, `SDPOE_N` | V | → | ADPCM-B : strobe, lecture |

Translateurs (74LVC16T245, TSSOP-48 ; côté A = 3,3 V FPGA, côté B = 5 V) :

| Groupe | Canaux | DIR | /OE |
|---|---|---|---|
| U1-U2 entrées FPGA P | A1-A19, ROMOE, PORTOE, PORTWEL/U (23) | fixe B→A | `XLAT_EN_N` (P) |
| U3 bus D | D0-D15 | `D_DIR` (1 = FPGA → console) | `XLAT_EN_N` (P) |
| U4 entrées FPGA V | SDRA8-9, 20-23, SDRMPX, SDROE, SDPA8-11, SDPMPX, SDPOE (14) | fixe B→A | `XLAT_EN_N` (P) |
| U5 bus ADPCM | SDRAD0-7 (moitié 1), SDPAD0-7 (moitié 2) | `RAD_DIR`, `PAD_DIR` | `XLAT_EN_N` (P) |

## Carte CHA

| Signal (nom FPGA) | FPGA | Sens | Rôle |
|---|---|---|---|
| `P[23:0]` | C (et `P[15:0]` vers SM) | → | bus P du LSPC (adresses sprites/fixe) |
| `PCK1B` | C | → | verrouillage de l'adresse C (front montant) |
| `CA4` | C | → | demi-tuile C |
| `CLK_12M`, `EVEN`, `LOAD`, `H` | C | → | horloge et commandes du sérialiseur ZMC2 |
| `GAD[3:0]`, `GBD[3:0]`, `DOTA`, `DOTB` | C | cartouche → console | pixels de sprites |
| `PCK2B`, `S2H1` | SM | → | verrou de l'adresse S, sélection d'octet |
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

## Mise sous tension

`XLAT_EN_N` est tiré à 3,3 V par une résistance de 10 kΩ : tant que les
FPGA ne sont pas configurés (quelques dizaines de ms depuis la flash SPI), **tous les
translateurs sont en haute impédance** et la cartouche est électriquement
absente du bus. Le FPGA P (resp. C) force `XLAT_EN_N` à 0 une fois sa PLL
verrouillée.
