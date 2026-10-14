// -----------------------------------------------------------------------------
// FPGA "P" de la carte PROG : programme 68000.
//
// Remplace la ROM P (+ registre de banque). Contient aussi le menu (BRAM) et
// la boîte aux lettres partagée avec le RP2350, et commande la bascule
// menu/jeu (sortie MODE vers les trois autres FPGA).
//
// Zone "port" 0x200000-0x2FFFFF en mode menu :
//   0x200000-0x2000FF  commande (écrite par le 68000)
//   0x200100-0x200FFF  réponse  (lue par le 68000), miroirs jusqu'à 0x2FFFDF
//   0x2FFFE0 lecture   : bit0 = commande en attente, bit1 = jeu armé
//   0x2FFFE0 écriture  : sonnette (LK_IRQ)
//   0x2FFFE2 écriture  : 0x5A5A = bascule vers le jeu (si armé)
// En mode jeu : écriture dans 0x2FFFF0-0x2FFFFF = banque P2 (si P > 2 Mo).
//
// Lecture anticipée : dès que l'adresse 68000 change (et se stabilise), les
// deux mots possibles (zone P1 et zone P2 banquée) sont lus en parallèle dans
// deux banques SDRAM. Quand /ROMOE ou /PORTOE arrive, la donnée est en
// général déjà prête ; sinon une lecture normale est faite.
// -----------------------------------------------------------------------------
`ifndef SDAES_VERSION
`define SDAES_VERSION 32'd0
`endif

module prog_p_core #(
    parameter MENU_P_HI_INIT  = "",
    parameter MENU_P_LO_INIT  = "",
    parameter MENU_AW         = 12,       // 4 K mots = 8 Ko
    parameter SDRAM_INIT_WAIT = 20000,
    parameter SDRAM_REFI      = 780
) (
    input  wire        clk,               // 100 MHz
    input  wire        rst,

    input  wire [19:1] a,
    input  wire [15:0] d_i,
    output wire [15:0] d_o,
    output wire        d_drive,
    input  wire        romoe_n,
    input  wire        portoe_n,
    input  wire        portwel_n,
    input  wire        portweu_n,
    output wire [2:0]  wait_n,            // {PWAIT1, PWAIT0, ROMWAIT}, actifs à 0

    input  wire        lk_sck,
    input  wire        lk_cs_n,
    input  wire [3:0]  lk_io_i,
    output wire [3:0]  lk_io_o,
    output wire        lk_io_oe,
    output wire        lk_irq,
    output wire        mode_out,

    output wire        sd_cke, sd_cs_n, sd_ras_n, sd_cas_n, sd_we_n,
    output wire [1:0]  sd_ba,
    output wire [12:0] sd_a,
    output wire [1:0]  sd_dqm,
    output wire [15:0] sd_dq_o,
    output wire        sd_dq_oe,
    input  wire [15:0] sd_dq_i,

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

    reg        ctrl_arm = 1'b0, ctrl_bank_en = 1'b0;
    reg        game_mode = 1'b0;
    reg        irq = 1'b0;
    reg [23:0] p_mask = 24'h07FFFF;      // en mots
    reg [2:0]  wait_cfg = 3'b111;        // pleine vitesse (cf. wiki neogeodev « Wait cycle »)
    reg [23:0] dbg_addr = 24'h0;
    reg [15:0] dbg_data = 16'h0;
    reg        dbg_req = 1'b0, dbg_busy = 1'b0;
    reg [15:0] cnt_romoe = 0, cnt_portoe = 0, cnt_spec_hit = 0;
    wire [31:0] map_rdata;

    wire sd_init_done, sd_idle, pk_empty, pk_ovf;

    always @(posedge clk) begin
        if (rst) begin
            ctrl_arm <= 1'b0; ctrl_bank_en <= 1'b0;
        end else if (reg_wr) begin
            case (reg_addr)
            8'h01: begin ctrl_arm <= reg_wdata[0]; ctrl_bank_en <= reg_wdata[3]; end
            8'h03: p_mask   <= reg_wdata[23:0];
            8'h04: wait_cfg <= reg_wdata[2:0];
            8'h10: dbg_addr <= reg_wdata[23:0];
            default: ;
            endcase
        end
    end

    always @* begin
        case (reg_addr)
        8'h00: reg_rdata = 32'h4E475032;   // "NGP2"
        8'h0F: reg_rdata = `SDAES_VERSION;   // version du bitstream (make VERSION=)
        8'h01: reg_rdata = {28'd0, ctrl_bank_en, 2'b00, ctrl_arm};
        8'h02: reg_rdata = {25'd0, pk_ovf, dbg_busy, irq, game_mode, pk_empty & sd_idle, sd_init_done, sd_init_done};
        8'h03: reg_rdata = {8'd0, p_mask};
        8'h04: reg_rdata = {29'd0, wait_cfg};
        8'h08, 8'h0A, 8'h0C: reg_rdata = map_rdata;
        8'h09: reg_rdata = {31'd0, irq};
        8'h10: reg_rdata = {8'd0, dbg_addr};
        8'h11: reg_rdata = {16'd0, dbg_data};
        8'h12: reg_rdata = {16'd0, cnt_romoe};
        8'h13: reg_rdata = {16'd0, cnt_portoe};
        8'h14: reg_rdata = {16'd0, cnt_spec_hit};
        default: reg_rdata = 32'hDEADBEEF;
        endcase
    end

    // =========================================================================
    // Synchronisation du bus 68000
    // =========================================================================
    // Adresse et données : un seul registre d'entrée suffit, car elles ne
    // sont utilisées qu'une fois stables (same_r). Signaux de
    // commande : synchroniseur à 2 bascules.
    reg  [18:0] a_s = 19'h0, a_d = 19'h0;
    reg  [15:0] d_s = 16'h0;
    wire [3:0]  c_s;     // {portweu_n, portwel_n, portoe_n, romoe_n}
    sync2 #(.W(4), .INIT(4'hF)) u_sc (.clk(clk), .d({portweu_n, portwel_n, portoe_n, romoe_n}), .q(c_s));
    reg  [3:0]  c_d = 4'hF;
    reg         same_r = 1'b0;
    always @(posedge clk) begin
        a_s    <= a;
        d_s    <= d_i;
        a_d    <= a_s;
        c_d    <= c_s;
        same_r <= (a_s == a_d);
    end
    // événements de lecture retardés d'un cycle : alignés sur same_r
    reg  rom_rd_ev = 1'b0, port_rd_ev = 1'b0;
    always @(posedge clk) begin
        rom_rd_ev  <= ~c_s[0] & c_d[0];
        port_rd_ev <= ~c_s[1] & c_d[1];
    end
    wire wr_now     = ~c_s[2] | ~c_s[3];
    wire wr_ev      = wr_now & c_d[2] & c_d[3];

    // décodage des adresses spéciales, registré (l'adresse est stable bien
    // avant l'événement de lecture/écriture correspondant)
    reg a_is_ctl = 1'b0;                        // 0x2FFFE0-0x2FFFEF (mode menu)
    always @(posedge clk) a_is_ctl <= (a_s[18:3] == 16'hFFFE);

    // adresse SDRAM en mots
    //   0x000000-0x0FFFFF -> A
    //   0x200000-0x2FFFFF -> p2_base_w + A  (fenêtre P2, fixée par le mapper)
    //   RAM PVC (0x2FE000-0x2FFFDF) -> PVC_RAM_W + index, hors masque
    localparam [23:0] PVC_RAM_W = 24'hC7F000;   // 8 derniers Ko de la banque SDRAM 3

    // =========================================================================
    // BRAM : programme du menu et boîte aux lettres
    // =========================================================================
    reg  [MENU_AW-1:0] mp_addr;
    wire [7:0] mph_rd, mpl_rd;
    bram_dp #(.DW(8), .AW(MENU_AW), .INIT(MENU_P_HI_INIT)) u_mp_h (
        .clk(clk), .a_we(mem_wr && mem_space == 8'd3 && !mem_addr[0]),
        .a_addr(mem_addr[MENU_AW:1]), .a_wdata(mem_wdata),
        .b_addr(mp_addr), .b_rdata(mph_rd));
    bram_dp #(.DW(8), .AW(MENU_AW), .INIT(MENU_P_LO_INIT)) u_mp_l (
        .clk(clk), .a_we(mem_wr && mem_space == 8'd3 &&  mem_addr[0]),
        .a_addr(mem_addr[MENU_AW:1]), .a_wdata(mem_wdata),
        .b_addr(mp_addr), .b_rdata(mpl_rd));

    // réponse : écrite par la liaison, lue par le 68000
    reg  [10:0] mb_addr;
    wire [7:0]  mrh_rd, mrl_rd;
    bram_dp #(.DW(8), .AW(11)) u_mr_h (
        .clk(clk), .a_we(mem_wr && mem_space == 8'd2 && !mem_addr[0]),
        .a_addr(mem_addr[11:1]), .a_wdata(mem_wdata), .b_addr(mb_addr), .b_rdata(mrh_rd));
    bram_dp #(.DW(8), .AW(11)) u_mr_l (
        .clk(clk), .a_we(mem_wr && mem_space == 8'd2 &&  mem_addr[0]),
        .a_addr(mem_addr[11:1]), .a_wdata(mem_wdata), .b_addr(mb_addr), .b_rdata(mrl_rd));
    // commande : écrite par le 68000, lue par la liaison
    reg        mc_we_h = 1'b0, mc_we_l = 1'b0;
    reg [6:0]  mc_waddr;
    reg [15:0] mc_wd;
    wire [7:0] mch_rd, mcl_rd;
    bram_dp #(.DW(8), .AW(7)) u_mc_h (
        .clk(clk), .a_we(mc_we_h), .a_addr(mc_waddr), .a_wdata(mc_wd[15:8]),
        .b_addr(mem_addr[7:1]), .b_rdata(mch_rd));
    bram_dp #(.DW(8), .AW(7)) u_mc_l (
        .clk(clk), .a_we(mc_we_l), .a_addr(mc_waddr), .a_wdata(mc_wd[7:0]),
        .b_addr(mem_addr[7:1]), .b_rdata(mcl_rd));

    // lecture par la liaison : zone commande uniquement
    always @* mem_rdata = (mem_space == 8'd2) ? (mem_addr[0] ? mcl_rd : mch_rd) : 8'hFF;

    // =========================================================================
    // Placement en SDRAM : P1 (1 Mo) seul dans la banque 0, la zone P2 dans
    // les banques 1 à 3. Ainsi les deux candidats d'une adresse 68000 (P1 et
    // P2) sont toujours dans des banques différentes et se lisent en parallèle.
    //   mot P < 0x80000  : banque 0, ligne/colonne = mot[18:0]
    //   mot P >= 0x80000 : w = mot - 0x80000, banque 1 + w[23:22], ligne/colonne = w[21:0]
    // Capacité : 1 Mo + 24 Mo.
    // =========================================================================
    function [23:0] p_phys(input [23:0] word);
        reg [23:0] w;
        begin
            if (word < 24'h080000) p_phys = {3'b000, word[18:9], 2'd0, word[8:0]};
            else begin
                w = word - 24'h080000;
                p_phys = {w[21:9], 2'd1 + w[23:22], w[8:0]};
            end
        end
    endfunction

    // =========================================================================
    // Client SDRAM : lecture anticipée / lecture 68000 / chargeur / diagnostic
    // =========================================================================
    reg         sq_req = 1'b0, sq_we = 1'b0;
    reg  [23:0] sq_addr, sq_addr2;
    reg  [1:0]  sq_nrd;
    reg  [15:0] sq_wdata;
    reg  [1:0]  sq_wmask;
    wire        sq_ack, sq_rvalid;
    wire [1:0]  sq_ridx;
    wire [15:0] sq_rdata;

    localparam OP_NONE = 3'd0, OP_SPEC = 3'd1, OP_REAL = 3'd2, OP_WR = 3'd3, OP_DBG = 3'd4;
    reg  [2:0]  op = OP_NONE;

    // anticipation : les deux candidats (P1 et P2) de l'adresse courante
    reg         spec_cur = 1'b0;       // anticipation lancée pour l'adresse courante
    reg  [1:0]  spec_ok = 2'b00;       // donnée disponible : [0] P1, [1] P2
    reg  [1:0]  spec_has = 2'b00;      // candidat demandé
    reg  [15:0] spec_d1, spec_d2;
    reg         want = 1'b0;           // le 68000 attend un candidat en cours de lecture
    wire        bank_chg = (bank_hold != 3'd0);
    reg         want_port;
    reg         real_pend = 1'b0;
    reg         real_port;

    reg  [15:0] p_dout = 16'hFFFF;

    // chargeur
    wire        pk_valid;  wire [23:0] pk_addr; wire [15:0] pk_data; wire [1:0] pk_mask;
    reg         pk_take;
    wr_packer #(.AW(24), .DEPTH(2)) u_pack (
        .clk(clk), .rst(rst),
        .in_stb(mem_wr && mem_space == 8'd0 && !game_mode), .in_addr(mem_addr), .in_data(mem_wdata),
        .flush(xfer_end),
        .out_valid(pk_valid), .out_addr(pk_addr), .out_data(pk_data), .out_mask(pk_mask),
        .out_take(pk_take), .empty(pk_empty), .overflow(pk_ovf));

    reg  [2:0]  bus_st = 3'd0;

    // rafraîchissement : juste après une lecture terminée, ou après 1 us sans lecture
    reg  [7:0]  since_rd = 8'hFF;
    wire        ref_ok = (since_rd < 8'd8) || (since_rd > 8'd100);

    wire        oe_ev     = rom_rd_ev | port_rd_ev;
    wire        oe_active = ~c_s[0] | ~c_s[1] | ~c_d[0] | ~c_d[1];

    // adresses physiques des deux candidats, calculées en pipeline (2 cycles)
    wire [22:0] p2_base_w;
    wire        pvc_mode;
    reg  [23:0] wp1_r, wp2_r, ph1_r, ph2_r;
    reg         p2hi_r, pvc_r = 1'b0;
    always @(posedge clk) begin
        wp1_r   <= {5'd0, a_s} & p_mask;
        wp2_r   <= ({5'd0, a_s} + {1'b0, p2_base_w}) & p_mask;
        pvc_r   <= pvc_mode && a_s[18:12] == 7'h7F;
        ph1_r   <= p_phys(wp1_r);
        ph2_r   <= p_phys(pvc_r ? PVC_RAM_W + {12'd0, a_d[11:0]} : wp2_r);
        p2hi_r  <= pvc_r || (wp2_r >= 24'h080000);
    end
    // ph*_r viennent de a_s deux cycles plus tôt ; same_r garantit qu'elle
    // n'a pas changé au cycle suivant (un changement ultérieur annule spec_cur)
    wire pipe_ok = same_r;

    // ----- protections / banques -----
    reg  game_d = 1'b0;
    always @(posedge clk) game_d <= game_mode;
    wire        game_start = game_mode & ~game_d;
    wire        wr_go = game_mode && bus_st == 3'd5;
    wire        base_chg, sp_rom_hit, sp_port_hit, gw_req;
    wire [15:0] sp_data, gw_data;
    wire [11:0] gw_word;
    wire [1:0]  gw_mask;
    p_mapper u_map (
        .clk(clk), .rst(rst), .game_start(game_start), .bank_en(ctrl_bank_en),
        .reg_wr(reg_wr), .reg_addr(reg_addr), .reg_wdata(reg_wdata),
        .tbl_wr(mem_wr && mem_space == 8'd4), .tbl_addr(mem_addr[7:0]), .tbl_data(mem_wdata),
        .cfg_rdata(map_rdata),
        .a(a_s), .d(d_s), .wr_go(wr_go), .wr_be({~c_s[3], ~c_s[2]}), .port_rd_ev(port_rd_ev),
        .p2_base_w(p2_base_w), .base_chg(base_chg), .pvc_mode(pvc_mode),
        .sp_rom_hit(sp_rom_hit), .sp_port_hit(sp_port_hit), .sp_data(sp_data),
        .gw_req(gw_req), .gw_word(gw_word), .gw_data(gw_data), .gw_mask(gw_mask));

    // écriture du jeu en SDRAM (RAM PVC) en attente
    reg         gw_pend = 1'b0;
    reg  [23:0] gw_addr;
    reg  [15:0] gw_d;
    reg  [1:0]  gw_m;
    reg  [2:0]  bank_hold = 3'd0;     // délai de traversée du pipeline d'adresses
    reg         inval;
    // conditions d'une nouvelle anticipation, registrées (chemin critique)
    reg  spec_go = 1'b0;
    wire hit     = spec_cur && spec_has[port_rd_ev];

    always @(posedge clk) begin
        pk_take <= 1'b0;
        mc_we_h <= 1'b0;
        mc_we_l <= 1'b0;
        if (rom_rd_ev)  cnt_romoe  <= cnt_romoe + 1;
        if (port_rd_ev) cnt_portoe <= cnt_portoe + 1;
        if (since_rd != 8'hFF) since_rd <= since_rd + 8'd1;

        if (reg_wr && reg_addr == 8'h09) irq <= 1'b0;
        if (reg_wr && reg_addr == 8'h01 && !reg_wdata[0]) game_mode <= 1'b0;
        if (reg_wr && reg_addr == 8'h01 &&  reg_wdata[1]) game_mode <= 1'b1;   // forçage (debug)
        if (reg_wr && reg_addr == 8'h10) begin dbg_req <= 1'b1; dbg_busy <= 1'b1; end

        if (rst) begin
            op <= OP_NONE; sq_req <= 1'b0; game_mode <= 1'b0; irq <= 1'b0; gw_pend <= 1'b0;
            spec_cur <= 1'b0; want <= 1'b0; real_pend <= 1'b0; bus_st <= 3'd0; bank_hold <= 3'd0;
            dbg_req <= 1'b0; dbg_busy <= 1'b0;
        end else begin
            inval = 1'b0;
            // ----- lecture 68000 en mode jeu -----
            if (game_mode && oe_ev) begin
                if ((port_rd_ev && sp_port_hit) || (rom_rd_ev && sp_rom_hit)) begin
                    p_dout <= sp_data;           // protection, générateur, registres PVC...
                end else if (hit) begin
                    cnt_spec_hit <= cnt_spec_hit + 1;
                    if (spec_ok[port_rd_ev])
                        p_dout <= port_rd_ev ? spec_d2 : spec_d1;
                    else if (op == OP_SPEC && sq_rvalid && sq_ridx[0] == port_rd_ev)
                        p_dout <= sq_rdata;
                    else begin
                        want <= 1'b1; want_port <= port_rd_ev;
                    end
                end else begin
                    real_pend <= 1'b1;
                    real_port <= port_rd_ev;
                end
            end

            // ----- menu : lectures BRAM et écritures -----
            case (bus_st)
            3'd0: if (!game_mode && oe_ev) begin
                      if (rom_rd_ev) begin
                          mp_addr <= a_s[MENU_AW-1:0];
                          bus_st  <= 3'd1;
                      end else if (a_is_ctl) begin
                          p_dout <= {14'd0, ctrl_arm, irq};
                      end else begin
                          mb_addr <= a_s[10:0];
                          bus_st  <= 3'd3;
                      end
                  end else if (wr_ev) bus_st <= 3'd5;
            3'd1: bus_st <= 3'd2;
            3'd2: begin p_dout <= {mph_rd, mpl_rd}; bus_st <= 3'd0; end
            3'd3: bus_st <= 3'd4;
            3'd4: begin p_dout <= {mrh_rd, mrl_rd}; bus_st <= 3'd0; end
            3'd5: begin       // écriture (D stabilisée un cycle de plus)
                if (game_mode) begin
                    inval = 1'b1;                   // traité par p_mapper (wr_go)
                end else if (a_is_ctl) begin
                    case (a_s[2:0])
                    3'd0: irq <= 1'b1;
                    3'd1: if (d_s == 16'h5A5A && ctrl_arm) game_mode <= 1'b1;
                    default: ;
                    endcase
                end else if (a_s[10:7] == 4'd0) begin
                    mc_waddr <= a_s[6:0];
                    mc_wd    <= d_s;
                    mc_we_h  <= ~c_s[3];
                    mc_we_l  <= ~c_s[2];
                end
                bus_st <= 3'd6;
            end
            3'd6: if (!wr_now) bus_st <= 3'd0;
            default: bus_st <= 3'd0;
            endcase

            // ----- client SDRAM -----
            case (op)
            OP_NONE: begin
                if (game_mode && gw_pend) begin
                    gw_pend <= 1'b0;
                    sq_req <= 1'b1; sq_we <= 1'b1; sq_nrd <= 2'd0; sq_addr <= gw_addr;
                    sq_wdata <= gw_d; sq_wmask <= gw_m; op <= OP_WR;
                end else if (game_mode && real_pend && pipe_ok && !bank_chg) begin
                    real_pend <= 1'b0;
                    sq_req <= 1'b1; sq_we <= 1'b0; sq_nrd <= 2'd0;
                    sq_addr <= real_port ? ph2_r : ph1_r; op <= OP_REAL;
                end else if (spec_go && !oe_ev && !spec_cur && bus_st < 3'd5) begin
                    // (pas pendant un cycle d'écriture : l'écriture invalide l'anticipation)
                    // nouvelle adresse stable : lit les deux candidats en parallèle
                    spec_cur <= 1'b1;
                    spec_ok  <= 2'b00;
                    sq_req   <= 1'b1;
                    sq_we    <= 1'b0;
                    sq_addr  <= ph1_r;
                    sq_addr2 <= ph2_r;
                    if (p2hi_r) begin
                        sq_nrd <= 2'd3; spec_has <= 2'b11;
                    end else begin
                        sq_nrd <= 2'd0; spec_has <= 2'b01;   // P2 replié sur P1 : lecture normale
                    end
                    op <= OP_SPEC;
                end else if (!game_mode && pk_valid) begin
                    sq_req <= 1'b1; sq_we <= 1'b1; sq_nrd <= 2'd0; sq_addr <= p_phys(pk_addr);
                    sq_wdata <= pk_data; sq_wmask <= pk_mask; pk_take <= 1'b1; op <= OP_WR;
                end else if (!game_mode && dbg_req) begin
                    dbg_req <= 1'b0;
                    sq_req <= 1'b1; sq_we <= 1'b0; sq_nrd <= 2'd0; sq_addr <= p_phys(dbg_addr[23:0]); op <= OP_DBG;
                end
            end
            OP_SPEC: begin
                if (sq_ack) sq_req <= 1'b0;
                if (sq_rvalid) begin
                    if (sq_ridx[0]) begin spec_d2 <= sq_rdata; spec_ok[1] <= 1'b1; end
                    else            begin spec_d1 <= sq_rdata; spec_ok[0] <= 1'b1; end
                    if (want && want_port == sq_ridx[0]) begin p_dout <= sq_rdata; want <= 1'b0; end
                    if (sq_ridx[0] || sq_nrd == 2'd0) begin since_rd <= 8'd0; op <= OP_NONE; end
                end
            end
            OP_REAL, OP_DBG: begin
                if (sq_ack) sq_req <= 1'b0;
                if (sq_rvalid) begin
                    since_rd <= 8'd0;
                    op <= OP_NONE;
                    if (op == OP_REAL) p_dout <= sq_rdata;
                    else begin dbg_data <= sq_rdata; dbg_busy <= 1'b0; end
                end
            end
            OP_WR: if (sq_ack) begin sq_req <= 1'b0; op <= OP_NONE; end
            default: op <= OP_NONE;
            endcase

            // un 68000 qui attend un candidat jamais demandé : lecture normale
            if (want && op == OP_NONE) begin
                want <= 1'b0;
                real_pend <= 1'b1;
                real_port <= want_port;
            end

            // même instant de décision que same_r (comparaison a_s == a_d),
            // mais calculé un cycle plus tôt et registré
            spec_go <= game_mode && !oe_active && (a_s == a_d) && (!spec_cur || !same_r)
                       && !want && !bank_chg && !gw_pend && !(op == OP_NONE && spec_go && !oe_ev);

            // l'adresse a changé, ou le jeu a écrit (banque, RAM PVC) :
            // l'anticipation en cours n'est plus valable
            if (!same_r || inval || base_chg) spec_cur <= 1'b0;
            // une nouvelle banque met plusieurs cycles à traverser le pipeline
            if (inval || base_chg) bank_hold <= 3'd7;
            else if (bank_hold != 3'd0) bank_hold <= bank_hold - 3'd1;
            if (gw_req) begin
                gw_pend <= 1'b1;
                gw_addr <= p_phys(PVC_RAM_W + {12'd0, gw_word});
                gw_d    <= gw_data;
                gw_m    <= gw_mask;
            end

            if (!game_mode) begin spec_cur <= 1'b0; want <= 1'b0; real_pend <= 1'b0; end
        end
    end

    sdram #(.COLW(9), .INIT_WAIT(SDRAM_INIT_WAIT), .REFI(SDRAM_REFI)) u_sdram (
        .clk(clk), .rst(rst),
        .req(sq_req), .we(sq_we), .addr(sq_addr), .nrd(sq_nrd), .col2(9'd0), .addr2(sq_addr2),
        .wdata(sq_wdata), .wmask(sq_wmask), .ack(sq_ack),
        .rvalid(sq_rvalid), .ridx(sq_ridx), .rdata(sq_rdata),
        .refresh_hold(game_mode && (sq_req || real_pend || want || gw_pend || !ref_ok)),
        .init_done(sd_init_done), .idle(sd_idle),
        .sd_cke(sd_cke), .sd_cs_n(sd_cs_n), .sd_ras_n(sd_ras_n), .sd_cas_n(sd_cas_n), .sd_we_n(sd_we_n),
        .sd_ba(sd_ba), .sd_a(sd_a), .sd_dqm(sd_dqm), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(sd_dq_i));

    assign d_o      = p_dout;
    assign wait_n   = wait_cfg;
    assign d_drive  = ~romoe_n | ~portoe_n;     // combinatoire depuis les broches
    assign mode_out = game_mode;
    assign lk_irq   = irq;
    reg led_r = 1'b0;
    always @(posedge clk) led_r <= game_mode ^ ~pk_empty;
    assign led = led_r;
endmodule
