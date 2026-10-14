# 7. État, validation et feuille de route

## Ce qui est fait et vérifié (sans matériel)

| Élément | Vérification |
|---|---|
| HDL des 4 FPGA | simulation Icarus au niveau carte (`make -C hdl sim`) : P+V et C+SM sur leurs bus de liaison partagés ; chargement, menu, bascule, lectures P anticipées avec banques, C (ZMC2, avec et sans retournement), S, M1 avec banques, ADPCM A/B, diagnostics |
| Synthèse et placement-routage | Yosys + nextpnr iCE40 HX8K/TQ144 (`make -C hdl lint pnr`) : 1 327 à 3 653 cellules, 101 à 118 MHz pour 100 MHz visés (broches non affectées) |
| Menu 68000 | compilé ; exécuté dans un émulateur 68000 face à une Neo Geo simulée (`tools/tests/test_menu_emu.py`) : écran, navigation, chargement, séquence de bascule depuis la RAM |
| Pilote Z80 | assemblé (vecteurs 0x38 / 0x66 vérifiés) |
| Firmware RP2350 | logique (navigation, protocole, chargement `.neo` vers les 4 FPGA, plan mémoire, registres, descriptions de protections) testée sur PC avec imitations de FatFs et de la liaison (`tools/tests/test_firmware.py`) |
| Protections | SMA, PVC, superposition KOF 98 : banc de test `tb_prog` ; outil d'extraction des tables SMA testé sur des extraits au format MAME |
| Outils | `tools/neotool.py` + 12 tests unitaires |

## Ce qui n'est PAS encore vérifié

* Aucun prototype matériel : schémas et routage restent à faire (KiCad).
* Brochage des connecteurs AES : relevé sur le wiki neogeodev
  (`hardware/aes_connector.csv`) ; reste à confirmer le sens de la
  numérotation et les faces sur une cartouche réelle.
* Correspondances de bits C/S et fronts du ZMC2 : conformes au wiki
  neogeodev ; ordre des pixels du ZMC2 (EVEN, H) et fronts du
  démultiplexage ADPCM : issus de la rétro-ingénierie publique. Le tout est
  isolé dans un seul bloc pour être corrigé facilement.
* `qlink.c`, `main.c`, `hw_config.c` n'ont pas été compilés avec le SDK Pico
  (pas d'accès au SDK dans l'environnement de développement).
* Timing avec les vraies broches (fichiers `.pcf` à compléter).
* Comportement du BIOS AES avec le menu (code de sécurité recopié,
  réinitialisation par chien de garde).

## Plan de mise en service

1. **Alimentations et configuration** : CDONE des 4 FPGA, PLL verrouillées,
   `XLAT_EN_N` à 0. Cartouche hors console.
2. **Liaison** : lecture des identifiants `NGP2`, `NGV2`, `NGC2`, `NGS2`.
3. **SDRAM/SRAM** : test mémoire par écriture (MEM_WR) + relecture par les
   registres de diagnostic (0x10/0x11) ; ajuster `RD_LAT` / la phase
   d'horloge si nécessaire.
4. **Menu sur console** : vérifier que le BIOS accepte le menu, que la
   police s'affiche (sinon corriger `s_byte_addr`), que la boîte aux lettres
   fonctionne (compteurs 0x12-0x14 utiles).
5. **Analyse logique** d'une vraie cartouche sur la console : relever les
   temps adresse → /ROMOE, PCK1B → LOAD, CA4, 2H1, l'ordre des bits P.
6. **Premier jeu simple** (P ≤ 1 Mo, sans banque), puis jeux à banques, puis
   gros jeux (C = 64 Mo), puis son (ADPCM-A/B).

## Limitations connues / à faire

* Protections : SMA, PVC et superposition KOF 98 sont intégrées (voir
  `docs/08-cartouches-protegees.md`) ; restent les **banques de couche fixe**
  des cartes CMC (ROM S de 512 Ko), PRO-CT0 et Metal Slug X.
* Pas de retour au menu sans le bouton de la cartouche.
* Mise à jour des bitstreams depuis la carte SD (le RP2350 peut écrire les
  flash SPI des FPGA) : à ajouter.
* Version MVS : autre brochage et autre forme de carte ; HDL réutilisable.
