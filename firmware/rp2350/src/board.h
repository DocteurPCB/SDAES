/*
 * Affectation des broches du Raspberry Pi Pico 2 (RP2350) sur la carte PROG.
 * Voir docs/04-liaison-rp2350.md et hardware/README.md.
 */
#ifndef SDAES_BOARD_H
#define SDAES_BOARD_H

/* Carte SD en mode SDIO 4 bits (PIO1) : CLK = D0 - 2, D0..D3 consécutifs */
#define PIN_SD_CLK      2
#define PIN_SD_CMD      3
#define PIN_SD_D0       4       /* D1 = 5, D2 = 6, D3 = 7 */

/* Bus de liaison de la carte PROG (FPGA P et V), sur la même carte */
#define PIN_PROG_SCK    8
#define PIN_PROG_IO0    9       /* IO0..IO3 = 9..12 */
#define PIN_CS_P        13
#define PIN_CS_V        14

/* Bus de liaison de la carte CHA (FPGA C et SM), via le câble inter-cartes */
#define PIN_CHA_SCK     15
#define PIN_CHA_IO0     16      /* IO0..IO3 = 16..19 */
#define PIN_CS_C        20
#define PIN_CS_SM       21

#define PIN_PROG_IRQ    22      /* commande du menu en attente (actif haut) */
#define PIN_CDONE       26      /* CDONE des 4 FPGA en ET câblé (drain ouvert) */
#define PIN_BUTTON      27      /* bouton "retour menu" (actif bas) */
#define PIN_CRESET_N    28      /* reset commun des 4 FPGA (tiré à la masse) */
#define PIN_LED         25      /* LED du Pico 2 */

/* Fréquence de la liaison : sys 150 MHz / (2 x LINK_CLKDIV) */
#define LINK_CLKDIV     4.0f    /* 18,75 MHz -> ~9 Mo/s par bus */

#endif
