# Simulation (Icarus Verilog), synthèse et placement-routage iCE40 HX8K-TQ144
#   make sim     : bancs de test des cartes PROG (P+V) et CHA (C+SM)
#   make lint    : synthèse Yosys des 4 FPGA
#   make pnr     : placement-routage nextpnr (broches non affectées), rapport de fréquence
#   make bits    : bitstreams (nécessite les .pcf complétés dans ../hardware)
IVERILOG ?= iverilog
VVP      ?= vvp
YOSYS    ?= yosys
NEXTPNR  ?= nextpnr-ice40
ICEPACK  ?= icepack
BUILD    ?= build

COMMON = common/sync2.v common/qlink.v common/sdram.v common/wr_packer.v \
         common/bram_dp.v common/sram_ctrl.v common/ice40_prims.v
SRC_prog_p_top = prog/p_mapper.v prog/prog_p_core.v prog/prog_p_top.v
SRC_prog_v_top = prog/prog_v_core.v prog/prog_v_top.v
SRC_cha_c_top  = cha/zmc2_dot.v cha/cha_c_core.v cha/cha_c_top.v
SRC_cha_sm_top = cha/cmc_fix.v cha/cha_sm_core.v cha/cha_sm_top.v
TOPS = prog_p_top prog_v_top cha_c_top cha_sm_top
HEX  = $(BUILD)/menu_s.hex $(BUILD)/menu_m1.hex $(BUILD)/menu_p_hi.hex $(BUILD)/menu_p_lo.hex

all: sim

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/tb_cha.vvp: sim/tb_cha.v sim/sdram_model.v sim/link_master.vh $(COMMON) $(SRC_cha_c_top) $(SRC_cha_sm_top) | $(BUILD)
	$(IVERILOG) -g2005 -DSIMULATION -Isim -s tb_cha -o $@ sim/tb_cha.v sim/sdram_model.v $(COMMON) $(SRC_cha_c_top) $(SRC_cha_sm_top)

$(BUILD)/tb_prog.vvp: sim/tb_prog.v sim/sdram_model.v sim/link_master.vh $(COMMON) $(SRC_prog_p_top) $(SRC_prog_v_top) | $(BUILD)
	$(IVERILOG) -g2005 -DSIMULATION -Isim -s tb_prog -o $@ sim/tb_prog.v sim/sdram_model.v $(COMMON) $(SRC_prog_p_top) $(SRC_prog_v_top)

sim: $(BUILD)/tb_cha.vvp $(BUILD)/tb_prog.vvp
	cd $(BUILD) && $(VVP) -n tb_cha.vvp  | grep -v "^VCD" | tee tb_cha.log  | grep -E "RESULTAT|ECHEC|info"
	cd $(BUILD) && $(VVP) -n tb_prog.vvp | grep -v "^VCD" | tee tb_prog.log | grep -E "RESULTAT|ECHEC|info"
	@grep -q "RESULTAT tb_cha : SUCCES" $(BUILD)/tb_cha.log && grep -q "RESULTAT tb_prog : SUCCES" $(BUILD)/tb_prog.log

# Fichiers d'init BRAM : produits par le Makefile racine ; vides à défaut.
$(HEX): | $(BUILD)
	[ -f $@ ] || : > $@

.SECONDEXPANSION:
$(BUILD)/%.json: $(HEX) $(COMMON) $$(SRC_$$*)
	cd $(BUILD) && $(YOSYS) -q -p "read_verilog $(addprefix ../,$(COMMON) $(SRC_$*)); synth_ice40 -top $* -json $*.json; tee -q -o $*_stat.txt stat" > $*_synth.log

lint: $(addprefix $(BUILD)/,$(addsuffix .json,$(TOPS)))
	@for t in $(TOPS); do echo "== $$t"; grep -E "SB_LUT4|SB_DFF|SB_RAM40|SB_IO |SB_PLL|SB_CARRY" $(BUILD)/$${t}_stat.txt | awk '{s[$$2]+=$$1} END {for (k in s) printf "   %-14s %d\n", k, s[k]}'; done

# Placement-routage sans contraintes de broches (estimation de fréquence) :
# essaie plusieurs graines et garde la première qui tient 100 MHz.
SEEDS ?= 1 2 3 4 5
$(BUILD)/%.asc: $(BUILD)/%.json
	cd $(BUILD) && for s in $(SEEDS); do \
	    $(NEXTPNR) --hx8k --package tq144:4k --json $*.json --asc $*.asc --freq 100 \
	        --pcf-allow-unconstrained --ignore-rel-clk --seed $$s > $*_pnr.log 2>&1 && break; \
	done; grep -q "PASS at 100" $*_pnr.log || (tail -5 $*_pnr.log; false)

pnr: $(addprefix $(BUILD)/,$(addsuffix .asc,$(TOPS)))
	@for t in $(TOPS); do echo "== $$t"; grep -E "Max frequency for clock +'clk'|ICESTORM_LC:|ICESTORM_RAM:|SB_IO:" $(BUILD)/$${t}_pnr.log | tail -4; done

# Bitstreams définitifs : nécessite les numéros de broches dans ../hardware/*.pcf
PCF_prog_p_top = ../hardware/prog_p.pcf
PCF_prog_v_top = ../hardware/prog_v.pcf
PCF_cha_c_top  = ../hardware/cha_c.pcf
PCF_cha_sm_top = ../hardware/cha_sm.pcf
$(BUILD)/%.bin: $(BUILD)/%.json
	cd $(BUILD) && $(NEXTPNR) --hx8k --package tq144:4k --json $*.json --pcf $(PCF_$*) \
	    --asc $*_final.asc --freq 100 --ignore-rel-clk > $*_final.log 2>&1 && $(ICEPACK) $*_final.asc $*.bin

bits: $(addprefix $(BUILD)/,$(addsuffix .bin,$(TOPS)))

clean:
	rm -rf $(BUILD)

.PHONY: all sim lint pnr bits clean
