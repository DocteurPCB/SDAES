# 8. Cartouches protégées

SNK a utilisé plusieurs mécanismes de protection. Certains ne concernent
que les données (chiffrement des ROM) : un `.neo` produit par NeoBuilder
contient déjà les données **déchiffrées**, rien n'est à faire en jeu.
D'autres agissent pendant le jeu (puce sur la cartouche qui répond au
68000) : SDAES les reproduit dans le FPGA P (`hdl/prog/p_mapper.v`).

## État de la prise en charge

| Protection | Jeux concernés (exemples) | SDAES |
|---|---|---|
| Banques P standard (écriture en 0x2FFFF0, 3 bits de banque comme MAME `data & 7`) | tous les jeux de plus de 2 Mo | ✅ intégré |
| CMC42 / CMC50 : chiffrement C, S, M1 | KOF 99-2003, Garou, Metal Slug 3-5, SVC, Matrimelee, Samurai Shodown V... | ✅ données déchiffrées dans le `.neo` |
| NEO-PCM2 : chiffrement V | KOF 2002, Matrimelee, Rage of the Dragons, Metal Slug 4... | ✅ données déchiffrées dans le `.neo` |
| **SMA** : banques brouillées, lecture de protection, générateur aléatoire | KOF 99, Garou, Metal Slug 3, KOF 2000 | ✅ intégré, **table par jeu à fournir** (voir plus bas) |
| **PVC** : RAM de protection, (dé)compactage de couleurs, banques à décalage libre | Metal Slug 5, SVC Chaos, KOF 2003 | ✅ intégré, reconnu automatiquement (NGH 0x268, 0x269, 0x271) |
| **Superposition KOF 98** : un code écrit en 0x20AAAA remplace deux mots en 0x000100 | KOF 98 | ✅ intégré, paramètres dans un fichier `.map` |
| **Banques de couche fixe**, type 2 (ROM S de 512 Ko, CMC50) | KOF 2000, SVC Chaos, KOF 2003 (Matrimelee) | ✅ intégré (FPGA SM), reconnu par le NGH |
| **Banques de couche fixe**, type 1 (CMC42/50) | Metal Slug 3, Metal Slug 4 ; Garou | ✅ banque constante ; ⚠️ **approché** pour Garou (voir plus bas) |
| **Metal Slug 5 Plus** (bootleg) : lecture en 0x2FFFF0, banques propres | Metal Slug 5 Plus | ✅ intégré (mode 4), reconnu par le NGH 268, la taille de P et le CRC de P1 |
| Bootleg Metal Slug 5 (`mslug5b`) : données brouillées seulement | Metal Slug 5 (bootleg) | ✅ banques standard ; `.neo` à désembrouiller avec `neotool build --descramble mslug5b` |
| Bootlegs de SVC Chaos (`svcboot`, `svcsplus` : PVC ; `svcplus`, `svcplusa` : rien) | SVC Chaos (bootlegs) | ✅ reconnus par la taille de P ; `.neo` avec `neotool mame` |
| Bootlegs de KOF 2003 : RAM de 8 Ko et banques (`kf2k3bl`, `kf2k3upl` : mode K3B ; `kf2k3pl`, `kf2k3bla` : mode K3P) | KOF 2003 (bootlegs), KOF 2004 Plus / Ultra Plus | ✅ intégrés (modes 5 et 6), reconnus par la taille de P ; `.neo` avec `neotool mame` |
| **PRO-CT0** : le sérialiseur de pixels du ZMC2 câblé sur le bus 68000 | Fatal Fury 2, Super Sidekicks | ✅ intégré (mode 3), reconnu par le NGH (047, 052) |
| Metal Slug X (puce Altera sur la carte PROG) | Metal Slug X | ✅ contrôles neutralisés dans P1 au chargement, reconnu par le NGH (250) |


## Fichiers de description (`.map` et `MAPPERS.TXT`)

Le firmware cherche la description d'un jeu dans cet ordre :

1. `<jeu>.map` dans le même dossier que `<jeu>.neo` ;
2. une section de `SDAES/MAPPERS.TXT` dont le nom est celui du fichier
   (sans `.neo`), ou dont `ngh` correspond à l'en-tête du `.neo` ;
3. la table interne (PVC, PRO-CT0, Metal Slug X) ;
4. sinon le schéma de banques standard.

Un jeu SMA connu (NGH 0x251, 0x253, 0x256, 0x257) sans description est
refusé avec le message « PROTECTION SMA: FICHIER .MAP REQUIS ».

Les versions **sans SMA** de ces jeux portent le même NGH : prototype de
Garou (`garoup`), Metal Slug 3 « h », KOF 2000 « n »... Dans MAME, les
versions SMA ont une zone P de 9 Mo (ROM interne de la puce comprise), les
autres 5 Mo au plus. Le firmware s'en sert : en dessous de 5 Mo, pas de
refus, et une section SMA de `MAPPERS.TXT` trouvée seulement par le NGH est
ignorée (une section trouvée par le nom du fichier, ou un `.map`, reste
appliquée).

Syntaxe (`#` ou `;` commencent un commentaire, nombres en hexadécimal
`0x...` ou en décimal) :

```
[kof99]                       ; pas de section dans un fichier .map
ngh        = 0x251            ; numéro de jeu (en-tête du .neo)
mapper     = sma              ; std | sma | pvc | ct0 | ms5p | k3b | k3p
bank_addr  = 0x2ffff0         ; adresse 68000 du registre de banque
bank_bits  = 14 6 8 10 12 5   ; bit de la donnée qui devient le bit 0, 1, ... 5 du numéro
bank_table = 0x000000 0x100000 0x200000 ...   ; jusqu'à 64 décalages (octets),
             0x3cc000 ...                     ; suite possible sur plusieurs lignes
prot       = 0x2fe446 0x9a37  ; adresse et valeur de la lecture de protection
rng        = 0x2ffff8 0x2ffffa; une ou deux adresses du générateur
rng_seed   = 0x2345           ; valeur initiale du générateur (défaut 0x2345)
overlay    = 0x20aaaa 0x0090 0x00f0 0x000100 0x00c2 0x00fd
             ; déclencheur, code d'activation, code de retrait,
             ; adresse du 1er mot remplacé, valeur 1, valeur 2
wait       = 0 0              ; cycles d'attente 68000 : zone ROM (0-1), zone PORT (0-2)
             ; 0 0 = pleine vitesse (défaut). Pour les jeux qui espacent leurs
             ; accès VRAM grâce à l'attente de leur cartouche d'origine.
fix_bank   = 2                ; banques de couche fixe NEO-CMC : 0, 1 (Garou), 2 (KOF 2000)
             ; par défaut : d'après le NGH
patch      = mslugx           ; correctif de P au chargement : none | mslugx
```

Le décalage de la table est ajouté à 0x100000 : la fenêtre 0x200000-0x2FFFFF
montre alors la région P à partir de `0x100000 + table[numéro]`.

Vérifier un fichier et voir les registres obtenus :

```
python3 tools/neotool.py mapper SDAES/MAPPERS.TXT --ngh 0x251
python3 tools/neotool.py mapper jeux/kof99.map
```

### Obtenir les tables SMA

Les tables de banques des jeux SMA (64 décalages par jeu) ne sont pas
reproduites dans ce dépôt : elles doivent être exactes et je ne peux pas
les vérifier ici. Elles sont publiées dans le code source de MAME (fichier
de la protection SMA, `src/devices/bus/neogeo/prot_sma.cpp` dans les
versions récentes, `sma_prot.cpp` / `neoprot.cpp` dans les plus
anciennes). L'outil fourni les extrait et produit `MAPPERS.TXT` :

```
python3 tools/neotool.py sma-from-mame prot_sma.cpp -o MAPPERS.TXT
```

Il reconnaît les deux façons d'écrire la permutation des bits utilisées
par MAME (`(((data>>N)&1)<<M)` et `bitswap<6>(...)`) et les adresses
installées par les fonctions `*_install_protection`. Copier ensuite
`MAPPERS.TXT` dans le dossier `SDAES/` de la carte SD.

Le KOF 98 (superposition) se décrit à la main, par exemple :

```
[kof98]
ngh     = 0x242
overlay = 0x20aaaa 0x0090 0x00f0 0x000100 0x00c2 0x00fd
```

(valeurs tirées de l'émulation MAME, à confirmer sur cartouche).

## Fonctionnement dans le FPGA P

* **Fenêtre P2 à décalage libre** : la base de la zone 0x200000 n'est plus un
  multiple de 1 Mo mais un décalage quelconque (mots de 16 bits). La lecture
  anticipée des deux candidats (P1 et P2) fonctionne à l'identique.
* **Banques standard** : seuls les bits 2-0 de la donnée écrite comptent
  (8 banques de 1 Mo, comme `write_banksel` de MAME) ; un jeu qui écrit
  par exemple 0xFFF9 sélectionne la banque 1.
* **SMA** : l'écriture au registre de banque passe par la permutation
  `bank_bits` puis par la table (BRAM de 64 entrées) ; trois cycles plus tard
  la nouvelle base est en place. Les lectures aux adresses `prot` et `rng`
  sont servies directement par le FPGA ; chaque lecture du générateur le fait
  avancer (registre à décalage de 16 bits, prises 2, 3, 5, 6, 7, 11, 12, 15),
  réinitialisé à `rng_seed` au lancement du jeu.
* **PVC** : la RAM de protection (8 Ko en 0x2FE000-0x2FFFFF) est placée dans
  les 8 derniers Ko de la SDRAM P (d'où la limite de P à 24 Mo) ; les mots
  0xFF0-0xFF9 sont gardés dans le FPGA :
  * écriture du mot 0xFF0 (0x2FFFE0) : la couleur est décompactée dans les
    mots 0xFF1 (vert/bleu, 5 bits chacun) et 0xFF2 (bit sombre/rouge) ;
  * écriture des mots 0xFF4-0xFF5 : la couleur est recompactée dans 0xFF6 ;
  * écriture des mots 0xFF8-0xFFF : base P2 = 0x100000 + {mot 0xFF9, octet
    haut du mot 0xFF8}, puis 0xFF8 = (0xFF8 & 0xFE00) | 0x00A0 et
    0xFF9 &= 0x7FFF (l'octet bas de 0xFF8 passe à 0xA0, le bit 0 de son
    octet haut et le bit 15 de 0xFF9 sont effacés).
  La RAM est remise à zéro par le RP2350 à chaque chargement.
* **Superposition** : après l'écriture du code d'activation à l'adresse de
  déclenchement, les lectures des deux mots désignés renvoient les valeurs
  de remplacement, jusqu'au code de retrait.
* Toute écriture du jeu annule la lecture anticipée en cours, pour ne jamais
  servir une donnée périmée.

Ces comportements suivent l'émulation de MAME ; ils sont vérifiés en
simulation (`hdl/sim/tb_prog.v`), pas encore sur cartouche.

## Banques de couche fixe (cartes NEO-CMC)

Sur les cartouches CMC dont la ROM S fait 512 Ko, la puce CMC ajoute deux
bits (A18-A17) à l'adresse S, d'après des valeurs que le jeu écrit dans les
colonnes cachées 40 à 47 de la carte de la couche fixe (VRAM 0x7500-0x75FF,
page « Fix bankswitching » du wiki neogeodev, MAME `neogeo_spr.cpp`).

**Ce que voit la cartouche.** Le LSPC lit ces colonnes à chaque ligne,
pendant le retour de ligne, et les présente sur le bus P comme des numéros
de tuile (P[11:0]) au verrou PCK2B. D'après le LSPC du cœur MiSTer NeoGeo
(reconstitué depuis le silicium), l'ordre des lectures d'une ligne est :
colonne 63, puis colonnes 0 à 46, deux impulsions PCK2B par colonne
(P15 = demi-tuile), soit 96 impulsions. Le numéro de ligne dans la tuile
(P[14:12] ; P12 change à chaque ligne) change à la lecture de la colonne 63 :
le FPGA SM retrouve ainsi la colonne de chaque impulsion
(`hdl/cha/cmc_fix.v`).

* **Type 2** (KOF 2000, SVC Chaos, KOF 2003, Matrimelee) : le mot de la
  colonne 40 + n (n = 0..6) donne 2 bits inversés pour chacune des tuiles
  6n à 6n+5. Il est capturé à la dernière ligne (7) d'une rangée, après ses
  colonnes visibles, et s'applique à la rangée suivante : c'est le
  décalage « y − 1 » de MAME. Reproduction complète.
* **Type 1** (Garou, Metal Slug 3 et 4) : un drapeau 0x0200 en colonne 40
  ou 41 et une banque (0xFFxx, bits 1-0 inversés) en colonne 44 ou 45 de la
  même rangée. MAME répartit ces valeurs sur les rangées de l'écran à partir
  de la rangée 2, ce qui exige de connaître le numéro de rangée à l'écran :
  **la cartouche ne le voit pas** (le LSPC lit la couche fixe en continu, y
  compris pendant le retour de trame, et aucun signal de synchronisation
  verticale n'arrive au connecteur). SDAES applique donc la dernière banque
  signalée jusqu'au changement suivant, et la banque 3 par défaut (comme
  MAME sans drapeau). C'est exact pour Metal Slug 3 et 4, qui n'utilisent
  en pratique qu'une banque ; pour Garou, les écrans qui changent de banque
  d'une rangée à l'autre peuvent afficher du texte faux. La vraie puce CMC42
  a forcément un moyen de se synchroniser sur la trame : il reste à le
  trouver (analyseur logique sur une cartouche Garou d'origine).
  **Alternative sûre : le prototype de Garou** (`garoup` dans MAME), complet
  et jouable, n'a ni SMA ni banques de couche fixe (ROM S de 128 Ko, carte
  standard) : il fonctionne entièrement avec SDAES. Mélanger sa ROM S avec
  le programme de la version finale ne marcherait pas : le programme final
  utilise d'autres numéros de tuiles, répartis sur 512 Ko.

Le type est choisi d'après le NGH (table de `firmware/rp2350/src/mapper.c`)
ou par la clé `fix_bank = 0|1|2` d'un fichier `.map` / `MAPPERS.TXT`. Il est
sans effet si la ROM S fait 128 Ko. Registre 0x06 du FPGA SM ; le registre
0x06 renvoie aussi (bits 13-8) la dernière colonne reconnue, utile pour
vérifier le repérage sur console.

**À valider sur matériel** : le repérage par changement de P[14:12] repose
sur le LSPC du cœur MiSTer ; la simulation (`hdl/sim/tb_cha.v`) rejoue cette
séquence.

## PRO-CT0 (Fatal Fury 2, Super Sidekicks)

Le PRO-CT0 (alias ALPHA-8921, SNK-9201) est le sérialiseur de pixels de
sprites des premières cartes CHA, ancêtre de la partie « sérialiseur » du
NEO-ZMC2. Sur Fatal Fury 2 et le premier Super Sidekicks, SNK en a placé
un sur la carte PROG, câblé sur le bus 68000, comme protection : le jeu y
charge des valeurs et vérifie les « pixels » relus. D'après MAME
(`prot_fatfury2.cpp`, `alpha_8921.cpp`) :

* chaque écriture en zone 0x200000-0x2FFFFF est un front d'horloge du
  sérialiseur, avec LOAD = A1, EVEN = A2, H = A3 ; le mot C de 32 bits est
  formé de A19..A4 (moitié haute) et D15..D0 (moitié basse), chaque moitié
  permutée (C1 = D4, C2 = D1...) ;
* une lecture dans la même zone renvoie GAD/GBD sur D7..D0
  (D0-D7 = GAD2, GAD3, GAD0, GAD1, GBD2, GBD3, GBD0, GBD1), avec EVEN = A2
  et H = A3 de l'adresse lue ;
* ces jeux n'ont pas de zone P2 (P de 1 Mo au plus) : toute la zone
  0x2xxxxx est la protection.

Le FPGA P reprend la logique de `hdl/cha/zmc2_dot.v` (décalages et sorties
identiques au modèle de MAME) ; le banc de test compare ses lectures à un
modèle transcrit de MAME.

## Metal Slug 5 : original, Plus et bootleg

Les trois versions portent le NGH 268 ; MAME les traite différemment :

| Version (MAME) | Zone P | En jeu | Données |
|---|---|---|---|
| `mslug5`, `mslug5h` (AES) | 8 Mo | PVC (mode 2) | P, C/S, M1, V chiffrés |
| `ms5plus` | 5 Mo | lecture en 0x2FFFF0-0x2FFFFF = 0x00A0 ; écriture de 0xA0 en 0x2FFFF0 : fenêtre P2 à l'octet 0xA0 ; écriture en 0x2FFFF4 : fenêtre à (donnée >> 4) Mo (mode 4) | C, M1, V : ceux de l'original (chiffrés) ; S brouillée |
| `mslug5b` | 5 Mo | rien : banques standard | S, V, C brouillés |

Le firmware choisit après la lecture de P : 8 Mo → PVC ; 5 Mo et CRC32 du
premier Mo égal à celui de `ms5-p1p.bin` (0x106B276F) → Metal Slug 5 Plus ;
sinon → banques standard. `mapper = ms5p` dans un `.map` force le mode 4.

**Fabriquer les `.neo`** (SDAES ne déchiffre rien au chargement) :

```
# bootleg : les fichiers de MAME, désembrouillés comme le fait MAME
python3 tools/neotool.py build -o mslug5b.neo --ngh 0x268 --name "METAL SLUG 5" \
    --p ms5b-p1.bin ms5b-p2.bin --s ms5b-s1.bin --m ms5b-m1.bin \
    --v1 ms5b-v1.bin ms5b-v2.bin ms5b-v3.bin ms5b-v4.bin \
    --c ms5b-c1.bin ms5b-c2.bin ms5b-c3.bin ms5b-c4.bin ms5b-c5.bin ms5b-c6.bin ms5b-c7.bin ms5b-c8.bin \
    --c-align --descramble mslug5b

# Metal Slug 5 Plus : P et S du Plus, le reste repris d'un mslug5.neo déchiffré
python3 tools/neotool.py build -o ms5plus.neo --ngh 0x268 --name "METAL SLUG 5 PLUS" \
    --from mslug5.neo --p ms5-p1p.bin ms5-p2p.bin ms5-p3p.bin --s ms5-s1p.bin --descramble ms5plus
```

`--descramble mslug5b` reprend `sx_decrypt(2)`, `mslug5b_vx_decrypt` et
`mslug5b_cx_decrypt` de MAME (`prot_misc.cpp`) ; `--c-align` place chaque
paire de ROM C comme dans la région de MAME (les c5/c6 du bootleg font 2 Mo
au lieu de 8). `--descramble ms5plus` reprend `sx_decrypt(1)`. Un `.neo`
produit par un autre outil peut déjà être désembrouillé : ne pas appliquer
deux fois.

## Bootlegs de SVC Chaos et de KOF 2003

D'après MAME (`boot_svc.cpp`, `boot_kof2k3.cpp`, `prot_kof2k3bl.cpp`) :

| Jeu MAME | NGH | Zone P | En jeu | Mode SDAES |
|---|---|---|---|---|
| `svc` (original) | 269 | 8 Mo | PVC | 2 |
| `svcboot`, `svcsplus` | 269 | 8 Mo | PVC | 2 |
| `svcplus`, `svcplusa` | 269 | 6 Mo | rien | 0 (banques standard) |
| `kof2003`, `kof2003h` | 271 | 9 Mo | PVC | 2 |
| `kf2k3bl`, `kf2k3upl` | 271 | 8 Mo | RAM 8 Ko + banque, mot en 0x058196 | 5 (K3B) |
| `kf2k3pl`, `kf2k3bla` | 271 | 7 Mo | RAM 8 Ko + banque | 6 (K3P) |

Le firmware choisit d'après le NGH et la taille de P ; `mapper = k3b` ou
`k3p` dans un `.map` force le mode. Aucun de ces bootlegs n'utilise les
banques de couche fixe CMC (ROM S de 128 Ko).

**Protection des bootlegs de KOF 2003** : 8 Ko de RAM en 0x2FE000 comme la
PVC, sans les couleurs. Une écriture dans les mots 0xFF8 ou 0xFF9
(0x2FFFF0, 0x2FFFF2) change la fenêtre P2 :

* K3B : 0x100000 + {octet haut de 0xFF9, octet bas de 0xFF9, octet haut de
  0xFF8}, puis 0xFF8 = (0xFF8 & 0xFE00) | 0x00A0 et 0xFF9 &= 0x7FFF, comme
  la PVC ; le mot lu en 0x058196 prend pour octet bas l'octet bas de 0xFF9
  (0 au départ) ;
* K3P : la même chose avec l'octet bas de 0xFF8 au lieu de l'octet haut, et
  sans écrire 0xA0.

**Fabriquer les `.neo`** : `neotool mame <jeu>` reproduit l'agencement des
fichiers de MAME (moitiés échangées, ordre des ROM V) et les fonctions de
remise en ordre de MAME (P, C, S, M1) :

```
python3 tools/neotool.py mame svcplus --dir roms/svcplus -o svcplus.neo
python3 tools/neotool.py mame kf2k3bl --dir roms/kf2k3bl -o kf2k3bl.neo --from kof2003.neo
```

Les C et V des bootlegs de KOF 2003 sont ceux de l'original, chiffrés :
`--from` les reprend d'un `kof2003.neo` déchiffré. Même chose pour
`ms5plus` (`--from mslug5.neo`). Jeux connus : `svcboot`, `svcplus`,
`svcplusa`, `svcsplus`, `kf2k3bl`, `kf2k3bla`, `kf2k3pl`, `kf2k3upl`,
`ms5plus`, `mslug5b`. Les fonctions sont vérifiées par des tests contre une
transcription littérale du code de MAME, pas contre de vrais fichiers.

### Correction de la PVC

En reprenant ce code, une erreur de la PVC a été corrigée : après un
changement de banque, MAME écrit 0xA0 dans l'octet **bas** du mot 0xFF8 et
efface le bit de poids fort du mot 0xFF9 (`ff8 = (ff8 & 0xFE00) | 0x00A0`,
`ff9 &= 0x7FFF`). SDAES le faisait sur les octets inverses. Le changement de
banque est aussi déclenché par une écriture dans les mots 0xFFA à 0xFFF,
comme dans MAME.

## Metal Slug X

La carte PROGEOP de Metal Slug X porte une puce Altera (EPM7128) reliée à
la ROM P1, dont la configuration n'est pas connue. Le modèle actuel de MAME
(`prot_mslugx.cpp`) lit une variable de la RAM de travail du 68000, avec un
commentaire « How should this be calculated? » : la carte PROG ne voit pas
A20-A23, l'imiter serait fragile.

SDAES fait comme la réparation décrite sur le wiki neogeodev (« Repairing
Metal Slug X ») : une ROM P1 **modifiée**, sans contrôle de protection, sur
une carte à banques standard (PROGBK1). Le firmware applique la modification
pendant le chargement, avec les mêmes changements que MAME 0.145
(`mslugx_install_protection`, dans `neoprot.c`) :

* dans P1 (premier Mo), chaque `andi.w #$1,D3` suivi d'un `bne` voit ce
  `bne` (deux mots) remplacé par deux NOP (0x4E71) ;
* les mots 0x3BDC, 0x3BDE, 0x3BE0, 0x3C0C, 0x3C0E, 0x3C10, 0x3C36 et
  0x3C38 deviennent des NOP.

Le message de chargement indique le nombre de séquences trouvées
(« P1 CORRIGEE: n »). Le fichier `.neo` n'est pas modifié. Reconnu par le
NGH 250 ; ailleurs, `patch = mslugx` dans un fichier `.map`. À vérifier sur
console : ces modifications viennent de l'émulation.
