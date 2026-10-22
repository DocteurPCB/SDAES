/* ---------------------------------------------------------------------------
 * Démarrage de la ROM de test SDAES : table des vecteurs, en-tête cartouche
 * Neo Geo, points d'entrée appelés par le BIOS (même schéma que le menu).
 *
 * Comme pour le menu, la zone du code de sécurité (0x186-0x3FF) est remplie
 * à la construction par tools/neotool.py (commande "security").
 * ------------------------------------------------------------------------- */

        .set BIOS_SYSTEM_MODE,  0x10FD80
        .set BIOS_USER_REQUEST, 0x10FDAE
        .set SYSTEM_RETURN,     0xC00444
        .set SYSTEM_INT1,       0xC00438
        .set REG_IRQACK,        0x3C000C

        .section .vectors, "ax"
        .global _rom_start
_rom_start:
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
        .word   0x0FFD                  /* 0x108 : numéro NGH de la ROM de test */
        .long   0x00010000              /* 0x10A : taille du programme */
        .long   0x0010E000              /* 0x10E : sauvegarde (inutilisée) */
        .word   0x0000                  /* 0x112 : taille sauvegarde */
        .byte   0x02                    /* 0x114 : pas d'animation d'intro */
        .byte   0x00                    /* 0x115 */
        .long   softdips                /* 0x116 : réglages JP */
        .long   softdips                /* 0x11A : réglages US */
        .long   softdips                /* 0x11E : réglages EU */
        .word   0x4EF9
        .long   user                    /* 0x122 : USER */
        .word   0x4EF9
        .long   player_start            /* 0x128 : PLAYER_START */
        .word   0x4EF9
        .long   demo_end                /* 0x12E : DEMO_END */
        .word   0x4EF9
        .long   coin_sound              /* 0x134 : COIN_SOUND */
        .global rom_sum_slot
rom_sum_slot:
        .word   0xFFFF                  /* 0x13A : somme de la ROM (neotool romsum) */
        .fill   0x182 - 0x13C, 1, 0xFF
        .long   0x00000186              /* 0x182 : pointeur code de sécurité */
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
5:      jsr     test_main               /* ne revient pas */
        bra.s   1b

player_start:
demo_end:
coin_sound:
        rts

irq_vblank:
        btst    #7, BIOS_SYSTEM_MODE
        bne.s   1f
        jmp     SYSTEM_INT1
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

        .section .rodata
softdips:
        .ascii  "SDAES TEST      "     /* 16 caractères */
        .byte   0xFF, 0xFF, 0xFF, 0xFF
        .byte   0xFF, 0xFF
        .fill   10, 1, 0x00
