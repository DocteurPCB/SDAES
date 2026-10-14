/*
 * Configuration des quatre FPGA depuis la carte SD (iCE40 en SPI esclave).
 */
#ifndef SDAES_FPGA_BOOT_H
#define SDAES_FPGA_BOOT_H

#include <stddef.h>

/* fichiers attendus dans 0:/SDAES (sorties de make -C hdl sd) */
#define FPGA_DIR "0:/SDAES"

/* codes d'erreur (= nombre de clignotements de la LED du Pico) */
#define BOOT_ERR_MISSING  4     /* fichier absent */
#define BOOT_ERR_SIZE     6     /* taille incohérente */
#define BOOT_ERR_READ     7     /* erreur de lecture */
#define BOOT_ERR_CDONE    8     /* configuration refusée (CDONE bas) */

/* 0 = les quatre FPGA sont configurés (CDONE haut) ; sinon BOOT_ERR_*,
 * message court dans msg et FPGA concerné dans *which (0 = P, 1 = V,
 * 2 = C, 3 = SM ; -1 si inconnu) */
int fpga_boot(char *msg, size_t msglen, int *which);

#endif
