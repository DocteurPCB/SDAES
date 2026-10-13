/* Imitations de FatFs et de la liaison FPGA pour le test sur PC. */
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "ff.h"
#include "qlink.h"
#include "fakes.h"

uint8_t *mem_prog[4], *mem_cha[4];
uint32_t reg_prog[256], reg_cha[256];
uint32_t max_addr_prog[4], max_addr_cha[4];
static const uint32_t sizes_prog[4] = { 32u << 20, 32u << 20, 4096, 32768 };
static const uint32_t sizes_cha[4]  = { 64u << 20, 1u << 20, 8192, 8192 };

void fakes_init(void)
{
    for (int i = 0; i < 4; i++) {
        mem_prog[i] = calloc(1, sizes_prog[i]);
        mem_cha[i]  = calloc(1, sizes_cha[i]);
    }
}

/* ---- FatFs ---- */
static void host_path(char *dst, const char *p)
{
    const char *root = getenv("SDAES_SD");
    if (!strncmp(p, "0:", 2)) p += 2;
    snprintf(dst, 1024, "%s%s", root ? root : ".", p);
}

FRESULT f_mount(FATFS *fs, const char *path, int opt) { (void)fs; (void)path; (void)opt; return FR_OK; }

FRESULT f_open(FIL *f, const char *path, int mode)
{
    char hp[1024];
    host_path(hp, path);
    f->fp = fopen(hp, (mode & FA_WRITE) ? "wb" : "rb");
    if (!f->fp) return FR_NO_FILE;
    struct stat st;
    stat(hp, &st);
    f->size = (uint32_t)st.st_size;
    return FR_OK;
}
FRESULT f_read(FIL *f, void *buf, UINT n, UINT *got) { *got = (UINT)fread(buf, 1, n, f->fp); return FR_OK; }
FRESULT f_write(FIL *f, const void *buf, UINT n, UINT *w) { *w = (UINT)fwrite(buf, 1, n, f->fp); return FR_OK; }
FRESULT f_close(FIL *f) { fclose(f->fp); return FR_OK; }
FRESULT f_mkdir(const char *path) { char hp[1024]; host_path(hp, path); mkdir(hp, 0755); return FR_OK; }

FRESULT f_opendir(DIR *d, const char *path)
{
    host_path(d->path, path);
    d->d = opendir(d->path);
    return d->d ? FR_OK : FR_NO_PATH;
}
FRESULT f_readdir(DIR *d, FILINFO *fi)
{
    struct dirent *e = readdir(d->d);
    if (!e) { fi->fname[0] = 0; return FR_OK; }
    snprintf(fi->fname, sizeof(fi->fname), "%s", e->d_name);
    char full[1300];
    snprintf(full, sizeof(full), "%s/%s", d->path, e->d_name);
    struct stat st;
    stat(full, &st);
    fi->fattrib = S_ISDIR(st.st_mode) ? AM_DIR : 0;
    fi->fsize = (uint32_t)st.st_size;
    return FR_OK;
}
FRESULT f_closedir(DIR *d) { closedir(d->d); return FR_OK; }

/* ---- liaison FPGA ---- */
void qlink_init(void) {}

void qlink_reg_write(link_id_t l, uint8_t reg, uint32_t val)
{
    if (l == LINK_PROG) reg_prog[reg] = val; else reg_cha[reg] = val;
}

uint32_t qlink_reg_read(link_id_t l, uint8_t reg)
{
    if (reg == REG_STATUS)            /* SDRAM prêtes, chargeur au repos */
        return l == LINK_PROG ? (PROG_ST_SDRAM_OK | PROG_ST_IDLE | 1) : (ST_SDRAM_OK | CHA_ST_IDLE);
    if (reg == REG_ID) return l == LINK_PROG ? ID_PROG : ID_CHA;
    return l == LINK_PROG ? reg_prog[reg] : reg_cha[reg];
}

static int pending_l = -1;
static void mem_store(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len)
{
    const uint32_t *sz = l == LINK_PROG ? sizes_prog : sizes_cha;
    uint8_t *m = (l == LINK_PROG ? mem_prog : mem_cha)[space];
    uint32_t *mx = l == LINK_PROG ? max_addr_prog : max_addr_cha;
    if (space > 3 || addr + len > sz[space]) {
        fprintf(stderr, "ECHEC écriture hors limites lien %d espace %d adr %x len %zu\n", l, space, addr, len);
        exit(1);
    }
    memcpy(m + addr, buf, len);
    if (addr + len > mx[space]) mx[space] = (uint32_t)(addr + len);
}
void qlink_mem_write(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len)
{
    if (pending_l >= 0) { fprintf(stderr, "ECHEC écriture pendant un DMA\n"); exit(1); }
    mem_store(l, space, addr, buf, len);
}
void qlink_mem_write_start(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len)
{
    if (pending_l >= 0) { fprintf(stderr, "ECHEC DMA déjà en cours\n"); exit(1); }
    mem_store(l, space, addr, buf, len);
    pending_l = l;
}
void qlink_mem_write_finish(link_id_t l)
{
    if (pending_l != (int)l) { fprintf(stderr, "ECHEC finish sans start (%d/%d)\n", pending_l, l); exit(1); }
    pending_l = -1;
}
void qlink_mem_read(link_id_t l, uint8_t space, uint32_t addr, void *buf, size_t len)
{
    if (pending_l >= 0) { fprintf(stderr, "ECHEC lecture pendant un DMA\n"); exit(1); }
    memcpy(buf, (l == LINK_PROG ? mem_prog : mem_cha)[space] + addr, len);
}
bool qlink_wait_idle(link_id_t l, uint32_t t) { (void)l; (void)t; return pending_l < 0; }
