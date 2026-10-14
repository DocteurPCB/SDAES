/*
 * Chargement d'un fichier .neo dans les mémoires de la cartouche.
 *
 * Ordre des régions dans le fichier : P, S, M1, V1, V2, C (lecture
 * séquentielle, la plus rapide sur carte SD). Chaque bloc lu est envoyé par
 * DMA pendant que le bloc suivant est lu (double tampon).
 *
 *   P  -> FPGA P  (SDRAM), adresse 0
 *   S  -> FPGA SM (SRAM),  adresse 0x00000
 *   M1 -> FPGA SM (SRAM),  adresse 0x80000
 *   V1 -> FPGA V  (SDRAM), adresse 0
 *   V2 -> FPGA V  (SDRAM), adresse v2_base (après V1, aligné sur 64 Ko)
 *   C  -> FPGA C  (SDRAM), adresse 0
 *
 * Doit rester cohérent avec tools/neotool.py (load_plan) et le FPGA.
 */
#include <string.h>
#include <stdio.h>
#include "ff.h"
#include "neo_loader.h"
#include "mapper.h"
#include "qlink.h"
#include "../../../protocol/sdaes_mailbox.h"

#define CHUNK        (32 * 1024)
#define LIMIT_P      (24u << 20)   /* SDRAM P : 25 Mo moins la RAM PVC */
#define PVC_RAM_BYTE 0x18FE000u    /* RAM de protection PVC (8 Ko), cf. prog_p_core.v */
#define MAP_TEXT_MAX (16 * 1024)
#define LIMIT_S      (512u << 10)
#define LIMIT_M      (512u << 10)
#define LIMIT_V      (32u << 20)
#define LIMIT_C      (64u << 20)
#define SRAM_M1_BASE 0x80000u

static uint8_t buf[2][CHUNK] __attribute__((aligned(4)));

static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }

static uint32_t mask_for(uint32_t size)
{
    if (size <= 1) return 0;
    uint32_t m = 1;
    while (m < size) m <<= 1;
    return m - 1;
}

int neo_parse_header(const uint8_t *raw, neo_header_t *h)
{
    if (raw[0] != 'N' || raw[1] != 'E' || raw[2] != 'O' || raw[3] != 1)
        return -1;
    h->psize  = rd32(raw + 0x04);
    h->ssize  = rd32(raw + 0x08);
    h->msize  = rd32(raw + 0x0C);
    h->v1size = rd32(raw + 0x10);
    h->v2size = rd32(raw + 0x14);
    h->csize  = rd32(raw + 0x18);
    h->year   = rd32(raw + 0x1C);
    h->genre  = rd32(raw + 0x20);
    h->screenshot = rd32(raw + 0x24);
    h->ngh    = rd32(raw + 0x28);
    memcpy(h->name, raw + 0x2C, 33); h->name[32] = 0;
    memcpy(h->manu, raw + 0x4D, 17); h->manu[16] = 0;
    return 0;
}

/* Recherche, pendant l'envoi de P1, des contrôles de protection de Metal
 * Slug X à neutraliser (cf. msx_patch_apply). Mots 68000 ; le .neo stocke P
 * en petit-boutiste. */
#define MSX_MAX_HITS 64
typedef struct {
    bool     on;
    uint16_t w0, w1;            /* deux mots précédents */
    uint32_t hits[MSX_MAX_HITS];
    int      n;
} msx_scan_t;

static void msx_scan(msx_scan_t *s, uint32_t addr, const uint8_t *b, uint32_t n)
{
    for (uint32_t i = 0; i + 1 < n; i += 2) {
        uint32_t a = addr + i;
        if (a >= 0x100000u) return;                 /* P1 seulement, comme MAME */
        uint16_t w = (uint16_t)(b[i] | (b[i + 1] << 8));
        /* andi.w #$1, D3 ; bne xxxx */
        if (s->w0 == 0x0243 && s->w1 == 0x0001 && w == 0x6600 && s->n < MSX_MAX_HITS)
            s->hits[s->n++] = a;
        s->w0 = s->w1;
        s->w1 = w;
    }
}

typedef struct {
    FIL            *f;
    uint32_t        done, total;
    neo_progress_cb cb;
    uint16_t        last;
    msx_scan_t     *scan;       /* NULL : pas de recherche */
} xfer_t;

/* envoie 'size' octets du fichier vers (lien, espace, adresse) */
static int stream(xfer_t *x, link_id_t l, uint8_t space, uint32_t addr, uint32_t size)
{
    int cur = 0;
    bool pending = false;
    link_id_t pend_link = l;
    while (size) {
        UINT n = size > CHUNK ? CHUNK : size, got = 0;
        /* lecture SD pendant que le bloc précédent part en DMA */
        if (f_read(x->f, buf[cur], n, &got) != FR_OK || got != n) {
            if (pending) qlink_mem_write_finish(pend_link);
            return -1;
        }
        if (pending) qlink_mem_write_finish(pend_link);
        if (x->scan && x->scan->on) msx_scan(x->scan, addr, buf[cur], n);
        qlink_mem_write_start(l, space, addr, buf[cur], n);
        pending = true;
        pend_link = l;
        addr += n;
        size -= n;
        cur ^= 1;
        x->done += n;
        uint16_t p = (uint16_t)((uint64_t)x->done * 1000 / (x->total ? x->total : 1));
        if (x->cb && p != x->last && (p - x->last >= 5 || p == 1000)) {
            qlink_mem_write_finish(l);      /* la boîte aux lettres passe par le FPGA P */
            pending = false;
            x->last = p;
            x->cb(p);
        }
    }
    if (pending) qlink_mem_write_finish(pend_link);
    return 0;
}

/* Metal Slug X : la carte PROGEOP porte une puce Altera dont le
 * comportement n'est pas connu. Comme la réparation décrite sur le wiki
 * neogeodev (« Repairing Metal Slug X » : ROM P1 modifiée sur une carte
 * standard), on neutralise les contrôles dans P1, avec les mêmes
 * modifications que MAME 0.145 (mslugx_install_protection) : le bne qui
 * suit chaque andi.w #$1,D3, et huit mots à des adresses fixes, deviennent
 * des NOP (0x4E71). */
static void msx_patch_apply(const msx_scan_t *s)
{
    static const uint8_t nop2[4] = { 0x71, 0x4E, 0x71, 0x4E };
    static const uint32_t fixed[] = { 0x3BDC, 0x3BDE, 0x3BE0, 0x3C0C, 0x3C0E, 0x3C10, 0x3C36, 0x3C38 };
    for (int i = 0; i < s->n; i++)
        qlink_mem_write(LINK_P, SP_P_SDRAM, s->hits[i], nop2, 4);
    for (unsigned i = 0; i < sizeof(fixed) / sizeof(fixed[0]); i++)
        qlink_mem_write(LINK_P, SP_P_SDRAM, fixed[i], nop2, 2);
}

static char map_text[MAP_TEXT_MAX + 1];

static bool read_text(const char *path)
{
    FIL f;
    UINT got = 0;
    if (f_open(&f, path, FA_READ) != FR_OK) return false;
    f_read(&f, map_text, MAP_TEXT_MAX, &got);
    f_close(&f);
    map_text[got] = 0;
    return true;
}

/* jeux SMA connus : leur table de banques doit venir d'un fichier .map */
static bool is_sma_ngh(uint32_t ngh)
{
    static const uint32_t sma[] = { 0x251, 0x253, 0x256, 0x257, 251, 253, 256, 257 };
    for (unsigned i = 0; i < sizeof(sma) / sizeof(sma[0]); i++) if (ngh == sma[i]) return true;
    return false;
}

/* Choisit la description de protection du jeu (voir mapper.h). */
static uint16_t find_mapper(const char *path, const neo_header_t *h, mapper_t *m, char *msg, int msglen)
{
    char side[260], base[64], err[48];
    const char *slash = strrchr(path, '/');
    snprintf(base, sizeof(base), "%s", slash ? slash + 1 : path);
    char *dot = strrchr(base, '.');
    if (dot) *dot = 0;

    snprintf(side, sizeof(side), "%s", path);
    dot = strrchr(side, '.');
    if (dot && strlen(dot) == 4) strcpy(dot, ".map");
    if (dot && read_text(side)) {
        if (!mapper_parse(map_text, base, h->ngh, true, m, err, sizeof(err))) {
            snprintf(msg, msglen, ".MAP: %s", err);
            return ST_ERR_FORMAT;
        }
        return ST_OK;
    }
    if (read_text("0:/SDAES/MAPPERS.TXT")) {
        if (mapper_parse(map_text, base, h->ngh, false, m, err, sizeof(err))) return ST_OK;
        if (err[0]) { snprintf(msg, msglen, "MAPPERS.TXT: %s", err); return ST_ERR_FORMAT; }
    }
    if (mapper_builtin(h->ngh, m)) return ST_OK;
    if (is_sma_ngh(h->ngh)) {
        snprintf(msg, msglen, "PROTECTION SMA: FICHIER .MAP REQUIS");
        return ST_ERR_UNSUPPORTED;
    }
    mapper_default(m);
    return ST_OK;
}

uint16_t neo_load(const char *path, neo_progress_cb cb, neo_header_t *h, char *msg, int msglen)
{
    static mapper_t m;
    FIL f;
    UINT got;
    msg[0] = 0;

    if (f_open(&f, path, FA_READ) != FR_OK) {
        snprintf(msg, msglen, "OUVERTURE IMPOSSIBLE");
        return ST_ERR_IO;
    }
    if (f_read(&f, buf[0], NEO_HEADER_SIZE, &got) != FR_OK || got != NEO_HEADER_SIZE
        || neo_parse_header(buf[0], h) != 0) {
        f_close(&f);
        snprintf(msg, msglen, "FICHIER .NEO INVALIDE");
        return ST_ERR_FORMAT;
    }

    uint32_t v2_base = h->v2size ? ((h->v1size + 0xFFFFu) & ~0xFFFFu) : 0;
    if (h->psize > LIMIT_P || h->ssize > LIMIT_S || h->msize > LIMIT_M ||
        v2_base + h->v2size > LIMIT_V || h->v1size > LIMIT_V || h->csize > LIMIT_C) {
        f_close(&f);
        snprintf(msg, msglen, "JEU TROP GROS POUR SDAES");
        return ST_ERR_TOO_BIG;
    }
    uint16_t mst = find_mapper(path, h, &m, msg, msglen);
    if (mst != ST_OK) {
        f_close(&f);
        return mst;
    }
    if (m.mode == MAP_SMA && m.bank_count == 0) {
        f_close(&f);
        snprintf(msg, msglen, "TABLE DE BANQUES SMA ABSENTE");
        return ST_ERR_FORMAT;
    }

    uint32_t expected = NEO_HEADER_SIZE + h->psize + h->ssize + h->msize + h->v1size + h->v2size + h->csize;
    if (f_size(&f) < expected) {
        f_close(&f);
        snprintf(msg, msglen, "FICHIER TRONQUE");
        return ST_ERR_FORMAT;
    }

    /* désarme : les mémoires reviennent au chargeur, la console reste sur le menu */
    for (int i = 0; i < 4; i++)
        qlink_reg_write((link_id_t)i, REG_CTRL, 0);

    static msx_scan_t scan;
    memset(&scan, 0, sizeof(scan));
    scan.on = (m.patch == PATCH_MSLUGX);
    xfer_t x = { &f, 0, expected - NEO_HEADER_SIZE, cb, 0, &scan };
    int r = 0;
    r |= stream(&x, LINK_P,  SP_P_SDRAM, 0,            h->psize);
    if (!r && scan.on) msx_patch_apply(&scan);
    r |= stream(&x, LINK_SM, SP_SM_SRAM, 0,            h->ssize);
    r |= stream(&x, LINK_SM, SP_SM_SRAM, SRAM_M1_BASE, h->msize);
    r |= stream(&x, LINK_V,  SP_V_SDRAM, 0,            h->v1size);
    r |= stream(&x, LINK_V,  SP_V_SDRAM, v2_base,      h->v2size);
    r |= stream(&x, LINK_C,  SP_C_SDRAM, 0,            h->csize);
    f_close(&f);
    if (r) {
        snprintf(msg, msglen, "ERREUR DE LECTURE SD");
        return ST_ERR_IO;
    }

    /* protections : RAM PVC à zéro, table SMA, registres du FPGA P */
    if (m.mode == MAP_PVC) {
        memset(buf[0], 0, 8192);
        qlink_mem_write(LINK_P, SP_P_SDRAM, PVC_RAM_BYTE, buf[0], 8192);
    }
    if (m.mode == MAP_SMA) {
        uint8_t *t = buf[0];
        for (int i = 0; i < 64; i++) {
            uint32_t o = i < m.bank_count ? m.bank_table[i] : 0;
            t[4 * i] = (uint8_t)(o >> 24); t[4 * i + 1] = (uint8_t)(o >> 16);
            t[4 * i + 2] = (uint8_t)(o >> 8); t[4 * i + 3] = (uint8_t)o;
        }
        qlink_mem_write(LINK_P, SP_P_SMA_TABLE, 0, t, 256);
    }
    mapper_reg_t regs[16];
    int nregs = mapper_registers(&m, regs, 16);
    for (int i = 0; i < nregs; i++)
        qlink_reg_write(LINK_P, regs[i].reg, regs[i].val);
    if (!qlink_wait_idle(LINK_P, 500) || !qlink_wait_idle(LINK_V, 500) ||
        !qlink_wait_idle(LINK_C, 500) || !qlink_wait_idle(LINK_SM, 500)) {
        snprintf(msg, msglen, "FPGA NE REPOND PAS");
        return ST_ERR_IO;
    }

    /* plan mémoire */
    qlink_reg_write(LINK_P,  REG_P_MASK,  mask_for(h->psize) >> 1);
    qlink_reg_write(LINK_V,  REG_V1_BASE, 0);
    qlink_reg_write(LINK_V,  REG_V1_MASK, mask_for(h->v1size));
    qlink_reg_write(LINK_V,  REG_V2_BASE, v2_base);
    qlink_reg_write(LINK_V,  REG_V2_MASK, mask_for(h->v2size ? h->v2size : h->v1size));
    qlink_reg_write(LINK_C,  REG_C_MASK,  mask_for(h->csize) >> 2);
    qlink_reg_write(LINK_SM, REG_S_MASK,  mask_for(h->ssize));
    qlink_reg_write(LINK_SM, REG_M1_MASK, mask_for(h->msize));
    qlink_reg_write(LINK_SM, REG_SM_FIX_BANK,
                    m.fix_bank == FIX_BANK_AUTO ? mapper_fix_bank(h->ngh) : m.fix_bank);

    /* arme les FPGA : la bascule effective est demandée par le menu (FPGA P,
     * qui la transmet aux trois autres par la ligne MODE) */
    qlink_reg_write(LINK_V,  REG_CTRL, CTRL_ARM);
    qlink_reg_write(LINK_C,  REG_CTRL, CTRL_ARM);
    qlink_reg_write(LINK_SM, REG_CTRL, CTRL_ARM);
    qlink_reg_write(LINK_P,  REG_CTRL, CTRL_ARM |
                    (m.mode == MAP_STD && h->psize > (2u << 20) ? CTRL_BANK_EN : 0));

    static const char *const kind[] = { "", " (SMA)", " (PVC)", " (PRO-CT0)" };
    if (scan.on)
        snprintf(msg, msglen, "%.30s (P1 CORRIGEE: %d)", h->name[0] ? h->name : "JEU", scan.n);
    else
        snprintf(msg, msglen, "%.40s%s", h->name[0] ? h->name : "JEU", kind[m.mode]);
    return ST_OK;
}
