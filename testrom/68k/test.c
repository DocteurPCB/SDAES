/*
 * ROM de test SDAES : petit « jeu » chargé depuis la carte SD par le menu.
 *
 * Couche fixe uniquement (ROM S : police du menu + tuile pleine en 0x7F).
 * Vérifie ce que la cartouche fournit au 68000 une fois le jeu lancé :
 * ROM P lue depuis la SDRAM (somme de contrôle comparée à celle inscrite
 * à la construction), RAM de travail, palettes, manette 1, START/SELECT.
 * Comme le menu : interruptions masquées, chien de garde nourri à la main.
 */
#include <stdint.h>

#define REG_P1CNT     (*(volatile uint8_t  *)0x300000)
#define REG_WATCHDOG  (*(volatile uint8_t  *)0x300001)
#define REG_STATUS_B  (*(volatile uint8_t  *)0x380000)
#define REG_VRAMADDR  (*(volatile uint16_t *)0x3C0000)
#define REG_VRAMRW    (*(volatile uint16_t *)0x3C0002)
#define REG_VRAMMOD   (*(volatile uint16_t *)0x3C0004)
#define REG_PALBANK0  (*(volatile uint8_t  *)0x3A001F)
#define PALRAM        ((volatile uint16_t *)0x400000)

#define RAM_TEST_LO   0x101000
#define RAM_TEST_HI   0x10F000                     /* 0x10F000+ : BIOS, pile */

#define PAL_TEXT   0
#define PAL_TITLE  1
#define PAL_ON     2
#define PAL_DIM    3
#define PAL_ERR    15
#define PAL_BAR0   4          /* 4..11 : barres de couleur */
#define BLOCK      0x7F       /* tuile pleine de la ROM S */

extern const uint16_t _rom_start[], _rom_end[];
extern const uint16_t rom_sum_slot;             /* 0x13A, inscrite par le Makefile */

static const uint16_t bars[8] = {
    0x4F00, 0x4F80, 0x6FF0, 0x20F0, 0x30FF, 0x100F, 0x4F0F, 0x7FFF
};
static const char banner[] =
    "SDAES : LE JEU A DEMARRE DEPUIS LA CARTE SD    "
    "ROM P EN SDRAM, ROM S ET M1 PAR LES FPGA    ";

static uint16_t frame;

static void wait_frame(void)
{
    for (volatile uint16_t i = 0; i < 2600; i++)
        ;
    REG_WATCHDOG = 0;
    frame++;
}

static void fix_put(uint8_t x, uint8_t y, uint8_t pal, const char *s)
{
    REG_VRAMADDR = 0x7000 + (uint16_t)x * 32 + y;
    REG_VRAMMOD  = 32;
    while (*s && x < 39) {
        REG_VRAMRW = ((uint16_t)pal << 12) | (uint8_t)*s++;
        x++;
    }
}

static void fix_clear(void)
{
    REG_VRAMADDR = 0x7000;
    REG_VRAMMOD  = 1;
    for (uint16_t i = 0; i < 40 * 32; i++)
        REG_VRAMRW = ' ';
}

static void put_hex(uint8_t x, uint8_t y, uint8_t pal, uint16_t v)
{
    char s[5];
    for (int i = 3; i >= 0; i--, v >>= 4)
        s[i] = "0123456789ABCDEF"[v & 15];
    s[4] = 0;
    fix_put(x, y, pal, s);
}

/* sans division : le __modsi3 de la libgcc m68k-linux n'est pas 68000 */
static void put_dec(uint8_t x, uint8_t y, uint8_t pal, uint16_t v)
{
    static const uint16_t pow10[5] = { 10000, 1000, 100, 10, 1 };
    char s[6];
    for (uint8_t i = 0; i < 5; i++) {
        s[i] = '0';
        while (v >= pow10[i]) { v -= pow10[i]; s[i]++; }
    }
    s[5] = 0;
    fix_put(x, y, pal, s);
}

/* somme des mots de la ROM P, sans le mot qui contient la somme attendue */
static uint16_t rom_sum(void)
{
    uint16_t sum = 0;
    for (const uint16_t *p = _rom_start; p < _rom_end; p++)
        if (p != &rom_sum_slot)
            sum += *p;
    return sum;
}

/* motifs, puis adresse dans chaque mot : détecte lignes collées et coupées */
static uint8_t ram_test(void)
{
    static const uint16_t pat[4] = { 0x0000, 0xFFFF, 0x5555, 0xAAAA };
    volatile uint16_t *lo = (volatile uint16_t *)RAM_TEST_LO;
    volatile uint16_t *hi = (volatile uint16_t *)RAM_TEST_HI;
    for (uint8_t k = 0; k < 4; k++) {
        for (volatile uint16_t *p = lo; p < hi; p++) *p = pat[k];
        for (volatile uint16_t *p = lo; p < hi; p++) if (*p != pat[k]) return 0;
        REG_WATCHDOG = 0;
    }
    for (volatile uint16_t *p = lo; p < hi; p++) *p = (uint16_t)(uintptr_t)p;
    for (volatile uint16_t *p = lo; p < hi; p++) if (*p != (uint16_t)(uintptr_t)p) return 0;
    return 1;
}

static void draw_bars(uint8_t y, uint8_t shift)
{
    REG_VRAMADDR = 0x7000 + 4 * 32 + y;
    REG_VRAMMOD  = 32;
    for (uint8_t i = 0; i < 32; i++)
        REG_VRAMRW = ((uint16_t)(PAL_BAR0 + (((i >> 2) + shift) & 7)) << 12) | BLOCK;
}

static void draw_inputs(void)
{
    static const char *const name[8] = { "^", "v", "<", ">", "A", "B", "C", "D" };
    uint8_t p1 = ~REG_P1CNT, st = ~REG_STATUS_B;
    for (uint8_t i = 0; i < 8; i++)
        fix_put(14 + i * 3, 21, (p1 >> i) & 1 ? PAL_ON : PAL_DIM, name[i]);
    fix_put(14, 23, st & 1 ? PAL_ON : PAL_DIM, "START");
    fix_put(21, 23, st & 2 ? PAL_ON : PAL_DIM, "SELECT");
}

static void draw_banner(void)
{
    static uint8_t off;
    const uint8_t len = sizeof(banner) - 1;
    if ((frame & 3) == 0 && ++off == len)
        off = 0;
    REG_VRAMADDR = 0x7000 + 1 * 32 + 27;
    REG_VRAMMOD  = 32;
    for (uint8_t i = 0, k = off; i < 38; i++) {
        REG_VRAMRW = ((uint16_t)PAL_TITLE << 12) | (uint8_t)banner[k];
        if (++k == len) k = 0;
    }
}

void test_main(void)
{
    REG_PALBANK0 = 0;
    PALRAM[PAL_TEXT  * 16 + 1] = 0x7FFF;
    PALRAM[PAL_TITLE * 16 + 1] = 0x6FF0;
    PALRAM[PAL_ON    * 16 + 1] = 0x30FF;
    PALRAM[PAL_DIM   * 16 + 1] = 0x0666;
    PALRAM[PAL_ERR   * 16 + 1] = 0x4F44;
    for (uint8_t i = 0; i < 8; i++)
        PALRAM[(PAL_BAR0 + i) * 16 + 1] = bars[i];
    PALRAM[0x0FFF] = 0x8000;
    fix_clear();

    fix_put(1, 3, PAL_TITLE, "SDAES  -  ROM DE TEST");
    fix_put(1, 5, PAL_DIM, "PALETTES");
    draw_bars(6, 0);

    uint16_t got = rom_sum(), want = rom_sum_slot;
    fix_put(1, 11, PAL_TEXT, "ROM P");
    fix_put(14, 11, PAL_TEXT, "SOMME");
    put_hex(20, 11, PAL_TEXT, got);
    fix_put(25, 11, PAL_DIM, "/");
    put_hex(27, 11, PAL_DIM, want);
    fix_put(33, 11, got == want ? PAL_ON : PAL_ERR, got == want ? "OK" : "ERREUR");

    fix_put(1, 13, PAL_TEXT, "RAM TRAVAIL");
    fix_put(14, 13, PAL_DIM, "EN COURS");
    uint8_t ram = ram_test();
    fix_put(14, 13, PAL_TEXT, "101000-10EFFF");
    fix_put(33, 13, ram ? PAL_ON : PAL_ERR, ram ? "OK" : "ERREUR");

    fix_put(1, 16, PAL_TEXT, "IMAGES");
    fix_put(1, 21, PAL_TEXT, "MANETTE 1");

    for (;;) {
        wait_frame();
        draw_bars(7, frame >> 3);
        put_dec(14, 16, PAL_TEXT, frame);
        draw_inputs();
        draw_banner();
    }
}
