# 5. Menu, boîte aux lettres et firmware

## Le menu (programme 68000)

`menu/68k/` — C + un peu d'assembleur, compilé avec `gcc-m68k-linux-gnu`.

* En-tête cartouche Neo Geo standard (0x100), pas d'animation d'intro.
* Le BIOS appelle `USER` ; pour la requête 0 le menu rend la main, sinon il
  masque les interruptions et prend le contrôle (il nourrit lui-même le chien
  de garde, lit la manette en direct et écrit dans la couche fixe).
* Affichage : couche fixe uniquement, police 8x8 générée depuis une police
  console PSF (`tools/neotool.py font`).
* Commandes : haut/bas, gauche/droite (page), A = ouvrir/lancer,
  B = dossier parent.

### Code de sécurité

Le BIOS vérifie une séquence d'octets fixe pointée par l'adresse 0x182 de
toute cartouche. Elle n'est **pas** distribuée ici : la construction la
recopie depuis un jeu `.neo` que vous possédez :

```
make SECURITY_FROM=/chemin/vers/un_jeu.neo
```

La zone 0x186-0x3FF du menu est réservée pour cela.

### Pilote Z80

`menu/z80/driver.asm` (z80asm) : répond aux commandes du 68000 (écho),
passe en boucle RAM sur la commande 0x01 (BIOS) ou 0x7F (SDAES, avant la
bascule), redémarre sur 0x03.

## Boîte aux lettres

Définie dans `protocol/sdaes_mailbox.h` (partagé menu/firmware).

| Zone (déc. depuis 0x200000) | Écrite par | Contenu |
|---|---|---|
| 0x000-0x00B | 68000 | commande, numéro de séquence, arguments |
| 0x100-0x10F | RP2350 | séquence de réponse, statut, progression, nombres d'entrées, nature |
| 0x110 / 0x150 | RP2350 | chemin courant / message (64 octets chacun) |
| 0x200-0x4FF | RP2350 | 24 entrées de 32 octets (type + nom) |

Déroulement : le 68000 écrit la commande puis la sonnette (0x2FFFE0) ; le
FPGA lève `LK_IRQ` ; le RP2350 lit la commande, acquitte, écrit
`RSP_BUSYSEQ`, traite (progression dans `RSP_PROGRESS` pendant un
chargement), puis écrit `RSP_SEQ` **en dernier**. Le 68000 attend
`RSP_SEQ == CMD_SEQ`.

Commandes : `PING`, `LIST(premier)`, `OPEN(index)` (dossier → y entre ;
fichier → charge et arme), `PARENT`, `RELOAD_LAST`.

## Firmware RP2350

`firmware/rp2350/` — SDK Pico ≥ 2.0 + bibliothèque
[no-OS-FatFS-SD-SDIO-SPI-RPi-Pico](https://github.com/carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico).

| Fichier | Rôle |
|---|---|
| `src/main.c` | démarrage, attente des FPGA, boucle principale, bouton |
| `src/qlink.c`, `src/qlink.pio` | liaison 4 bits (en-têtes logiciels + rafales PIO/DMA) |
| `src/neo_loader.c` | lecture d'un `.neo` et écriture dans les mémoires |
| `src/browser.c` | navigation SD et commandes du menu |
| `src/hw_config.c` | configuration SDIO de la bibliothèque FatFs |
| `test/` | imitations de FatFs et de la liaison pour tester sur PC |

Le dernier jeu lancé est mémorisé dans `SDAES/LAST.TXT` sur la carte SD.

Construction :

```
git clone https://github.com/carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico firmware/rp2350/lib/fatfs-sd
export PICO_SDK_PATH=/chemin/vers/pico-sdk
cmake -S firmware/rp2350 -B firmware/rp2350/build -DPICO_BOARD=pico2
cmake --build firmware/rp2350/build
```

## Préparer la carte SD

* FAT32 ou exFAT, fichiers `.neo` dans n'importe quels dossiers.
* Les `.neo` peuvent être produits par NeoBuilder (outil TerraOnion) ou par
  `tools/neotool.py build` à partir de vos propres dumps décryptés :

```
python3 tools/neotool.py build -o jeu.neo --name "MON JEU" \
    --p 001-p1.p1 --s 001-s1.s1 --m 001-m1.m1 \
    --v1 001-v1.v1 001-v2.v2 --c 001-c1.c1 001-c2.c2 001-c3.c3 001-c4.c4
python3 tools/neotool.py info jeu.neo
```
