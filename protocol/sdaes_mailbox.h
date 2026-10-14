/*
 * Protocole de la boîte aux lettres menu 68000 <-> RP2350 (carte PROG).
 * Partagé par le menu (menu/68k) et le firmware (firmware/rp2350).
 *
 * Vue 68000 : base 0x200000, mots grand-boutistes.
 * Vue RP2350 : espace mémoire 2 de la liaison PROG, même ordre d'octets
 *              (adresse paire = octet de poids fort).
 *
 *  0x000-0x0FF  zone COMMANDE (écrite par le 68000 uniquement)
 *  0x100-0xFFF  zone RÉPONSE  (écrite par le RP2350 uniquement)
 *
 * Registres spéciaux côté 68000 :
 *  0x2FFFE0 lecture  : bit0 = commande non encore prise, bit1 = jeu armé
 *  0x2FFFE0 écriture : sonnette (lève LK_IRQ vers le RP2350)
 *  0x2FFFE2 écriture : 0x5A5A = bascule vers le jeu (si armé)
 */
#ifndef SDAES_MAILBOX_H
#define SDAES_MAILBOX_H

#define MB_68K_BASE        0x200000UL
#define MB_68K_STATUS      0x2FFFE0UL
#define MB_68K_DOORBELL    0x2FFFE0UL
#define MB_68K_SWITCH      0x2FFFE2UL
#define MB_SWITCH_MAGIC    0x5A5A

/* zone commande */
#define MB_CMD_ID          0x000   /* u16 */
#define MB_CMD_SEQ         0x002   /* u16, incrémenté à chaque commande */
#define MB_CMD_ARG0        0x004   /* u32 */
#define MB_CMD_ARG1        0x008   /* u32 */

/* zone réponse */
#define MB_RSP_SEQ         0x100   /* u16 = CMD_SEQ quand la réponse est complète */
#define MB_RSP_STATUS      0x102   /* u16, voir ST_* */
#define MB_RSP_PROGRESS    0x104   /* u16, 0..1000 pendant un chargement */
#define MB_RSP_COUNT       0x106   /* u16, entrées valides dans cette page */
#define MB_RSP_TOTAL       0x108   /* u16, entrées dans le dossier */
#define MB_RSP_KIND        0x10A   /* u16, voir KIND_* */
#define MB_RSP_BUSYSEQ     0x10C   /* u16 = CMD_SEQ dès la prise en compte */
#define MB_RSP_FWVER       0x10E   /* u16, version du firmware */
#define MB_RSP_PATH        0x110   /* char[64], dossier courant */
#define MB_RSP_MSG         0x150   /* char[64], message (erreur, nom du jeu) */
#define MB_RSP_FPGAVER     0x190   /* 4 x u16 : versions des bitstreams P, V, C, SM */
#define MB_RSP_ENTRIES     0x200   /* MB_PAGE_SIZE entrées de 32 octets */
#define MB_ENTRY_SIZE      32      /* [0] type, [1..31] nom terminé par 0 */
#define MB_PAGE_SIZE       24
#define MB_NAME_MAX        30

/* commandes */
#define CMD_PING           0x0001
#define CMD_LIST           0x0002  /* ARG0 = premier index */
#define CMD_OPEN           0x0003  /* ARG0 = index : dossier -> entre, .neo -> charge */
#define CMD_PARENT         0x0004
#define CMD_RELOAD_LAST    0x0005  /* recharge le dernier jeu lancé */

/* statut */
#define ST_OK              0x0000
#define ST_BUSY            0x0001
#define ST_ERR_IO          0x0080
#define ST_ERR_FORMAT      0x0081
#define ST_ERR_TOO_BIG     0x0082
#define ST_ERR_UNSUPPORTED 0x0083
#define ST_ERR_NOCARD      0x0084
#define ST_ERR_ARG         0x0085

/* nature de la réponse */
#define KIND_NONE          0
#define KIND_LIST          1
#define KIND_DIR_CHANGED   2
#define KIND_GAME_READY    3

/* type d'entrée */
#define ENT_FILE           0
#define ENT_DIR            1

#endif
