# 8. Cartouches protégées

SNK a utilisé plusieurs mécanismes de protection. Certains ne concernent
que les données (chiffrement des ROM) : un `.neo` produit par NeoBuilder
contient déjà les données **déchiffrées**, rien n'est à faire en jeu.
D'autres agissent pendant le jeu (puce sur la cartouche qui répond au
68000) : SDAES les reproduit dans le FPGA P (`hdl/prog/p_mapper.v`).

## État de la prise en charge

| Protection | Jeux concernés (exemples) | SDAES |
|---|---|---|
| Banques P standard (écriture en 0x2FFFF0) | tous les jeux de plus de 2 Mo | ✅ intégré |
| CMC42 / CMC50 : chiffrement C, S, M1 | KOF 99-2003, Garou, Metal Slug 3-5, SVC, Matrimelee, Samurai Shodown V... | ✅ données déchiffrées dans le `.neo` |
| NEO-PCM2 : chiffrement V | KOF 2002, Matrimelee, Rage of the Dragons, Metal Slug 4... | ✅ données déchiffrées dans le `.neo` |
| **SMA** : banques brouillées, lecture de protection, générateur aléatoire | KOF 99, Garou, Metal Slug 3, KOF 2000 | ✅ intégré, **table par jeu à fournir** (voir plus bas) |
| **PVC** : RAM de protection, (dé)compactage de couleurs, banques à décalage libre | Metal Slug 5, SVC Chaos, KOF 2003 | ✅ intégré, reconnu automatiquement (NGH 0x268, 0x269, 0x271) |
| **Superposition KOF 98** : un code écrit en 0x20AAAA remplace deux mots en 0x000100 | KOF 98 | ✅ intégré, paramètres dans un fichier `.map` |
| **Banques de couche fixe**, type 2 (ROM S de 512 Ko, CMC50) | KOF 2000, SVC Chaos, KOF 2003 (Matrimelee) | ✅ intégré (FPGA SM), reconnu par le NGH |
| **Banques de couche fixe**, type 1 (CMC42/50) | Metal Slug 3, Metal Slug 4 ; Garou | ✅ banque constante ; ⚠️ **approché** pour Garou (voir plus bas) |
| PRO-CT0 (Fatal Fury 2, Super Sidekicks), protection de Metal Slug X | — | ❌ non traité |


## Fichiers de description (`.map` et `MAPPERS.TXT`)

Le firmware cherche la description d'un jeu dans cet ordre :

1. `<jeu>.map` dans le même dossier que `<jeu>.neo` ;
2. une section de `SDAES/MAPPERS.TXT` dont le nom est celui du fichier
   (sans `.neo`), ou dont `ngh` correspond à l'en-tête du `.neo` ;
3. la table interne (PVC) ;
4. sinon le schéma de banques standard.

Un jeu SMA connu (NGH 0x251, 0x253, 0x256, 0x257) sans description est
refusé avec le message « PROTECTION SMA: FICHIER .MAP REQUIS ».

Syntaxe (`#` ou `;` commencent un commentaire, nombres en hexadécimal
`0x...` ou en décimal) :

```
[kof99]                       ; pas de section dans un fichier .map
ngh        = 0x251            ; numéro de jeu (en-tête du .neo)
mapper     = sma              ; std | sma | pvc
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
  * écriture des mots 0xFF8-0xFF9 : base P2 = 0x100000 + {mot 0xFF9, octet
    haut du mot 0xFF8}, puis l'octet haut de 0xFF8 passe à 0xA0 et les bits
    0 de 0xFF8 et 7 de 0xFF9 sont effacés.
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

Le type est choisi d'après le NGH (table de `firmware/rp2350/src/mapper.c`)
ou par la clé `fix_bank = 0|1|2` d'un fichier `.map` / `MAPPERS.TXT`. Il est
sans effet si la ROM S fait 128 Ko. Registre 0x06 du FPGA SM ; le registre
0x06 renvoie aussi (bits 13-8) la dernière colonne reconnue, utile pour
vérifier le repérage sur console.

**À valider sur matériel** : le repérage par changement de P[14:12] repose
sur le LSPC du cœur MiSTer ; la simulation (`hdl/sim/tb_cha.v`) rejoue cette
séquence.
