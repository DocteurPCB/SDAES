// Banc de test de la carte PROG : menu en BRAM, boîte aux lettres, bascule
// vers le jeu, lectures P depuis la SDRAM avec banques, lectures ADPCM A/B.
`timescale 1ns/1ps
module tb_prog;
    real LK_HALF = 25.0;
    integer errors = 0;

    reg clk = 0;
    always #3.75 clk = ~clk;
    reg rst = 1;

    reg        lk_sck = 0, lk_cs_n = 1;
    reg  [3:0] lk_drv = 0;
    reg        lk_drv_en = 0;
    wire [3:0] lk_io_o;
    wire       lk_io_oe;
    wire [3:0] lk_io = lk_drv_en ? lk_drv : (lk_io_oe ? lk_io_o : 4'hz);
    `include "link_master.vh"

    // bus 68000
    reg  [19:1] a = 0;
    reg  [15:0] d_wr = 0;
    wire [15:0] d_o;
    wire        d_drive;
    reg         romoe_n = 1, portoe_n = 1, portwel_n = 1, portweu_n = 1;
    // YM2610
    reg  [7:0]  rad = 0, pad = 0;
    reg  [9:8]  ra_l = 0;
    reg  [23:20] ra_u = 0;
    reg  [11:8] pa = 0;
    reg         rmpx = 0, roe_n = 1, pmpx = 0, poe_n = 1;
    wire [7:0]  rad_o, pad_o;
    wire        rad_drive, pad_drive, lk_irq, mode_out, led;

    wire p_cke, p_cs_n, p_ras_n, p_cas_n, p_we_n, p_dq_oe;
    wire [1:0] p_ba, p_dqm; wire [12:0] p_sa; wire [15:0] p_dq_o;
    wire [15:0] p_dq = p_dq_oe ? p_dq_o : 16'hz;
    wire v_cke, v_cs_n, v_ras_n, v_cas_n, v_we_n, v_dq_oe;
    wire [1:0] v_ba, v_dqm; wire [12:0] v_sa; wire [15:0] v_dq_o;
    wire [15:0] v_dq = v_dq_oe ? v_dq_o : 16'hz;

    prog_core #(.SDRAM_INIT_WAIT(200), .SDRAM_REFI(1000)) dut (
        .clk(clk), .rst(rst),
        .a(a), .d_i(d_wr), .d_o(d_o), .d_drive(d_drive),
        .romoe_n(romoe_n), .portoe_n(portoe_n), .portwel_n(portwel_n), .portweu_n(portweu_n),
        .rad_i(rad), .rad_o(rad_o), .rad_drive(rad_drive), .ra_l(ra_l), .ra_u(ra_u), .rmpx(rmpx), .roe_n(roe_n),
        .pad_i(pad), .pad_o(pad_o), .pad_drive(pad_drive), .pa(pa), .pmpx(pmpx), .poe_n(poe_n),
        .lk_sck(lk_sck), .lk_cs_n(lk_cs_n), .lk_io_i(lk_io), .lk_io_o(lk_io_o), .lk_io_oe(lk_io_oe),
        .lk_irq(lk_irq), .mode_out(mode_out),
        .p_cke(p_cke), .p_cs_n(p_cs_n), .p_ras_n(p_ras_n), .p_cas_n(p_cas_n), .p_we_n(p_we_n),
        .p_ba(p_ba), .p_sa(p_sa), .p_dqm(p_dqm), .p_dq_o(p_dq_o), .p_dq_oe(p_dq_oe), .p_dq_i(p_dq),
        .v_cke(v_cke), .v_cs_n(v_cs_n), .v_ras_n(v_ras_n), .v_cas_n(v_cas_n), .v_we_n(v_we_n),
        .v_ba(v_ba), .v_sa(v_sa), .v_dqm(v_dqm), .v_dq_o(v_dq_o), .v_dq_oe(v_dq_oe), .v_dq_i(v_dq),
        .led(led)
    );

    // RB = 10 : la mémoire modélisée couvre les adresses de test sans repliement
    sdram_model #(.DW(16), .RB(10)) u_p (
        .clk(~clk), .cke(p_cke), .cs_n(p_cs_n), .ras_n(p_ras_n), .cas_n(p_cas_n), .we_n(p_we_n),
        .ba(p_ba), .a(p_sa), .dqm(p_dqm), .dq(p_dq));
    sdram_model #(.DW(16), .RB(10)) u_v (
        .clk(~clk), .cke(v_cke), .cs_n(v_cs_n), .ras_n(v_ras_n), .cas_n(v_cas_n), .we_n(v_we_n),
        .ba(v_ba), .a(v_sa), .dqm(v_dqm), .dq(v_dq));

    task check(input [8*48-1:0] what, input [31:0] got, input [31:0] exp);
        if (got !== exp) begin
            $display("ECHEC %0s : lu %h attendu %h", what, got, exp);
            errors = errors + 1;
        end else $display("ok    %0s = %h", what, got);
    endtask

    // Cycle de lecture 68000 à 12 MHz : ~250 ns entre /OE et l'échantillonnage
    real t_oe, worst = 0, alat = 0;
    task m68k_read(input [23:0] addr, output [15:0] v);
        begin
            a = addr[19:1];
            #30;
            if (addr[21]) portoe_n = 0; else romoe_n = 0;
            t_oe = $realtime;
            #200 v = d_o;
            if (!d_drive) begin $display("ECHEC d_drive inactif"); errors = errors + 1; end
            romoe_n = 1; portoe_n = 1;
            #20 if (d_drive) begin $display("ECHEC d_drive reste actif"); errors = errors + 1; end
            #80;
        end
    endtask

    task m68k_write(input [23:0] addr, input [15:0] v);
        begin
            a = addr[19:1]; d_wr = v;
            #30 portwel_n = 0; portweu_n = 0;
            #200 portwel_n = 1; portweu_n = 1;
            #100;
        end
    endtask

    // ADPCM-A : adresse multiplexée sur RAD/RA8-9 (bas sur front montant,
    // haut sur front descendant), puis lecture avec /ROE
    task adpcm_a_read(input [23:0] addr, output [7:0] v);
        begin
            ra_u = addr[23:20];
            {ra_l, rad} = addr[9:0];
            #50 rmpx = 1;
            #50 {ra_l, rad} = addr[19:10];
            #50 rmpx = 0;
            #50 rad = 8'hzz; roe_n = 0;
            t_oe = $realtime;
            fork
                begin @(rad_o); if ($realtime - t_oe > alat) alat = $realtime - t_oe; end
                #300;
            join
            v = rad_o;
            if (!rad_drive) begin $display("ECHEC rad_drive"); errors = errors + 1; end
            roe_n = 1;
            #100;
        end
    endtask

    task adpcm_b_read(input [23:0] addr, output [7:0] v);
        begin
            {pa, pad} = addr[11:0];
            #50 pmpx = 1;
            #50 {pa, pad} = addr[23:12];
            #50 pmpx = 0;
            #50 poe_n = 0;
            #300 v = pad_o;
            poe_n = 1;
            #100;
        end
    endtask

    function [15:0] pword(input [31:0] wa); pword = wa[15:0] ^ 16'h5A00 ^ {wa[23:16], 8'h00}; endfunction
    function [7:0]  vbyte(input [31:0] ba); vbyte = (ba[7:0] * 8'd29 + 8'd7) ^ ba[15:8] ^ ba[23:16]; endfunction

    integer i;
    reg [31:0] v;
    reg [15:0] w;
    reg [7:0]  b;
    reg [31:0] wa, ba;

    task load_pword(input [31:0] wordaddr);
        reg [15:0] x;
        begin
            x = pword(wordaddr);
            lk_mem_wr_begin(8'd0, wordaddr << 1);
            lk_byte_out(x[7:0]);  lk_byte_out(x[15:8]);   // fichier : mots petit-boutistes
            lk_end;
        end
    endtask

    initial begin
        $dumpfile("tb_prog.vcd");
        $dumpvars(0, tb_prog);
        #100 rst = 0;
        #3000;
        lk_reg_rd(8'h00, v);  check("ID", v, 32'h4E475031);
        lk_reg_rd(8'h02, v);  check("SDRAM P+V initialisees", v & 3, 3);

        // ===== MENU =====
        $display("--- mode menu");
        // programme du menu : octets dans l'ordre 68000 (adresse paire = poids fort)
        lk_mem_wr_begin(8'd3, 32'h100);
        lk_byte_out(8'h4E); lk_byte_out(8'h45); lk_byte_out(8'h4F); lk_byte_out(8'h2D);   // "NEO-"
        lk_end;
        m68k_read(24'h000100, w); check("menu P [000100]", w, 16'h4E45);
        m68k_read(24'h000102, w); check("menu P [000102]", w, 16'h4F2D);

        // commande 68000 -> RP2350
        m68k_write(24'h200000, 16'h0001);
        m68k_write(24'h200002, 16'hBEEF);
        lk_mem_rd_begin(8'd2, 32'h0);
        lk_byte_in(b); check("BAL cmd [0]", b, 8'h00);
        lk_byte_in(b); check("BAL cmd [1]", b, 8'h01);
        lk_byte_in(b); check("BAL cmd [2]", b, 8'hBE);
        lk_byte_in(b); check("BAL cmd [3]", b, 8'hEF);
        lk_end;
        check("IRQ au repos", lk_irq, 0);
        m68k_write(24'h2FFFE0, 16'h0000);      // sonnette
        check("IRQ levee", lk_irq, 1);
        m68k_read(24'h2FFFE0, w); check("etat 68000 (irq)", w, 16'h0001);
        lk_reg_wr(8'h09, 32'h0);               // acquittement
        #100 check("IRQ acquittee", lk_irq, 0);

        // réponse RP2350 -> 68000
        lk_mem_wr_begin(8'd2, 32'h100);
        lk_byte_out(8'h12); lk_byte_out(8'h34); lk_byte_out(8'h56); lk_byte_out(8'h78);
        lk_end;
        m68k_read(24'h200100, w); check("BAL reponse [100]", w, 16'h1234);
        m68k_read(24'h200102, w); check("BAL reponse [102]", w, 16'h5678);

        // chargement d'un "jeu"
        load_pword(32'h000080);               // 0x000100 dans P1
        load_pword(32'h080000 + 32'h40);      // P2 banque 0, 0x200080
        load_pword(32'h100000 + 32'h40);      // P2 banque 1, 0x200080
        for (i = 0; i < 4; i = i + 1) begin
            ba = 32'h012345 + i;               // V1 (ADPCM-A)
            lk_mem_wr_begin(8'd1, ba); lk_byte_out(vbyte(ba)); lk_end;
        end
        ba = 32'h400000 + 32'h00ABC;          // V2 (ADPCM-B) placé à 4 Mo
        lk_mem_wr_begin(8'd1, ba); lk_byte_out(vbyte(ba)); lk_end;
        lk_reg_rd(8'h02, v);  check("chargeur au repos", (v >> 2) & 1, 1);

        lk_reg_wr(8'h03, 32'h001FFFFF);       // P = 4 Mo (masque en mots)
        lk_reg_wr(8'h04, 32'h0);              // V1 à 0
        lk_reg_wr(8'h05, 32'h003FFFFF);
        lk_reg_wr(8'h06, 32'h400000);         // V2 à 4 Mo
        lk_reg_wr(8'h07, 32'h000FFFFF);

        // bascule refusée tant que non armé
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("bascule refusee sans armement", mode_out, 0);
        lk_reg_wr(8'h01, 32'h9);              // armé + banques actives
        m68k_read(24'h2FFFE0, w); check("etat 68000 (arme)", w, 16'h0002);
        m68k_write(24'h2FFFE2, 16'h1234);
        check("mauvais code ignore", mode_out, 0);
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("mode jeu", mode_out, 1);

        // ===== JEU =====
        $display("--- mode jeu");
        m68k_read(24'h000100, w); check("P1 [000100]", w, pword(32'h80));
        m68k_read(24'h200080, w); check("P2 banque0 [200080]", w, pword(32'h080040));
        // rafale de lectures sur plusieurs périodes de rafraîchissement
        worst = 0;
        v = u_p.refreshes;
        for (i = 0; i < 80; i = i + 1) begin
            m68k_read(24'h000100, w);
            if (w !== pword(32'h80)) begin $display("ECHEC rafale %0d", i); errors = errors + 1; end
        end
        $display("info  latence max sur la rafale = %0.1f ns (%0d rafraichissements pendant la rafale)", worst, u_p.refreshes - v);
        if (worst > 100.0) begin $display("ECHEC latence 68000 trop elevee"); errors = errors + 1; end
        m68k_write(24'h2FFFF0, 16'h0001);
        m68k_read(24'h200080, w); check("P2 banque1 [200080]", w, pword(32'h100040));
        lk_reg_rd(8'h08, v); check("registre de banque", v, 1);

        adpcm_a_read(24'h012346, b); check("ADPCM-A [012346]", b, vbyte(32'h012346));
        adpcm_a_read(24'h012345, b); check("ADPCM-A [012345]", b, vbyte(32'h012345));
        adpcm_b_read(24'h000ABC, b); check("ADPCM-B [000ABC]", b, vbyte(32'h400ABC));
        $display("info  latence ADPCM-A /SDROE -> donnee max : %0.1f ns", alat);

        // retour menu par le RP2350
        lk_reg_wr(8'h01, 32'h0);
        #100 check("retour menu", mode_out, 0);
        m68k_read(24'h000100, w); check("menu P apres retour", w, 16'h4E45);

        errors = errors + u_p.errors + u_v.errors;
        if (errors == 0) $display("RESULTAT tb_prog : SUCCES");
        else             $display("RESULTAT tb_prog : %0d ERREUR(S)", errors);
        $finish;
    end

    // mesure de latence 68000 : temps entre /OE et la stabilisation de d_o
    always @(d_o) if (!romoe_n || !portoe_n)
        if ($realtime - t_oe > worst) begin
            worst = $realtime - t_oe;
        end

    initial begin #10_000_000; $display("RESULTAT tb_prog : TIMEOUT"); $finish; end
endmodule
