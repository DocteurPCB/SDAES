/* Imitations de FatFs et de la liaison FPGA pour le test sur PC. */
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "ff.h"
#include "qlink.h"
#include "fakes.h"

/* mémoire [FPGA][espace], registres [FPGA][registre] */
uint8_t *mem[4][4];
uint32_t regs[4][256];
uint32_t max_addr[4][4];
static const uint32_t sizes[4][4] = {
    [LINK_P]  = { 25u << 20, 0, 4096, 8192 },
    [LINK_V]  = { 32u << 20, 0, 0, 0 },
    [LINK_C]  = { 64u << 20, 0, 0, 0 },
    [LINK_SM] = { 1u << 20,  0, 8192, 2048 },
};

void fakes_init(void)
{
    for (int f = 0; f < 4; f++)
        for (int sp = 0; sp < 4; sp++)
            mem[f][sp] = sizes[f][sp] ? calloc(1, sizes[f][sp]) : NULL;
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

void qlink_reg_write(link_id_t l, uint8_t reg, uint32_t val) { regs[l][reg] = val; }

uint32_t qlink_reg_read(link_id_t l, uint8_t reg)
{
    static const uint32_t ids[4] = { ID_P, ID_V, ID_C, ID_SM };
    if (reg == REG_STATUS)            /* mémoire prête, chargeur au repos */
        return ST_MEM_OK | (l == LINK_P ? P_ST_IDLE : VCS_ST_IDLE);
    if (reg == REG_ID) return ids[l];
    return regs[l][reg];
}

static int pending_l = -1;
static void mem_store(link_id_t l, uint8_t space, uint32_t addr, const void *buf, size_t len)
{
    if (space > 3 || !mem[l][space] || addr + len > sizes[l][space]) {
        fprintf(stderr, "ECHEC écriture hors limites FPGA %d espace %d adr %x len %zu\n", l, space, addr, len);
        exit(1);
    }
    memcpy(mem[l][space] + addr, buf, len);
    if (addr + len > max_addr[l][space]) max_addr[l][space] = (uint32_t)(addr + len);
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
    memcpy(buf, mem[l][space] + addr, len);
}
bool qlink_wait_idle(link_id_t l, uint32_t t) { (void)l; (void)t; return pending_l < 0; }
