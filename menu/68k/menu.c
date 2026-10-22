/*
 * Menu SDAES exécuté par le 68000 de la Neo Geo.
 *
 * Affichage sur la couche fixe uniquement (police en ROM S du menu), lecture
 * directe des manettes, dialogue avec le RP2350 par la boîte aux lettres.
 * Les interruptions restent masquées : le menu nourrit lui-même le chien de
 * garde et n'a besoin d'aucun service du BIOS.
 */
#include <stdint.h>
#include "../../protocol/sdaes_mailbox.h"

#define REG_P1CNT     (*(volatile uint8_t  *)0x300000)
#define REG_WATCHDOG  (*(volatile uint8_t  *)0x300001)
#define REG_SOUND     (*(volatile uint8_t  *)0x320000)
#define REG_STATUS_B  (*(volatile uint8_t  *)0x380000)
#define REG_VRAMADDR  (*(volatile uint16_t *)0x3C0000)
#define REG_VRAMRW    (*(volatile uint16_t *)0x3C0002)
#define REG_VRAMMOD   (*(volatile uint16_t *)0x3C0004)
#define REG_PALBANK0  (*(volatile uint8_t  *)0x3A001F)
#define PALRAM        ((volatile uint16_t *)0x400000)

#define MB16(off)     (*(volatile uint16_t *)(MB_68K_BASE + (off)))
#define MB32(off)     (*(volatile uint32_t *)(MB_68K_BASE + (off)))
#define MB8(off)      (*(volatile uint8_t  *)(MB_68K_BASE + (off)))
#define MB_STATUS     (*(volatile uint16_t *)MB_68K_STATUS)
#define MB_DOORBELL   (*(volatile uint16_t *)MB_68K_DOORBELL)

/* manette (actif à 1 après inversion) */
#define J_UP    0x01
#define J_DOWN  0x02
#define J_LEFT  0x04
#define J_RIGHT 0x08
#define J_A     0x10
#define J_B     0x20
#define J_C     0x40
#define J_D     0x80

/* palettes de la couche fixe */
#define PAL_TEXT   0
#define PAL_TITLE  1
#define PAL_SEL    2
#define PAL_DIM    3
#define PAL_ERR    4

#define SCREEN_X0  1          /* colonnes visibles 1..38 */
#define SCREEN_W   38
#define LIST_Y0    6
#define LIST_ROWS  MB_PAGE_SIZE

extern const uint8_t launch_stub[], launch_stub_end[];

static uint16_t seq;
static uint16_t total, top, cursor, page_count;
static uint8_t  pad_prev;
static uint8_t  repeat_cnt;

/* --------------------------------------------------------------------- */

static void watchdog(void) { REG_WATCHDOG = 0; }

static void wait_frame(void)
{
    /* ~16 ms à 12 MHz ; pas d'IRQ VBlank, on se contente d'une attente */
    for (volatile uint16_t i = 0; i < 2600; i++)
        ;
    watchdog();
}

static void fix_put(uint8_t x, uint8_t y, uint8_t pal, const char *s)
{
    REG_VRAMADDR = 0x7000 + (uint16_t)x * 32 + y;
    REG_VRAMMOD  = 32;
    while (*s && x < SCREEN_X0 + SCREEN_W) {
        REG_VRAMRW = ((uint16_t)pal << 12) | (uint8_t)*s++;
        x++;
    }
}

static void fix_fill(uint8_t x, uint8_t y, uint8_t w)
{
    REG_VRAMADDR = 0x7000 + (uint16_t)x * 32 + y;
    REG_VRAMMOD  = 32;
    while (w--)
        REG_VRAMRW = ' ';
}

static void fix_clear(void)
{
    REG_VRAMADDR = 0x7000;
    REG_VRAMMOD  = 1;
    for (uint16_t i = 0; i < 40 * 32; i++)
        REG_VRAMRW = ' ';
}

static void put_line(uint8_t y, uint8_t pal, const char *s)
{
    fix_fill(SCREEN_X0, y, SCREEN_W);
    fix_put(SCREEN_X0, y, pal, s);
}

/* écrit v en décimal ; renvoie la colonne qui suit le dernier chiffre */
static uint8_t put_num(uint8_t x, uint8_t y, uint8_t pal, uint16_t v)
{
    char buf[6];
    int i = 5;
    buf[5] = 0;
    do { buf[--i] = '0' + v % 10; v /= 10; } while (v && i);
    fix_put(x, y, pal, &buf[i]);
    return x + 5 - i;
}

/* copie une chaîne de la boîte aux lettres (octets) */
static void mb_str(uint16_t off, char *dst, uint8_t max)
{
    uint8_t i;
    for (i = 0; i < max - 1; i++) {
        char c = MB8(off + i);
        if (!c) break;
        dst[i] = (c >= 0x20 && c < 0x7F) ? c : '?';
    }
    dst[i] = 0;
}

static void palettes(void)
{
    REG_PALBANK0 = 0;
    PALRAM[PAL_TEXT  * 16 + 1] = 0x7FFF;   /* blanc  */
    PALRAM[PAL_TITLE * 16 + 1] = 0x6FF0;   /* jaune  */
    PALRAM[PAL_SEL   * 16 + 1] = 0x30FF;   /* cyan   */
    PALRAM[PAL_DIM   * 16 + 1] = 0x0888;   /* gris   */
    PALRAM[PAL_ERR   * 16 + 1] = 0x4F44;   /* rouge  */
    PALRAM[0x0FFF] = 0x8000;               /* fond noir */
}

static uint8_t read_pad(void)
{
    uint8_t cur  = ~REG_P1CNT;
    uint8_t edge = cur & ~pad_prev;
    if (cur & (J_UP | J_DOWN | J_LEFT | J_RIGHT)) {
        if (cur == pad_prev) {
            if (++repeat_cnt > 18) { repeat_cnt = 15; edge |= cur & (J_UP | J_DOWN | J_LEFT | J_RIGHT); }
        } else repeat_cnt = 0;
    }
    pad_prev = cur;
    return edge;
}

/* --------------------------------------------------------------------- */
/* Dialogue avec le RP2350                                                */

static void mb_send(uint16_t cmd, uint32_t arg0)
{
    seq++;
    MB32(MB_CMD_ARG0) = arg0;
    MB16(MB_CMD_ID)   = cmd;
    MB16(MB_CMD_SEQ)  = seq;
    MB_DOORBELL = 1;
}

/* attend la réponse ; affiche la progression si show_progress */
static uint16_t mb_wait(uint16_t timeout_frames, uint8_t show_progress)
{
    uint16_t n = 0;
    while (MB16(MB_RSP_SEQ) != seq) {
        wait_frame();
        if (show_progress && MB16(MB_RSP_BUSYSEQ) == seq) {
            uint16_t p = MB16(MB_RSP_PROGRESS);
            uint8_t bar = (uint8_t)((uint32_t)p * 30 / 1000);
            REG_VRAMADDR = 0x7000 + (SCREEN_X0 + 4) * 32 + 16;
            REG_VRAMMOD  = 32;
            for (uint8_t i = 0; i < 30; i++)
                REG_VRAMRW = ((uint16_t)(i < bar ? PAL_SEL : PAL_DIM) << 12) | (i < bar ? '#' : '-');
            fix_put(put_num(SCREEN_X0 + 16, 18, PAL_TEXT, p / 10), 18, PAL_TEXT, "%  ");
        }
        if (timeout_frames && ++n >= timeout_frames)
            return 0xFFFF;
    }
    return MB16(MB_RSP_STATUS);
}

/* --------------------------------------------------------------------- */

/* versions : firmware du RP2350 et bitstreams des 4 FPGA (cartes SD) */
static void draw_versions(void)
{
    static const char tag[4] = { 'P', 'V', 'C', 'S' };
    fix_fill(SCREEN_X0, 3, SCREEN_W);
    fix_put(SCREEN_X0, 3, PAL_DIM, "FW");
    put_num(SCREEN_X0 + 3, 3, PAL_DIM, MB16(MB_RSP_FWVER));
    fix_put(SCREEN_X0 + 9, 3, PAL_DIM, "FPGA");
    for (uint8_t i = 0; i < 4; i++) {
        char t[2] = { tag[i], 0 };
        uint8_t x = SCREEN_X0 + 14 + i * 6;
        fix_put(x, 3, PAL_DIM, t);
        put_num(x + 1, 3, PAL_DIM, MB16(MB_RSP_FPGAVER + 2 * i));
    }
}

static void draw_header(void)
{
    char path[40];
    put_line(2, PAL_TITLE, "SDAES  -  NEO GEO SD");
    draw_versions();
    mb_str(MB_RSP_PATH, path, sizeof(path));
    put_line(4, PAL_DIM, path);
}

static void draw_footer(void)
{
    put_line(LIST_Y0 + LIST_ROWS + 1, PAL_DIM, "A:LANCER  B:RETOUR  </>:PAGE");
}

static void draw_list(void)
{
    char name[MB_NAME_MAX + 2];
    for (uint8_t i = 0; i < LIST_ROWS; i++) {
        uint8_t y = LIST_Y0 + i;
        fix_fill(SCREEN_X0, y, SCREEN_W);
        if (i >= page_count) continue;
        uint16_t e = MB_RSP_ENTRIES + i * MB_ENTRY_SIZE;
        uint8_t pal = (top + i == cursor) ? PAL_SEL : PAL_TEXT;
        fix_put(SCREEN_X0, y, pal, (top + i == cursor) ? ">" : " ");
        if (MB8(e) == ENT_DIR) {
            fix_put(SCREEN_X0 + 1, y, PAL_TITLE, "/");
        }
        mb_str(e + 1, name, sizeof(name));
        fix_put(SCREEN_X0 + 2, y, pal, name);
    }
    put_line(LIST_Y0 + LIST_ROWS, PAL_DIM, "");
    if (total) {
        uint8_t x = put_num(SCREEN_X0, LIST_Y0 + LIST_ROWS, PAL_DIM, cursor + 1);
        fix_put(x, LIST_Y0 + LIST_ROWS, PAL_DIM, "/");
        put_num(x + 1, LIST_Y0 + LIST_ROWS, PAL_DIM, total);
    } else {
        fix_put(SCREEN_X0, LIST_Y0 + LIST_ROWS, PAL_DIM, "(DOSSIER VIDE)");
    }
}

static void show_error(uint16_t st)
{
    char msg[40];
    mb_str(MB_RSP_MSG, msg, sizeof(msg));
    put_line(LIST_Y0 + LIST_ROWS + 2, PAL_ERR, st == 0xFFFF ? "PAS DE REPONSE DU RP2350" : msg);
}

static void list_page(uint16_t first)
{
    mb_send(CMD_LIST, first);
    uint16_t st = mb_wait(120, 0);
    if (st != ST_OK) { show_error(st); page_count = 0; return; }
    top        = first;
    total      = MB16(MB_RSP_TOTAL);
    page_count = MB16(MB_RSP_COUNT);
    draw_header();
    draw_list();
}

static void ensure_visible(void)
{
    if (cursor < top || cursor >= top + LIST_ROWS)
        list_page(cursor - cursor % LIST_ROWS);
    else
        draw_list();
}

static void launch(void)
{
    char name[40];
    mb_str(MB_RSP_MSG, name, sizeof(name));
    fix_clear();
    put_line(12, PAL_TITLE, "LANCEMENT");
    put_line(14, PAL_TEXT, name);

    /* met le Z80 à l'abri en RAM avant que la ROM M1 ne change */
    REG_SOUND = 0x7F;
    for (uint8_t i = 0; i < 10; i++) wait_frame();

    /* copie la routine de bascule en RAM de travail et l'exécute */
    uint8_t *dst = (uint8_t *)0x101000;
    for (const uint8_t *p = launch_stub; p < launch_stub_end; p++)
        *dst++ = *p;
    ((void (*)(void))0x101000)();
}

static void open_entry(void)
{
    if (!total) return;
    if (MB8(MB_RSP_ENTRIES + (cursor - top) * MB_ENTRY_SIZE) != ENT_DIR) {
        /* jeu : la liste laisse place au nom et à la barre de progression */
        char name[MB_NAME_MAX + 2];
        mb_str(MB_RSP_ENTRIES + (cursor - top) * MB_ENTRY_SIZE + 1, name, sizeof(name));
        for (uint8_t y = LIST_Y0; y < LIST_Y0 + LIST_ROWS; y++)
            fix_fill(SCREEN_X0, y, SCREEN_W);
        fix_put(SCREEN_X0 + 4, 14, PAL_TITLE, name);
    }
    put_line(LIST_Y0 + LIST_ROWS + 2, PAL_TEXT, "CHARGEMENT...");
    mb_send(CMD_OPEN, cursor);
    uint16_t st = mb_wait(0, 1);   /* un gros jeu peut prendre ~20 s */
    if (st != ST_OK) {
        fix_clear(); draw_header(); draw_footer(); draw_list();
        show_error(st);
        return;
    }
    if (MB16(MB_RSP_KIND) == KIND_GAME_READY) {
        launch();
    } else {
        fix_clear(); draw_footer();
        cursor = 0;
        list_page(0);
    }
}

static void go_parent(void)
{
    mb_send(CMD_PARENT, 0);
    uint16_t st = mb_wait(120, 0);
    if (st != ST_OK) { show_error(st); return; }
    fix_clear(); draw_footer();
    cursor = 0;
    list_page(0);
}

void menu_main(void)
{
    palettes();
    fix_clear();
    put_line(2, PAL_TITLE, "SDAES  -  NEO GEO SD");
    put_line(12, PAL_TEXT, "ATTENTE DE LA CARTE SD...");

    seq = MB16(MB_RSP_SEQ);   /* reprend la séquence là où elle en est */
    for (;;) {
        mb_send(CMD_PING, 0);
        uint16_t st = mb_wait(60, 0);
        if (st == ST_OK) break;
        if (st != 0xFFFF) { show_error(st); for (uint8_t i = 0; i < 60; i++) wait_frame(); }
    }

    fix_clear();
    draw_footer();
    cursor = 0;
    list_page(0);

    for (;;) {
        wait_frame();
        uint8_t k = read_pad();
        if (!total && !(k & J_B)) continue;
        if (k & J_UP)    { if (cursor) cursor--; else cursor = total - 1; ensure_visible(); }
        if (k & J_DOWN)  { if (cursor + 1 < total) cursor++; else cursor = 0; ensure_visible(); }
        if (k & J_LEFT)  { cursor = cursor >= LIST_ROWS ? cursor - LIST_ROWS : 0; ensure_visible(); }
        if (k & J_RIGHT) { cursor = cursor + LIST_ROWS < total ? cursor + LIST_ROWS : total - 1; ensure_visible(); }
        if (k & J_A)     open_entry();
        if (k & J_B)     go_parent();
    }
}
