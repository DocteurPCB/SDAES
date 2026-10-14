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

/* un bus = SCK + IO[3:0] partagés par deux FPGA, une machine PIO */
typedef struct {
    uint sck, io0;
    PIO  pio;
    uint sm;
    int  dma;
} bus_t;

static bus_t buses[2] = {
    { PIN_PROG_SCK, PIN_PROG_IO0, pio0, 0, -1 },   /* FPGA P et V */
    { PIN_CHA_SCK,  PIN_CHA_IO0,  pio0, 1, -1 },   /* FPGA C et SM */
};

typedef struct { bus_t *bus; uint cs; } link_t;
static link_t links[4] = {
    [LINK_P]  = { &buses[0], PIN_CS_P },
    [LINK_V]  = { &buses[0], PIN_CS_V },
    [LINK_C]  = { &buses[1], PIN_CS_C },
    [LINK_SM] = { &buses[1], PIN_CS_SM },
};

/* demi-période logicielle : >= 4 périodes de l'horloge FPGA (100 MHz) */
static inline void half(void) { busy_wait_at_least_cycles(15); }

static void pins_sio(bus_t *b, bool out)
{
    gpio_set_function(b->sck, GPIO_FUNC_SIO);
    gpio_set_dir(b->sck, GPIO_OUT);
    for (uint i = 0; i < 4; i++) {
        gpio_set_function(b->io0 + i, GPIO_FUNC_SIO);
        gpio_set_dir(b->io0 + i, out ? GPIO_OUT : GPIO_IN);
    }
}

static void pins_pio(bus_t *b)
{
    pio_gpio_init(b->pio, b->sck);
    for (uint i = 0; i < 4; i++)
        pio_gpio_init(b->pio, b->io0 + i);
}

static void nib_out(link_t *k, uint8_t n)
{
    bus_t *b = k->bus;
    gpio_put_masked(0xFu << b->io0, (uint32_t)n << b->io0);
    half();
    gpio_put(b->sck, 1);
    half();
    gpio_put(b->sck, 0);
}

static void byte_out(link_t *k, uint8_t b)
{
    nib_out(k, b >> 4);
    nib_out(k, b & 0xF);
}

static uint8_t nib_in(link_t *k)
{
    bus_t *b = k->bus;
    half();
    gpio_put(b->sck, 1);
    /* le FPGA ne modifie ses sorties que ~40 ns après ce front : on lit tout de suite */
    uint8_t n = (gpio_get_all() >> b->io0) & 0xF;
    half();
    gpio_put(b->sck, 0);
    return n;
}

static uint8_t byte_in(link_t *k)
{
    uint8_t hi = nib_in(k);
    return (uint8_t)((hi << 4) | nib_in(k));
}

static void begin(link_t *k)
{
    pins_sio(k->bus, true);
    gpio_put(k->bus->sck, 0);
    gpio_put(k->cs, 0);
    half();
}

static void end(link_t *k)
{
    half(); half();
    gpio_put(k->cs, 1);
    pins_sio(k->bus, true);
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
    for (int i = 0; i < 4; i++) {
        gpio_init(links[i].cs);
        gpio_set_dir(links[i].cs, GPIO_OUT);
        gpio_put(links[i].cs, 1);
    }
    for (int i = 0; i < 2; i++) {
        bus_t *b = &buses[i];
        gpio_init(b->sck);
        for (uint n = 0; n < 4; n++) gpio_init(b->io0 + n);
        pins_sio(b, true);
        gpio_put(b->sck, 0);

        pio_sm_claim(b->pio, b->sm);
        pio_sm_config c = qlink_tx_program_get_default_config(offset);
        sm_config_set_out_pins(&c, b->io0, 4);
        sm_config_set_sideset_pins(&c, b->sck);
        sm_config_set_out_shift(&c, false, true, 8);   /* MSB d'abord, autopull 8 bits */
        sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
        sm_config_set_clkdiv(&c, LINK_CLKDIV);
        pio_sm_init(b->pio, b->sm, offset, &c);
        /* directions côté PIO fixées une fois pour toutes (machine à l'arrêt) ;
         * elles ne s'appliquent que lorsque les broches sont en mode PIO */
        pio_sm_set_consecutive_pindirs(b->pio, b->sm, b->io0, 4, true);
        pio_sm_set_consecutive_pindirs(b->pio, b->sm, b->sck, 1, true);
        pio_sm_set_enabled(b->pio, b->sm, true);

        b->dma = dma_claim_unused_channel(true);
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
    pins_sio(k->bus, false);       /* retournement du bus */
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
    pins_sio(k->bus, false);
    (void)byte_in(k);
    while (len--)
        *p++ = byte_in(k);
    end(k);
}

void qlink_mem_write_start(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len)
{
    link_t *k = &links[l];
    bus_t  *b = k->bus;
    begin(k);
    header(k, CMD_MEM_WR, space, addr);

    /* rafale : PIO + DMA, le processeur est libre pendant le transfert */
    pins_pio(b);
    dma_channel_config c = dma_channel_get_default_config(b->dma);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_dreq(&c, pio_get_dreq(b->pio, b->sm, true));
    dma_channel_configure(b->dma, &c, &b->pio->txf[b->sm], buf, len, true);
}

void qlink_mem_write_finish(link_id_t l)
{
    link_t *k = &links[l];
    bus_t  *b = k->bus;
    uint32_t stall = 1u << (PIO_FDEBUG_TXSTALL_LSB + b->sm);
    dma_channel_wait_for_finish_blocking(b->dma);
    /* attend que le dernier quartet soit sorti (machine bloquée, SCK = 0) */
    while (!pio_sm_is_tx_fifo_empty(b->pio, b->sm))
        tight_loop_contents();
    b->pio->fdebug = stall;
    while (!(b->pio->fdebug & stall))
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
    uint32_t bit = (l == LINK_P) ? P_ST_IDLE : VCS_ST_IDLE;
    absolute_time_t t = make_timeout_time_ms(timeout_ms);
    while (!(qlink_reg_read(l, REG_STATUS) & bit))
        if (time_reached(t)) return false;
    return true;
}

/* ------------------------------------------------------------------ */
/* Configuration des iCE40 en SPI esclave (note Lattice TN1248) :
 * CRESET bas, SS bas ; CRESET haut -> mode esclave ; >= 1200 us ;
 * SS haut + 8 coups d'horloge ; SS bas, bitstream (mode SPI 3, MSB
 * d'abord) ; SS haut ; >= 149 coups d'horloge (CDONE puis E/S actives). */

static void cfg_clocks(bus_t *b, int n)
{
    for (int i = 0; i < n; i++) {
        gpio_put(b->sck, 0); half();
        gpio_put(b->sck, 1); half();
    }
}

void qlink_cfg_reset(void)
{
    gpio_init(PIN_CRESET_N);
    gpio_set_dir(PIN_CRESET_N, GPIO_OUT);
    gpio_put(PIN_CRESET_N, 0);
    for (int i = 0; i < 2; i++) {
        pins_sio(&buses[i], true);
        gpio_put(buses[i].sck, 1);
    }
    for (int i = 0; i < 4; i++)
        gpio_put(links[i].cs, 0);           /* SS bas au relâchement : esclave */
    sleep_us(10);
    gpio_put(PIN_CRESET_N, 1);
    sleep_us(2000);
    for (int i = 0; i < 4; i++)
        gpio_put(links[i].cs, 1);
    for (int i = 0; i < 2; i++)
        cfg_clocks(&buses[i], 8);
}

void qlink_cfg_begin(link_id_t l)
{
    link_t *k = &links[l];
    pins_sio(k->bus, true);
    gpio_put(k->bus->sck, 1);
    gpio_put(k->cs, 0);
    half();
}

void qlink_cfg_data(link_id_t l, const void *buf, size_t len)
{
    bus_t *b = links[l].bus;
    const uint8_t *p = buf;
    while (len--) {
        uint8_t v = *p++;
        for (int i = 7; i >= 0; i--) {
            gpio_put(b->sck, 0);
            gpio_put(b->io0, (v >> i) & 1);
            half();
            gpio_put(b->sck, 1);              /* échantillonné au front montant */
            half();
        }
    }
}

void qlink_cfg_end(link_id_t l)
{
    link_t *k = &links[l];
    gpio_put(k->cs, 1);
    cfg_clocks(k->bus, 160);
    gpio_put(k->bus->sck, 0);
}

bool qlink_cfg_done(void)
{
    return gpio_get(PIN_CDONE);
}
