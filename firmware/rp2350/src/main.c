/*
 * Firmware SDAES pour Raspberry Pi Pico 2 (RP2350).
 *
 * 1. monte la carte SD (FatFs, SDIO 4 bits)
 * 2. configure les quatre FPGA depuis SDAES/fpga_*.bin, attend
 *    l'initialisation des SDRAM
 * 3. répond aux commandes du menu 68000 (sonnette LK_IRQ)
 * 4. bouton : désarme les FPGA -> la console redémarre sur le menu
 */
#include <stdio.h>
#include "pico/stdlib.h"
#include "ff.h"
#include "board.h"
#include "qlink.h"
#include "browser.h"
#include "fpga_boot.h"

static FATFS fs;

static void blink(int n)
{
    for (int i = 0; i < n; i++) {
        gpio_put(PIN_LED, 1); sleep_ms(120);
        gpio_put(PIN_LED, 0); sleep_ms(120);
    }
}

/* Échec au démarrage : la LED du Pico répète sans fin le code d'erreur
 * (n clignotements), puis, après une pause, le numéro du FPGA concerné
 * (1 = P, 2 = V, 3 = C, 4 = SM ; rien si inconnu). Codes :
 *   3 FPGA configuré mais muet ou SDRAM en défaut   4 fichier absent
 *   5 pas de carte SD                                6 taille incohérente
 *   7 erreur de lecture                              8 CDONE bas */
static void fail(int code, int which)
{
    for (;;) {
        blink(code);
        sleep_ms(600);
        if (which >= 0) {
            blink(which + 1);
        }
        sleep_ms(1500);
    }
}

/* -1 = les quatre FPGA répondent et leur mémoire est prête ; sinon le
 * premier FPGA en défaut */
static int fpga_ready(void)
{
    static const uint32_t ids[4] = { ID_P, ID_V, ID_C, ID_SM };
    if (!gpio_get(PIN_CDONE)) return -2;
    for (int i = 0; i < 4; i++) {
        if (qlink_reg_read((link_id_t)i, REG_ID) != ids[i]) return i;
        if (!(qlink_reg_read((link_id_t)i, REG_STATUS) & ST_MEM_OK)) return i;
    }
    return -1;
}

int main(void)
{
    stdio_init_all();

    gpio_init(PIN_LED);       gpio_set_dir(PIN_LED, GPIO_OUT);
    gpio_init(PIN_PROG_IRQ);  gpio_set_dir(PIN_PROG_IRQ, GPIO_IN);  gpio_pull_down(PIN_PROG_IRQ);
    gpio_init(PIN_CDONE);     gpio_set_dir(PIN_CDONE, GPIO_IN);     gpio_pull_up(PIN_CDONE);
    gpio_init(PIN_BUTTON);    gpio_set_dir(PIN_BUTTON, GPIO_IN);    gpio_pull_up(PIN_BUTTON);

    qlink_init();

    /* sans flash, les FPGA ne démarrent qu'avec les fichiers de la carte SD */
    int sd_ok = f_mount(&fs, "0:", 1) == FR_OK;
    printf("SDAES: carte SD %s\n", sd_ok ? "montée" : "absente");
    if (!sd_ok) {
        printf("SDAES: pas de carte SD, FPGA laissés en reset\n");
        fail(5, -1);
    }
    char msg[40];
    int which;
    int err = fpga_boot(msg, sizeof(msg), &which);
    printf("SDAES: %s\n", msg);
    if (err)
        fail(err, which);

    absolute_time_t t = make_timeout_time_ms(2000);
    int bad;
    while ((bad = fpga_ready()) != -1) {
        if (time_reached(t)) {
            printf("SDAES: FPGA muet ou SDRAM en défaut (%d)\n", bad);
            fail(bad == -2 ? BOOT_ERR_CDONE : 3, bad >= 0 ? bad : -1);
        }
        sleep_ms(5);
    }

    browser_init(sd_ok);
    uint16_t ver[4];
    for (int i = 0; i < 4; i++)
        ver[i] = (uint16_t)qlink_reg_read((link_id_t)i, REG_VERSION);
    browser_set_fpga_versions(ver);
    printf("SDAES: versions FPGA P%u V%u C%u SM%u\n", ver[0], ver[1], ver[2], ver[3]);
    gpio_put(PIN_LED, 1);

    for (;;) {
        if (gpio_get(PIN_PROG_IRQ)) {
            gpio_put(PIN_LED, 0);
            browser_handle_command();
            gpio_put(PIN_LED, 1);
        }
        if (!gpio_get(PIN_BUTTON)) {
            /* retour au menu : les ROM du menu réapparaissent, le jeu plante
             * et le chien de garde de la console la redémarre sur le menu */
            for (int i = 0; i < 4; i++)
                qlink_reg_write((link_id_t)i, REG_CTRL, 0);
            blink(2);
            while (!gpio_get(PIN_BUTTON)) sleep_ms(10);
        }
        tight_loop_contents();
    }
}
