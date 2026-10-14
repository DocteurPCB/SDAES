// -----------------------------------------------------------------------------
// Protections et changements de banque des cartouches (FPGA P, mode jeu).
//
//   mode 0  STD : écriture en 0x2FFFF0-0x2FFFFF = numéro de banque de 1 Mo
//   mode 1  SMA : (KOF 99, Garou, Metal Slug 3, KOF 2000)
//                 - registre de banque à une adresse propre au jeu, numéro
//                   brouillé (6 bits choisis dans la donnée) puis table de
//                   64 décalages chargée par le RP2350
//                 - lecture de protection (adresse/valeur configurables)
//                 - deux adresses de générateur pseudo-aléatoire (LFSR 16 bits)
//   mode 2  PVC : (Metal Slug 5, SVC Chaos, KOF 2003)
//                 - 8 Ko de RAM en 0x2FE000-0x2FFFFF (en SDRAM, sauf les mots
//                   0xFF0-0xFF9 utilisés par la protection, gardés ici)
//                 - écriture en 0x2FFFE0 : décompactage d'une couleur
//                 - écriture en 0x2FFFE8-0x2FFFEB : compactage d'une couleur
//                 - écriture en 0x2FFFF0-0x2FFFF3 : banque P2 à un décalage
//                   quelconque
//   mode 3  PRO-CT0 : (Fatal Fury 2, Super Sidekicks) le sérialiseur de
//                 pixels du ZMC2 (ALPHA-8921) câblé sur le bus 68000, comme
//                 dans MAME (prot_fatfury2.cpp) : une écriture en zone
//                 0x2xxxxx = un front d'horloge, avec LOAD = A1, EVEN = A2,
//                 H = A3 et le mot C = {A19..A4, D15..D0} permutés ; une
//                 lecture renvoie GAD/GBD sur D7..D0 (EVEN = A2, H = A3).
//   mode 4  MS5P : (Metal Slug 5 Plus, MAME boot_ms5plus) lecture en
//                 0x2FFFF0-0x2FFFFF = 0x00A0 ; écriture de 0xA0 en 0x2FFFF0 :
//                 fenêtre P2 à l'octet 0xA0 ; écriture en 0x2FFFF4 : fenêtre
//                 à (donnée >> 4) x 1 Mo.
//   superposition (KOF 98) : une écriture d'un code à une adresse donnée
//                 remplace deux mots de la zone P1 par d'autres valeurs.
//
// Tous les paramètres propres à un jeu sont fournis par le RP2350 (fichiers
// .map sur la carte SD, voir docs/08-cartouches-protegees.md).
// Adresses : index de mot A[19:1] dans la fenêtre concernée (19 bits).
// -----------------------------------------------------------------------------
module p_mapper (
    input  wire        clk,
    input  wire        rst,
    input  wire        game_start,       // impulsion au passage en mode jeu
    input  wire        bank_en,          // CTRL.BANK_EN (mode STD)

    // configuration par la liaison
    input  wire        reg_wr,
    input  wire [7:0]  reg_addr,
    input  wire [31:0] reg_wdata,
    input  wire        tbl_wr,           // octet de la table SMA (espace 4)
    input  wire [7:0]  tbl_addr,         // adresse octet 0..255 (4 octets par entrée, MSB d'abord)
    input  wire [7:0]  tbl_data,
    output reg  [31:0] cfg_rdata,        // relecture selon reg_addr

    // bus 68000 (adresse stable, événements synchronisés)
    input  wire [18:0] a,
    input  wire [15:0] d,
    input  wire        wr_go,            // impulsion : écriture en zone 0x2xxxxx
    input  wire [1:0]  wr_be,            // {octet haut, octet bas}
    input  wire        port_rd_ev,

    // vers le cœur
    output reg  [22:0] p2_base_w,        // début de la fenêtre P2 en mots
    output reg         base_chg,         // impulsion : p2_base_w vient de changer
    output wire        pvc_mode,
    output reg         sp_rom_hit,       // lecture P1 servie par le mapper
    output reg         sp_port_hit,      // lecture P2 servie par le mapper
    output reg  [15:0] sp_data,
    output reg         gw_req,           // impulsion : écriture RAM PVC en SDRAM
    output reg  [11:0] gw_word,          // index de mot dans la RAM PVC
    output reg  [15:0] gw_data,
    output reg  [1:0]  gw_mask
);
    localparam M_STD = 3'd0, M_SMA = 3'd1, M_PVC = 3'd2, M_CT0 = 3'd3, M_MS5P = 3'd4;

    reg [2:0]  mode = M_STD;
    assign pvc_mode = (mode == M_PVC);
    reg        ovl_en = 1'b0;
    reg [18:0] sma_bank_addr = 19'h7FFF8;
    reg [23:0] sma_perm = 24'h543210;
    reg [18:0] prot_addr = 19'h0;   reg prot_en = 1'b0;
    reg [15:0] prot_val = 16'h0;
    reg [18:0] rng_addr0 = 19'h0;   reg rng_en0 = 1'b0;
    reg [18:0] rng_addr1 = 19'h0;   reg rng_en1 = 1'b0;
    reg [15:0] rng_seed = 16'h2345;
    reg [18:0] ovl_trig = 19'h0;
    reg [15:0] ovl_on = 16'h0, ovl_off = 16'h0;
    reg [18:0] ovl_addr = 19'h0;
    reg [15:0] ovl_v0 = 16'h0, ovl_v1 = 16'h0;

    always @(posedge clk) begin
        if (rst) begin
            mode <= M_STD; ovl_en <= 1'b0; prot_en <= 1'b0; rng_en0 <= 1'b0; rng_en1 <= 1'b0;
        end else if (reg_wr) begin
            case (reg_addr)
            8'h0A: begin mode <= reg_wdata[2:0]; ovl_en <= reg_wdata[8]; end
            8'h0B: sma_bank_addr <= reg_wdata[18:0];
            8'h0C: sma_perm <= reg_wdata[23:0];
            8'h0D: begin prot_addr <= reg_wdata[18:0]; prot_en <= reg_wdata[31]; end
            8'h0E: prot_val <= reg_wdata[15:0];
            8'h0F: begin rng_addr0 <= reg_wdata[18:0]; rng_en0 <= reg_wdata[31]; end
            8'h15: begin rng_addr1 <= reg_wdata[18:0]; rng_en1 <= reg_wdata[31]; end
            8'h16: rng_seed <= reg_wdata[15:0];
            8'h17: ovl_trig <= reg_wdata[18:0];
            8'h18: begin ovl_on <= reg_wdata[31:16]; ovl_off <= reg_wdata[15:0]; end
            8'h19: ovl_addr <= reg_wdata[18:0];
            8'h1A: begin ovl_v0 <= reg_wdata[31:16]; ovl_v1 <= reg_wdata[15:0]; end
            default: ;
            endcase
        end
    end

    always @* begin
        case (reg_addr)
        8'h08: cfg_rdata = {9'd0, p2_base_w};
        8'h0A: cfg_rdata = {23'd0, ovl_en, 5'd0, mode};
        8'h0C: cfg_rdata = {8'd0, sma_perm};
        default: cfg_rdata = 32'hDEADBEEF;
        endcase
    end

    // ---- table SMA : 64 décalages (octets, 24 bits), BRAM ----
    reg  [23:0] tbl_hold;
    reg         tbl_we = 1'b0;
    reg  [5:0]  tbl_widx;
    reg  [22:0] tbl [0:63];
    reg  [5:0]  tbl_ridx;
    reg  [22:0] tbl_q;
    always @(posedge clk) begin
        tbl_we <= 1'b0;
        if (tbl_wr) begin
            case (tbl_addr[1:0])
            2'd1: tbl_hold[23:16] <= tbl_data;
            2'd2: tbl_hold[15:8]  <= tbl_data;
            2'd3: begin tbl_hold[7:0] <= tbl_data; tbl_we <= 1'b1; tbl_widx <= tbl_addr[7:2]; end
            default: ;   // octet de poids fort ignoré
            endcase
        end
        if (tbl_we) tbl[tbl_widx] <= tbl_hold[23:1];   // en mots
        tbl_q <= tbl[tbl_ridx];
    end

    // numéro de banque SMA : bit i = d[sma_perm[4i+3:4i]]
    function [5:0] sma_idx(input [15:0] v, input [23:0] p);
        integer i;
        for (i = 0; i < 6; i = i + 1) sma_idx[i] = v[p[4*i +: 4]];
    endfunction

    // ---- générateur pseudo-aléatoire SMA ----
    reg  [15:0] rng = 16'h2345;
    wire        rng_fb = rng[2] ^ rng[3] ^ rng[5] ^ rng[6] ^ rng[7] ^ rng[11] ^ rng[12] ^ rng[15];

    // ---- registres PVC 0xFF0-0xFF9 (mots de la RAM de protection) ----
    reg  [15:0] sh [0:9];
    integer     k;

    // ---- superposition ----
    reg         ovl_active = 1'b0;

    // ---- PRO-CT0 : registre à décalage du sérialiseur (cf. cha/zmc2_dot.v) ----
    reg  [31:0] ct0_sr = 32'h0;
    // permutation des broches C (MAME : bitswap<16>(x, 15,11,14,10,13,9,12,8,7,3,6,2,5,1,4,0))
    function [15:0] ct0_sw(input [15:0] x);
        ct0_sw = {x[15], x[11], x[14], x[10], x[13], x[9], x[12], x[8],
                  x[7],  x[3],  x[6],  x[2],  x[5],  x[1], x[4],  x[0]};
    endfunction
    // GAD/GBD selon EVEN et H, puis D7..D0 = {GBD1,GBD0,GBD3,GBD2,GAD1,GAD0,GAD3,GAD2}
    function [7:0] ct0_out(input [31:0] sr, input even, input h);
        reg [3:0] ga, gb;
        begin
            case ({even, h})
            2'b11:   {gb, ga} = {sr[31], sr[23], sr[15], sr[7], sr[30], sr[22], sr[14], sr[6]};
            2'b10:   {gb, ga} = {sr[24], sr[16], sr[8],  sr[0], sr[25], sr[17], sr[9],  sr[1]};
            2'b01:   {gb, ga} = {sr[30], sr[22], sr[14], sr[6], sr[31], sr[23], sr[15], sr[7]};
            default: {gb, ga} = {sr[25], sr[17], sr[9],  sr[1], sr[24], sr[16], sr[8],  sr[0]};
            endcase
            ct0_out = {gb[1:0], gb[3:2], ga[1:0], ga[3:2]};
        end
    endfunction

    // ---- décodage registré de l'adresse courante ----
    wire        in_pvc_region = (a[18:12] == 7'h7F);           // 0x2FE000-0x2FFFFF
    wire        in_pvc_regs   = in_pvc_region && (a[11:4] == 8'hFF) && (a[3:0] <= 4'd9);
    reg  f_prot = 1'b0, f_rng0 = 1'b0, f_rng1 = 1'b0, f_pvcr = 1'b0, f_pvcram = 1'b0;
    reg  f_ovl0 = 1'b0, f_ovl1 = 1'b0, f_bank = 1'b0, f_trig = 1'b0, f_std = 1'b0;
    reg  f_ct0 = 1'b0, f_ms5p = 1'b0;
    reg  [1:0] ct0_eh = 2'b00;    // {EVEN, H} = {A2, A3} de la lecture
    always @(posedge clk) begin
        f_prot   <= mode == M_SMA && prot_en && a == prot_addr;
        f_rng0   <= mode == M_SMA && rng_en0 && a == rng_addr0;
        f_rng1   <= mode == M_SMA && rng_en1 && a == rng_addr1;
        f_pvcr   <= mode == M_PVC && in_pvc_regs;
        f_pvcram <= mode == M_PVC && in_pvc_region && !in_pvc_regs;
        f_ovl0   <= ovl_en && a == ovl_addr;
        f_ovl1   <= ovl_en && a == ovl_addr + 19'd1;
        f_bank   <= mode == M_SMA && a == sma_bank_addr;
        f_trig   <= ovl_en && a == ovl_trig;
        f_std    <= mode == M_STD && a[18:3] == 16'hFFFF;    // 0x2FFFF0-0x2FFFFF
        f_ct0    <= mode == M_CT0;
        f_ms5p   <= mode == M_MS5P && a[18:3] == 16'hFFFF;   // 0x2FFFF0-0x2FFFFF
        ct0_eh   <= {a[1], a[2]};
    end

    always @(posedge clk) begin
        sp_port_hit <= f_prot || f_rng0 || f_rng1 || f_pvcr || f_ct0 || f_ms5p;
        sp_rom_hit  <= ovl_active && (f_ovl0 || f_ovl1);
        if (f_pvcr)                  sp_data <= sh[a[3:0]];
        else if (f_prot)             sp_data <= prot_val;
        else if (f_rng0 || f_rng1)   sp_data <= rng;
        else if (f_ct0)              sp_data <= {8'h00, ct0_out(ct0_sr, ct0_eh[1], ct0_eh[0])};
        else if (f_ms5p)             sp_data <= 16'h00A0;
        else if (f_ovl0)             sp_data <= ovl_v0;
        else                         sp_data <= ovl_v1;
    end

    // ---- écritures et effets ----
    reg       pvc_wr = 1'b0;     // écriture PVC registrée, appliquée au cycle suivant
    reg [15:0] pvc_wd;
    reg [1:0]  pvc_wbe;
    reg       pvc_op = 1'b0;     // un registre PVC a été écrit au cycle précédent
    reg [3:0] pvc_reg_w = 4'h0;  // ... lequel
    reg [1:0] sma_pend = 2'd0;   // attente de la lecture de la table SMA

    // remise à zéro au passage en mode jeu, registrée (chemin critique)
    reg start_r = 1'b0;
    always @(posedge clk) start_r <= rst | game_start;

    always @(posedge clk) begin
        base_chg <= 1'b0;
        gw_req   <= 1'b0;

        if (start_r) begin
            p2_base_w  <= 23'h080000;        // 0x100000 octets
            rng        <= rng_seed;
            ovl_active <= 1'b0;
            sma_pend   <= 2'd0;
            pvc_op     <= 1'b0;
            pvc_wr     <= 1'b0;
            for (k = 0; k < 10; k = k + 1) sh[k] <= 16'h0000;
            ct0_sr     <= 32'h0;
        end else begin
            // lecture du générateur : avance d'un pas
            if (port_rd_ev && (f_rng0 || f_rng1)) rng <= {rng[14:0], rng_fb};

            pvc_op <= 1'b0;
            pvc_wr <= 1'b0;
            if (wr_go) begin
                if (f_std && bank_en && wr_be[0]) begin
                    p2_base_w <= 23'h080000 + {d[7:0], 19'd0};
                    base_chg  <= 1'b1;
                end
                if (f_bank) begin
                    tbl_ridx <= sma_idx(d, sma_perm);
                    sma_pend <= 2'd2;
                end
                if (f_ms5p && a[2:0] == 3'd0 && d == 16'h00A0) begin   // 0x2FFFF0
                    p2_base_w <= 23'h000050;                            // octet 0xA0
                    base_chg  <= 1'b1;
                end
                if (f_ms5p && a[2:0] == 3'd2) begin                     // 0x2FFFF4
                    p2_base_w <= {d[7:4], 19'd0};                       // (d >> 4) Mo
                    base_chg  <= 1'b1;
                end
                if (f_ct0) begin
                    if (a[0])            // LOAD = A1
                        ct0_sr <= {ct0_sw(a[18:3]), ct0_sw(d)};
                    else if (a[2])       // H = A3 : deux pixels vers la gauche
                        ct0_sr <= {ct0_sr[29:24], 2'b00, ct0_sr[21:16], 2'b00, ct0_sr[13:8], 2'b00, ct0_sr[5:0], 2'b00};
                    else
                        ct0_sr <= {2'b00, ct0_sr[31:26], 2'b00, ct0_sr[23:18], 2'b00, ct0_sr[15:10], 2'b00, ct0_sr[7:2]};
                end
                if (f_trig) begin
                    if (d == ovl_on)  ovl_active <= 1'b1;
                    if (d == ovl_off) ovl_active <= 1'b0;
                end
                if (f_pvcr) begin
                    pvc_wr    <= 1'b1;
                    pvc_reg_w <= a[3:0];
                    pvc_wd    <= d;
                    pvc_wbe   <= wr_be;
                end
                if (f_pvcram) begin
                    gw_req  <= 1'b1;
                    gw_word <= a[11:0];
                    gw_data <= d;
                    gw_mask <= wr_be;
                end
            end

            // SMA : tbl_ridx est pris au cycle suivant, tbl_q un cycle après
            if (sma_pend == 2'd2) sma_pend <= 2'd1;
            if (sma_pend == 2'd1) begin
                sma_pend  <= 2'd0;
                p2_base_w <= 23'h080000 + tbl_q;
                base_chg  <= 1'b1;
            end

            // PVC : écriture du registre, puis effets au cycle suivant
            if (pvc_wr) begin
                if (pvc_wbe[1]) sh[pvc_reg_w][15:8] <= pvc_wd[15:8];
                if (pvc_wbe[0]) sh[pvc_reg_w][7:0]  <= pvc_wd[7:0];
                pvc_op <= 1'b1;
            end
            if (pvc_op) begin
                if (pvc_reg_w == 4'h0) begin
                    // décompactage de la couleur du mot 0xFF0
                    sh[1] <= {3'b000, sh[0][7:4], sh[0][13], 3'b000, sh[0][3:0], sh[0][12]};
                    sh[2] <= {7'b0000000, sh[0][15], 3'b000, sh[0][11:8], sh[0][14]};
                end else if (pvc_reg_w == 4'h4 || pvc_reg_w == 4'h5) begin
                    // compactage des mots 0xFF4 (vert/bleu) et 0xFF5 (sombre/rouge)
                    sh[6] <= {sh[5][8], sh[5][0], sh[4][8], sh[4][0],
                              sh[5][4:1], sh[4][12:9], sh[4][4:1]};
                end else if (pvc_reg_w[3]) begin
                    // changement de banque : décalage = 0x100000 + {mot 0xFF9, octet haut de 0xFF8}
                    p2_base_w <= 23'h080000 + {sh[9], sh[8][15:9]};
                    base_chg  <= 1'b1;
                    sh[8] <= {8'hA0, sh[8][7:1], 1'b0};
                    sh[9] <= {sh[9][15:8], 1'b0, sh[9][6:0]};
                end
            end
        end
    end
endmodule
