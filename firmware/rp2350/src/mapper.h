/*
 * Description des protections de cartouche (voir docs/08-cartouches-protegees.md).
 *
 * Sources, par ordre de priorité :
 *   1. fichier <jeu>.map à côté de <jeu>.neo
 *   2. section du fichier 0:/SDAES/MAPPERS.TXT dont le nom est celui du
 *      fichier (sans .neo) ou dont "ngh" correspond à l'en-tête du .neo
 *   3. table interne (PVC : Metal Slug 5, SVC Chaos, KOF 2003)
 *   4. sinon : schéma de banque standard
 */
#ifndef SDAES_MAPPER_H
#define SDAES_MAPPER_H

#include <stdint.h>
#include <stdbool.h>

typedef enum { MAP_STD = 0, MAP_SMA = 1, MAP_PVC = 2 } map_mode_t;

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
} mapper_t;

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
