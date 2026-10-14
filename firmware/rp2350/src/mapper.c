/*
 * Lecture des descriptions de protections (format texte, voir
 * docs/08-cartouches-protegees.md) et conversion en registres du FPGA P.
 */
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <ctype.h>
#include "mapper.h"

#define PORT_BASE 0x200000u

static bool ngh_match(uint32_t want, uint32_t have);

void mapper_default(mapper_t *m)
{
    memset(m, 0, sizeof(*m));
    m->mode = MAP_STD;
    for (int i = 0; i < 6; i++) m->bank_bits[i] = (uint8_t)i;
    m->rng_seed = 0x2345;
    m->fix_bank = FIX_BANK_AUTO;
}

/* Jeux NEO-CMC dont la ROM S fait 512 Ko (wiki neogeodev « Fix bankswitching »,
 * MAME neogeo_spr.cpp). Sans effet si la ROM S fait 128 Ko (masque). */
uint8_t mapper_fix_bank(uint32_t ngh)
{
    static const struct { uint16_t ngh; uint8_t type; } t[] = {
        { 0x253, 1 },   /* Garou */
        { 0x256, 1 },   /* Metal Slug 3 */
        { 0x263, 1 },   /* Metal Slug 4 */
        { 0x257, 2 },   /* KOF 2000 */
        { 0x266, 2 },   /* Matrimelee */
        { 0x269, 2 },   /* SVC Chaos */
        { 0x271, 2 },   /* KOF 2003 */
    };
    for (unsigned i = 0; i < sizeof(t) / sizeof(t[0]); i++)
        if (ngh_match(t[i].ngh, ngh)) return t[i].type;
    return 0;
}

bool mapper_builtin(uint32_t ngh, mapper_t *out)
{
    /* PVC : aucun paramètre propre au jeu */
    static const uint32_t pvc[] = { 0x268, 0x269, 0x271, 268, 269, 271 };
    for (unsigned i = 0; i < sizeof(pvc) / sizeof(pvc[0]); i++) {
        if (ngh == pvc[i]) {
            mapper_default(out);
            out->mode = MAP_PVC;
            out->builtin = true;
            out->ngh_seen = ngh;
            snprintf(out->name, sizeof(out->name), "pvc-%x", (unsigned)ngh);
            return true;
        }
    }
    /* Metal Slug X : banques standard + correctif de P1 (neo_loader.c) */
    static const uint32_t msx[] = { 0x250, 250, 0x2500, 2500 };
    for (unsigned i = 0; i < sizeof(msx) / sizeof(msx[0]); i++) {
        if (ngh == msx[i]) {
            mapper_default(out);
            out->patch = PATCH_MSLUGX;
            snprintf(out->name, sizeof(out->name), "mslugx");
            return true;
        }
    }
    /* PRO-CT0 (sérialiseur du ZMC2 sur le bus 68000) : aucun paramètre */
    static const uint32_t ct0[] = { 0x047, 0x052, 47, 52 };   /* Fatal Fury 2, Super Sidekicks */
    for (unsigned i = 0; i < sizeof(ct0) / sizeof(ct0[0]); i++) {
        if (ngh == ct0[i]) {
            mapper_default(out);
            out->mode = MAP_CT0;
            snprintf(out->name, sizeof(out->name), "pro-ct0-%03x", (unsigned)ngh);
            return true;
        }
    }
    return false;
}

void mapper_pvc_resolve(mapper_t *m, uint32_t psize, uint32_t crc_p1)
{
    if (!m->builtin || m->mode != MAP_PVC) return;
    const char *name = NULL;
    if (ngh_match(0x268, m->ngh_seen) && psize <= 0x500000u) {
        m->mode = (crc_p1 == MS5PLUS_P1_CRC) ? MAP_MS5P : MAP_STD;
        name = m->mode == MAP_MS5P ? "ms5plus" : "mslug5-bootleg";
    } else if (ngh_match(0x269, m->ngh_seen) && psize <= 0x700000u) {
        m->mode = MAP_STD;
        name = "svcplus";
    } else if (ngh_match(0x271, m->ngh_seen) && psize <= 0x800000u) {
        m->mode = psize > 0x700000u ? MAP_K3B : psize > 0x600000u ? MAP_K3P : MAP_STD;
        name = m->mode == MAP_K3B ? "kf2k3bl" : m->mode == MAP_K3P ? "kf2k3pl" : "kof2003-bootleg";
    }
    if (name) {
        m->fix_bank = 0;             /* bootlegs : ROM S de 128 Ko, pas de banques CMC */
        snprintf(m->name, sizeof(m->name), "%s", name);
    }
}

/* NGH écrit en hexadécimal "à la SNK" (0x251) ou en décimal (251) */
static bool ngh_match(uint32_t want, uint32_t have)
{
    if (!want) return false;
    if (want == have) return true;
    uint32_t dec = 0, mul = 1, v = want;
    while (v) { if ((v & 0xF) > 9) return false; dec += (v & 0xF) * mul; mul *= 10; v >>= 4; }
    return dec == have;
}

static int ieq(const char *a, const char *b)
{
    while (*a && *b) { if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0; a++; b++; }
    return *a == *b;
}

/* lit des entiers (hex 0x.. ou décimal) dans une chaîne */
static int parse_nums(const char *s, uint32_t *out, int max)
{
    int n = 0;
    while (*s && n < max) {
        while (*s && !isxdigit((unsigned char)*s)) s++;
        if (!*s) break;
        char *end;
        out[n++] = (uint32_t)strtoul(s, &end, 0);
        if (end == s) break;
        s = end;
    }
    return n;
}

typedef struct {
    mapper_t m;
    bool     in_table;       /* suite de "bank_table" sur les lignes suivantes */
} sect_t;

static bool apply_key(sect_t *st, const char *key, const char *val, char *err, int errlen)
{
    mapper_t *m = &st->m;
    uint32_t v[8];
    st->in_table = false;
    if (ieq(key, "ngh")) {
        if (parse_nums(val, v, 1) != 1) goto bad;
        m->ngh = v[0];
    } else if (ieq(key, "mapper")) {
        while (*val == ' ' || *val == '\t') val++;
        if      (!strncmp(val, "sma", 3)) m->mode = MAP_SMA;
        else if (!strncmp(val, "pvc", 3)) m->mode = MAP_PVC;
        else if (!strncmp(val, "std", 3)) m->mode = MAP_STD;
        else if (!strncmp(val, "ct0", 3)) m->mode = MAP_CT0;
        else if (!strncmp(val, "ms5p", 4)) m->mode = MAP_MS5P;
        else if (!strncmp(val, "k3b", 3)) m->mode = MAP_K3B;
        else if (!strncmp(val, "k3p", 3)) m->mode = MAP_K3P;
        else goto bad;
    } else if (ieq(key, "bank_addr")) {
        if (parse_nums(val, v, 1) != 1) goto bad;
        m->bank_addr = v[0];
    } else if (ieq(key, "bank_bits")) {
        if (parse_nums(val, v, 6) != 6) goto bad;
        for (int i = 0; i < 6; i++) { if (v[i] > 15) goto bad; m->bank_bits[i] = (uint8_t)v[i]; }
    } else if (ieq(key, "bank_table")) {
        m->bank_count = parse_nums(val, m->bank_table, 64);
        st->in_table = true;
    } else if (ieq(key, "prot")) {
        if (parse_nums(val, v, 2) != 2) goto bad;
        m->prot_addr = v[0]; m->prot_value = v[1];
    } else if (ieq(key, "rng")) {
        int n = parse_nums(val, v, 2);
        if (n < 1) goto bad;
        m->rng_addr[0] = v[0]; m->rng_addr[1] = n > 1 ? v[1] : 0;
    } else if (ieq(key, "rng_seed")) {
        if (parse_nums(val, v, 1) != 1) goto bad;
        m->rng_seed = (uint16_t)v[0];
    } else if (ieq(key, "overlay")) {
        /* déclencheur, code_on, code_off, adresse, valeur0, valeur1 */
        if (parse_nums(val, v, 6) != 6) goto bad;
        m->ovl = true;
        m->ovl_trig = v[0]; m->ovl_on = v[1]; m->ovl_off = v[2];
        m->ovl_addr = v[3]; m->ovl_v0 = v[4]; m->ovl_v1 = v[5];
    } else if (ieq(key, "fix_bank")) {
        /* banques de couche fixe NEO-CMC : 0, 1 (Garou) ou 2 (KOF 2000) */
        if (parse_nums(val, v, 1) != 1 || v[0] > 2) goto bad;
        m->fix_bank = (uint8_t)v[0];
    } else if (ieq(key, "patch")) {
        while (*val == ' ' || *val == '\t') val++;
        if      (!strncmp(val, "mslugx", 6)) m->patch = PATCH_MSLUGX;
        else if (!strncmp(val, "none", 4))   m->patch = PATCH_NONE;
        else goto bad;
    } else if (ieq(key, "wait")) {
        /* cycles d'attente : zone ROM (0-1), zone PORT (0-2) */
        if (parse_nums(val, v, 2) != 2 || v[0] > 1 || v[1] > 2) goto bad;
        m->rom_wait = (uint8_t)v[0]; m->port_wait = (uint8_t)v[1];
    } else {
        snprintf(err, errlen, "CLE INCONNUE: %.20s", key);
        return false;
    }
    return true;
bad:
    snprintf(err, errlen, "VALEUR INVALIDE: %.20s", key);
    return false;
}

bool mapper_parse(const char *text, const char *game_name, uint32_t ngh,
                  bool whole_file, mapper_t *out, char *err, int errlen)
{
    sect_t cur;
    bool active = whole_file, found = false, by_name = false;
    char line[512];
    mapper_default(&cur.m);
    cur.in_table = false;
    err[0] = 0;

    /* une section trouvée par son nom l'emporte sur une section trouvée par NGH */
    #define CLOSE_SECTION() do { \
        if (active && !whole_file) { \
            bool nm = game_name && ieq(cur.m.name, game_name); \
            bool nn = ngh_match(cur.m.ngh, ngh); \
            if ((nm && !by_name) || (nn && !found)) { \
                *out = cur.m; out->by_name = nm; found = true; by_name = by_name || nm; } \
        } } while (0)

    const char *p = text;
    while (*p) {
        int n = 0;
        while (*p && *p != '\n' && n < (int)sizeof(line) - 1) line[n++] = *p++;
        while (*p && *p != '\n') p++;
        if (*p == '\n') p++;
        line[n] = 0;
        char *c = strpbrk(line, "#;");
        if (c) *c = 0;
        char *s = line;
        while (*s == ' ' || *s == '\t' || *s == '\r') s++;
        int l = (int)strlen(s);
        while (l && (s[l - 1] == ' ' || s[l - 1] == '\t' || s[l - 1] == '\r')) s[--l] = 0;
        if (!*s) continue;

        if (*s == '[') {
            CLOSE_SECTION();
            mapper_default(&cur.m);
            cur.in_table = false;
            char *e = strchr(s, ']');
            if (!e) { snprintf(err, errlen, "SECTION INVALIDE"); return false; }
            *e = 0;
            snprintf(cur.m.name, sizeof(cur.m.name), "%s", s + 1);
            active = true;
            continue;
        }
        char *eq = strchr(s, '=');
        if (!eq) {
            /* suite de bank_table */
            if (cur.in_table) {
                cur.m.bank_count += parse_nums(s, cur.m.bank_table + cur.m.bank_count, 64 - cur.m.bank_count);
                continue;
            }
            snprintf(err, errlen, "LIGNE INVALIDE");
            return false;
        }
        *eq = 0;
        char *key = s;
        int kl = (int)strlen(key);
        while (kl && (key[kl - 1] == ' ' || key[kl - 1] == '\t')) key[--kl] = 0;
        if (active && !apply_key(&cur, key, eq + 1, err, errlen)) return false;
    }
    if (whole_file) {
        *out = cur.m;
        if (game_name) snprintf(out->name, sizeof(out->name), "%s", game_name);
        return true;
    }
    CLOSE_SECTION();
    return found;
    #undef CLOSE_SECTION
}

static uint32_t port_index(uint32_t addr) { return ((addr - PORT_BASE) >> 1) & 0x7FFFF; }

int mapper_registers(const mapper_t *m, mapper_reg_t *r, int max)
{
    int n = 0;
    #define REG(a, v) do { if (n < max) { r[n].reg = (a); r[n].val = (v); n++; } } while (0)
    REG(0x0A, (uint32_t)m->mode | (m->ovl ? 0x100u : 0));
    /* 0x04 : {PWAIT1, PWAIT0, ROMWAIT}, actifs à 0 (wiki neogeodev « Wait cycle ») */
    static const uint8_t pwait[3] = { 0x3, 0x2, 0x1 };
    REG(0x04, (uint32_t)(pwait[m->port_wait] << 1) | (m->rom_wait ? 0u : 1u));
    if (m->mode == MAP_SMA) {
        uint32_t perm = 0;
        for (int i = 0; i < 6; i++) perm |= (uint32_t)(m->bank_bits[i] & 0xF) << (4 * i);
        REG(0x0B, port_index(m->bank_addr));
        REG(0x0C, perm);
        REG(0x0D, m->prot_addr ? (0x80000000u | port_index(m->prot_addr)) : 0);
        REG(0x0E, m->prot_value & 0xFFFF);
        REG(0x0F, m->rng_addr[0] ? (0x80000000u | port_index(m->rng_addr[0])) : 0);
        REG(0x15, m->rng_addr[1] ? (0x80000000u | port_index(m->rng_addr[1])) : 0);
        REG(0x16, m->rng_seed);
    }
    if (m->ovl) {
        REG(0x17, port_index(m->ovl_trig));
        REG(0x18, ((m->ovl_on & 0xFFFF) << 16) | (m->ovl_off & 0xFFFF));
        REG(0x19, (m->ovl_addr >> 1) & 0x7FFFF);
        REG(0x1A, ((m->ovl_v0 & 0xFFFF) << 16) | (m->ovl_v1 & 0xFFFF));
    }
    return n;
    #undef REG
}
