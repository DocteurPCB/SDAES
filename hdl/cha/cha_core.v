// -----------------------------------------------------------------------------
// Cœur FPGA de la carte CHA (graphismes + son Z80).
//
// Remplace sur la cartouche : ROM C + NEO-273 (verrous d'adresses C/S) +
// NEO-ZMC2 (sérialiseur de pixels + banques Z80) + ROM S + ROM M1.
//
//   ROM C  -> 2 x SDRAM x16 en parallèle (32 bits, 64 Mo)
//   ROM S  -> SRAM 1 Mo, adresses 0x00000-0x7FFFF
//   ROM M1 -> SRAM 1 Mo, adresses 0x80000-0xFFFFF
//   Menu   -> BRAM internes (police S + pilote Z80), C = transparent
//
// Toutes les entrées "console" sont supposées déjà ramenées en 3,3 V par les
// translateurs de niveaux. Les correspondances d'adresses dépendant de la
// rétro-ingénierie publique sont regroupées dans la section "CARTOGRAPHIE".
// -----------------------------------------------------------------------------
module cha_core #(
    parameter MENU_S_INIT  = "",
    parameter MENU_M1_INIT = "",
    parameter SDRAM_INIT_WAIT = 27000,
    parameter SDRAM_REFI      = 1000
) (
    input  wire        clk,          // 133 MHz
    input  wire        rst,

    // --- bus cartouche CHA (côté FPGA des translateurs) ---
    input  wire [23:0] pbus,
    input  wire        pck1b,
    input  wire        pck2b,
    input  wire        ca4,
    input  wire        s2h1,
    input  wire        clk_12m,
    input  wire        even,
    input  wire        load,
    input  wire        h,
    output wire [3:0]  gad,
    output wire [3:0]  gbd,
    output wire        dota,
    output wire        dotb,
    output wire [7:0]  fixd,

    input  wire [15:0] sda,
    input  wire        sdmrd_n,
    input  wire        sdrom_n,
    input  wire        sdrd0_n,
    output wire [7:0]  sdd_o,
    output wire        sdd_drive,    // 1 : translateur SDD vers la console

    // --- liaison RP2350 ---
    input  wire        lk_sck,
    input  wire        lk_cs_n,
    input  wire [3:0]  lk_io_i,
    output wire [3:0]  lk_io_o,
    output wire        lk_io_oe,
    input  wire        mode_in,      // depuis la carte PROG (bascule menu/jeu)

    // --- SDRAM C (32 bits) ---
    output wire        sd_cke, sd_cs_n, sd_ras_n, sd_cas_n, sd_we_n,
    output wire [1:0]  sd_ba,
    output wire [12:0] sd_a,
    output wire [3:0]  sd_dqm,
    output wire [31:0] sd_dq_o,
    output wire        sd_dq_oe,
    input  wire [31:0] sd_dq_i,

    // --- SRAM S/M1 ---
    output wire [19:0] sr_a,
    output wire [7:0]  sr_d_o,
    output wire        sr_d_oe,
    input  wire [7:0]  sr_d_i,
    output wire        sr_ce_n,
    output wire        sr_oe_n,
    output wire        sr_we_n,

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

    reg        ctrl_arm = 1'b0, ctrl_force = 1'b0;
    reg [23:0] c_mask  = 24'hFFFFFF;
    reg [18:0] s_mask  = 19'h1FFFF;
    reg [18:0] m1_mask = 19'h1FFFF;
    reg [31:0] dbg_addr = 32'h0;
    reg [31:0] dbg_data = 32'h0;
    reg        dbg_req = 1'b0, dbg_busy = 1'b0;
    reg [31:0] cnt_pck1b = 0, cnt_pck2b = 0, cnt_z80 = 0;

    wire mode_in_s;
    sync2 u_sync_mode (.clk(clk), .d(mode_in), .q(mode_in_s));
    wire game_mode = (ctrl_arm & mode_in_s) | ctrl_force;

    wire sd_init_done, sd_idle, pk_empty, pk_ovf, sw_empty;

    // signaux partagés entre les blocs SRAM / Z80 / diagnostic
    reg         s_req = 1'b0, z_req = 1'b0;
    reg  [19:0] s_sa, z_sa;
    wire        s_ack, z_ack, w_ack;
    wire [7:0]  sram_rdata;
    reg  [1:0]  z_st = 2'd0;
    wire        z_rd_ev;
    reg         dbg_sram_act = 1'b0;
    wire sram_dbg_start = dbg_req && dbg_addr[31] && !game_mode && !dbg_sram_act
                          && z_st == 2'd0 && !z_rd_ev;
    wire sram_dbg_done  = dbg_sram_act && z_ack;
    localparam CL_IDLE = 2'd0, CL_C = 2'd1, CL_W = 2'd2, CL_DBG = 2'd3;
    reg  [1:0]  cl_st = CL_IDLE;

    always @(posedge clk) begin
        if (rst) begin
            ctrl_arm <= 1'b0; ctrl_force <= 1'b0;
        end else if (reg_wr) begin
            case (reg_addr)
            8'h01: begin ctrl_arm <= reg_wdata[0]; ctrl_force <= reg_wdata[1]; end
            8'h03: c_mask  <= reg_wdata[23:0];
            8'h04: s_mask  <= reg_wdata[18:0];
            8'h05: m1_mask <= reg_wdata[18:0];
            8'h10: dbg_addr <= reg_wdata;
            default: ;
            endcase
        end
    end

    always @* begin
        case (reg_addr)
        8'h00: reg_rdata = 32'h4E474331;   // "NGC1"
        8'h01: reg_rdata = {30'd0, ctrl_force, ctrl_arm};
        8'h02: reg_rdata = {26'd0, dbg_busy, pk_ovf, mode_in_s, game_mode,
                            pk_empty & sw_empty & sd_idle & (cl_st == CL_IDLE), sd_init_done};
        8'h03: reg_rdata = {8'd0, c_mask};
        8'h04: reg_rdata = {13'd0, s_mask};
        8'h05: reg_rdata = {13'd0, m1_mask};
        8'h10: reg_rdata = dbg_addr;
        8'h11: reg_rdata = dbg_data;
        8'h12: reg_rdata = cnt_pck1b;
        8'h13: reg_rdata = cnt_pck2b;
        8'h14: reg_rdata = cnt_z80;
        default: reg_rdata = 32'hDEADBEEF;
        endcase
    end

    // =========================================================================
    // CARTOGRAPHIE (à valider sur matériel, cf. docs/03-memoire-et-timings.md)
    // =========================================================================
    // Verrous du NEO-273 : capturés directement sur les broches PCK1B/PCK2B
    // (front montant = fin de l'impulsion), comme la puce d'origine.
    reg [23:0] c_latch = 24'h0;
    reg [15:0] s_latch = 16'h0;
    always @(posedge pck1b) c_latch <= pbus;
    always @(posedge pck2b) s_latch <= pbus[15:0];

    // Mot C (32 bits) : {tuile[19:0], CA4, ligne[3:0]}
    //   tuile[15:0] = P[15:0], ligne = P[19:16], tuile[19:16] = P[23:20]
    function [24:0] c_word_addr(input [23:0] p, input half);
        c_word_addr = {p[23:20], p[15:0], half, p[19:16]};
    endfunction

    // Octet S : {tuile[11:0], P3, 2H1, ligne[2:0]} (17 bits, 128 Ko)
    function [16:0] s_byte_addr(input [15:0] p, input h1);
        s_byte_addr = {p[15:4], p[3], h1, p[2:0]};
    endfunction

    // Réordonne un mot lu en SDRAM (octets du fichier .neo : c1 et c2
    // entrelacés octet par octet) vers le bus CR du ZMC2.
    //   voie0 = c1 bas  -> CR[7:0]     voie1 = c2 bas  -> CR[23:16]
    //   voie2 = c1 haut -> CR[15:8]    voie3 = c2 haut -> CR[31:24]
    function [31:0] c_remap(input [31:0] w);
        c_remap = {w[31:24], w[15:8], w[23:16], w[7:0]};
    endfunction

    // =========================================================================
    // ROM C : lecture SDRAM sur chaque nouveau verrou PCK1B
    // =========================================================================
    wire [1:0] pck_s;
    sync2 #(.W(2), .INIT(2'b11)) u_sync_pck (.clk(clk), .d({pck2b, pck1b}), .q(pck_s));
    reg  [1:0] pck_d = 2'b11;
    always @(posedge clk) pck_d <= pck_s;
    wire pck1_ev = pck_s[0] & ~pck_d[0];
    wire pck2_ev = pck_s[1] & ~pck_d[1];

    reg [31:0] c_half0 = 32'h0, c_half1 = 32'h0;
    reg        c_pend = 1'b0;
    reg        c_busy = 1'b0;
    reg [24:0] c_a0;
    reg [7:0]  since_ev = 8'hFF;

    // client SDRAM
    reg         sd_req;
    reg         sd_we;
    reg  [23:0] sd_addr;
    reg         sd_dual;
    reg  [8:0]  sd_col2;
    reg  [31:0] sd_wdata;
    reg  [3:0]  sd_wmask;
    wire        sd_ack, sd_rvalid, sd_rvalid2;
    wire [31:0] sd_rdata, sd_rdata2;

    // chargeur -> SDRAM
    wire        pk_valid;
    wire [23:0] pk_addr;
    wire [31:0] pk_data;
    wire [3:0]  pk_mask;
    reg         pk_take;

    wire ld_sd = mem_wr && mem_space == 8'd0 && !game_mode;
    wr_packer #(.DW(32), .AW(24), .DEPTH(16)) u_pack (
        .clk(clk), .rst(rst),
        .in_stb(ld_sd), .in_addr(mem_addr), .in_data(mem_wdata), .flush(xfer_end),
        .out_valid(pk_valid), .out_addr(pk_addr), .out_data(pk_data), .out_mask(pk_mask),
        .out_take(pk_take), .empty(pk_empty), .overflow(pk_ovf)
    );


    always @(posedge clk) begin
        pk_take <= 1'b0;
        if (since_ev != 8'hFF) since_ev <= since_ev + 8'd1;
        if (pck1_ev) begin
            c_pend   <= 1'b1;
            since_ev <= 8'd0;
            cnt_pck1b <= cnt_pck1b + 1;
        end
        if (pck2_ev) cnt_pck2b <= cnt_pck2b + 1;
        if (reg_wr && reg_addr == 8'h10) begin dbg_req <= 1'b1; dbg_busy <= 1'b1; end

        if (rst) begin
            cl_st <= CL_IDLE; sd_req <= 1'b0; c_pend <= 1'b0; dbg_req <= 1'b0; dbg_busy <= 1'b0;
        end else case (cl_st)
        CL_IDLE: begin
            if (game_mode && (c_pend || pck1_ev)) begin
                c_pend  <= 1'b0;
                c_a0    = c_word_addr(c_latch, 1'b0);
                sd_req  <= 1'b1;
                sd_we   <= 1'b0;
                sd_addr <= c_a0[23:0] & c_mask;
                sd_dual <= 1'b1;
                sd_col2 <= c_a0[8:0] | 9'h010;
                cl_st   <= CL_C;
            end else if (!game_mode && pk_valid) begin
                sd_req   <= 1'b1;
                sd_we    <= 1'b1;
                sd_addr  <= pk_addr;
                sd_dual  <= 1'b0;
                sd_wdata <= pk_data;
                sd_wmask <= pk_mask;
                pk_take  <= 1'b1;
                cl_st    <= CL_W;
            end else if (!game_mode && dbg_req && !dbg_addr[31]) begin
                dbg_req <= 1'b0;
                sd_req  <= 1'b1;
                sd_we   <= 1'b0;
                sd_dual <= 1'b0;
                sd_addr <= dbg_addr[23:0];
                cl_st   <= CL_DBG;
            end
            if (!game_mode) c_pend <= 1'b0;
        end
        CL_C: begin
            if (sd_ack) sd_req <= 1'b0;
            if (sd_rvalid)  c_half0 <= c_remap(sd_rdata);
            if (sd_rvalid2) begin c_half1 <= c_remap(sd_rdata2); cl_st <= CL_IDLE; end
        end
        CL_W: begin
            if (sd_ack) begin sd_req <= 1'b0; cl_st <= CL_IDLE; end
        end
        CL_DBG: begin
            if (sd_ack) sd_req <= 1'b0;
            if (sd_rvalid) begin dbg_data <= sd_rdata; dbg_busy <= 1'b0; cl_st <= CL_IDLE; end
        end
        endcase

        if (!game_mode) begin
            c_half0 <= 32'h0;   // menu : sprites transparents
            c_half1 <= 32'h0;
        end
        if (sram_dbg_done) begin dbg_data <= {24'd0, sram_rdata}; dbg_busy <= 1'b0; end
        if (!rst && dbg_req && dbg_addr[31] && sram_dbg_start) dbg_req <= 1'b0;
    end

    // Rafraîchissement : autorisé juste après une lecture C (la prochaine
    // impulsion PCK1B est loin) ou quand le bus est inactif depuis > 1,5 us.
    wire ref_window = (since_ev < 8'd40) || (since_ev == 8'hFF) || (since_ev > 8'd200);
    wire ref_hold   = game_mode && (c_pend || pck1_ev || cl_st == CL_C || !ref_window);

    sdram #(.DW(32), .INIT_WAIT(SDRAM_INIT_WAIT), .REFI(SDRAM_REFI)) u_sdram (
        .clk(clk), .rst(rst),
        .req(sd_req), .we(sd_we), .addr(sd_addr), .dual(sd_dual), .col2(sd_col2),
        .wdata(sd_wdata), .wmask(sd_wmask), .ack(sd_ack),
        .rvalid(sd_rvalid), .rdata(sd_rdata), .rvalid2(sd_rvalid2), .rdata2(sd_rdata2),
        .refresh_hold(ref_hold), .init_done(sd_init_done), .idle(sd_idle),
        .sd_cke(sd_cke), .sd_cs_n(sd_cs_n), .sd_ras_n(sd_ras_n), .sd_cas_n(sd_cas_n),
        .sd_we_n(sd_we_n), .sd_ba(sd_ba), .sd_a(sd_a), .sd_dqm(sd_dqm),
        .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(sd_dq_i)
    );

    // ZMC2 : bus CR = moitié choisie par CA4 (combinatoire, comme une ROM)
    wire [31:0] cr = ca4 ? c_half1 : c_half0;
    zmc2_dot u_zmc2 (
        .clk_12m(clk_12m), .even(even), .load(load), .h(h), .cr(cr),
        .gad(gad), .gbd(gbd), .dota(dota), .dotb(dotb)
    );

    // =========================================================================
    // BRAM du menu (police S et pilote Z80)
    // =========================================================================
    wire [7:0] ms_a_rd, mm_a_rd, ms_b_rd, mm_b_rd;
    reg  [12:0] ms_b_addr, mm_b_addr;
    wire ms_we = mem_wr && mem_space == 8'd2;
    wire mm_we = mem_wr && mem_space == 8'd3;
    bram_dp #(.DW(8), .AW(13), .INIT(MENU_S_INIT)) u_menu_s (
        .clk(clk), .a_we(ms_we), .a_addr(mem_addr[12:0]), .a_wdata(mem_wdata), .a_rdata(ms_a_rd),
        .b_addr(ms_b_addr), .b_rdata(ms_b_rd)
    );
    bram_dp #(.DW(8), .AW(13), .INIT(MENU_M1_INIT)) u_menu_m1 (
        .clk(clk), .a_we(mm_we), .a_addr(mem_addr[12:0]), .a_wdata(mem_wdata), .a_rdata(mm_a_rd),
        .b_addr(mm_b_addr), .b_rdata(mm_b_rd)
    );
    always @* begin
        case (mem_space)
        8'd2:    mem_rdata = ms_a_rd;
        8'd3:    mem_rdata = mm_a_rd;
        default: mem_rdata = 8'hFF;
        endcase
    end

    // =========================================================================
    // SRAM partagée S / M1 / chargeur
    // =========================================================================

    // écritures du chargeur (espace 1) : petite FIFO d'octets
    reg  [27:0] sw_fifo [0:15];
    reg  [4:0]  sw_wp = 0, sw_rp = 0;
    assign sw_empty = (sw_wp == sw_rp);
    always @(posedge clk) begin
        if (rst) begin sw_wp <= 0; sw_rp <= 0; end
        else begin
            if (mem_wr && mem_space == 8'd1 && !game_mode && (sw_wp - sw_rp) != 5'd16) begin
                sw_fifo[sw_wp[3:0]] <= {mem_addr[19:0], mem_wdata};
                sw_wp <= sw_wp + 5'd1;
            end
            if (w_ack) sw_rp <= sw_rp + 5'd1;
        end
    end
    wire [27:0] sw_head = sw_fifo[sw_rp[3:0]];

    // lecture de diagnostic SRAM (dbg_addr[31] = 1)

    sram_ctrl u_sram (
        .clk(clk), .rst(rst),
        .r0_req(s_req), .r0_addr(s_sa), .r0_ack(s_ack),
        .r1_req(z_req | dbg_sram_act), .r1_addr(dbg_sram_act ? dbg_addr[19:0] : z_sa), .r1_ack(z_ack),
        .rdata(sram_rdata),
        .w_req(!sw_empty && !game_mode), .w_addr(sw_head[27:8]), .w_data(sw_head[7:0]), .w_ack(w_ack),
        .sr_a(sr_a), .sr_d_o(sr_d_o), .sr_d_oe(sr_d_oe), .sr_d_i(sr_d_i),
        .sr_ce_n(sr_ce_n), .sr_oe_n(sr_oe_n), .sr_we_n(sr_we_n)
    );

    // =========================================================================
    // ROM S (couche fixe) : 2 octets lus par verrou PCK2B (2H1 = 0 puis 1)
    // =========================================================================
    reg [7:0] fix0 = 8'h00, fix1 = 8'h00;
    reg [2:0] s_st = 3'd0;
    reg       s_pend = 1'b0;
    reg [15:0] s_lat_q;
    reg [16:0] s_ba;

    always @(posedge clk) begin
        if (pck2_ev) s_pend <= 1'b1;
        if (rst) begin s_st <= 3'd0; s_req <= 1'b0; s_pend <= 1'b0; end
        else case (s_st)
        3'd0: if (s_pend || pck2_ev) begin
                  s_pend  <= 1'b0;
                  s_lat_q <= s_latch;
                  s_st    <= game_mode ? 3'd1 : 3'd4;
                  s_ba     = s_byte_addr(s_latch, 1'b0);
                  s_sa    <= {3'b000, s_ba} & {1'b0, s_mask};
                  s_req   <= game_mode;
                  ms_b_addr <= s_ba[12:0];
              end
        // SRAM
        3'd1: if (s_ack) begin
                  fix0  <= sram_rdata;
                  s_ba   = s_byte_addr(s_lat_q, 1'b1);
                  s_sa  <= {3'b000, s_ba} & {1'b0, s_mask};
                  s_st  <= 3'd2;
              end
        3'd2: s_st <= 3'd3;           // laisse l'arbitre voir la nouvelle requête
        3'd3: if (s_ack) begin fix1 <= sram_rdata; s_req <= 1'b0; s_st <= 3'd0; end
        // BRAM du menu
        3'd4: begin s_ba = s_byte_addr(s_lat_q, 1'b1); ms_b_addr <= s_ba[12:0]; s_st <= 3'd5; end
        3'd5: begin fix0 <= ms_b_rd; s_st <= 3'd6; end
        3'd6: begin fix1 <= ms_b_rd; s_st <= 3'd0; end
        default: s_st <= 3'd0;
        endcase
    end
    assign fixd = s2h1 ? fix1 : fix0;

    // =========================================================================
    // ROM M1 (Z80) + banques NEO-ZMC
    // =========================================================================
    wire [15:0] sda_s;
    wire [2:0]  zc_s;   // {sdrd0_n, sdrom_n, sdmrd_n}
    sync2 #(.W(16)) u_sync_sda (.clk(clk), .d(sda), .q(sda_s));
    sync2 #(.W(3), .INIT(3'b111)) u_sync_zc (.clk(clk), .d({sdrd0_n, sdrom_n, sdmrd_n}), .q(zc_s));
    reg [2:0] zc_d = 3'b111;
    always @(posedge clk) zc_d <= zc_s;
    wire z_rd_now  = ~zc_s[0] & ~zc_s[1];
    wire z_rd_prev = ~zc_d[0] & ~zc_d[1];
    assign z_rd_ev = z_rd_now & ~z_rd_prev;
    wire bank_ev   = ~zc_s[2] & zc_d[2];

    reg [7:0] bank0 = 8'h1E;   // fenêtre F000-F7FF (2 Ko)
    reg [6:0] bank1 = 7'h0E;   // fenêtre E000-EFFF (4 Ko)
    reg [5:0] bank2 = 6'h06;   // fenêtre C000-DFFF (8 Ko)
    reg [4:0] bank3 = 5'h02;   // fenêtre 8000-BFFF (16 Ko)

    function [18:0] m1_addr(input [15:0] a);
        if (!a[15])      m1_addr = {4'b0000, a[14:0]};
        else if (!a[14]) m1_addr = {bank3, a[13:0]};
        else if (!a[13]) m1_addr = {bank2, a[12:0]};
        else if (!a[12]) m1_addr = {bank1, a[11:0]};
        else             m1_addr = {bank0, a[10:0]};
    endfunction

    reg [7:0] z_dout = 8'hFF;
    reg [18:0] z_ma;
    always @(posedge clk) begin
        if (bank_ev) begin
            case (sda_s[1:0])
            // numéro de banque = registre B du Z80 (A15-A8) lors d'un IN (C)
            2'd0: bank0 <= sda_s[15:8];
            2'd1: bank1 <= sda_s[14:8];
            2'd2: bank2 <= sda_s[13:8];
            2'd3: bank3 <= sda_s[12:8];
            endcase
        end
        if (rst) begin z_st <= 2'd0; z_req <= 1'b0; dbg_sram_act <= 1'b0; end
        else case (z_st)
        2'd0: if (z_rd_ev) begin
                  cnt_z80 <= cnt_z80 + 1;
                  z_ma = m1_addr(sda_s);
                  if (game_mode) begin
                      z_sa  <= {1'b1, z_ma & m1_mask};
                      z_req <= 1'b1;
                      z_st  <= 2'd1;
                  end else begin
                      mm_b_addr <= z_ma[12:0];
                      z_st <= 2'd2;
                  end
              end else if (sram_dbg_start) begin
                  dbg_sram_act <= 1'b1;
                  z_st <= 2'd1;
              end
        2'd1: if (z_ack) begin
                  if (dbg_sram_act) dbg_sram_act <= 1'b0;
                  else z_dout <= sram_rdata;
                  z_req <= 1'b0;
                  z_st <= 2'd0;
              end
        2'd2: z_st <= 2'd3;
        2'd3: begin z_dout <= mm_b_rd; z_st <= 2'd0; end
        endcase
    end
    assign sdd_o     = z_dout;
    // sens du translateur : combinatoire depuis les broches pour libérer le
    // bus dès la fin du cycle de lecture
    assign sdd_drive = ~sdmrd_n & ~sdrom_n;

    // LED : allumée en mode jeu, clignote pendant l'activité du chargeur
    assign led = game_mode ^ (~pk_empty | ~sw_empty);
endmodule
