# Simulation (Icarus Verilog) et vérification de synthèse (Yosys, ECP5)
#   make sim        : lance les deux bancs de test
#   make lint       : synthèse ECP5 des deux FPGA (sans placement-routage)
IVERILOG ?= iverilog
VVP      ?= vvp
YOSYS    ?= yosys
BUILD    ?= build

COMMON = common/sync2.v common/qlink.v common/sdram.v common/wr_packer.v \
         common/bram_dp.v common/sram_ctrl.v common/ecp5_pll.v
CHA    = cha/zmc2_dot.v cha/cha_core.v cha/cha_top.v
PROG   = prog/prog_core.v prog/prog_top.v

all: sim

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/tb_cha.vvp: sim/tb_cha.v sim/sdram_model.v sim/link_master.vh $(COMMON) $(CHA) | $(BUILD)
	$(IVERILOG) -g2005 -DSIMULATION -Isim -s tb_cha -o $@ sim/tb_cha.v sim/sdram_model.v $(COMMON) $(CHA)

$(BUILD)/tb_prog.vvp: sim/tb_prog.v sim/sdram_model.v sim/link_master.vh $(COMMON) $(PROG) | $(BUILD)
	$(IVERILOG) -g2005 -DSIMULATION -Isim -s tb_prog -o $@ sim/tb_prog.v sim/sdram_model.v $(COMMON) $(PROG)

sim: $(BUILD)/tb_cha.vvp $(BUILD)/tb_prog.vvp
	cd $(BUILD) && $(VVP) -n tb_cha.vvp  | grep -v "^VCD" | tee tb_cha.log  | grep -E "RESULTAT|ECHEC|latence"
	cd $(BUILD) && $(VVP) -n tb_prog.vvp | grep -v "^VCD" | tee tb_prog.log | grep -E "RESULTAT|ECHEC|latence"
	@grep -q "RESULTAT tb_cha : SUCCES" $(BUILD)/tb_cha.log && grep -q "RESULTAT tb_prog : SUCCES" $(BUILD)/tb_prog.log

# Les fichiers d'init BRAM du menu sont produits par le Makefile racine ;
# pour la vérification de synthèse on utilise des fichiers vides.
lint: | $(BUILD)
	for f in menu_s.hex menu_m1.hex menu_p_hi.hex menu_p_lo.hex; do [ -f $(BUILD)/$$f ] || : > $(BUILD)/$$f; done
	cd $(BUILD) && $(YOSYS) -q -p "read_verilog $(addprefix ../,$(COMMON) $(CHA)); synth_ecp5 -top cha_top -run begin:map_luts; tee -q -o lint_cha_stat.txt stat" > lint_cha.log
	cd $(BUILD) && $(YOSYS) -q -p "read_verilog $(addprefix ../,$(COMMON) $(PROG)); synth_ecp5 -top prog_top -run begin:map_luts; tee -q -o lint_prog_stat.txt stat" > lint_prog.log
	@echo "lint OK"

clean:
	rm -rf $(BUILD)

.PHONY: all sim lint clean
