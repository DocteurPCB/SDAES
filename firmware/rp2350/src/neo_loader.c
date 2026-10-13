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
#include "qlink.h"
#include "../../../protocol/sdaes_mailbox.h"

#define CHUNK        (32 * 1024)
#define LIMIT_P      (25u << 20)   /* 1 Mo (banque 0) + 24 Mo (banques 1-3) */
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

typedef struct {
    FIL            *f;
    uint32_t        done, total;
    neo_progress_cb cb;
    uint16_t        last;
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

uint16_t neo_load(const char *path, neo_progress_cb cb, neo_header_t *h, char *msg, int msglen)
{
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
    uint32_t expected = NEO_HEADER_SIZE + h->psize + h->ssize + h->msize + h->v1size + h->v2size + h->csize;
    if (f_size(&f) < expected) {
        f_close(&f);
        snprintf(msg, msglen, "FICHIER TRONQUE");
        return ST_ERR_FORMAT;
    }

    /* désarme : les mémoires reviennent au chargeur, la console reste sur le menu */
    for (int i = 0; i < 4; i++)
        qlink_reg_write((link_id_t)i, REG_CTRL, 0);

    xfer_t x = { &f, 0, expected - NEO_HEADER_SIZE, cb, 0 };
    int r = 0;
    r |= stream(&x, LINK_P,  SP_P_SDRAM, 0,            h->psize);
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

    /* arme les FPGA : la bascule effective est demandée par le menu (FPGA P,
     * qui la transmet aux trois autres par la ligne MODE) */
    qlink_reg_write(LINK_V,  REG_CTRL, CTRL_ARM);
    qlink_reg_write(LINK_C,  REG_CTRL, CTRL_ARM);
    qlink_reg_write(LINK_SM, REG_CTRL, CTRL_ARM);
    qlink_reg_write(LINK_P,  REG_CTRL, CTRL_ARM | (h->psize > (2u << 20) ? CTRL_BANK_EN : 0));

    snprintf(msg, msglen, "%s", h->name[0] ? h->name : "JEU");
    return ST_OK;
}
