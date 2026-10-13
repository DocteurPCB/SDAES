#ifndef SDAES_BROWSER_H
#define SDAES_BROWSER_H

#include <stdint.h>

#define FW_VERSION 0x0001

/* à appeler après le montage de la carte SD (sd_ok = 0 si absente) */
void browser_init(int sd_ok);
/* traite une commande en attente dans la boîte aux lettres */
void browser_handle_command(void);

#endif
