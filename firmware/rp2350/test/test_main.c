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
    browser_init(1);

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

    printf("RESULTAT firmware : %s\n", failures ? "ECHEC" : "SUCCES");
    return failures ? 1 : 0;
}
