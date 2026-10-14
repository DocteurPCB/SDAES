/*
 * Description des protections de cartouche (voir docs/08-cartouches-protegees.md).
 *
 * Sources, par ordre de priorité :
 *   1. fichier <jeu>.map à côté de <jeu>.neo
 *   2. section du fichier 0:/SDAES/MAPPERS.TXT dont le nom est celui du
 *      fichier (sans .neo) ou dont "ngh" correspond à l'en-tête du .neo
 *   3. table interne (PVC : Metal Slug 5, SVC Chaos, KOF 2003 ;
 *      PRO-CT0 : Fatal Fury 2, Super Sidekicks)
 *   4. sinon : schéma de banque standard
 */
#ifndef SDAES_MAPPER_H
#define SDAES_MAPPER_H

#include <stdint.h>
#include <stdbool.h>

typedef enum { MAP_STD = 0, MAP_SMA = 1, MAP_PVC = 2, MAP_CT0 = 3, MAP_MS5P = 4,
               MAP_K3B = 5, MAP_K3P = 6 } map_mode_t;

typedef struct {
    char       name[32];
    uint32_t   ngh;            /* 0 = non précisé */
    map_mode_t mode;
    /* SMA */
    uint32_t   bank_addr;      /* adresse 68000 du registre de banque */
    uint8_t    bank_bits[6];   /* bit de la donnée -> bit 0..5 du numéro */
    uint32_t   bank_table[64]; /* décalages en octets après 0x100000 */
    int        bank_count;
    uint32_t   prot_addr, prot_value;   /* prot_addr = 0 : aucune */
    uint32_t   rng_addr[2];             /* 0 : aucun */
    uint16_t   rng_seed;
    /* superposition (KOF 98) */
    bool       ovl;
    uint32_t   ovl_trig, ovl_on, ovl_off, ovl_addr, ovl_v0, ovl_v1;
    /* cycles d'attente 68000 demandés à la console (/ROMWAIT, /PWAIT0-1) :
     * zone ROM 0 ou 1, zone PORT 0, 1 ou 2 ; 0 = pleine vitesse */
    uint8_t    rom_wait, port_wait;
    /* banques de couche fixe NEO-CMC (FPGA SM) : 0 aucune, 1 type Garou,
     * 2 type KOF 2000 ; FIX_BANK_AUTO = selon le NGH (mapper_fix_bank) */
    uint8_t    fix_bank;
    /* correctif appliqué à P au chargement */
    uint8_t    patch;          /* PATCH_NONE, PATCH_MSLUGX */
    bool       by_name;        /* section de MAPPERS.TXT trouvée par son nom */
    bool       builtin;        /* description de la table interne (d'après le NGH) */
    uint32_t   ngh_seen;       /* NGH du jeu pour lequel la description a été choisie */
} mapper_t;

/* Les jeux SMA ont une zone P de 9 Mo (ROM interne de la puce comprise) ;
 * leurs versions sans SMA (prototype de Garou, Metal Slug 3 « h »,
 * KOF 2000 « n »...) ont le même NGH et une zone P de 5 Mo au plus. */
#define SMA_MIN_PSIZE  0x500001u

/* Jeux PVC et leurs bootlegs (même NGH), départagés par la taille de P
 * (régions de MAME) :
 *   Metal Slug 5 (268) : 8 Mo PVC ; 5 Mo : Plus (CRC32 du 1er Mo de P =
 *     celui de ms5-p1p.bin) ou bootleg mslug5b (banques standard)
 *   SVC Chaos (269)    : 8 Mo PVC (svc, svcboot, svcsplus) ; 6 Mo :
 *     svcplus, svcplusa (banques standard)
 *   KOF 2003 (271)     : 9 Mo PVC ; 8 Mo : kf2k3bl, kf2k3upl (K3B) ;
 *     7 Mo : kf2k3pl, kf2k3bla (K3P) */
#define MS5PLUS_P1_CRC     0x106B276Fu

/* Choix final, une fois P lu (crc_p1 : CRC32 du 1er Mo). */
void mapper_pvc_resolve(mapper_t *m, uint32_t psize, uint32_t crc_p1);

enum { PATCH_NONE = 0, PATCH_MSLUGX = 1 };

#define FIX_BANK_AUTO 0xFF

/* Type de banques de couche fixe d'après le NGH (cartes NEO-CMC). */
uint8_t mapper_fix_bank(uint32_t ngh);

/* Initialise une description "standard". */
void mapper_default(mapper_t *m);

/* Cherche dans un texte (contenu d'un .map ou de MAPPERS.TXT) la description
 * correspondant au jeu. section = NULL : le texte entier décrit le jeu.
 * Retourne true si trouvé ; err reçoit un message en cas d'erreur de syntaxe. */
bool mapper_parse(const char *text, const char *game_name, uint32_t ngh,
                  bool whole_file, mapper_t *out, char *err, int errlen);

/* Description interne pour un numéro NGH (PVC), true si connue. */
bool mapper_builtin(uint32_t ngh, mapper_t *out);

/* Valeurs des registres du FPGA P (cf. hdl/prog/p_mapper.v). */
typedef struct { uint8_t reg; uint32_t val; } mapper_reg_t;
int  mapper_registers(const mapper_t *m, mapper_reg_t *regs, int max);

#endif
