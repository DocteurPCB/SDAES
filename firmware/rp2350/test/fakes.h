#ifndef FAKES_H
#define FAKES_H
#include <stdint.h>
extern uint8_t *mem[4][4];
extern uint32_t regs[4][256];
extern uint32_t max_addr[4][4];
extern uint8_t sma_table[256];
extern int     sma_table_writes;
void fakes_init(void);
#endif
