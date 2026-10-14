/*
 * Test sur PC du firmware : navigation, protocole de la boîte aux lettres et
 * chargement d'un .neo. Les images mémoire obtenues sont écrites dans
 * $SDAES_OUT pour être comparées par tools/tests/test_firmware.py.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ff.h"
#include "qlink.h"
#include "browser.h"
#include "fpga_boot.h"
#include "fakes.h"
#include "../../../protocol/sdaes_mailbox.h"

static uint16_t seq;
static int failures;

static uint16_t mb16(uint16_t off) { return (uint16_t)((mem[LINK_P][SP_P_MAILBOX][off] << 8) | mem[LINK_P][SP_P_MAILBOX][off + 1]); }
static const char *mbstr(uint16_t off) { return (const char *)&mem[LINK_P][SP_P_MAILBOX][off]; }

static uint16_t send(uint16_t cmd, uint32_t arg0)
{
    uint8_t *m = mem[LINK_P][SP_P_MAILBOX];
    seq++;
    m[0] = cmd >> 8; m[1] = (uint8_t)cmd;
    m[2] = seq >> 8; m[3] = (uint8_t)seq;
    m[4] = arg0 >> 24; m[5] = arg0 >> 16; m[6] = arg0 >> 8; m[7] = (uint8_t)arg0;
    browser_handle_command();
    if (mb16(MB_RSP_SEQ) != seq) { printf("ECHEC pas de réponse à la commande %d\n", cmd); failures++; }
    return mb16(MB_RSP_STATUS);
}

static int find(const char *name)
{
    for (int i = 0; i < mb16(MB_RSP_COUNT); i++)
        if (!strcmp(mbstr(MB_RSP_ENTRIES + i * MB_ENTRY_SIZE + 1), name)) return i;
    return -1;
}

static void expect(int cond, const char *what)
{
    printf("%s %s\n", cond ? "ok   " : "ECHEC", what);
    if (!cond) failures++;
}

static void dump(const char *name, const uint8_t *p, uint32_t len)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/%s", getenv("SDAES_OUT"), name);
    FILE *f = fopen(path, "wb");
    fwrite(p, 1, len, f);
    fclose(f);
}

int main(void)
{
    fakes_init();

    /* configuration des FPGA depuis SDAES/fpga_*.bin */
    {
        char msg[40], a[1024], b[1024];
        int which;
        int r = fpga_boot(msg, sizeof(msg), &which);
        printf("info  fpga_boot : %s\n", msg);
        expect(r == 0 && cfg_resets == 1, "FPGA configurés depuis la carte SD");
        dump("cfg_p.bin", cfg_buf[LINK_P], (uint32_t)cfg_len[LINK_P]);
        dump("cfg_v.bin", cfg_buf[LINK_V], (uint32_t)cfg_len[LINK_V]);
        dump("cfg_c.bin", cfg_buf[LINK_C], (uint32_t)cfg_len[LINK_C]);
        dump("cfg_sm.bin", cfg_buf[LINK_SM], (uint32_t)cfg_len[LINK_SM]);
        snprintf(a, sizeof(a), "%s/SDAES/fpga_v.bin", getenv("SDAES_SD"));
        snprintf(b, sizeof(b), "%s/SDAES/fpga_v.tmp", getenv("SDAES_SD"));
        rename(a, b);
        r = fpga_boot(msg, sizeof(msg), &which);
        expect(r == BOOT_ERR_MISSING && which == LINK_V && !strcmp(msg, "MANQUE SDAES/fpga_v.bin") && cfg_resets == 1,
               "fichier manquant : FPGA laissés en reset");
        rename(b, a);
    }

    browser_init(1);
    {
        static const uint16_t ver[4] = { 41, 42, 43, 44 };
        browser_set_fpga_versions(ver);
        expect(mb16(MB_RSP_FPGAVER) == 41 && mb16(MB_RSP_FPGAVER + 6) == 44, "versions FPGA dans la boîte aux lettres");
    }

    expect(send(CMD_PING, 0) == ST_OK, "PING");
    expect(send(CMD_LIST, 0) == ST_OK, "LIST racine");
    expect(mb16(MB_RSP_KIND) == KIND_LIST, "nature = liste");
    printf("info  racine : %d entrées, chemin '%s'\n", mb16(MB_RSP_TOTAL), mbstr(MB_RSP_PATH));
    for (int i = 0; i < mb16(MB_RSP_COUNT); i++)
        printf("info   [%d] %s%s\n", i, mem[LINK_P][SP_P_MAILBOX][MB_RSP_ENTRIES + i * 32] ? "/" : " ",
               mbstr(MB_RSP_ENTRIES + i * 32 + 1));
    int d = find("Jeux");
    expect(d == 0, "dossier en tête de liste");
    expect(find("readme.txt") < 0, "fichiers non .neo masqués");

    expect(send(CMD_OPEN, (uint32_t)d) == ST_OK && mb16(MB_RSP_KIND) == KIND_DIR_CHANGED, "entrée dans Jeux");
    expect(send(CMD_LIST, 0) == ST_OK, "LIST Jeux");
    expect(!strcmp(mbstr(MB_RSP_PATH), "/Jeux"), "chemin /Jeux");
    int bad = find("casse");
    int g = find("test");
    expect(g >= 0 && bad >= 0, "jeux listés sans extension");

    expect(send(CMD_OPEN, (uint32_t)bad) == ST_ERR_FORMAT, "fichier invalide refusé");
    printf("info  message : %s\n", mbstr(MB_RSP_MSG));
    expect(regs[LINK_P][REG_CTRL] == 0 && regs[LINK_C][REG_CTRL] == 0, "pas armé après échec");

    expect(send(CMD_OPEN, (uint32_t)g) == ST_OK, "chargement test.neo");
    expect(mb16(MB_RSP_KIND) == KIND_GAME_READY, "jeu prêt");
    expect(mb16(MB_RSP_PROGRESS) == 1000, "progression 100 %");
    expect(!strcmp(mbstr(MB_RSP_MSG), "SDAES TEST"), "nom du jeu renvoyé");
    expect((regs[LINK_P][REG_CTRL] & CTRL_ARM) && (regs[LINK_V][REG_CTRL] & CTRL_ARM) &&
           (regs[LINK_C][REG_CTRL] & CTRL_ARM) && (regs[LINK_SM][REG_CTRL] & CTRL_ARM), "4 FPGA armés");

    FILE *r = fopen(strcat(strcpy((char[512]){0}, getenv("SDAES_OUT")), "/regs.txt"), "w");
    fprintf(r, "prog_ctrl=%u\np_mask=%u\nv1_base=%u\nv1_mask=%u\nv2_base=%u\nv2_mask=%u\n",
            regs[LINK_P][REG_CTRL], regs[LINK_P][REG_P_MASK], regs[LINK_V][REG_V1_BASE],
            regs[LINK_V][REG_V1_MASK], regs[LINK_V][REG_V2_BASE], regs[LINK_V][REG_V2_MASK]);
    fprintf(r, "cha_ctrl=%u\nc_mask=%u\ns_mask=%u\nm1_mask=%u\n",
            regs[LINK_C][REG_CTRL], regs[LINK_C][REG_C_MASK], regs[LINK_SM][REG_S_MASK], regs[LINK_SM][REG_M1_MASK]);
    fclose(r);
    dump("prog_p.bin", mem[LINK_P][SP_P_SDRAM], max_addr[LINK_P][SP_P_SDRAM]);
    dump("prog_v.bin", mem[LINK_V][SP_V_SDRAM], max_addr[LINK_V][SP_V_SDRAM]);
    dump("cha_c.bin",  mem[LINK_C][SP_C_SDRAM], max_addr[LINK_C][SP_C_SDRAM]);
    dump("cha_sram.bin", mem[LINK_SM][SP_SM_SRAM], 1u << 20);

    expect(send(CMD_PARENT, 0) == ST_OK, "PARENT");
    send(CMD_LIST, 0);
    expect(!strcmp(mbstr(MB_RSP_PATH), "/"), "retour à la racine");
    expect(send(CMD_RELOAD_LAST, 0) == ST_OK && mb16(MB_RSP_KIND) == KIND_GAME_READY, "rechargement du dernier jeu");
    expect(send(0x77, 0) == ST_ERR_ARG, "commande inconnue refusée");

    /* ===== cartouches protégées ===== */
    send(CMD_LIST, 0);
    expect(send(CMD_OPEN, (uint32_t)find("Jeux")) == ST_OK, "retour dans Jeux");
    send(CMD_LIST, 0);

    /* SMA sans fichier .map : refusé avec un message clair */
    expect(send(CMD_OPEN, (uint32_t)find("kof99")) == ST_ERR_UNSUPPORTED, "SMA sans .map refuse");
    printf("info  message : %s\n", mbstr(MB_RSP_MSG));

    /* SMA avec fichier .map à côté du jeu */
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("kof99b")) == ST_OK, "SMA avec .map charge");
    printf("info  message : %s\n", mbstr(MB_RSP_MSG));
    expect(regs[LINK_P][0x0A] == 1, "SMA : mode");
    expect(regs[LINK_P][REG_P_WAIT] == 7, "attente : pleine vitesse par defaut");
    expect(regs[LINK_SM][REG_SM_FIX_BANK] == 0, "couche fixe : pas de banques (kof99)");
    expect(regs[LINK_P][0x0B] == 0x7FFF8, "SMA : registre de banque 0x2FFFF0");
    expect(regs[LINK_P][0x0C] == 0x5CA86E, "SMA : permutation des bits");
    expect(regs[LINK_P][0x0D] == (0x80000000u | 0x7F223), "SMA : adresse de protection");
    expect(regs[LINK_P][0x0E] == 0x9A37, "SMA : valeur de protection");
    expect(regs[LINK_P][0x0F] == (0x80000000u | 0x7FFFC) && regs[LINK_P][0x15] == (0x80000000u | 0x7FFFD),
           "SMA : generateurs");
    expect(sma_table[16] == 0x00 && sma_table[17] == 0x3C && sma_table[18] == 0xC0 && sma_table[19] == 0x00,
           "SMA : entree 4 de la table = 0x3CC000");
    expect(sma_table[20] == 0 && sma_table[23] == 0, "SMA : entrees absentes a zero");
    expect((regs[LINK_P][REG_CTRL] & CTRL_BANK_EN) == 0, "SMA : banque standard desactivee");

    /* SMA décrit dans MAPPERS.TXT (trouvé par le nom) */
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("garou")) == ST_OK, "SMA via MAPPERS.TXT");
    expect(regs[LINK_P][0x0B] == 0x7FFE0, "SMA garou : banque 0x2FFFC0");
    expect(regs[LINK_SM][REG_SM_FIX_BANK] == 1, "couche fixe garou : type 1 d'apres le NGH");

    /* prototype de Garou : même NGH, zone P de 5 Mo au plus -> pas de SMA */
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("garoup")) == ST_OK, "Garou prototype accepte (sans SMA)");
    expect(regs[LINK_P][0x0A] == 0, "Garou prototype : banques standard");

    /* superposition KOF 98 décrite dans MAPPERS.TXT (trouvée par le NGH) */
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("roi98")) == ST_OK, "superposition via NGH");
    expect(regs[LINK_P][0x0A] == 0x100, "superposition : mode");
    expect(regs[LINK_P][0x17] == 0x5555 && regs[LINK_P][0x18] == 0x009000F0 &&
           regs[LINK_P][0x19] == 0x80 && regs[LINK_P][0x1A] == 0x00C200FD, "superposition : registres");
    expect(regs[LINK_P][REG_P_WAIT] == 2, "attente : ROM 1 cycle, PORT 2 cycles");
    expect(regs[LINK_SM][REG_SM_FIX_BANK] == 2, "couche fixe : cle fix_bank");

    /* PVC reconnu par son NGH sans fichier */
    memset(regs, 0, sizeof(regs));
    memset(mem[LINK_P][SP_P_SDRAM] + 0x18FE000, 0xAA, 8192);
    expect(send(CMD_OPEN, (uint32_t)find("mslug5")) == ST_OK, "PVC interne");
    printf("info  message : %s\n", mbstr(MB_RSP_MSG));
    expect(regs[LINK_P][0x0A] == 2, "PVC : mode");
    int zero = 1;
    for (int i = 0; i < 8192; i++) if (mem[LINK_P][SP_P_SDRAM][0x18FE000 + i]) zero = 0;
    expect(zero, "PVC : RAM de protection remise a zero");

    /* Metal Slug 5 Plus (reconnu par le CRC de P1) et bootleg (P de 5 Mo) */
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("ms5plus")) == ST_OK, "Metal Slug 5 Plus");
    printf("info  message : %s\n", mbstr(MB_RSP_MSG));
    expect(regs[LINK_P][0x0A] == 4, "MS5 Plus : mode MS5P");
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("mslug5b")) == ST_OK, "Metal Slug 5 bootleg");
    expect(regs[LINK_P][0x0A] == 0, "MS5 bootleg : banques standard");
    expect((regs[LINK_P][REG_CTRL] & CTRL_BANK_EN) == 0, "MS5 bootleg : petit P, pas de banque");

    /* SVC Chaos et KOF 2003 : versions d'après la taille de P */
    {
        static const struct { const char *name; uint32_t mode; uint32_t fix; } v[] = {
            { "svcplus", 0, 0 }, { "kof2003", 2, 2 }, { "kf2k3bl", 5, 0 }, { "kf2k3pl", 6, 0 },
        };
        for (unsigned i = 0; i < sizeof(v) / sizeof(v[0]); i++) {
            char what[64];
            memset(regs, 0, sizeof(regs));
            memset(mem[LINK_P][SP_P_SDRAM] + 0x18FE000, 0xAA, 8192);
            snprintf(what, sizeof(what), "%s : charge", v[i].name);
            expect(send(CMD_OPEN, (uint32_t)find(v[i].name)) == ST_OK, what);
            printf("info  message : %s\n", mbstr(MB_RSP_MSG));
            snprintf(what, sizeof(what), "%s : mode %u", v[i].name, (unsigned)v[i].mode);
            expect(regs[LINK_P][0x0A] == v[i].mode, what);
            snprintf(what, sizeof(what), "%s : couche fixe %u", v[i].name, (unsigned)v[i].fix);
            expect(regs[LINK_SM][REG_SM_FIX_BANK] == v[i].fix, what);
            if (v[i].mode >= 2 && v[i].mode != 3) {
                int z = 1;
                for (int k = 0; k < 8192; k++) if (mem[LINK_P][SP_P_SDRAM][0x18FE000 + k]) z = 0;
                snprintf(what, sizeof(what), "%s : RAM de protection a zero", v[i].name);
                expect(z, what);
            }
        }
    }

    /* Metal Slug X : correctif de P1 */
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("mslugx")) == ST_OK, "Metal Slug X");
    printf("info  message : %s\n", mbstr(MB_RSP_MSG));
    {
        const uint8_t *p = mem[LINK_P][SP_P_SDRAM];
        static const uint8_t nop2[4] = { 0x71, 0x4E, 0x71, 0x4E };
        expect(!memcmp(p + 0x1004, nop2, 4), "MSX : bne neutralise (0x1004)");
        expect(!memcmp(p + 0x8000, nop2, 4), "MSX : bne neutralise a cheval sur deux blocs (0x8000)");
        expect(p[0x1000] == 0x43 && p[0x1002] == 0x01, "MSX : andi.w conserve");
        expect(!memcmp(p + 0x3BDC, nop2, 4) && !memcmp(p + 0x3C36, nop2, 4), "MSX : adresses fixes");
        expect(p[0x3BE2] == 0 && p[0x3C3A] == 0, "MSX : rien d'autre");
        expect(regs[LINK_P][0x0A] == 0, "MSX : banques standard");
    }

    /* PRO-CT0 reconnu par son NGH */
    memset(regs, 0, sizeof(regs));
    expect(send(CMD_OPEN, (uint32_t)find("fatfury2")) == ST_OK, "PRO-CT0 interne");
    expect(regs[LINK_P][0x0A] == 3, "PRO-CT0 : mode");
    expect((regs[LINK_P][REG_CTRL] & CTRL_BANK_EN) == 0, "PRO-CT0 : banque standard desactivee");

    printf("RESULTAT firmware : %s\n", failures ? "ECHEC" : "SUCCES");
    return failures ? 1 : 0;
}
