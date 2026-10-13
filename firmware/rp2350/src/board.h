/*
 * Affectation des broches du Raspberry Pi Pico 2 (RP2350) sur la carte CHA.
 * Voir docs/05-firmware-rp2350.md et hardware/README.md.
 */
#ifndef SDAES_BOARD_H
#define SDAES_BOARD_H

/* Carte SD en mode SDIO 4 bits (PIO1) : CLK = D0 - 2, D0..D3 consécutifs */
#define PIN_SD_CLK      2
#define PIN_SD_CMD      3
#define PIN_SD_D0       4       /* D1 = 5, D2 = 6, D3 = 7 */

/* Liaison vers le FPGA PROG (passe par le connecteur inter-cartes) */
#define PIN_PROG_SCK    8
#define PIN_PROG_IO0    9       /* IO0..IO3 = 9..12 */
#define PIN_PROG_CS     13

/* Liaison vers le FPGA CHA */
#define PIN_CHA_SCK     14
#define PIN_CHA_IO0     15      /* IO0..IO3 = 15..18 */
#define PIN_CHA_CS      19

#define PIN_PROG_IRQ    20      /* commande du menu en attente (actif haut) */
#define PIN_CHA_DONE    21      /* DONE des FPGA (configuration terminée) */
#define PIN_PROG_DONE   22
#define PIN_BUTTON      26      /* bouton "retour menu" (actif bas) */
#define PIN_LED         25      /* LED du Pico 2 */

/* Fréquence de la liaison : sys 150 MHz / (2 x LINK_CLKDIV) */
#define LINK_CLKDIV     4.0f    /* 18,75 MHz -> ~9 Mo/s par liaison */

#endif
