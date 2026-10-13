# 3. Mémoires, correspondances d'adresses et timings

## Plan mémoire

| Contenu | Composant | Adresse | Taille max |
|---|---|---|---|
| P | SDRAM P (W9825G6KH, x16) | mots 0.. | 32 Mo |
| V1 (ADPCM-A) | SDRAM V (x16) | octet 0 | 32 Mo au total |
| V2 (ADPCM-B) | SDRAM V | après V1, aligné sur 64 Ko | (V1 + V2) |
| C | 2 x SDRAM en parallèle (32 bits) | mots 0.. | 64 Mo |
| S | SRAM 1 Mo | 0x00000 | 512 Ko |
| M1 | SRAM 1 Mo | 0x80000 | 512 Ko |
| menu P | BRAM PROG | — | 32 Ko |
| boîte aux lettres | BRAM PROG | 0x200000 (68000) | 4 Ko |
| menu S / M1 | BRAM CHA | — | 8 Ko + 8 Ko |

Chaque région a un **masque d'adresse** (puissance de 2 supérieure − 1) :
les jeux dont la taille n'est pas une puissance de 2 sont répliqués comme
sur une vraie cartouche.

## Correspondances d'adresses

Elles sont regroupées dans la section « CARTOGRAPHIE » de
`hdl/cha/cha_core.v` et dans `p_word()` de `hdl/prog/prog_core.v`, pour
pouvoir être corrigées en un seul endroit lors de la validation.

* **P** : 0x000000-0x0FFFFF → mots 0x000000-0x07FFFF ; 0x200000-0x2FFFFF →
  mots 0x080000 + banque × 0x80000. Une écriture dans 0x2FFFF0-0x2FFFFF
  choisit la banque (schéma standard, activé si P > 2 Mo).
* **C** : mot de 32 bits = `{tuile[19:0], CA4, ligne[3:0]}`, avec
  tuile[15:0] = P[15:0], ligne = P[19:16], tuile[19:16] = P[23:20] (verrou
  PCK1B). Les deux moitiés (CA4 = 0/1) sont lues en une seule activation.
* **Bus CR du ZMC2** : CR[7:0] = plan 0, CR[15:8] = plan 1 (ROM C impaire),
  CR[23:16] = plan 2, CR[31:24] = plan 3 (ROM C paire). Le `.neo` stocke
  c1/c2 entrelacés octet par octet ; le FPGA réordonne
  `{v3,v2,v1,v0}` → `{v3,v1,v2,v0}`.
* **S** : octet = `{tuile[11:0], P3, 2H1, ligne[2:0]}` (verrou PCK2B).
* **M1** : fenêtres Z80 0x0000-0x7FFF fixe, 0x8000/16 Ko, 0xC000/8 Ko,
  0xE000/4 Ko, 0xF000/2 Ko ; banque = registre B lors d'un `IN (C)` sur les
  ports 0x0B/0x0A/0x09/0x08. Valeurs initiales 2/6/0x0E/0x1E (identité).
* **ADPCM** : front montant de *MPX = partie basse de l'adresse, front
  descendant = partie haute (rôle du NEO-PCM2).

## Budgets de temps (simulation)

Horloge système 133 MHz, SDRAM CL3, horloge SDRAM = horloge système
inversée, données lues capturées sur le front descendant.

| Accès | Contrainte (estimée) | SDAES, simulé |
|---|---|---|
| 68000 : /ROMOE → donnée | ~140 ns | **≤ 89 ns**, y compris pendant les rafraîchissements |
| PCK1B → mot C prêt (deux moitiés) | avant le LOAD suivant (~300 ns) | **86 ns** |
| PCK2B → octets S prêts (deux) | ~300 ns | **95 ns** |
| Z80 : lecture M1 | ~300 ns | **53 ns** |
| ADPCM : /SDROE → donnée | plusieurs centaines de ns | **81 ns** |

Le rafraîchissement SDRAM n'est jamais placé devant une lecture critique :
sur PROG il est déclenché juste après une lecture 68000 (le cycle suivant
arrive au plus tôt ~250 ns plus tard) ; sur CHA juste après la lecture C.

Ces chiffres sont des résultats de **simulation** avec un modèle SDRAM
(tAC 5,4 ns, tOH 2,7 ns). Les délais réels des translateurs (~4-6 ns), des
pistes et de l'horloge SDRAM devront être vérifiés à l'analyseur logique ;
`RD_LAT` et la phase de l'horloge SDRAM sont paramétrables.

## Points à valider en priorité sur matériel

1. Ordre exact des bits de P lors de PCK1B/PCK2B (adresses C et S).
2. Sens du sérialiseur ZMC2 (ordre des pixels, rôle de EVEN et H).
3. Fronts de démultiplexage ADPCM.
4. Marge réelle entre PCK1B et LOAD.
5. Réinitialisation par le chien de garde sur AES.
