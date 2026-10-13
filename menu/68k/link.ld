/* Menu SDAES : ROM P en BRAM (32 Ko max), données en RAM de travail. */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)

MEMORY
{
    rom  (rx)  : ORIGIN = 0x000000, LENGTH = 32K
    wram (rwx) : ORIGIN = 0x100000, LENGTH = 0xF000   /* 0x10F000+ : BIOS */
}

SECTIONS
{
    .vectors 0x000000 : { KEEP(*(.vectors)) } > rom
    .header  0x000100 : { KEEP(*(.header)) } > rom
    .text    0x000400 : { *(.text .text.*) } > rom
    .rodata           : { *(.rodata .rodata.*) } > rom
    _data_load = .;
    .data : AT(_data_load) { _data_start = .; *(.data .data.*) _data_end = .; } > wram
    .bss (NOLOAD) : { _bss_start = .; *(.bss .bss.* COMMON) _bss_end = .; } > wram
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
