; -----------------------------------------------------------------------------
; Pilote Z80 minimal du menu SDAES (ROM M1 du menu, en BRAM sur la carte CHA)
;
; Rôle : répondre aux commandes du BIOS/68000 pour que le démarrage se passe
; normalement. Aucun son n'est produit.
;   commande 0x01 (préparation changement de slot) : passe en RAM, répond 0x01
;   commande 0x03 (reset logiciel)                 : redémarre en 0x0000
;   commande 0x7F (SDAES : parking avant bascule)  : passe en RAM, répond 0x7F
;   autre                                          : renvoie la commande
; Assembleur : z80asm (paquet Debian/Ubuntu "z80asm").
; -----------------------------------------------------------------------------

PORT_FROM_68K:  equ 0x00
PORT_TO_68K:    equ 0x0C
PORT_NMI_ON:    equ 0x08
PORT_NMI_OFF:   equ 0x18
RAM_LOOP:       equ 0xF800

        org 0x0000
        di
        im 1
        ld sp, 0xFFFC
        jp start

        defs 0x0038 - $, 0x00
irq:    ei                      ; IRQ du YM2610 : ignorée
        reti

        defs 0x0066 - $, 0x00
nmi:    push af
        in a, (PORT_FROM_68K)
        cp 0x01
        jr z, park
        cp 0x7F
        jr z, park
        cp 0x03
        jr z, soft_reset
        out (PORT_TO_68K), a
        pop af
        retn

park:   out (PORT_TO_68K), a
        ; boucle "jr $" en RAM : plus aucun accès à la ROM M1
        ld a, 0x18
        ld (RAM_LOOP), a
        ld a, 0xFE
        ld (RAM_LOOP + 1), a
        pop af
        ld sp, 0xFFFC
        jp RAM_LOOP

soft_reset:
        out (PORT_TO_68K), a
        pop af
        jp 0x0000

start:  xor a
        out (PORT_TO_68K), a
        out (PORT_NMI_ON), a    ; autorise les NMI (commandes du 68000)
main:   jr main
