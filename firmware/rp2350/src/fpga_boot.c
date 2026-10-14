/*
 * Configuration des quatre FPGA depuis la carte SD.
 *
 * Les iCE40 n'ont pas de flash : au démarrage, le RP2350 les tient en reset
 * (CRESET_N commun), les fait démarrer en mode SPI esclave, puis leur envoie
 * l'un après l'autre leur bitstream par le bus de liaison (SCK, IO0 = SDI,
 * CS = SS du FPGA visé). Mettre à jour le code des FPGA = copier les
 * fichiers .bin sur la carte SD. Voir docs/04-liaison-rp2350.md.
 */
#include <stdio.h>
#include <string.h>
#include "ff.h"
#include "qlink.h"
#include "fpga_boot.h"

static const struct { link_id_t link; const char *file; } images[4] = {
    { LINK_P,  "fpga_p.bin"  },
    { LINK_V,  "fpga_v.bin"  },
    { LINK_C,  "fpga_c.bin"  },
    { LINK_SM, "fpga_sm.bin" },
};

/* taille d'un bitstream iCE40 HX4K/HX8K non compressé : 135 100 octets */
#define BITSTREAM_MIN 1024u
#define BITSTREAM_MAX (256u * 1024u)

static uint8_t chunk[4096];

int fpga_boot(char *msg, size_t msglen, int *which)
{
    *which = -1;
    char path[64];
    FIL f;

    /* toutes les images présentes avant de toucher aux FPGA */
    for (int i = 0; i < 4; i++) {
        snprintf(path, sizeof(path), "%s/%s", FPGA_DIR, images[i].file);
        if (f_open(&f, path, FA_READ) != FR_OK) {
            snprintf(msg, msglen, "MANQUE SDAES/%s", images[i].file);
            *which = i;
            return BOOT_ERR_MISSING;
        }
        uint32_t size = f_size(&f);
        f_close(&f);
        if (size < BITSTREAM_MIN || size > BITSTREAM_MAX) {
            snprintf(msg, msglen, "TAILLE SDAES/%s", images[i].file);
            *which = i;
            return BOOT_ERR_SIZE;
        }
    }

    qlink_cfg_reset();
    for (int i = 0; i < 4; i++) {
        snprintf(path, sizeof(path), "%s/%s", FPGA_DIR, images[i].file);
        if (f_open(&f, path, FA_READ) != FR_OK) {
            snprintf(msg, msglen, "LECTURE SDAES/%s", images[i].file);
            *which = i;
            return BOOT_ERR_READ;
        }
        qlink_cfg_begin(images[i].link);
        UINT got;
        int err = 0;
        do {
            if (f_read(&f, chunk, sizeof(chunk), &got) != FR_OK) { err = 1; break; }
            qlink_cfg_data(images[i].link, chunk, got);
        } while (got == sizeof(chunk));
        qlink_cfg_end(images[i].link);
        f_close(&f);
        if (err) {
            snprintf(msg, msglen, "LECTURE SDAES/%s", images[i].file);
            *which = i;
            return BOOT_ERR_READ;
        }
    }
    if (!qlink_cfg_done()) {
        snprintf(msg, msglen, "CDONE BAS");
        return BOOT_ERR_CDONE;
    }
    snprintf(msg, msglen, "FPGA OK");
    return 0;
}
