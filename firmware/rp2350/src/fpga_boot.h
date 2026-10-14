/*
 * Configuration des quatre FPGA depuis la carte SD (iCE40 en SPI esclave).
 */
#ifndef SDAES_FPGA_BOOT_H
#define SDAES_FPGA_BOOT_H

#include <stddef.h>

/* fichiers attendus dans 0:/SDAES (sorties de make -C hdl sd) */
#define FPGA_DIR "0:/SDAES"

/* 0 = les quatre FPGA sont configurés (CDONE haut) ;
 * < 0 = erreur, message court dans msg */
int fpga_boot(char *msg, size_t msglen);

#endif
