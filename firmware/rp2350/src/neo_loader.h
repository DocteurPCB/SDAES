#ifndef SDAES_NEO_LOADER_H
#define SDAES_NEO_LOADER_H

#include <stdint.h>

#define NEO_HEADER_SIZE 4096

typedef struct {
    uint32_t psize, ssize, msize, v1size, v2size, csize;
    uint32_t year, genre, screenshot, ngh;
    char     name[33];
    char     manu[17];
} neo_header_t;

/* progression : 0..1000 */
typedef void (*neo_progress_cb)(uint16_t permille);

/* Charge un fichier .neo dans les mémoires de la cartouche et arme les FPGA.
 * Retourne un code ST_* (sdaes_mailbox.h) ; msg reçoit un texte court. */
uint16_t neo_load(const char *path, neo_progress_cb cb, neo_header_t *hdr, char *msg, int msglen);

/* Analyse un en-tête .neo (4096 octets). Retourne 0 si valide. */
int neo_parse_header(const uint8_t *raw, neo_header_t *h);

#endif
