/* Imitation minimale de FatFs pour tester le firmware sur PC.
 * "0:/" est relié au dossier donné par la variable d'environnement SDAES_SD. */
#ifndef FAKE_FF_H
#define FAKE_FF_H
#include <stdio.h>
#include <stdint.h>
#include <dirent.h>

#define FF_MAX_LFN 255
typedef unsigned int UINT;
typedef enum { FR_OK = 0, FR_DISK_ERR, FR_NO_FILE, FR_NO_PATH, FR_EXIST } FRESULT;
typedef struct { FILE *fp; uint32_t size; } FIL;
typedef struct { DIR *d; char path[512]; } FF_DIR;
#define DIR FF_DIR
typedef struct { char fname[FF_MAX_LFN + 1]; uint8_t fattrib; uint32_t fsize; } FILINFO;
typedef struct { int dummy; } FATFS;

#define AM_RDO 0x01
#define AM_HID 0x02
#define AM_SYS 0x04
#define AM_DIR 0x10
#define FA_READ          0x01
#define FA_WRITE         0x02
#define FA_CREATE_ALWAYS 0x08

FRESULT f_mount(FATFS *fs, const char *path, int opt);
FRESULT f_open(FIL *f, const char *path, int mode);
FRESULT f_read(FIL *f, void *buf, UINT n, UINT *got);
FRESULT f_write(FIL *f, const void *buf, UINT n, UINT *w);
FRESULT f_close(FIL *f);
FRESULT f_opendir(DIR *d, const char *path);
FRESULT f_readdir(DIR *d, FILINFO *fi);
FRESULT f_closedir(DIR *d);
FRESULT f_mkdir(const char *path);
#define f_size(f) ((f)->size)
#endif
