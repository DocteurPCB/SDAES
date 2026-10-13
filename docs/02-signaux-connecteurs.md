# 2. Signaux des connecteurs et translateurs de niveaux

> **Important.** Les noms et rôles des signaux ci-dessous proviennent de la
> rétro-ingénierie publique des puces que SDAES remplace (NEO-273, NEO-ZMC2,
> NEO-PCM2, ROM). Les **numéros de contacts** du connecteur AES ne sont pas
> reproduits ici : ils doivent être relevés sur une cartouche réelle et
> recoupés avec le wiki neogeodev (pages « Cartridge pinout » AES PROG/CHA)
> avant de dessiner le circuit imprimé. Les fichiers de contraintes
> `hardware/*_pins.lpf` contiennent les noms de signaux, pas encore les sites.

Chaque carte se connecte à la console par un connecteur de bord (contacts
dorés, chanfreinés). Alimentation : +5 V et masse par le connecteur.

## Carte PROG

| Signal (nom FPGA) | Sens | Rôle |
|---|---|---|
| `A[19:1]` | console → cartouche | adresse 68000 (mots) |
| `D[15:0]` | bidirectionnel | données 68000 ; la cartouche pilote en lecture |
| `ROMOE_N` | → | lecture zone 0x000000-0x0FFFFF (P1) |
| `PORTOE_N` | → | lecture zone 0x200000-0x2FFFFF (P2 / banques) |
| `PORTWEL_N`, `PORTWEU_N` | → | écriture octet bas / haut en zone 0x2xxxxx |
| `SDRAD[7:0]` | bidirectionnel | ADPCM-A : adresse multiplexée puis donnée |
| `SDRA_L[9:8]`, `SDRA_U[23:20]` | → | ADPCM-A : adresse (8-9 multiplexés) |
| `SDRMPX`, `SDROE_N` | → | ADPCM-A : strobe de multiplexage, lecture |
| `SDPAD[7:0]` | bidirectionnel | ADPCM-B : adresse multiplexée puis donnée |
| `SDPA[11:8]` | → | ADPCM-B : adresse (multiplexée) |
| `SDPMPX`, `SDPOE_N` | → | ADPCM-B : strobe, lecture |

Translateurs (74LVC16T245, côté A = 3,3 V FPGA, côté B = 5 V console) :

| Groupe | Canaux | DIR | /OE |
|---|---|---|---|
| U1-U3 entrées | A1-A19, ROMOE, PORTOE, PORTWEL/U, signaux YM (37) | fixe B→A | `XLAT_EN_N` |
| U4 bus D | D0-D15 | `D_DIR` (1 = FPGA → console en lecture) | `XLAT_EN_N` |
| U5 bus ADPCM | SDRAD0-7 (moitié 1), SDPAD0-7 (moitié 2) | `RAD_DIR`, `PAD_DIR` | `XLAT_EN_N` |

`D_DIR`, `RAD_DIR`, `PAD_DIR` sont calculés **en combinatoire** à partir de
/ROMOE, /PORTOE, /SDROE, /SDPOE : la cartouche libère le bus quelques
nanosecondes après la fin du cycle de lecture.

## Carte CHA

| Signal (nom FPGA) | Sens | Rôle |
|---|---|---|
| `P[23:0]` | → | bus P du LSPC (adresses sprites/fixe multiplexées) |
| `PCK1B`, `PCK2B` | → | verrouillage de l'adresse C / S (front montant) |
| `CA4` | → | demi-tuile C (colonnes 0-7 / 8-15) |
| `S2H1` | → | sélection d'octet de la couche fixe |
| `CLK_12M`, `EVEN`, `LOAD`, `H` | → | horloge et commandes du sérialiseur ZMC2 |
| `GAD[3:0]`, `GBD[3:0]` | cartouche → console | pixels de sprites (2 par cycle 12 MHz) |
| `DOTA`, `DOTB` | ← | pixel opaque A / B |
| `FIXD[7:0]` | ← | donnée de la couche fixe |
| `SDA[15:0]` | → | adresse Z80 |
| `SDMRD_N`, `SDROM_N` | → | lecture mémoire Z80, sélection ROM M1 |
| `SDRD0_N` | → | lecture des ports 0x08-0x0B (banques M1) |
| `SDD[7:0]` | ← | donnée Z80 (pilotée seulement en lecture M1) |

Translateurs :

| Groupe | Canaux | DIR | /OE |
|---|---|---|---|
| U1-U4 entrées | P0-23, PCK1B/2B, CA4, S2H1, 12M, EVEN, LOAD, H, SDA0-15, SDMRD, SDROM, SDRD0 (51) | fixe B→A | `XLAT_EN_N` |
| U5-U6 sorties | GAD, GBD, DOTA, DOTB, FIXD (18) | fixe A→B | `XLAT_EN_N` |
| U7 SDD (74LVC8T245) | SDD0-7 | fixe A→B | `SDD_OE_N` (combinatoire) |

## Câble inter-cartes (12 contacts)

| Contact | Signal | Sens |
|---|---|---|
| 1 | `PROG_SCK` | RP2350 → FPGA PROG |
| 2-5 | `PROG_IO0..3` | bidirectionnel |
| 6 | `PROG_CS_N` | RP2350 → PROG |
| 7 | `LK_IRQ` | PROG → RP2350 |
| 8 | `MODE` | FPGA PROG → FPGA CHA |
| 9 | `PROG_DONE` | PROG → RP2350 |
| 10-12 | GND | |

Longueur courte (< 10 cm) ; résistances série de 33 Ω côté émetteur sur
SCK et IO. Chaque carte est alimentée par son propre connecteur.

## Mise sous tension

`XLAT_EN_N` est tiré à 3,3 V par une résistance de 10 kΩ : tant que le FPGA
n'est pas configuré (≈ 30 ms depuis la flash SPI), **tous les translateurs
sont en haute impédance** et la cartouche est électriquement absente du bus.
Le FPGA force `XLAT_EN_N` à 0 une fois la PLL verrouillée.
