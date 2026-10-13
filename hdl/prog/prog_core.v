// -----------------------------------------------------------------------------
// Cœur FPGA de la carte PROG (programme 68000 + échantillons ADPCM).
//
// Remplace sur la cartouche : ROM P (+ registre de banque), ROM V + NEO-PCM2
// (démultiplexage des adresses YM2610).
//
//   ROM P  -> SDRAM x16 n°1 (32 Mo)
//   ROM V  -> SDRAM x16 n°2 (32 Mo) : V1 (ADPCM-A) et V2 (ADPCM-B)
//   Menu   -> BRAM : programme 68000 du menu (32 Ko) + boîte aux lettres
//             (4 Ko) partagée avec le RP2350, mappée dans la zone 0x2xxxxx.
//
// Zone "port" 0x200000-0x2FFFFF en mode menu :
//   0x200000-0x200FFF  boîte aux lettres (miroirs jusqu'à 0x2FFFDF)
//   0x2FFFE0 (lecture) état  : bit0 = commande en attente côté RP2350,
//                              bit1 = jeu prêt (armé)
//   0x2FFFE0 (écriture)      sonnette : signale une commande au RP2350
//   0x2FFFE2 (écriture)      0x5A5A : bascule vers le jeu (si armé)
// En mode jeu : écriture dans 0x2FFFF0-0x2FFFFF = numéro de banque P2
// (schéma standard, actif si P > 2 Mo).
// -----------------------------------------------------------------------------
module prog_core #(
    parameter MENU_P_HI_INIT  = "",   // octets pairs (D15-D8) du menu
    parameter MENU_P_LO_INIT  = "",   // octets impairs (D7-D0)
    parameter SDRAM_INIT_WAIT = 27000,
    parameter SDRAM_REFI      = 1000
) (
    input  wire        clk,          // 133 MHz
    input  wire        rst,

    // --- bus 68000 (côté FPGA des translateurs) ---
    input  wire [19:1] a,
    input  wire [15:0] d_i,
    output wire [15:0] d_o,
    output wire        d_drive,      // 1 : translateurs D vers la console
    input  wire        romoe_n,      // lecture 0x000000-0x0FFFFF
    input  wire        portoe_n,     // lecture 0x200000-0x2FFFFF
    input  wire        portwel_n,    // écriture octet bas  0x2xxxxx
    input  wire        portweu_n,    // écriture octet haut 0x2xxxxx

    // --- bus YM2610 ADPCM-A (V1) ---
    input  wire [7:0]  rad_i,
    output wire [7:0]  rad_o,
    output wire        rad_drive,
    input  wire [9:8]  ra_l,         // SDRA8-9 (multiplexés)
    input  wire [23:20] ra_u,        // SDRA20-23
    input  wire        rmpx,
    input  wire        roe_n,
    // --- bus YM2610 ADPCM-B (V2) ---
    input  wire [7:0]  pad_i,
    output wire [7:0]  pad_o,
    output wire        pad_drive,
    input  wire [11:8] pa,           // SDPA8-11 (multiplexés)
    input  wire        pmpx,
    input  wire        poe_n,

    // --- liaison RP2350 ---
    input  wire        lk_sck,
    input  wire        lk_cs_n,
    input  wire [3:0]  lk_io_i,
    output wire [3:0]  lk_io_o,
    output wire        lk_io_oe,
    output wire        lk_irq,       // commande du menu en attente
    output wire        mode_out,     // vers la carte CHA

    // --- SDRAM P ---
    output wire        p_cke, p_cs_n, p_ras_n, p_cas_n, p_we_n,
    output wire [1:0]  p_ba,
    output wire [12:0] p_sa,
    output wire [1:0]  p_dqm,
    output wire [15:0] p_dq_o,
    output wire        p_dq_oe,
    input  wire [15:0] p_dq_i,
    // --- SDRAM V ---
    output wire        v_cke, v_cs_n, v_ras_n, v_cas_n, v_we_n,
    output wire [1:0]  v_ba,
    output wire [12:0] v_sa,
    output wire [1:0]  v_dqm,
    output wire [15:0] v_dq_o,
    output wire        v_dq_oe,
    input  wire [15:0] v_dq_i,

    output wire        led
);
    // =========================================================================
    // Liaison et registres
    // =========================================================================
    wire [7:0]  reg_addr;  wire reg_wr;  wire [31:0] reg_wdata;  reg [31:0] reg_rdata;
    wire        reg_rd;
    wire [7:0]  mem_space; wire [31:0] mem_addr; wire mem_wr; wire [7:0] mem_wdata;
    wire        mem_rd;    reg  [7:0]  mem_rdata; wire xfer_end;

    qlink u_link (
        .clk(clk), .rst(rst),
        .sck_i(lk_sck), .cs_n_i(lk_cs_n), .io_i(lk_io_i), .io_o(lk_io_o), .io_oe(lk_io_oe),
        .reg_addr(reg_addr), .reg_wr(reg_wr), .reg_wdata(reg_wdata), .reg_rdata(reg_rdata), .reg_rd(reg_rd),
        .mem_space(mem_space), .mem_addr(mem_addr), .mem_wr(mem_wr), .mem_wdata(mem_wdata),
        .mem_rd(mem_rd), .mem_rdata(mem_rdata), .xfer_end(xfer_end)
    );

    reg        ctrl_arm = 1'b0, ctrl_force = 1'b0, ctrl_bank_en = 1'b0;
    reg        game_mode = 1'b0;
    reg        irq = 1'b0;
    reg [23:0] p_mask  = 24'h07FFFF;     // en mots
    reg [24:0] v1_base = 25'h0, v2_base = 25'h0;   // en octets
    reg [24:0] v1_mask = 25'hFFFFF, v2_mask = 25'hFFFFF;
    reg [31:0] dbg_addr = 32'h0, dbg_data = 32'h0;
    reg        dbg_req = 1'b0, dbg_busy = 1'b0;
    reg [31:0] cnt_romoe = 0, cnt_portoe = 0, cnt_adpcm = 0;
    reg [7:0]  p_bank = 8'h00;

    wire p_init_done, v_init_done, p_idle, v_idle;
    wire pk_empty, pk_ovf, vk_empty, vk_ovf;

    // =========================================================================
    // Synchronisation du bus 68000
    // =========================================================================
    wire [18:0] a_s;
    wire [15:0] d_s;
    wire [3:0]  c_s;     // {portweu_n, portwel_n, portoe_n, romoe_n}
    sync2 #(.W(19)) u_sa (.clk(clk), .d(a), .q(a_s));
    sync2 #(.W(16)) u_sd (.clk(clk), .d(d_i), .q(d_s));
    sync2 #(.W(4), .INIT(4'hF)) u_sc (.clk(clk), .d({portweu_n, portwel_n, portoe_n, romoe_n}), .q(c_s));
    reg [3:0] c_d = 4'hF;
    always @(posedge clk) c_d <= c_s;
    wire rom_rd_ev  = ~c_s[0] & c_d[0];
    wire port_rd_ev = ~c_s[1] & c_d[1];
    wire wr_now     = ~c_s[2] | ~c_s[3];
    wire wr_ev      = wr_now & c_d[2] & c_d[3];
    wire rd_active  = ~c_s[0] | ~c_s[1];

    // adresses spéciales (A19..A4 tous à 1 sauf A4 -> 0x2FFFE0-0x2FFFEF)
    wire a_is_ctl  = (a_s[18:3] == 16'hFFFE);
    wire a_is_bank = (a_s[18:3] == 16'hFFFF);

    // =========================================================================
    // Registres de la liaison
    // =========================================================================
    always @(posedge clk) begin
        if (rst) begin
            ctrl_arm <= 1'b0; ctrl_force <= 1'b0; ctrl_bank_en <= 1'b0;
        end else if (reg_wr) begin
            case (reg_addr)
            8'h01: begin
                ctrl_arm     <= reg_wdata[0];
                ctrl_force   <= reg_wdata[1];
                ctrl_bank_en <= reg_wdata[3];
            end
            8'h03: p_mask  <= reg_wdata[23:0];
            8'h04: v1_base <= reg_wdata[24:0];
            8'h05: v1_mask <= reg_wdata[24:0];
            8'h06: v2_base <= reg_wdata[24:0];
            8'h07: v2_mask <= reg_wdata[24:0];
            8'h10: dbg_addr <= reg_wdata;
            default: ;
            endcase
        end
    end

    always @* begin
        case (reg_addr)
        8'h00: reg_rdata = 32'h4E475031;   // "NGP1"
        8'h01: reg_rdata = {28'd0, ctrl_bank_en, 1'b0, ctrl_force, ctrl_arm};
        8'h09: reg_rdata = {31'd0, irq};
        8'h02: reg_rdata = {24'd0, vk_ovf | pk_ovf, dbg_busy, irq, game_mode,
                            v_init_done, pk_empty & vk_empty & p_idle & v_idle, p_init_done & v_init_done, p_init_done};
        8'h03: reg_rdata = {8'd0, p_mask};
        8'h04: reg_rdata = {7'd0, v1_base};
        8'h05: reg_rdata = {7'd0, v1_mask};
        8'h06: reg_rdata = {7'd0, v2_base};
        8'h07: reg_rdata = {7'd0, v2_mask};
        8'h08: reg_rdata = {24'd0, p_bank};
        8'h10: reg_rdata = dbg_addr;
        8'h11: reg_rdata = dbg_data;
        8'h12: reg_rdata = cnt_romoe;
        8'h13: reg_rdata = cnt_portoe;
        8'h14: reg_rdata = cnt_adpcm;
        default: reg_rdata = 32'hDEADBEEF;
        endcase
    end

    // =========================================================================
    // BRAM : programme du menu (16 K mots) et boîte aux lettres (2 K mots)
    // =========================================================================
    // Programme menu : écrit par la liaison (espace 3, octets dans l'ordre
    // du 68000 : adresse paire = octet haut).
    reg  [13:0] mp_addr;
    wire [7:0]  mph_rd, mpl_rd, mph_ard, mpl_ard;
    wire mp_we_h = mem_wr && mem_space == 8'd3 && !mem_addr[0];
    wire mp_we_l = mem_wr && mem_space == 8'd3 &&  mem_addr[0];
    bram_dp #(.DW(8), .AW(14), .INIT(MENU_P_HI_INIT)) u_mp_h (
        .clk(clk), .a_we(mp_we_h), .a_addr(mem_addr[14:1]), .a_wdata(mem_wdata), .a_rdata(mph_ard),
        .b_addr(mp_addr), .b_rdata(mph_rd));
    bram_dp #(.DW(8), .AW(14), .INIT(MENU_P_LO_INIT)) u_mp_l (
        .clk(clk), .a_we(mp_we_l), .a_addr(mem_addr[14:1]), .a_wdata(mem_wdata), .a_rdata(mpl_ard),
        .b_addr(mp_addr), .b_rdata(mpl_rd));

    // Boîte aux lettres, deux zones à écrivain unique (mappage BRAM simple) :
    //   0x000-0x0FF : commande, écrite par le 68000, lue par la liaison
    //   0x100-0xFFF : réponse, écrite par la liaison, lue par le 68000
    reg  [10:0] mb_addr;
    reg         mb_we_h = 1'b0, mb_we_l = 1'b0;
    reg  [15:0] mb_wd;
    wire [7:0]  mbh_rd, mbl_rd, mrh_ard, mrl_ard, mch_rd, mcl_rd, mch_ard_unused, mcl_ard_unused;
    wire mrl_lk_we = mem_wr && mem_space == 8'd2 &&  mem_addr[0];
    wire mrh_lk_we = mem_wr && mem_space == 8'd2 && !mem_addr[0];
    // réponse : port A = liaison (lecture/écriture), port B = lecture 68000
    bram_dp #(.DW(8), .AW(11)) u_mr_h (
        .clk(clk), .a_we(mrh_lk_we), .a_addr(mem_addr[11:1]), .a_wdata(mem_wdata), .a_rdata(mrh_ard),
        .b_addr(mb_addr), .b_rdata(mbh_rd));
    bram_dp #(.DW(8), .AW(11)) u_mr_l (
        .clk(clk), .a_we(mrl_lk_we), .a_addr(mem_addr[11:1]), .a_wdata(mem_wdata), .a_rdata(mrl_ard),
        .b_addr(mb_addr), .b_rdata(mbl_rd));
    // commande : port A = écriture 68000, port B = lecture liaison
    bram_dp #(.DW(8), .AW(7)) u_mc_h (
        .clk(clk), .a_we(mb_we_h), .a_addr(mb_addr[6:0]), .a_wdata(mb_wd[15:8]), .a_rdata(mch_ard_unused),
        .b_addr(mem_addr[7:1]), .b_rdata(mch_rd));
    bram_dp #(.DW(8), .AW(7)) u_mc_l (
        .clk(clk), .a_we(mb_we_l), .a_addr(mb_addr[6:0]), .a_wdata(mb_wd[7:0]), .a_rdata(mcl_ard_unused),
        .b_addr(mem_addr[7:1]), .b_rdata(mcl_rd));
    wire [7:0] mbh_ard = (mem_addr[11:8] == 4'd0) ? mch_rd : mrh_ard;
    wire [7:0] mbl_ard = (mem_addr[11:8] == 4'd0) ? mcl_rd : mrl_ard;

    always @* begin
        case (mem_space)
        8'd2:    mem_rdata = mem_addr[0] ? mbl_ard : mbh_ard;
        8'd3:    mem_rdata = mem_addr[0] ? mpl_ard : mph_ard;
        default: mem_rdata = 8'hFF;
        endcase
    end

    // =========================================================================
    // Bus 68000 : lectures et écritures
    // =========================================================================
    reg  [15:0] p_dout = 16'hFFFF;
    reg         p_req = 1'b0;
    reg  [23:0] p_req_addr;
    wire        p_ack, p_rvalid;
    wire [15:0] p_rdata;
    reg  [2:0]  bus_st = 3'd0;
    reg         from_rom;

    // adresse SDRAM en mots
    //   0x000000-0x0FFFFF -> mots 0x000000-0x07FFFF
    //   0x200000-0x2FFFFF -> mots 0x080000 + banque * 0x80000 + A
    function [23:0] p_word(input rom, input [18:0] aa, input [7:0] bank);
        if (rom) p_word = {5'd0, aa};
        else     p_word = {5'd0, aa} + 24'h080000 + {bank, 19'd0};
    endfunction

    always @(posedge clk) begin
        mb_we_h <= 1'b0;
        mb_we_l <= 1'b0;
        if (rom_rd_ev)  cnt_romoe  <= cnt_romoe + 1;
        if (port_rd_ev) cnt_portoe <= cnt_portoe + 1;

        // acquittement de la requête par le RP2350 (écriture du registre 0x09)
        if (reg_wr && reg_addr == 8'h09) irq <= 1'b0;
        if (reg_wr && reg_addr == 8'h01 && !reg_wdata[0]) game_mode <= 1'b0;
        if (reg_wr && reg_addr == 8'h01 && reg_wdata[1])  game_mode <= 1'b1;

        if (rst) begin
            bus_st <= 3'd0; p_req <= 1'b0; game_mode <= 1'b0; irq <= 1'b0; p_bank <= 8'd0;
        end else case (bus_st)
        3'd0: begin
            if (rom_rd_ev || port_rd_ev) begin
                from_rom <= rom_rd_ev;
                if (game_mode) begin
                    p_req      <= 1'b1;
                    p_req_addr <= p_word(rom_rd_ev, a_s, p_bank) & p_mask;
                    bus_st     <= 3'd1;
                end else if (rom_rd_ev) begin
                    mp_addr <= a_s[13:0];
                    bus_st  <= 3'd2;
                end else if (a_is_ctl) begin
                    p_dout <= {14'd0, ctrl_arm, irq};
                end else begin
                    mb_addr <= a_s[10:0];
                    bus_st  <= 3'd4;
                end
            end else if (wr_ev) begin
                bus_st <= 3'd6;   // laisse D se stabiliser un cycle de plus
            end
        end
        // lecture SDRAM
        3'd1: begin
            if (p_ack) p_req <= 1'b0;
            if (p_rvalid) begin p_dout <= p_rdata; bus_st <= 3'd0; end
        end
        // lecture BRAM menu
        3'd2: bus_st <= 3'd3;
        3'd3: begin p_dout <= {mph_rd, mpl_rd}; bus_st <= 3'd0; end
        // lecture boîte aux lettres
        3'd4: bus_st <= 3'd5;
        3'd5: begin p_dout <= {mbh_rd, mbl_rd}; bus_st <= 3'd0; end
        // écriture
        3'd6: begin
            if (game_mode) begin
                if (a_is_bank && ctrl_bank_en && !c_s[2]) p_bank <= d_s[7:0];
            end else if (a_is_ctl) begin
                case (a_s[2:0])
                3'd0: irq <= 1'b1;                                     // 0x2FFFE0
                3'd1: if (d_s == 16'h5A5A && ctrl_arm) game_mode <= 1'b1; // 0x2FFFE2
                default: ;
                endcase
            end else begin
                mb_addr <= a_s[10:0];
                mb_wd   <= d_s;
                mb_we_h <= ~c_s[3] && a_s[10:7] == 4'd0;   // zone commande uniquement
                mb_we_l <= ~c_s[2] && a_s[10:7] == 4'd0;
            end
            bus_st <= 3'd7;
        end
        3'd7: if (!wr_now) bus_st <= 3'd0;   // attend la fin du cycle d'écriture
        endcase
    end

    assign d_o     = p_dout;
    // sens des translateurs : combinatoire depuis les broches
    assign d_drive = ~romoe_n | ~portoe_n;
    assign mode_out = game_mode;
    assign lk_irq   = irq;

    // =========================================================================
    // SDRAM P : lectures 68000 (mode jeu) / écritures du chargeur (mode menu)
    // =========================================================================
    wire        pk_valid;  wire [23:0] pk_addr; wire [15:0] pk_data; wire [1:0] pk_mask;
    reg         pk_take;
    wire ld_p = mem_wr && mem_space == 8'd0 && !game_mode;
    wr_packer #(.DW(16), .AW(24), .DEPTH(16)) u_pk_p (
        .clk(clk), .rst(rst), .in_stb(ld_p), .in_addr(mem_addr), .in_data(mem_wdata), .flush(xfer_end),
        .out_valid(pk_valid), .out_addr(pk_addr), .out_data(pk_data), .out_mask(pk_mask),
        .out_take(pk_take), .empty(pk_empty), .overflow(pk_ovf));

    reg         ps_req = 1'b0, ps_we = 1'b0;
    reg  [23:0] ps_addr;
    reg  [15:0] ps_wdata;
    reg  [1:0]  ps_wmask;
    reg  [1:0]  ps_st = 2'd0;    // 0 libre, 1 lecture 68k, 2 écriture, 3 diag
    wire        ps_ack, ps_rvalid, ps_rvalid2;
    wire [15:0] ps_rdata, ps_rdata2;

    reg dbg_v_req = 1'b0;
    always @(posedge clk) begin
        pk_take <= 1'b0;
        if (reg_wr && reg_addr == 8'h10) begin
            dbg_busy <= 1'b1;
            if (reg_wdata[31]) dbg_v_req <= 1'b1; else dbg_req <= 1'b1;
        end
        if (rst) begin ps_st <= 2'd0; ps_req <= 1'b0; dbg_req <= 1'b0; dbg_v_req <= 1'b0; dbg_busy <= 1'b0; end
        else case (ps_st)
        2'd0: begin
            if (game_mode && p_req) begin
                ps_req <= 1'b1; ps_we <= 1'b0; ps_addr <= p_req_addr; ps_st <= 2'd1;
            end else if (!game_mode && pk_valid) begin
                ps_req <= 1'b1; ps_we <= 1'b1; ps_addr <= pk_addr;
                ps_wdata <= pk_data; ps_wmask <= pk_mask; pk_take <= 1'b1; ps_st <= 2'd2;
            end else if (!game_mode && dbg_req) begin
                dbg_req <= 1'b0;
                ps_req <= 1'b1; ps_we <= 1'b0; ps_addr <= dbg_addr[23:0]; ps_st <= 2'd3;
            end
        end
        2'd1: begin
            if (ps_ack) ps_req <= 1'b0;
            if (ps_rvalid) ps_st <= 2'd0;
        end
        2'd2: if (ps_ack) begin ps_req <= 1'b0; ps_st <= 2'd0; end
        2'd3: begin
            if (ps_ack) ps_req <= 1'b0;
            if (ps_rvalid) begin dbg_data <= {16'd0, ps_rdata}; dbg_busy <= 1'b0; ps_st <= 2'd0; end
        end
        endcase
        if (vs_dbg_done) begin dbg_data <= {16'd0, vs_rdata}; dbg_busy <= 1'b0; end
        if (vs_dbg_take) dbg_v_req <= 1'b0;
    end
    assign p_ack    = (ps_st == 2'd1) && ps_ack;
    assign p_rvalid = (ps_st == 2'd1) && ps_rvalid;
    assign p_rdata  = ps_rdata;

    // Rafraîchissement : uniquement juste après une lecture 68000 (le cycle
    // suivant arrive au plus tôt ~250 ns plus tard) ou après 1 us sans lecture.
    // Ainsi un rafraîchissement ne retarde jamais une lecture du programme.
    reg [7:0] since_p = 8'hFF;
    always @(posedge clk) begin
        if (ps_st == 2'd1 && ps_rvalid)    since_p <= 8'd0;
        else if (rom_rd_ev || port_rd_ev)  since_p <= 8'd200;
        else if (since_p != 8'hFF)         since_p <= since_p + 8'd1;
    end
    wire p_ref_ok = (since_p < 8'd12) || (since_p > 8'd133 && since_p < 8'd200) || since_p == 8'hFF;
    sdram #(.DW(16), .INIT_WAIT(SDRAM_INIT_WAIT), .REFI(SDRAM_REFI)) u_sdram_p (
        .clk(clk), .rst(rst),
        .req(ps_req), .we(ps_we), .addr(ps_addr), .dual(1'b0), .col2(9'd0),
        .wdata(ps_wdata), .wmask(ps_wmask), .ack(ps_ack),
        .rvalid(ps_rvalid), .rdata(ps_rdata), .rvalid2(ps_rvalid2), .rdata2(ps_rdata2),
        .refresh_hold(game_mode && (p_req || !p_ref_ok)), .init_done(p_init_done), .idle(p_idle),
        .sd_cke(p_cke), .sd_cs_n(p_cs_n), .sd_ras_n(p_ras_n), .sd_cas_n(p_cas_n), .sd_we_n(p_we_n),
        .sd_ba(p_ba), .sd_a(p_sa), .sd_dqm(p_dqm), .sd_dq_o(p_dq_o), .sd_dq_oe(p_dq_oe), .sd_dq_i(p_dq_i));

    // =========================================================================
    // ADPCM : démultiplexage des adresses (rôle du NEO-PCM2)
    // =========================================================================
    // Front montant de *MPX : partie basse ; front descendant : partie haute.
    reg [9:0]  ra_lo = 0, ra_hi = 0;
    reg [11:0] pa_lo = 0, pa_hi = 0;
    always @(posedge rmpx) ra_lo <= {ra_l, rad_i};
    always @(negedge rmpx) ra_hi <= {ra_l, rad_i};
    always @(posedge pmpx) pa_lo <= {pa, pad_i};
    always @(negedge pmpx) pa_hi <= {pa, pad_i};
    wire [23:0] adpcm_a_addr = {ra_u, ra_hi, ra_lo};
    wire [23:0] adpcm_b_addr = {pa_hi, pa_lo};

    wire [1:0] voe_s;
    sync2 #(.W(2), .INIT(2'b11)) u_svoe (.clk(clk), .d({poe_n, roe_n}), .q(voe_s));
    reg  [1:0] voe_d = 2'b11;
    always @(posedge clk) voe_d <= voe_s;
    wire a_ev = ~voe_s[0] & voe_d[0];
    wire b_ev = ~voe_s[1] & voe_d[1];

    reg  [7:0] rad_dout = 8'h00, pad_dout = 8'h00;
    reg        a_pend = 1'b0, b_pend = 1'b0;

    wire        vk_valid;  wire [23:0] vk_addr; wire [15:0] vk_data; wire [1:0] vk_mask;
    reg         vk_take;
    wire ld_v = mem_wr && mem_space == 8'd1 && !game_mode;
    wr_packer #(.DW(16), .AW(24), .DEPTH(16)) u_pk_v (
        .clk(clk), .rst(rst), .in_stb(ld_v), .in_addr(mem_addr), .in_data(mem_wdata), .flush(xfer_end),
        .out_valid(vk_valid), .out_addr(vk_addr), .out_data(vk_data), .out_mask(vk_mask),
        .out_take(vk_take), .empty(vk_empty), .overflow(vk_ovf));

    reg         vs_req = 1'b0, vs_we = 1'b0;
    reg  [23:0] vs_addr;
    reg  [15:0] vs_wdata;
    reg  [1:0]  vs_wmask;
    reg  [2:0]  vs_st = 3'd0;    // 0 libre, 1 lecture A, 2 lecture B, 3 écriture, 4 diag
    reg         vs_lane;
    wire        vs_ack, vs_rvalid, vs_rvalid2;
    wire [15:0] vs_rdata, vs_rdata2;
    wire        vs_dbg_take = (vs_st == 3'd0) && !game_mode && dbg_v_req && !vk_valid;
    wire        vs_dbg_done = (vs_st == 3'd4) && vs_rvalid;
    reg  [24:0] vba;

    always @(posedge clk) begin
        vk_take <= 1'b0;
        if (a_ev) a_pend <= 1'b1;
        if (b_ev) b_pend <= 1'b1;
        if (rst) begin vs_st <= 3'd0; vs_req <= 1'b0; a_pend <= 1'b0; b_pend <= 1'b0; end
        else case (vs_st)
        3'd0: begin
            if (game_mode && (a_pend || a_ev)) begin
                a_pend <= 1'b0;
                cnt_adpcm <= cnt_adpcm + 1;
                vba = v1_base + ({1'b0, adpcm_a_addr} & v1_mask);
                vs_lane <= vba[0];
                vs_req <= 1'b1; vs_we <= 1'b0; vs_addr <= vba[24:1]; vs_st <= 3'd1;
            end else if (game_mode && (b_pend || b_ev)) begin
                b_pend <= 1'b0;
                vba = v2_base + ({1'b0, adpcm_b_addr} & v2_mask);
                vs_lane <= vba[0];
                vs_req <= 1'b1; vs_we <= 1'b0; vs_addr <= vba[24:1]; vs_st <= 3'd2;
            end else if (!game_mode && vk_valid) begin
                vs_req <= 1'b1; vs_we <= 1'b1; vs_addr <= vk_addr;
                vs_wdata <= vk_data; vs_wmask <= vk_mask; vk_take <= 1'b1; vs_st <= 3'd3;
            end else if (vs_dbg_take) begin
                vs_req <= 1'b1; vs_we <= 1'b0; vs_addr <= dbg_addr[23:0]; vs_st <= 3'd4;
            end
            if (!game_mode) begin a_pend <= 1'b0; b_pend <= 1'b0; end
        end
        3'd1, 3'd2: begin
            if (vs_ack) vs_req <= 1'b0;
            if (vs_rvalid) begin
                if (vs_st == 3'd1) rad_dout <= vs_lane ? vs_rdata[15:8] : vs_rdata[7:0];
                else               pad_dout <= vs_lane ? vs_rdata[15:8] : vs_rdata[7:0];
                vs_st <= 3'd0;
            end
        end
        3'd3: if (vs_ack) begin vs_req <= 1'b0; vs_st <= 3'd0; end
        3'd4: begin
            if (vs_ack) vs_req <= 1'b0;
            if (vs_rvalid) vs_st <= 3'd0;
        end
        default: vs_st <= 3'd0;
        endcase
    end

    sdram #(.DW(16), .INIT_WAIT(SDRAM_INIT_WAIT), .REFI(SDRAM_REFI)) u_sdram_v (
        .clk(clk), .rst(rst),
        .req(vs_req), .we(vs_we), .addr(vs_addr), .dual(1'b0), .col2(9'd0),
        .wdata(vs_wdata), .wmask(vs_wmask), .ack(vs_ack),
        .rvalid(vs_rvalid), .rdata(vs_rdata), .rvalid2(vs_rvalid2), .rdata2(vs_rdata2),
        .refresh_hold(1'b0), .init_done(v_init_done), .idle(v_idle),
        .sd_cke(v_cke), .sd_cs_n(v_cs_n), .sd_ras_n(v_ras_n), .sd_cas_n(v_cas_n), .sd_we_n(v_we_n),
        .sd_ba(v_ba), .sd_a(v_sa), .sd_dqm(v_dqm), .sd_dq_o(v_dq_o), .sd_dq_oe(v_dq_oe), .sd_dq_i(v_dq_i));

    assign rad_o     = rad_dout;
    assign pad_o     = pad_dout;
    assign rad_drive = ~roe_n;
    assign pad_drive = ~poe_n;

    assign led = game_mode ^ (~pk_empty | ~vk_empty);
endmodule

