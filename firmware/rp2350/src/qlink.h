/*
 * Pilote de la liaison 4 bits vers les FPGA (voir docs/04-liaison-rp2350.md).
 */
#ifndef SDAES_QLINK_H
#define SDAES_QLINK_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* quatre FPGA : P et V sur le bus PROG, C et SM sur le bus CHA */
typedef enum { LINK_P = 0, LINK_V = 1, LINK_C = 2, LINK_SM = 3 } link_id_t;

/* espaces mémoire */
#define SP_P_SDRAM       0
#define SP_P_MAILBOX     2
#define SP_P_MENU        3
#define SP_V_SDRAM       0
#define SP_C_SDRAM       0
#define SP_SM_SRAM       0       /* S en 0x00000, M1 en 0x80000 */
#define SP_SM_MENU_S     2
#define SP_SM_MENU_M1    3

/* registres communs */
#define REG_ID           0x00
#define REG_CTRL         0x01
#define REG_STATUS       0x02
#define REG_DBG_ADDR     0x10
#define REG_DBG_DATA     0x11
/* FPGA P */
#define REG_P_MASK       0x03
#define REG_P_BANK       0x08
#define REG_IRQ_ACK      0x09   /* écriture : acquitte LK_IRQ */
/* FPGA V */
#define REG_V1_BASE      0x04
#define REG_V1_MASK      0x05
#define REG_V2_BASE      0x06
#define REG_V2_MASK      0x07
/* FPGA C */
#define REG_C_MASK       0x03
/* FPGA SM */
#define REG_S_MASK       0x04
#define REG_M1_MASK      0x05

#define CTRL_ARM         (1u << 0)
#define CTRL_FORCE       (1u << 1)
#define CTRL_BANK_EN     (1u << 3)   /* FPGA P */

/* STATUS : bit0 = mémoire prête (SDRAM initialisée) sur les 4 FPGA ;
 * chargeur au repos : bit2 sur P, bit1 sur V, C et SM */
#define ST_MEM_OK        (1u << 0)
#define P_ST_IDLE        (1u << 2)
#define P_ST_GAME        (1u << 3)
#define VCS_ST_IDLE      (1u << 1)
#define VCS_ST_GAME      (1u << 2)

#define ID_P             0x4E475032u  /* "NGP2" */
#define ID_V             0x4E475632u  /* "NGV2" */
#define ID_C             0x4E474332u  /* "NGC2" */
#define ID_SM            0x4E475332u  /* "NGS2" */

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
