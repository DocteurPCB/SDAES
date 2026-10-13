#ifndef FAKES_H
#define FAKES_H
#include <stdint.h>
extern uint8_t *mem_prog[4], *mem_cha[4];
extern uint32_t reg_prog[256], reg_cha[256];
extern uint32_t max_addr_prog[4], max_addr_cha[4];
void fakes_init(void);
#endif
