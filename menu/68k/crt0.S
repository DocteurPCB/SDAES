/* ---------------------------------------------------------------------------
 * Démarrage du menu SDAES : table des vecteurs, en-tête cartouche Neo Geo,
 * points d'entrée appelés par le BIOS.
 *
 * Le "code de sécurité" vérifié par le BIOS n'est pas fourni ici : la zone
 * 0x186-0x3FF est réservée et remplie au moment de la construction par
 * tools/neotool.py (commande "security") à partir d'un jeu que vous possédez.
 * ------------------------------------------------------------------------- */

        .set BIOS_SYSTEM_MODE,  0x10FD80
        .set BIOS_USER_REQUEST, 0x10FDAE
        .set SYSTEM_RETURN,     0xC00444
        .set SYSTEM_INT1,       0xC00438
        .set REG_IRQACK,        0x3C000C
        .set REG_WATCHDOG,      0x300001
        .set REG_SWITCH,        0x2FFFE2
        .set REG_SWPBIOS,       0x3A0003

        .section .vectors, "ax"
        .long   0x0010F300              /* SSP initial */
        .long   0x00C00402              /* PC initial : BIOS */
        .rept   23
        .long   exc_handler             /* 0x08-0x60 : exceptions */
        .endr
        .long   irq_vblank              /* 0x64 : niveau 1 (VBlank) */
        .long   irq_timer               /* 0x68 : niveau 2 (timer) */
        .long   irq_other               /* 0x6C : niveau 3 */
        .rept   36
        .long   exc_handler             /* 0x70-0xFC */
        .endr

        .section .header, "ax"
        .ascii  "NEO-GEO"
        .byte   0x00                    /* 0x107 */
        .word   0x0FFE                  /* 0x108 : numéro NGH du menu */
        .long   0x00002000              /* 0x10A : taille du programme */
        .long   0x0010E000              /* 0x10E : sauvegarde (inutilisée) */
        .word   0x0000                  /* 0x112 : taille sauvegarde */
        .byte   0x02                    /* 0x114 : pas d'animation d'intro */
        .byte   0x00                    /* 0x115 */
        .long   softdips                /* 0x116 : réglages JP */
        .long   softdips                /* 0x11A : réglages US */
        .long   softdips                /* 0x11E : réglages EU */
        /* JMP absolus longs (6 octets) codés à la main pour figer la taille */
        .word   0x4EF9
        .long   user                    /* 0x122 : USER */
        .word   0x4EF9
        .long   player_start            /* 0x128 : PLAYER_START */
        .word   0x4EF9
        .long   demo_end                /* 0x12E : DEMO_END */
        .word   0x4EF9
        .long   coin_sound              /* 0x134 : COIN_SOUND */
        .fill   0x182 - 0x13A, 1, 0xFF
        .long   0x00000186              /* 0x182 : pointeur code de sécurité */
        /* 0x186-0x3FF : réservé au code de sécurité (rempli à la construction) */
        .fill   0x400 - 0x186, 1, 0x00

        .text
        .global _start
_start:
user:
        move.w  #0x2700, %sr
        tst.b   BIOS_USER_REQUEST
        bne.s   1f
        jmp     SYSTEM_RETURN           /* requête 0 : initialisation */
1:      move.b  #0x80, BIOS_SYSTEM_MODE /* le jeu prend la main */
        lea     0x0010F300, %sp
        /* .bss à zéro, .data copiée depuis la ROM */
        lea     _bss_start, %a0
        lea     _bss_end, %a1
2:      cmpa.l  %a1, %a0
        bcc.s   3f
        clr.b   (%a0)+
        bra.s   2b
3:      lea     _data_load, %a0
        lea     _data_start, %a1
        lea     _data_end, %a2
4:      cmpa.l  %a2, %a1
        bcc.s   5f
        move.b  (%a0)+, (%a1)+
        bra.s   4b
5:      jsr     menu_main               /* ne revient pas */
        bra.s   1b

player_start:
demo_end:
coin_sound:
        rts

irq_vblank:
        btst    #7, BIOS_SYSTEM_MODE
        bne.s   1f
        jmp     SYSTEM_INT1             /* mode système : le BIOS gère */
1:      move.w  #4, REG_IRQACK
        rte
irq_timer:
        move.w  #2, REG_IRQACK
        rte
irq_other:
        move.w  #1, REG_IRQACK
        rte

exc_handler:
        bra.s   exc_handler             /* le chien de garde redémarre */

/* ---------------------------------------------------------------------------
 * Routine de bascule copiée en RAM de travail puis exécutée :
 *  1. demande au FPGA PROG de passer en mode jeu (les ROM changent)
 *  2. attend sans nourrir le chien de garde -> reset matériel complet
 *  3. secours si aucun reset ne survient : saut au point d'entrée du BIOS
 * ------------------------------------------------------------------------- */
        .global launch_stub, launch_stub_end
launch_stub:
        move.w  #0x2700, %sr
        move.w  #0x5A5A, REG_SWITCH
        move.l  #0x00300000, %d0        /* ~0,5 s */
2:      subq.l  #1, %d0
        bne.s   2b
        move.b  #1, REG_SWPBIOS
        move.l  0x00C00000, %sp
        move.l  0x00C00004, %a0
        jmp     (%a0)
launch_stub_end:

        .section .rodata
softdips:
        .ascii  "SDAES MENU      "     /* 16 caractères */
        .byte   0xFF, 0xFF, 0xFF, 0xFF  /* pas de réglage de temps */
        .byte   0xFF, 0xFF              /* pas de compteur */
        .fill   10, 1, 0x00             /* aucune option */
