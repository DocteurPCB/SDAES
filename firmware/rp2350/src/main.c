/*
 * Firmware SDAES pour Raspberry Pi Pico 2 (RP2350).
 *
 * 1. attend la configuration des quatre FPGA et l'initialisation des SDRAM
 * 2. monte la carte SD (FatFs, SDIO 4 bits)
 * 3. répond aux commandes du menu 68000 (sonnette LK_IRQ)
 * 4. bouton : désarme les FPGA -> la console redémarre sur le menu
 */
#include <stdio.h>
#include "pico/stdlib.h"
#include "ff.h"
#include "board.h"
#include "qlink.h"
#include "browser.h"

static FATFS fs;

static void blink(int n)
{
    for (int i = 0; i < n; i++) {
        gpio_put(PIN_LED, 1); sleep_ms(120);
        gpio_put(PIN_LED, 0); sleep_ms(120);
    }
}

static bool fpga_ready(void)
{
    static const uint32_t ids[4] = { ID_P, ID_V, ID_C, ID_SM };
    if (!gpio_get(PIN_CDONE)) return false;
    for (int i = 0; i < 4; i++) {
        if (qlink_reg_read((link_id_t)i, REG_ID) != ids[i]) return false;
        if (!(qlink_reg_read((link_id_t)i, REG_STATUS) & ST_MEM_OK)) return false;
    }
    return true;
}

int main(void)
{
    stdio_init_all();

    gpio_init(PIN_LED);       gpio_set_dir(PIN_LED, GPIO_OUT);
    gpio_init(PIN_PROG_IRQ);  gpio_set_dir(PIN_PROG_IRQ, GPIO_IN);  gpio_pull_down(PIN_PROG_IRQ);
    gpio_init(PIN_CDONE);     gpio_set_dir(PIN_CDONE, GPIO_IN);     gpio_pull_up(PIN_CDONE);
    gpio_init(PIN_BUTTON);    gpio_set_dir(PIN_BUTTON, GPIO_IN);    gpio_pull_up(PIN_BUTTON);

    qlink_init();

    absolute_time_t t = make_timeout_time_ms(2000);
    while (!fpga_ready()) {
        if (time_reached(t)) {
            printf("SDAES: FPGA absents ou SDRAM en défaut\n");
            for (;;) blink(3), sleep_ms(1000);
        }
        sleep_ms(5);
    }

    int sd_ok = f_mount(&fs, "0:", 1) == FR_OK;
    printf("SDAES: carte SD %s\n", sd_ok ? "montée" : "absente");
    browser_init(sd_ok);
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
