// Banc de test de la carte CHA (FPGA C + FPGA SM sur le même bus de liaison) :
// chargement, puis lecture C (ZMC2), S (couche fixe) et M1 (Z80 avec
// banques), en mode menu puis en mode jeu.
`timescale 1ns/1ps
module tb_cha;
    real LK_HALF = 25.0;
    integer errors = 0;

    reg clk = 0;
    always #5 clk = ~clk;            // 100 MHz
    reg rst = 1;

    reg        lk_sck = 0, lk_cs0 = 1, lk_cs1 = 1, lk_sel = 0;
    reg  [3:0] lk_drv = 0;
    reg        lk_drv_en = 0;
    wire [3:0] lk_io_c, lk_io_s;
    wire       lk_oe_c, lk_oe_s;
    wire [3:0] lk_io = lk_drv_en ? lk_drv : lk_oe_c ? lk_io_c : lk_oe_s ? lk_io_s : 4'hz;
    `include "link_master.vh"
    localparam C = 1'b0, SM = 1'b1;

    reg  [23:0] pbus = 0;
    reg         pck1b = 1, pck2b = 1, ca4 = 0, s2h1 = 0, clk_12m = 0, even = 0, load = 0, h = 0;
    wire [3:0]  gad, gbd;
    wire        dota, dotb;
    wire [7:0]  fixd;
    reg  [15:0] sda = 0;
    reg         sdmrd_n = 1, sdrom_n = 1, sdrd0_n = 1;
    wire [7:0]  sdd_o;
    wire        sdd_drive;
    reg         mode = 0;
    wire        led_c, led_s;

    wire sd_cke, sd_cs_n, sd_ras_n, sd_cas_n, sd_we_n, sd_dq_oe;
    wire [1:0] sd_ba, sd_dqm; wire [12:0] sd_a; wire [15:0] sd_dq_o;
    wire [15:0] sd_dq = sd_dq_oe ? sd_dq_o : 16'hz;
    wire [19:0] sr_a; wire [7:0] sr_d_o; wire sr_d_oe, sr_ce_n, sr_oe_n, sr_we_n;
    wire [7:0] sr_d = sr_d_oe ? sr_d_o : 8'hz;

    cha_c_core #(.SDRAM_INIT_WAIT(200)) dut_c (
        .clk(clk), .rst(rst),
        .pbus(pbus), .pck1b(pck1b), .ca4(ca4), .clk_12m(clk_12m), .even(even), .load(load), .h(h),
        .gad(gad), .gbd(gbd), .dota(dota), .dotb(dotb),
        .lk_sck(lk_sck), .lk_cs_n(lk_cs0), .lk_io_i(lk_io), .lk_io_o(lk_io_c), .lk_io_oe(lk_oe_c),
        .mode_in(mode),
        .sd_cke(sd_cke), .sd_cs_n(sd_cs_n), .sd_ras_n(sd_ras_n), .sd_cas_n(sd_cas_n), .sd_we_n(sd_we_n),
        .sd_ba(sd_ba), .sd_a(sd_a), .sd_dqm(sd_dqm), .sd_dq_o(sd_dq_o), .sd_dq_oe(sd_dq_oe), .sd_dq_i(sd_dq),
        .led(led_c));

    cha_sm_core dut_s (
        .clk(clk), .rst(rst),
        .pbus(pbus[15:0]), .pck2b(pck2b), .s2h1(s2h1), .fixd(fixd),
        .sda(sda), .sdmrd_n(sdmrd_n), .sdrom_n(sdrom_n), .sdrd0_n(sdrd0_n),
        .sdd_o(sdd_o), .sdd_drive(sdd_drive),
        .lk_sck(lk_sck), .lk_cs_n(lk_cs1), .lk_io_i(lk_io), .lk_io_o(lk_io_s), .lk_io_oe(lk_oe_s),
        .mode_in(mode),
        .sr_a(sr_a), .sr_d_o(sr_d_o), .sr_d_oe(sr_d_oe), .sr_d_i(sr_d),
        .sr_ce_n(sr_ce_n), .sr_oe_n(sr_oe_n), .sr_we_n(sr_we_n), .led(led_s));

    sdram_model #(.DW(16), .RB(6), .CB(10)) u_sd (
        .clk(~clk), .cke(sd_cke), .cs_n(sd_cs_n), .ras_n(sd_ras_n), .cas_n(sd_cas_n), .we_n(sd_we_n),
        .ba(sd_ba), .a(sd_a), .dqm(sd_dqm), .dq(sd_dq));
    sram_model u_sr (.a(sr_a), .d(sr_d), .ce_n(sr_ce_n), .oe_n(sr_oe_n), .we_n(sr_we_n));


    // ---- couche fixe NEO-CMC : séquence LSPC d'une ligne (colonne 63, puis 0..46) ----
    localparam [11:0] FTILE = 12'h0AB;
    reg [11:0] fword [0:6];          // mots des colonnes 40-46
    function [18:0] faddr(input [1:0] bk, input hf, input h1, input [2:0] ln);
        faddr = {bk, FTILE, hf, h1, ln};
    endfunction
    function [7:0] fval(input [18:0] a);  fval = {a[18:17], a[4:3], 1'b1, a[2:0]}; endfunction
    task fix_pulse(input [15:0] pv, input do_chk, input [1:0] bk, input [2:0] ln);
        begin
            pbus[15:0] = pv;
            #50 pck2b = 0; #55 pck2b = 1;
            if (do_chk) begin
                #250 s2h1 = 0; #5 check("CMC banque, 2H1=0", fixd, fval(faddr(bk, pv[15], 1'b0, ln)));
                s2h1 = 1; #5 check("CMC banque, 2H1=1", fixd, fval(faddr(bk, pv[15], 1'b1, ln)));
                #245;
            end else #510;
        end
    endtask
    task fix_line(input [2:0] ln, input integer chk_col, input [1:0] bk);
        integer c, hf;
        reg [11:0] t;
        begin
            fix_pulse({1'b0, ln, 12'h000}, 0, 0, ln);   // colonne 63
            fix_pulse({1'b1, ln, 12'h000}, 0, 0, ln);
            for (c = 0; c < 47; c = c + 1)
                for (hf = 0; hf < 2; hf = hf + 1) begin
                    t = (c >= 40) ? fword[c - 40] : FTILE;
                    fix_pulse({hf[0], ln, t}, c == chk_col, bk, ln);
                end
        end
    endtask

    // --------------------------------------------------------------------
    localparam [19:0] TILE = 20'h00123;
    localparam [3:0]  LINE = 4'd5;
    function [7:0] cbyte(input [31:0] byte_addr);
        cbyte = (byte_addr[7:0] * 8'd37 + 8'd11) ^ byte_addr[15:8];
    endfunction
    function [7:0] sbyte(input [31:0] a);  sbyte = a[7:0] ^ 8'h3C ^ a[15:8]; endfunction
    function [7:0] mbyte(input [31:0] a);  mbyte = a[7:0] ^ 8'hC3 ^ a[15:8] ^ a[18:16]; endfunction

    function [31:0] expected_cr(input half);
        reg [31:0] wa, ba, w;
        begin
            wa = {7'd0, TILE, half, LINE};
            ba = wa << 2;
            w  = {cbyte(ba+3), cbyte(ba+2), cbyte(ba+1), cbyte(ba)};
            expected_cr = {w[31:24], w[15:8], w[23:16], w[7:0]};
        end
    endfunction

    task check(input [8*48-1:0] what, input [31:0] got, input [31:0] exp);
        if (got !== exp) begin
            $display("ECHEC %0s : lu %h attendu %h", what, got, exp);
            errors = errors + 1;
        end else $display("ok    %0s = %h", what, got);
    endtask

    task zmc2_check(input [31:0] cr, input flip);
        integer n;
        reg [3:0] ea, eb;
        begin
            h = flip; even = 0;
            #10 load = 1;
            #41.6 clk_12m = 1; #41.6 clk_12m = 0;   // front descendant : chargement
            #2 load = 0;
            for (n = 0; n < 4; n = n + 1) begin
                #3;
                if (!flip) begin
                    ea = {cr[24+2*n], cr[16+2*n], cr[8+2*n], cr[2*n]};
                    eb = {cr[25+2*n], cr[17+2*n], cr[9+2*n], cr[2*n+1]};
                end else begin
                    ea = {cr[31-2*n], cr[23-2*n], cr[15-2*n], cr[7-2*n]};
                    eb = {cr[30-2*n], cr[22-2*n], cr[14-2*n], cr[6-2*n]};
                end
                if (gad !== ea || gbd !== eb) begin
                    $display("ECHEC ZMC2 pixel %0d (h=%0d) : GAD=%h GBD=%h attendu %h %h", 2*n, flip, gad, gbd, ea, eb);
                    errors = errors + 1;
                end
                #36.6 clk_12m = 1; #41.6 clk_12m = 0;
            end
            $display("ok    ZMC2 h=%0d mot %h", flip, cr);
        end
    endtask

    // Chronogramme réel du LSPC : CA4 bascule au front descendant de 12M où
    // le ZMC2 prend la donnée ; il doit prendre la moitié de l'ancien CA4.
    task zmc2_race(input [31:0] cr_old);
        integer n;
        reg [3:0] ea, eb;
        begin
            h = 0; even = 0;
            #10 load = 1;
            #41.6 clk_12m = 1; #41.6 clk_12m = 0; ca4 = ~ca4;   // même instant
            #2 load = 0;
            for (n = 0; n < 4; n = n + 1) begin
                #3;
                ea = {cr_old[24+2*n], cr_old[16+2*n], cr_old[8+2*n], cr_old[2*n]};
                eb = {cr_old[25+2*n], cr_old[17+2*n], cr_old[9+2*n], cr_old[2*n+1]};
                if (gad !== ea || gbd !== eb) begin
                    $display("ECHEC ZMC2 CA4 simultane, pixel %0d : GAD=%h GBD=%h attendu %h %h", 2*n, gad, gbd, ea, eb);
                    errors = errors + 1;
                end
                #36.6 clk_12m = 1; #41.6 clk_12m = 0;
            end
            $display("ok    ZMC2 CA4 bascule avec LOAD : ancienne moitie %h", cr_old);
        end
    endtask

    real t0, zlat = 0;
    task z80_read(input [15:0] addr, output [7:0] v);
        begin
            sda = addr;
            #60 sdmrd_n = 0; sdrom_n = 0;
            t0 = $realtime;
            fork
                begin @(dut_s.z_dout); if ($realtime - t0 > zlat) zlat = $realtime - t0; end
                #250;
            join
            v = sdd_o;
            if (!sdd_drive) begin $display("ECHEC sdd_drive inactif"); errors = errors + 1; end
            sdmrd_n = 1; sdrom_n = 1;
            #20 if (sdd_drive) begin $display("ECHEC sdd_drive reste actif"); errors = errors + 1; end
            #100;
        end
    endtask

    task z80_bank(input [7:0] port, input [7:0] bank);
        begin
            sda = {bank, port};
            #60 sdrd0_n = 0;
            #250 sdrd0_n = 1;
            #100;
        end
    endtask

    integer i;
    reg [31:0] v, base;
    reg [7:0]  b;

    initial begin
        $dumpfile("tb_cha.vcd");
        $dumpvars(0, tb_cha);
        #100 rst = 0;
        #3000;

        lk_sel = C;  lk_reg_rd(8'h00, v);  check("ID C", v, 32'h4E474332);
        lk_sel = SM; lk_reg_rd(8'h00, v);  check("ID SM", v, 32'h4E475332);
        lk_sel = C;  lk_reg_rd(8'h02, v);  check("SDRAM C initialisee", v & 1, 1);

        // --- ROM C : deux moitiés de la ligne LINE de la tuile TILE
        lk_sel = C;
        base = {7'd0, TILE, 1'b0, LINE} << 2;
        lk_mem_wr_begin(8'd0, base);
        for (i = 0; i < 4; i = i + 1) lk_byte_out(cbyte(base + i));
        lk_end;
        base = {7'd0, TILE, 1'b1, LINE} << 2;
        lk_mem_wr_begin(8'd0, base);
        for (i = 0; i < 4; i = i + 1) lk_byte_out(cbyte(base + i));
        lk_end;
        // diagnostic : mot de 16 bits de poids fort de la moitié 1
        lk_reg_wr(8'h10, (base >> 1) + 1);
        #2000 lk_reg_rd(8'h11, v);
        check("diag SDRAM C", v, {cbyte(base+3), cbyte(base+2)});
        lk_reg_rd(8'h02, v);  check("chargeur C au repos", (v >> 1) & 1, 1);

        // --- S et M1 dans la SRAM du FPGA SM
        lk_sel = SM;
        base = {15'd0, 12'h456, 1'b1, 1'b0, 3'd3};
        lk_mem_wr_begin(8'd0, base);     lk_byte_out(sbyte(base));     lk_end;
        lk_mem_wr_begin(8'd0, base + 8); lk_byte_out(sbyte(base + 8)); lk_end;
        lk_mem_wr_begin(8'd0, 32'h80000 + 32'h1234);  lk_byte_out(mbyte(32'h1234));  lk_end;
        lk_mem_wr_begin(8'd0, 32'h80000 + 32'h0C010); lk_byte_out(mbyte(32'h0C010)); lk_end;
        // menu : police (espace 2) et pilote Z80 (espace 3)
        lk_mem_wr_begin(8'd2, {12'h041, 1'b0, 1'b0, 3'd2}); lk_byte_out(8'h11); lk_end;
        lk_mem_wr_begin(8'd2, {12'h041, 1'b0, 1'b1, 3'd2}); lk_byte_out(8'h22); lk_end;
        lk_mem_wr_begin(8'd3, 32'h0066);
        lk_byte_out(8'hC3); lk_byte_out(8'h00); lk_byte_out(8'h01);
        lk_end;
        lk_reg_wr(8'h10, 32'h80000 + 32'h1234);
        #2000 lk_reg_rd(8'h11, v);
        check("diag SRAM", v, mbyte(32'h1234));
        lk_reg_rd(8'h02, v);  check("chargeur SM au repos", (v >> 1) & 1, 1);

        // ================= mode MENU =================
        $display("--- mode menu");
        pbus = {8'd0, 1'b0, 3'd2, 12'h041};   // P15 = demi-tuile, P14..12 = ligne
        #50 pck2b = 0; #80 pck2b = 1;
        #300 s2h1 = 0; #5 check("menu FIX 2H1=0", fixd, 8'h11);
        s2h1 = 1; #5 check("menu FIX 2H1=1", fixd, 8'h22);
        z80_read(16'h0066, b); check("menu M1 [0066]", b, 8'hC3);
        z80_read(16'h0068, b); check("menu M1 [0068]", b, 8'h01);
        pbus = {4'd0, LINE, TILE[15:0]};
        #50 pck1b = 0; #80 pck1b = 1;
        #300 ca4 = 0;
        zmc2_check(32'h0, 0);

        // ================= mode JEU =================
        $display("--- mode jeu");
        lk_sel = C;  lk_reg_wr(8'h03, 32'h00FFFFFF);  lk_reg_wr(8'h01, 32'h1);
        lk_sel = SM; lk_reg_wr(8'h04, 32'h0001FFFF);  lk_reg_wr(8'h05, 32'h0001FFFF);  lk_reg_wr(8'h01, 32'h1);
        mode = 1;
        #200;
        lk_sel = C;  lk_reg_rd(8'h02, v);  check("C en mode jeu", (v >> 2) & 1, 1);
        lk_sel = SM; lk_reg_rd(8'h02, v);  check("SM en mode jeu", (v >> 2) & 1, 1);

        pbus = {TILE[19:16], LINE, TILE[15:0]};
        #50 pck1b = 0; #80 pck1b = 1;
        t0 = $realtime;
        @(dut_c.c_half1);
        $display("info  latence PCK1B -> mots C disponibles : %0.1f ns", $realtime - t0);
        #150 ca4 = 0;
        zmc2_check(expected_cr(0), 0);
        ca4 = 1;
        zmc2_check(expected_cr(1), 0);
        zmc2_check(expected_cr(1), 1);
        zmc2_race(expected_cr(1));            // CA4 passe à 0 au moment du LOAD
        zmc2_check(expected_cr(0), 0);        // LOAD suivant : nouvelle moitié

        pbus = {8'd0, 1'b1, 3'd3, 12'h456};
        #50 pck2b = 0; #80 pck2b = 1;
        t0 = $realtime;
        @(dut_s.fix1);
        $display("info  latence PCK2B -> octets S disponibles : %0.1f ns", $realtime - t0);
        #200 s2h1 = 0; #5 check("FIX 2H1=0", fixd, sbyte({15'd0, 12'h456, 1'b1, 1'b0, 3'd3}));
        s2h1 = 1; #5 check("FIX 2H1=1", fixd, sbyte({15'd0, 12'h456, 1'b1, 1'b1, 3'd3}));


        // ================= banques de couche fixe NEO-CMC =================
        $display("--- couche fixe NEO-CMC");
        begin : cmc
            integer bk, hf, h1, ln;
            for (bk = 0; bk < 4; bk = bk + 1) for (hf = 0; hf < 2; hf = hf + 1)
                for (h1 = 0; h1 < 2; h1 = h1 + 1) for (ln = 0; ln < 8; ln = ln + 1)
                    u_sr.mem[faddr(bk, hf, h1, ln)] = fval(faddr(bk, hf, h1, ln));
        end
        lk_sel = SM; lk_reg_wr(8'h04, 32'h0007FFFF);
        // type 2 : banque de la colonne 13 = bits 9:8 du mot de la colonne 42, inversés
        lk_reg_wr(8'h06, 32'h2);
        fword[0] = 12'h000; fword[1] = 12'h000; fword[2] = 12'h100; fword[3] = 12'h000;
        fword[4] = 12'h000; fword[5] = 12'h000; fword[6] = 12'h000;
        fix_line(3'd7, 99, 0);                       // dernière ligne de la rangée précédente
        fix_line(3'd0, 13, 2'd2);                    // colonne 13 : banque ~01 = 2
        fix_line(3'd1, 12, 2'd3);                    // colonne 12 : banque ~00 = 3
        lk_reg_rd(8'h06, v);  check("CMC colonne lue en dernier", (v >> 8) & 63, 46);
        // type 1 : drapeau 0x200 en colonne 40, banque 0xF01 en colonne 44 (même rangée)
        lk_reg_wr(8'h06, 32'h1);
        fword[0] = 12'h000; fword[4] = 12'hF01;
        fix_line(3'd2, 13, 2'd3);                    // sans drapeau : banque 3 par défaut
        fword[0] = 12'h200;
        fix_line(3'd3, 99, 0);
        fix_line(3'd4, 5, 2'd2);                     // drapeau vu : banque ~01 = 2
        lk_reg_wr(8'h06, 32'h0);  lk_reg_wr(8'h04, 32'h0001FFFF);

        z80_read(16'h1234, b); check("M1 [1234]", b, mbyte(32'h1234));
        z80_bank(8'h0B, 8'h03);
        z80_read(16'h8010, b); check("M1 banque3 [8010]", b, mbyte(32'h0C010));
        $display("info  latence lecture Z80 (M1) max : %0.1f ns", zlat);

        mode = 0;
        #200 lk_sel = C; lk_reg_rd(8'h02, v);  check("retour menu", (v >> 2) & 1, 0);

        errors = errors + u_sd.errors;
        if (errors == 0) $display("RESULTAT tb_cha : SUCCES");
        else             $display("RESULTAT tb_cha : %0d ERREUR(S)", errors);
        $finish;
    end

    initial begin #5_000_000; $display("RESULTAT tb_cha : TIMEOUT"); $finish; end
endmodule
