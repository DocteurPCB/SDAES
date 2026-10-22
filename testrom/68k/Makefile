# ROM de test SDAES (programme 68000) - nécessite gcc-m68k-linux-gnu (ou m68k-elf-gcc)
CROSS  ?= m68k-linux-gnu-
CC      = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy
CFLAGS  = -m68000 -Os -ffreestanding -fno-builtin -nostdlib -fomit-frame-pointer \
          -fno-pic -fno-pie -Wall -Wextra -std=gnu99
LDFLAGS = -m68000 -nostdlib -static -no-pie -T link.ld -Wl,--build-id=none -Wl,-z,noexecstack

all: test_p.bin

test.elf: crt0.S test.c link.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ crt0.S test.c -lgcc

test_p.bin: test.elf
	$(OBJCOPY) -O binary $< $@
	python3 ../../tools/neotool.py romsum $@ -o $@
	@ls -l $@

clean:
	rm -f test.elf test_p.bin

.PHONY: all clean
