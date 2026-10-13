# Menu SDAES (programme 68000) - nécessite gcc-m68k-linux-gnu (ou m68k-elf-gcc)
CROSS  ?= m68k-linux-gnu-
CC      = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy
CFLAGS  = -m68000 -Os -ffreestanding -fno-builtin -nostdlib -fomit-frame-pointer \
          -fno-pic -fno-pie -Wall -Wextra -std=gnu99
LDFLAGS = -m68000 -nostdlib -static -no-pie -T link.ld -Wl,--build-id=none -Wl,-z,noexecstack

all: menu_p.bin

menu.elf: crt0.S menu.c link.ld ../../protocol/sdaes_mailbox.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ crt0.S menu.c -lgcc

menu_p.bin: menu.elf
	$(OBJCOPY) -O binary $< $@
	@ls -l $@

clean:
	rm -f menu.elf menu_p.bin

.PHONY: all clean
