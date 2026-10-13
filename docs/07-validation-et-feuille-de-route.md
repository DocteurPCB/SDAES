# 7. État, validation et feuille de route

## Ce qui est fait et vérifié (sans matériel)

| Élément | Vérification |
|---|---|
| HDL des deux FPGA | simulation Icarus (`make -C hdl sim`) : chargement par la liaison, menu, bascule, lectures P avec banques, C (ZMC2, avec et sans retournement), S, M1 avec banques, ADPCM A/B, lectures de diagnostic ; synthèse Yosys ECP5 sans erreur (`make -C hdl lint`), ~1 300 bascules et 16/36 BRAM par FPGA |
| Menu 68000 | compilé ; exécuté dans un émulateur 68000 face à une Neo Geo simulée (`tools/tests/test_menu_emu.py`) : écran, navigation, chargement, séquence de bascule depuis la RAM |
| Pilote Z80 | assemblé (vecteurs 0x38 / 0x66 vérifiés) |
| Firmware RP2350 | logique (navigation, protocole, chargement `.neo`, plan mémoire, registres) testée sur PC avec imitations de FatFs et de la liaison (`tools/tests/test_firmware.py`) |
| Outils | `tools/neotool.py` + 12 tests unitaires |

## Ce qui n'est PAS encore vérifié

* Aucun prototype matériel n'a été fabriqué : schéma et routage restent à
  faire (KiCad), à partir de `docs/02` et `docs/06`.
* Brochage exact des connecteurs AES (voir l'avertissement de `docs/02`).
* Correspondances de bits C/S, ordre des pixels du ZMC2, fronts du
  démultiplexage ADPCM : issues de la rétro-ingénierie publique, isolées
  dans un seul bloc pour être corrigées facilement.
* `qlink.c`, `main.c`, `hw_config.c` n'ont pas été compilés avec le SDK Pico
  (pas d'accès au SDK dans l'environnement de développement) ; l'API de la
  bibliothèque FatFs-SDIO peut nécessiter de petits ajustements.
* Placement-routage (nextpnr) et analyse de timing à 133 MHz.
* Comportement du BIOS AES avec le menu (code de sécurité recopié,
  réinitialisation par chien de garde).

## Plan de mise en service

1. **Alimentations et configuration** : DONE des deux FPGA, PLL verrouillée,
   `XLAT_EN_N` à 0. Cartouche hors console.
2. **Liaison** : lecture des identifiants `NGP1` / `NGC1` depuis le RP2350.
3. **SDRAM/SRAM** : test mémoire complet par écriture (MEM_WR) + relecture
   par les registres de diagnostic (0x10/0x11) ; ajuster `RD_LAT` / la phase
   d'horloge si nécessaire.
4. **Menu sur console** : vérifier que le BIOS accepte le menu, que la
   police s'affiche (sinon corriger `s_byte_addr`), que la boîte aux lettres
   fonctionne (compteurs 0x12-0x14 utiles).
5. **Analyse logique** d'une vraie cartouche sur la console : relever les
   temps PCK1B → LOAD, CA4, 2H1, l'ordre des bits P, et comparer.
6. **Premier jeu simple** (P ≤ 1 Mo, sans banque), puis jeux à banques, puis
   gros jeux (C = 64 Mo), puis son (ADPCM-A/B).

## Limitations connues / à faire

* Jeux protégés nécessitant une émulation de puce supplémentaire :
  **SMA** (KOF 99, Garou, Metal Slug 3, KOF 2000), **PVC** (Metal Slug 5,
  SVC Chaos, KOF 2003), banques de couche fixe 512 Ko des cartes **CMC50**.
  Le registre CTRL et le format laissent la place à des « mappers » par
  numéro NGH.
* Pas de retour au menu sans le bouton de la cartouche.
* Mise à jour des bitstreams FPGA depuis la carte SD (le RP2350 peut écrire
  les flash SPI) : à ajouter.
* Version MVS : autre brochage et autre forme de carte ; l'architecture et
  le HDL sont réutilisables.
