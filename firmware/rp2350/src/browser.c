/*
 * Navigation dans la carte SD et traitement des commandes du menu 68000
 * (protocole : protocol/sdaes_mailbox.h).
 */
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "ff.h"
#include "browser.h"
#include "neo_loader.h"
#include "qlink.h"
#include "../../../protocol/sdaes_mailbox.h"

#define MAX_ENTRIES   1024
#define PATH_MAX_LEN  256
#define LAST_FILE     "0:/SDAES/LAST.TXT"

typedef struct {
    char    name[FF_MAX_LFN + 1];
    uint8_t is_dir;
} entry_t;

static entry_t  entries[MAX_ENTRIES];
static entry_t *sorted[MAX_ENTRIES];
static uint16_t n_entries;
static char     cwd[PATH_MAX_LEN] = "0:/";
static int      card_ok;
static uint16_t cur_seq;

/* --------------------------------------------------------------------- */
/* accès à la boîte aux lettres (ordre 68000 : grand-boutiste)            */

static void mb_w16(uint16_t off, uint16_t v)
{
    uint8_t b[2] = { (uint8_t)(v >> 8), (uint8_t)v };
    qlink_mem_write(LINK_PROG, SP_PROG_MAILBOX, off, b, 2);
}

static void mb_wstr(uint16_t off, const char *s, int max)
{
    uint8_t b[64];
    int n = 0;
    while (n < max - 1 && s[n]) {
        char c = s[n];
        b[n++] = (c >= 0x20 && c < 0x7F) ? (uint8_t)c : '?';
    }
    b[n++] = 0;
    qlink_mem_write(LINK_PROG, SP_PROG_MAILBOX, off, b, n);
}

static void respond(uint16_t status, uint16_t kind, const char *msg)
{
    mb_w16(MB_RSP_STATUS, status);
    mb_w16(MB_RSP_KIND, kind);
    if (msg) mb_wstr(MB_RSP_MSG, msg, 64);
    mb_w16(MB_RSP_SEQ, cur_seq);                      /* toujours en dernier */
}

static void progress(uint16_t permille)
{
    mb_w16(MB_RSP_PROGRESS, permille);
}

/* --------------------------------------------------------------------- */
/* dossier courant                                                         */

static int has_neo_ext(const char *n)
{
    size_t l = strlen(n);
    return l > 4 && n[l - 4] == '.' && (n[l - 3] | 32) == 'n' && (n[l - 2] | 32) == 'e' && (n[l - 1] | 32) == 'o';
}

static int cmp_entry(const void *a, const void *b)
{
    const entry_t *x = *(entry_t *const *)a, *y = *(entry_t *const *)b;
    if (x->is_dir != y->is_dir) return y->is_dir - x->is_dir;   /* dossiers d'abord */
    const char *p = x->name, *q = y->name;
    while (*p && *q) {
        int c = (*p | 32) - (*q | 32);
        if (c) return c;
        p++; q++;
    }
    return (unsigned char)*p - (unsigned char)*q;
}

static void scan(void)
{
    DIR d;
    FILINFO fi;
    n_entries = 0;
    if (!card_ok || f_opendir(&d, cwd) != FR_OK) return;
    while (n_entries < MAX_ENTRIES && f_readdir(&d, &fi) == FR_OK && fi.fname[0]) {
        if (fi.fattrib & (AM_HID | AM_SYS)) continue;
        if (fi.fname[0] == '.') continue;
        int dir = (fi.fattrib & AM_DIR) != 0;
        if (!dir && !has_neo_ext(fi.fname)) continue;
        entry_t *e = &entries[n_entries];
        strncpy(e->name, fi.fname, sizeof(e->name) - 1);
        e->name[sizeof(e->name) - 1] = 0;
        e->is_dir = (uint8_t)dir;
        sorted[n_entries] = e;
        n_entries++;
    }
    f_closedir(&d);
    qsort(sorted, n_entries, sizeof(sorted[0]), cmp_entry);
}

static void write_path(void)
{
    const char *p = cwd + 2;                          /* sans "0:" */
    int l = (int)strlen(p);
    if (l > 37) p += l - 37;                          /* garde la fin du chemin */
    mb_wstr(MB_RSP_PATH, p, 64);
}

static int path_join(char *dst, const char *dir, const char *name)
{
    size_t l = strlen(dir);
    int n = snprintf(dst, PATH_MAX_LEN, "%s%s%s", dir, (l && dir[l - 1] == '/') ? "" : "/", name);
    return n > 0 && n < PATH_MAX_LEN;
}

/* --------------------------------------------------------------------- */
/* commandes                                                               */

static void cmd_list(uint32_t first)
{
    uint8_t page[MB_PAGE_SIZE * MB_ENTRY_SIZE];
    uint16_t count = 0;
    memset(page, 0, sizeof(page));
    for (uint32_t i = first; i < n_entries && count < MB_PAGE_SIZE; i++, count++) {
        uint8_t *e = &page[count * MB_ENTRY_SIZE];
        e[0] = sorted[i]->is_dir ? ENT_DIR : ENT_FILE;
        const char *n = sorted[i]->name;
        size_t l = strlen(n);
        if (!sorted[i]->is_dir && l > 4) l -= 4;     /* masque ".neo" */
        if (l > MB_NAME_MAX) l = MB_NAME_MAX;
        for (size_t k = 0; k < l; k++) {
            char c = n[k];
            e[1 + k] = (c >= 0x20 && c < 0x7F) ? (uint8_t)c : '?';
        }
    }
    qlink_mem_write(LINK_PROG, SP_PROG_MAILBOX, MB_RSP_ENTRIES, page, sizeof(page));
    mb_w16(MB_RSP_COUNT, count);
    mb_w16(MB_RSP_TOTAL, n_entries);
    write_path();
    respond(ST_OK, KIND_LIST, NULL);
}

static void save_last(const char *path)
{
    FIL f;
    UINT w;
    f_mkdir("0:/SDAES");
    if (f_open(&f, LAST_FILE, FA_WRITE | FA_CREATE_ALWAYS) == FR_OK) {
        f_write(&f, path, (UINT)strlen(path), &w);
        f_close(&f);
    }
}

static void load_game(const char *path)
{
    neo_header_t h;
    char msg[64];
    mb_w16(MB_RSP_PROGRESS, 0);
    uint16_t st = neo_load(path, progress, &h, msg, sizeof(msg));
    if (st == ST_OK) {
        save_last(path);
        respond(ST_OK, KIND_GAME_READY, msg);
    } else {
        respond(st, KIND_NONE, msg);
    }
}

static void cmd_open(uint32_t idx)
{
    char path[PATH_MAX_LEN];
    if (idx >= n_entries || !path_join(path, cwd, sorted[idx]->name)) {
        respond(ST_ERR_ARG, KIND_NONE, "ENTREE INVALIDE");
        return;
    }
    if (sorted[idx]->is_dir) {
        strcpy(cwd, path);
        scan();
        write_path();
        respond(ST_OK, KIND_DIR_CHANGED, NULL);
    } else {
        load_game(path);
    }
}

static void cmd_parent(void)
{
    char *s = strrchr(cwd, '/');
    if (s && s > cwd + 2) *s = 0;                    /* "0:/a/b" -> "0:/a" */
    else strcpy(cwd, "0:/");
    scan();
    write_path();
    respond(ST_OK, KIND_DIR_CHANGED, NULL);
}

static void cmd_reload_last(void)
{
    FIL f;
    UINT got = 0;
    char path[PATH_MAX_LEN];
    if (f_open(&f, LAST_FILE, FA_READ) != FR_OK) {
        respond(ST_ERR_IO, KIND_NONE, "AUCUN JEU PRECEDENT");
        return;
    }
    f_read(&f, path, sizeof(path) - 1, &got);
    f_close(&f);
    path[got] = 0;
    load_game(path);
}

void browser_init(int sd_ok)
{
    card_ok = sd_ok;
    strcpy(cwd, "0:/");
    scan();
    mb_w16(MB_RSP_FWVER, FW_VERSION);
}

void browser_handle_command(void)
{
    uint8_t c[12];
    qlink_mem_read(LINK_PROG, SP_PROG_MAILBOX, MB_CMD_ID, c, sizeof(c));
    qlink_reg_write(LINK_PROG, REG_IRQ_ACK, 0);

    uint16_t cmd  = (uint16_t)((c[0] << 8) | c[1]);
    uint32_t arg0 = ((uint32_t)c[4] << 24) | ((uint32_t)c[5] << 16) | ((uint32_t)c[6] << 8) | c[7];
    cur_seq = (uint16_t)((c[2] << 8) | c[3]);
    mb_w16(MB_RSP_BUSYSEQ, cur_seq);

    if (!card_ok && cmd != CMD_PING) {
        respond(ST_ERR_NOCARD, KIND_NONE, "CARTE SD ABSENTE");
        return;
    }
    switch (cmd) {
    case CMD_PING:
        if (card_ok) respond(ST_OK, KIND_NONE, NULL);
        else         respond(ST_ERR_NOCARD, KIND_NONE, "CARTE SD ABSENTE OU ILLISIBLE");
        break;
    case CMD_LIST:        cmd_list(arg0);   break;
    case CMD_OPEN:        cmd_open(arg0);   break;
    case CMD_PARENT:      cmd_parent();     break;
    case CMD_RELOAD_LAST: cmd_reload_last(); break;
    default:
        respond(ST_ERR_ARG, KIND_NONE, "COMMANDE INCONNUE");
        break;
    }
}
