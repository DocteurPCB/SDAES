# Matériel

Ce dossier accueillera les projets KiCad des deux cartes (PROG et CHA).
Pour l'instant il contient les gabarits de contraintes des 4 FPGA iCE40,
générés à partir des tops Verilog :

```
python3 tools/gen_pcf.py hdl/prog/prog_p_top.v prog_p_top hardware/prog_p.pcf
python3 tools/gen_pcf.py hdl/prog/prog_v_top.v prog_v_top hardware/prog_v.pcf
python3 tools/gen_pcf.py hdl/cha/cha_c_top.v   cha_c_top  hardware/cha_c.pcf
python3 tools/gen_pcf.py hdl/cha/cha_sm_top.v  cha_sm_top hardware/cha_sm.pcf
```

| FPGA | Carte | E/S utilisées |
|---|---|---|
| P | PROG | 90 |
| V | PROG | 80 |
| C | CHA | 89 |
| SM | CHA | 92 |

Le boîtier TQ144 de l'iCE40HX4K offre une centaine d'E/S (la fiche
technique Lattice fait foi ; certaines broches sont des entrées seules,
utilisables pour les signaux venant de la console).

## Règles de placement des broches

* `CLK25` sur une entrée globale (GBIN) utilisable par la PLL.
* Signaux utilisés **comme horloges** dans le HDL — à placer sur des
  entrées globales (GBIN) : `CLK_12M`, `PCK1B` (FPGA C) ; `PCK2B` (SM) ;
  `SDRMPX`, `SDPMPX` (V).
* SDRAM regroupée sur un même côté du boîtier, `SD_CLK` en sortie DDR
  (SB_IO) avec résistance série.
* Bancs d'E/S en 3,3 V ; VPP de l'iCE40 relié au 3,3 V.

## À faire

1. Relever le brochage et les cotes des cartes AES PROG/CHA sur une
   cartouche réelle (voir `docs/02-signaux-connecteurs.md`).
2. Schémas : alimentations, FPGA + flash SPI, SDRAM, SRAM, translateurs,
   Pico 2 + microSD (CHA), câble inter-cartes.
3. Routage 4 couches, contacts dorés chanfreinés.
4. Compléter les fichiers `.pcf` puis `make -C hdl bits`.
