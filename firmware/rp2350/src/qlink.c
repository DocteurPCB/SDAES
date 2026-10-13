/*
 * Liaison 4 bits vers les FPGA.
 *
 * - Les en-têtes (commande, registre, adresse) et les lectures sont faits
 *   en logiciel (broches en mode SIO), à ~5 MHz.
 * - Les données en rafale passent par une machine PIO alimentée par DMA ;
 *   les broches basculent en mode PIO le temps du transfert.
 */
#include "qlink.h"
#include "board.h"
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "qlink.pio.h"

#define CMD_REG_WR 0x01
#define CMD_REG_RD 0x02
#define CMD_MEM_WR 0x10
#define CMD_MEM_RD 0x11

typedef struct {
    uint sck, io0, cs;
    PIO  pio;
    uint sm;
    int  dma;
} link_t;

static link_t links[2] = {
    [LINK_PROG] = { PIN_PROG_SCK, PIN_PROG_IO0, PIN_PROG_CS, pio0, 0, -1 },
    [LINK_CHA]  = { PIN_CHA_SCK,  PIN_CHA_IO0,  PIN_CHA_CS,  pio0, 1, -1 },
};

/* demi-période logicielle : >= 3 périodes de l'horloge FPGA (133 MHz) */
static inline void half(void) { busy_wait_at_least_cycles(15); }

static void pins_sio(link_t *k, bool out)
{
    gpio_set_function(k->sck, GPIO_FUNC_SIO);
    gpio_set_dir(k->sck, GPIO_OUT);
    for (uint i = 0; i < 4; i++) {
        gpio_set_function(k->io0 + i, GPIO_FUNC_SIO);
        gpio_set_dir(k->io0 + i, out ? GPIO_OUT : GPIO_IN);
    }
}

static void pins_pio(link_t *k)
{
    pio_gpio_init(k->pio, k->sck);
    for (uint i = 0; i < 4; i++)
        pio_gpio_init(k->pio, k->io0 + i);
}

static void nib_out(link_t *k, uint8_t n)
{
    gpio_put_masked(0xFu << k->io0, (uint32_t)n << k->io0);
    half();
    gpio_put(k->sck, 1);
    half();
    gpio_put(k->sck, 0);
}

static void byte_out(link_t *k, uint8_t b)
{
    nib_out(k, b >> 4);
    nib_out(k, b & 0xF);
}

static uint8_t nib_in(link_t *k)
{
    half();
    gpio_put(k->sck, 1);
    /* le FPGA ne modifie ses sorties que ~25 ns après ce front : on lit tout de suite */
    uint8_t n = (gpio_get_all() >> k->io0) & 0xF;
    half();
    gpio_put(k->sck, 0);
    return n;
}

static uint8_t byte_in(link_t *k)
{
    uint8_t hi = nib_in(k);
    return (uint8_t)((hi << 4) | nib_in(k));
}

static void begin(link_t *k)
{
    pins_sio(k, true);
    gpio_put(k->sck, 0);
    gpio_put(k->cs, 0);
    half();
}

static void end(link_t *k)
{
    half();
    gpio_put(k->cs, 1);
    pins_sio(k, true);
    half(); half();
}

static void header(link_t *k, uint8_t cmd, uint8_t space, uint32_t addr)
{
    byte_out(k, cmd);
    byte_out(k, space);
    byte_out(k, addr >> 24);
    byte_out(k, addr >> 16);
    byte_out(k, addr >> 8);
    byte_out(k, addr);
}

void qlink_init(void)
{
    uint offset = pio_add_program(pio0, &qlink_tx_program);
    for (int i = 0; i < 2; i++) {
        link_t *k = &links[i];
        gpio_init(k->cs);
        gpio_set_dir(k->cs, GPIO_OUT);
        gpio_put(k->cs, 1);
        gpio_init(k->sck);
        for (uint b = 0; b < 4; b++) gpio_init(k->io0 + b);
        pins_sio(k, true);
        gpio_put(k->sck, 0);

        pio_sm_claim(k->pio, k->sm);
        pio_sm_config c = qlink_tx_program_get_default_config(offset);
        sm_config_set_out_pins(&c, k->io0, 4);
        sm_config_set_sideset_pins(&c, k->sck);
        sm_config_set_out_shift(&c, false, true, 8);   /* MSB d'abord, autopull 8 bits */
        sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
        sm_config_set_clkdiv(&c, LINK_CLKDIV);
        pio_sm_init(k->pio, k->sm, offset, &c);
        /* directions côté PIO fixées une fois pour toutes (machine à l'arrêt) ;
         * elles ne s'appliquent que lorsque les broches sont en mode PIO */
        pio_sm_set_consecutive_pindirs(k->pio, k->sm, k->io0, 4, true);
        pio_sm_set_consecutive_pindirs(k->pio, k->sm, k->sck, 1, true);
        pio_sm_set_enabled(k->pio, k->sm, true);

        k->dma = dma_claim_unused_channel(true);
    }
}

void qlink_reg_write(link_id_t l, uint8_t reg, uint32_t val)
{
    link_t *k = &links[l];
    begin(k);
    byte_out(k, CMD_REG_WR);
    byte_out(k, reg);
    byte_out(k, val >> 24);
    byte_out(k, val >> 16);
    byte_out(k, val >> 8);
    byte_out(k, val);
    end(k);
}

uint32_t qlink_reg_read(link_id_t l, uint8_t reg)
{
    link_t *k = &links[l];
    begin(k);
    byte_out(k, CMD_REG_RD);
    byte_out(k, reg);
    pins_sio(k, false);            /* retournement du bus */
    (void)byte_in(k);              /* octet de retournement */
    uint32_t v = 0;
    for (int i = 0; i < 4; i++)
        v = (v << 8) | byte_in(k);
    end(k);
    return v;
}

void qlink_mem_read(link_id_t l, uint8_t space, uint32_t addr, void *buf, size_t len)
{
    link_t *k = &links[l];
    uint8_t *p = buf;
    begin(k);
    header(k, CMD_MEM_RD, space, addr);
    pins_sio(k, false);
    (void)byte_in(k);
    while (len--)
        *p++ = byte_in(k);
    end(k);
}

void qlink_mem_write_start(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len)
{
    link_t *k = &links[l];
    begin(k);
    header(k, CMD_MEM_WR, space, addr);

    /* rafale : PIO + DMA, le processeur est libre pendant le transfert */
    pins_pio(k);
    dma_channel_config c = dma_channel_get_default_config(k->dma);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_dreq(&c, pio_get_dreq(k->pio, k->sm, true));
    dma_channel_configure(k->dma, &c, &k->pio->txf[k->sm], buf, len, true);
}

void qlink_mem_write_finish(link_id_t l)
{
    link_t *k = &links[l];
    uint32_t stall = 1u << (PIO_FDEBUG_TXSTALL_LSB + k->sm);
    dma_channel_wait_for_finish_blocking(k->dma);
    /* attend que le dernier quartet soit sorti (machine bloquée, SCK = 0) */
    while (!pio_sm_is_tx_fifo_empty(k->pio, k->sm))
        tight_loop_contents();
    k->pio->fdebug = stall;
    while (!(k->pio->fdebug & stall))
        tight_loop_contents();
    end(k);
}

void qlink_mem_write(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len)
{
    if (!len) return;
    qlink_mem_write_start(l, space, addr, buf, len);
    qlink_mem_write_finish(l);
}

bool qlink_wait_idle(link_id_t l, uint32_t timeout_ms)
{
    uint32_t bit = (l == LINK_CHA) ? CHA_ST_IDLE : PROG_ST_IDLE;
    absolute_time_t t = make_timeout_time_ms(timeout_ms);
    while (!(qlink_reg_read(l, REG_STATUS) & bit))
        if (time_reached(t)) return false;
    return true;
}
