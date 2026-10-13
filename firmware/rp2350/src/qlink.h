/*
 * Pilote de la liaison 4 bits vers les FPGA (voir docs/04-liaison-rp2350.md).
 */
#ifndef SDAES_QLINK_H
#define SDAES_QLINK_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

typedef enum { LINK_PROG = 0, LINK_CHA = 1 } link_id_t;

/* espaces mémoire */
#define SP_PROG_P        0
#define SP_PROG_V        1
#define SP_PROG_MAILBOX  2
#define SP_PROG_MENU_P   3
#define SP_CHA_C         0
#define SP_CHA_SRAM      1
#define SP_CHA_MENU_S    2
#define SP_CHA_MENU_M1   3

/* registres communs */
#define REG_ID           0x00
#define REG_CTRL         0x01
#define REG_STATUS       0x02
#define REG_DBG_ADDR     0x10
#define REG_DBG_DATA     0x11
/* PROG */
#define REG_P_MASK       0x03
#define REG_V1_BASE      0x04
#define REG_V1_MASK      0x05
#define REG_V2_BASE      0x06
#define REG_V2_MASK      0x07
#define REG_P_BANK       0x08
#define REG_IRQ_ACK      0x09   /* écriture : acquitte LK_IRQ */
/* CHA */
#define REG_C_MASK       0x03
#define REG_S_MASK       0x04
#define REG_M1_MASK      0x05

#define CTRL_ARM         (1u << 0)
#define CTRL_FORCE       (1u << 1)
#define CTRL_BANK_EN     (1u << 3)   /* PROG */

/* STATUS */
#define ST_SDRAM_OK      (1u << 0)
#define CHA_ST_IDLE      (1u << 1)
#define CHA_ST_GAME      (1u << 2)
#define PROG_ST_SDRAM_OK (1u << 1)   /* SDRAM P et V */
#define PROG_ST_IDLE     (1u << 2)
#define PROG_ST_GAME     (1u << 4)

#define ID_PROG          0x4E475031u  /* "NGP1" */
#define ID_CHA           0x4E474331u  /* "NGC1" */

void     qlink_init(void);
void     qlink_reg_write(link_id_t l, uint8_t reg, uint32_t val);
uint32_t qlink_reg_read(link_id_t l, uint8_t reg);
/* écriture en rafale (DMA + PIO) */
void     qlink_mem_write(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len);
/* version asynchrone : start lance le DMA, finish attend la fin et relâche CS */
void     qlink_mem_write_start(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len);
void     qlink_mem_write_finish(link_id_t l);
/* lecture (espaces BRAM uniquement), lente, pour la boîte aux lettres */
void     qlink_mem_read(link_id_t l, uint8_t space, uint32_t addr, void *buf, size_t len);
/* attend que les écritures soient arrivées en mémoire */
bool     qlink_wait_idle(link_id_t l, uint32_t timeout_ms);

#endif
