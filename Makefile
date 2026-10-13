# SDAES - construction et tests
#
#   make            : menu (ROM P/S/M1) + fichiers d'init BRAM pour les FPGA
#   make test       : tests Python (outils + firmware sur PC) et simulations HDL
#   make menu.neo   : menu empaqueté en .neo (essai dans un émulateur)
#
# Variables :
#   FONT=...            police PSF 8x8 (défaut : police console Lat15-VGA8)
#   SECURITY_FROM=x.neo jeu dont on recopie le code de sécurité (obligatoire
#                       pour que le BIOS accepte le menu sur une vraie console)
FONT          ?= /usr/share/consolefonts/Lat15-VGA8.psf.gz
SECURITY_FROM ?=
PYTHON        ?= python3
BUILD          = build
HDLBUILD       = hdl/build
NEOTOOL        = $(PYTHON) tools/neotool.py

all: bram

$(BUILD) $(HDLBUILD):
	mkdir -p $@

$(BUILD)/menu_m1.bin: menu/z80/driver.asm | $(BUILD)
	z80asm -o $@ $<

$(BUILD)/menu_s.bin: tools/neotool.py | $(BUILD)
	$(NEOTOOL) font $(FONT) -o $@

menu/68k/menu_p.bin: FORCE
	$(MAKE) -C menu/68k

$(BUILD)/menu_p.bin: menu/68k/menu_p.bin | $(BUILD)
ifeq ($(SECURITY_FROM),)
	@echo "ATTENTION : SECURITY_FROM non défini, le menu n'aura pas de code de sécurité"
	cp $< $@
else
	$(NEOTOOL) security $< $(SECURITY_FROM) -o $@
endif

bram: $(BUILD)/menu_p.bin $(BUILD)/menu_s.bin $(BUILD)/menu_m1.bin | $(HDLBUILD)
	$(NEOTOOL) bramhex16 $(BUILD)/menu_p.bin --hi $(HDLBUILD)/menu_p_hi.hex --lo $(HDLBUILD)/menu_p_lo.hex --size 8192
	$(NEOTOOL) bramhex $(BUILD)/menu_s.bin  -o $(HDLBUILD)/menu_s.hex  --size 8192
	$(NEOTOOL) bramhex $(BUILD)/menu_m1.bin -o $(HDLBUILD)/menu_m1.hex --size 2048

menu.neo: $(BUILD)/menu_p.bin $(BUILD)/menu_s.bin $(BUILD)/menu_m1.bin
	$(NEOTOOL) build -o $(BUILD)/$@ --p $(BUILD)/menu_p.bin --p-swap --s $(BUILD)/menu_s.bin \
	    --m $(BUILD)/menu_m1.bin --name "SDAES MENU" --manu "SDAES" --ngh 0xFFE

test:
	$(PYTHON) -m unittest discover -s tools/tests -v
	$(MAKE) -C hdl sim

clean:
	rm -rf $(BUILD)
	$(MAKE) -C menu/68k clean
	$(MAKE) -C hdl clean

.PHONY: all bram test clean FORCE
