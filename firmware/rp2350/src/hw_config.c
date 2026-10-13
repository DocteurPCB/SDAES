/*
 * Configuration de la carte SD pour la bibliothèque
 * no-OS-FatFS-SD-SDIO-SPI-RPi-Pico (carlk3), mode SDIO 4 bits sur PIO1.
 * Les noms de champs suivent la v3 de la bibliothèque ; à adapter si besoin.
 */
#include "hw_config.h"
#include "board.h"

static sd_sdio_if_t sdio_if = {
    .CMD_gpio    = PIN_SD_CMD,
    .D0_gpio     = PIN_SD_D0,          /* CLK = D0 - 2, D1..D3 = D0 + 1..3 */
    .SDIO_PIO    = pio1,
    .DMA_IRQ_num = DMA_IRQ_1,
    .baud_rate   = 150 * 1000 * 1000 / 6,   /* 25 MHz */
};

static sd_card_t sd_card = {
    .type      = SD_IF_SDIO,
    .sdio_if_p = &sdio_if,
};

size_t sd_get_num(void) { return 1; }

sd_card_t *sd_get_by_num(size_t num)
{
    return num == 0 ? &sd_card : NULL;
}
