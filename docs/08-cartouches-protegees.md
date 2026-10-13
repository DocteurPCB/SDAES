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
| **Banques de couche fixe** (ROM S de 512 Ko, puces CMC) | Garou, Metal Slug 3, KOF 2000-2003, Metal Slug 4-5, SVC... | ❌ **à faire** (voir plus bas) |
| PRO-CT0 (Fatal Fury 2, Super Sidekicks), protection de Metal Slug X | — | ❌ non traité |

Conséquence de la ligne « banques de couche fixe » : les jeux CMC dont la
ROM S fait plus de 128 Ko démarrent, mais le texte de la couche fixe (score,
crédits, messages) risque d'être faux tant que ce point n'est pas réglé.

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

## À faire : banques de couche fixe

Sur les cartouches CMC dont la ROM S dépasse 128 Ko, la puce CMC choisit la
banque de 128 Ko de la couche fixe d'après des valeurs que le jeu écrit dans
des colonnes cachées de la table de la couche fixe (VRAM 0x7500-0x75FF).
MAME l'émule au niveau de l'image (deux variantes : Garou/Metal Slug 3 d'un
côté, KOF 2000 et suivants de l'autre).

Sur le bus de la cartouche, seule la ROM S voit passer ces informations, au
moment où le LSPC lit les colonnes cachées. Pour reproduire la puce CMC dans
le FPGA SM, il faut d'abord savoir exactement ce que le LSPC présente sur le
bus P lors de ces lectures. Plan proposé :

1. sur une console, avec une cartouche d'origine concernée, capturer à
   l'analyseur logique le bus P au front de PCK2B pendant une ligne entière ;
2. identifier les cycles des colonnes cachées et le format des valeurs ;
3. ajouter au FPGA SM un registre de banque par ligne (bits hauts de
   l'adresse S), alimenté par ces cycles, sur le modèle de MAME.
