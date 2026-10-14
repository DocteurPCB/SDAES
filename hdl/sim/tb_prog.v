// Banc de test de la carte PROG (FPGA P + FPGA V sur le même bus de liaison) :
// menu en BRAM, boîte aux lettres, bascule vers le jeu, lectures P depuis la
// SDRAM (anticipées ou non, avec banques), lectures ADPCM A/B.
`timescale 1ns/1ps
module tb_prog;
    real LK_HALF = 25.0;
    integer errors = 0;

    reg clk = 0;
    always #5 clk = ~clk;            // 100 MHz
    reg rst = 1;

    reg        lk_sck = 0, lk_cs0 = 1, lk_cs1 = 1, lk_sel = 0;
    reg  [3:0] lk_drv = 0;
    reg        lk_drv_en = 0;
    wire [3:0] lk_io_p, lk_io_v;
    wire       lk_oe_p, lk_oe_v;
    wire [3:0] lk_io = lk_drv_en ? lk_drv : lk_oe_p ? lk_io_p : lk_oe_v ? lk_io_v : 4'hz;
    `include "link_master.vh"
    localparam P = 1'b0, V = 1'b1;

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
    wire        rad_drive, pad_drive, lk_irq, mode, led_p, led_v;

    wire p_cke, p_cs_n, p_ras_n, p_cas_n, p_we_n, p_dq_oe;
    wire [1:0] p_ba, p_dqm; wire [12:0] p_sa; wire [15:0] p_dq_o;
    wire [15:0] p_dq = p_dq_oe ? p_dq_o : 16'hz;
    wire v_cke, v_cs_n, v_ras_n, v_cas_n, v_we_n, v_dq_oe;
    wire [1:0] v_ba, v_dqm; wire [12:0] v_sa; wire [15:0] v_dq_o;
    wire [15:0] v_dq = v_dq_oe ? v_dq_o : 16'hz;

    wire [2:0] wait_n;
    prog_p_core #(.SDRAM_INIT_WAIT(200)) dut_p (
        .clk(clk), .rst(rst),
        .a(a), .d_i(d_wr), .d_o(d_o), .d_drive(d_drive),
        .romoe_n(romoe_n), .portoe_n(portoe_n), .portwel_n(portwel_n), .portweu_n(portweu_n),
        .wait_n(wait_n),
        .lk_sck(lk_sck), .lk_cs_n(lk_cs0), .lk_io_i(lk_io), .lk_io_o(lk_io_p), .lk_io_oe(lk_oe_p),
        .lk_irq(lk_irq), .mode_out(mode),
        .sd_cke(p_cke), .sd_cs_n(p_cs_n), .sd_ras_n(p_ras_n), .sd_cas_n(p_cas_n), .sd_we_n(p_we_n),
        .sd_ba(p_ba), .sd_a(p_sa), .sd_dqm(p_dqm), .sd_dq_o(p_dq_o), .sd_dq_oe(p_dq_oe), .sd_dq_i(p_dq),
        .led(led_p));

    prog_v_core #(.SDRAM_INIT_WAIT(200)) dut_v (
        .clk(clk), .rst(rst),
        .rad_i(rad), .rad_o(rad_o), .rad_drive(rad_drive), .ra_l(ra_l), .ra_u(ra_u), .rmpx(rmpx), .roe_n(roe_n),
        .pad_i(pad), .pad_o(pad_o), .pad_drive(pad_drive), .pa(pa), .pmpx(pmpx), .poe_n(poe_n),
        .lk_sck(lk_sck), .lk_cs_n(lk_cs1), .lk_io_i(lk_io), .lk_io_o(lk_io_v), .lk_io_oe(lk_oe_v),
        .mode_in(mode),
        .sd_cke(v_cke), .sd_cs_n(v_cs_n), .sd_ras_n(v_ras_n), .sd_cas_n(v_cas_n), .sd_we_n(v_we_n),
        .sd_ba(v_ba), .sd_a(v_sa), .sd_dqm(v_dqm), .sd_dq_o(v_dq_o), .sd_dq_oe(v_dq_oe), .sd_dq_i(v_dq),
        .led(led_v));

    sdram_model #(.DW(16), .RB(11)) u_p (
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

    // Cycle de lecture 68000 : adresse posée AS_DELAY ns avant /OE, donnée
    // échantillonnée 200 ns après /OE. Mesure /OE -> dernière transition de d_o.
    real t_oe, t_last, worst = 0;
    real AS_DELAY = 40.0;
    task m68k_read(input [23:0] addr, output [15:0] v);
        begin
            a = addr[19:1];
            #(AS_DELAY);
            if (addr[21]) portoe_n = 0; else romoe_n = 0;
            t_oe = $realtime; t_last = t_oe;
            #200 v = d_o;
            if (t_last - t_oe > worst) worst = t_last - t_oe;
            if (!d_drive) begin $display("ECHEC d_drive inactif"); errors = errors + 1; end
            romoe_n = 1; portoe_n = 1;
            #20 if (d_drive) begin $display("ECHEC d_drive reste actif"); errors = errors + 1; end
            #73;
        end
    endtask
    always @(d_o) if (!romoe_n || !portoe_n) t_last = $realtime;

    task m68k_write(input [23:0] addr, input [15:0] v);
        begin
            a = addr[19:1]; d_wr = v;
            #30 portwel_n = 0; portweu_n = 0;
            #200 portwel_n = 1; portweu_n = 1;
            #100;
        end
    endtask

    real t_v, alat = 0;
    task adpcm_a_read(input [23:0] addr, output [7:0] v);
        begin
            ra_u = addr[23:20];
            {ra_l, rad} = addr[9:0];
            #50 rmpx = 1;
            #50 {ra_l, rad} = addr[19:10];
            #50 rmpx = 0;
            #50 rad = 8'hzz; roe_n = 0;
            t_v = $realtime;
            fork
                begin @(rad_o); if ($realtime - t_v > alat) alat = $realtime - t_v; end
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
    reg [31:0] v, hits;
    reg [15:0] w;
    reg [7:0]  b;
    reg [31:0] ba;
    reg [15:0] rng_v;

    task load_pwords(input [31:0] wordaddr, input integer n);
        integer k;
        reg [15:0] x;
        begin
            lk_sel = P;
            lk_mem_wr_begin(8'd0, wordaddr << 1);
            for (k = 0; k < n; k = k + 1) begin
                x = pword(wordaddr + k);
                lk_byte_out(x[7:0]);  lk_byte_out(x[15:8]);   // fichier : mots petit-boutistes
            end
            lk_end;
        end
    endtask

    initial begin
        $dumpfile("tb_prog.vcd");
        $dumpvars(0, tb_prog);
        #100 rst = 0;
        #3000;
        lk_sel = P; lk_reg_rd(8'h00, v);  check("ID P", v, 32'h4E475032);
        lk_sel = V; lk_reg_rd(8'h00, v);  check("ID V", v, 32'h4E475632);
        lk_sel = P;
        check("attente par défaut (pleine vitesse)", wait_n, 3'b111);
        lk_reg_wr(8'h04, 32'h6);  lk_reg_rd(8'h04, v);
        check("ROMWAIT = 1 cycle", {29'd0, wait_n}, 32'h6);
        lk_reg_wr(8'h04, 32'h7);
        lk_sel = P; lk_reg_rd(8'h02, v);  check("SDRAM P initialisee", v & 1, 1);
        lk_sel = V; lk_reg_rd(8'h02, v);  check("SDRAM V initialisee", v & 1, 1);

        // ===== MENU =====
        $display("--- mode menu");
        lk_sel = P;
        lk_mem_wr_begin(8'd3, 32'h100);
        lk_byte_out(8'h4E); lk_byte_out(8'h45); lk_byte_out(8'h4F); lk_byte_out(8'h2D);   // "NEO-"
        lk_end;
        m68k_read(24'h000100, w); check("menu P [000100]", w, 16'h4E45);
        m68k_read(24'h000102, w); check("menu P [000102]", w, 16'h4F2D);

        m68k_write(24'h200000, 16'h0001);
        m68k_write(24'h200002, 16'hBEEF);
        lk_mem_rd_begin(8'd2, 32'h0);
        lk_byte_in(b); check("BAL cmd [0]", b, 8'h00);
        lk_byte_in(b); check("BAL cmd [1]", b, 8'h01);
        lk_byte_in(b); check("BAL cmd [2]", b, 8'hBE);
        lk_byte_in(b); check("BAL cmd [3]", b, 8'hEF);
        lk_end;
        check("IRQ au repos", lk_irq, 0);
        m68k_write(24'h2FFFE0, 16'h0000);
        check("IRQ levee", lk_irq, 1);
        m68k_read(24'h2FFFE0, w); check("etat 68000 (irq)", w, 16'h0001);
        lk_reg_wr(8'h09, 32'h0);
        #100 check("IRQ acquittee", lk_irq, 0);

        lk_mem_wr_begin(8'd2, 32'h100);
        lk_byte_out(8'h12); lk_byte_out(8'h34); lk_byte_out(8'h56); lk_byte_out(8'h78);
        lk_end;
        m68k_read(24'h200100, w); check("BAL reponse [100]", w, 16'h1234);
        m68k_read(24'h200102, w); check("BAL reponse [102]", w, 16'h5678);

        // chargement d'un "jeu"
        load_pwords(32'h000080, 64);           // 0x000100-0x00017F dans P1
        load_pwords(32'h080000 + 32'h40, 4);   // P2 banque 0, 0x200080
        load_pwords(32'h100000 + 32'h40, 4);   // P2 banque 1, 0x200080
        lk_sel = V;
        for (i = 0; i < 4; i = i + 1) begin
            ba = 32'h012345 + i;
            lk_mem_wr_begin(8'd0, ba); lk_byte_out(vbyte(ba)); lk_end;
        end
        ba = 32'h400000 + 32'h00ABC;
        lk_mem_wr_begin(8'd0, ba); lk_byte_out(vbyte(ba)); lk_end;
        lk_reg_rd(8'h02, v);  check("chargeur V au repos", (v >> 1) & 1, 1);
        lk_sel = P;
        lk_reg_rd(8'h02, v);  check("chargeur P au repos", (v >> 2) & 1, 1);

        lk_sel = P; lk_reg_wr(8'h03, 32'h001FFFFF);
        lk_sel = V;
        lk_reg_wr(8'h04, 32'h0);
        lk_reg_wr(8'h05, 32'h003FFFFF);
        lk_reg_wr(8'h06, 32'h400000);
        lk_reg_wr(8'h07, 32'h000FFFFF);
        lk_reg_wr(8'h01, 32'h1);                // V armé

        lk_sel = P;
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("bascule refusee sans armement", mode, 0);
        lk_reg_wr(8'h01, 32'h9);                // P armé + banques
        m68k_read(24'h2FFFE0, w); check("etat 68000 (arme)", w, 16'h0002);
        m68k_write(24'h2FFFE2, 16'h1234);
        check("mauvais code ignore", mode, 0);
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("mode jeu (MODE)", mode, 1);
        #100;
        lk_sel = V; lk_reg_rd(8'h02, v); check("V suit MODE", (v >> 2) & 1, 1);

        // ===== JEU =====
        $display("--- mode jeu");
        m68k_read(24'h000100, w); check("P1 [000100]", w, pword(32'h80));
        m68k_read(24'h200080, w); check("P2 banque0 [200080] (type change)", w, pword(32'h080040));

        // rafale de lectures séquentielles (code), plusieurs rafraîchissements
        worst = 0;
        v = u_p.refreshes;
        lk_sel = P; lk_reg_rd(8'h14, hits);
        for (i = 0; i < 100; i = i + 1) begin
            m68k_read(24'h000100 + ((i % 64) << 1), w);
            if (w !== pword(32'h80 + (i % 64))) begin $display("ECHEC rafale %0d : %h", i, w); errors = errors + 1; end
        end
        $display("info  68000 /OE -> donnee, max sur la rafale (adresse 40 ns avant /OE) : %0.1f ns (%0d rafraichissements)",
                 worst, u_p.refreshes - v);
        lk_reg_rd(8'h14, v);
        $display("info  anticipations reussies : %0d / 100", (v - hits) & 16'hFFFF);
        if (worst > 100.0) begin $display("ECHEC latence 68000 trop elevee avec anticipation"); errors = errors + 1; end

        // alternance code (P1) / données (P2), adresse 40 ns avant /OE
        worst = 0;
        for (i = 0; i < 20; i = i + 1) begin
            m68k_read((i & 1) ? 24'h200080 : 24'h000100 + (i << 1), w);
            if (w !== ((i & 1) ? pword(32'h080040) : pword(32'h80 + i))) begin
                $display("ECHEC alternance %0d : %h", i, w); errors = errors + 1;
            end
        end
        $display("info  alternance P1/P2 (adresse 40 ns avant /OE) : %0.1f ns", worst);
        if (worst > 100.0) begin $display("ECHEC latence alternance"); errors = errors + 1; end

        // pire cas : adresse posée au même instant que /OE, alternance P1/P2
        AS_DELAY = 0.0; worst = 0;
        for (i = 0; i < 20; i = i + 1) begin
            m68k_read((i & 1) ? 24'h200080 : 24'h000100 + (i << 1), w);
            if (w !== ((i & 1) ? pword(32'h080040) : pword(32'h80 + i))) begin
                $display("ECHEC pire cas %0d : %h", i, w); errors = errors + 1;
            end
        end
        $display("info  pire cas (adresse en meme temps que /OE, alternance P1/P2) : %0.1f ns", worst);
        if (worst > 130.0) begin $display("ECHEC latence pire cas"); errors = errors + 1; end
        AS_DELAY = 40.0;

        m68k_write(24'h2FFFF0, 16'h0001);
        m68k_read(24'h200080, w); check("P2 banque1 [200080]", w, pword(32'h100040));
        lk_reg_rd(8'h08, v); check("base P2 (mots) apres banque 1", v, 32'h100000);

        adpcm_a_read(24'h012346, b); check("ADPCM-A [012346]", b, vbyte(32'h012346));
        adpcm_a_read(24'h012345, b); check("ADPCM-A [012345]", b, vbyte(32'h012345));
        adpcm_b_read(24'h000ABC, b); check("ADPCM-B [000ABC]", b, vbyte(32'h400ABC));
        $display("info  latence ADPCM-A /SDROE -> donnee max : %0.1f ns", alat);

        lk_sel = P; lk_reg_wr(8'h01, 32'h0);
        #100 check("retour menu", mode, 0);
        m68k_read(24'h000100, w); check("menu P apres retour", w, 16'h4E45);

        // ================= PROTECTIONS =================
        // ---- SMA (table de banques, protection, générateur) + superposition KOF98
        $display("--- SMA + superposition");
        lk_sel = P;
        load_pwords(32'h080000 + 32'h3CC000/2 + 32'h40, 1);   // banque SMA choisie, 0x200080
        lk_reg_wr(8'h03, 32'h007FFFFF);         // P = 16 Mo
        lk_reg_wr(8'h0A, 32'h101);              // mode SMA + superposition
        lk_reg_wr(8'h0B, 32'h7FFF8);            // registre de banque en 0x2FFFF0
        lk_reg_wr(8'h0C, 32'h5CA86E);           // bits 14,6,8,10,12,5 -> numéro 0..5
        lk_reg_wr(8'h0D, 32'h80000000 | 32'h7F223);   // protection en 0x2FE446
        lk_reg_wr(8'h0E, 32'h9A37);
        lk_reg_wr(8'h0F, 32'h80000000 | 32'h7FFFC);   // générateur en 0x2FFFF8
        lk_reg_wr(8'h15, 32'h80000000 | 32'h7FFFD);   // et 0x2FFFFA
        lk_reg_wr(8'h16, 32'h2345);
        lk_reg_wr(8'h17, 32'h5555);             // déclencheur en 0x20AAAA
        lk_reg_wr(8'h18, 32'h009000F0);
        lk_reg_wr(8'h19, 32'h80);               // mots 0x000100 et 0x000102
        lk_reg_wr(8'h1A, 32'h00C200FD);
        // table : entrée i = i * 0x10000, sauf l'entrée 0x2B = 0x3CC000
        lk_mem_wr_begin(8'd4, 32'h0);
        for (i = 0; i < 64; i = i + 1) begin
            ba = (i == 8'h2B) ? 32'h3CC000 : i * 32'h10000;
            lk_byte_out(ba[31:24]); lk_byte_out(ba[23:16]); lk_byte_out(ba[15:8]); lk_byte_out(ba[7:0]);
        end
        lk_end;
        lk_reg_wr(8'h01, 32'h1);
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("mode jeu SMA", mode, 1);
        m68k_read(24'h2FE446, w); check("SMA lecture de protection", w, 16'h9A37);
        rng_v = 16'h2345;
        for (i = 0; i < 6; i = i + 1) begin
            m68k_read((i & 1) ? 24'h2FFFFA : 24'h2FFFF8, w);
            if (w !== rng_v) begin $display("ECHEC generateur SMA %0d : %h attendu %h", i, w, rng_v); errors = errors + 1; end
            rng_v = {rng_v[14:0], rng_v[2] ^ rng_v[3] ^ rng_v[5] ^ rng_v[6] ^ rng_v[7] ^ rng_v[11] ^ rng_v[12] ^ rng_v[15]};
        end
        $display("ok    generateur SMA (6 lectures)");
        m68k_write(24'h2FFFF0, 16'h4460);       // bits 14,6,10,5 -> numéro 0x2B
        m68k_read(24'h200080, w); check("SMA banque 0x2B [200080]", w, pword(32'h080000 + 32'h3CC000/2 + 32'h40));
        m68k_read(24'h000100, w); check("superposition inactive", w, pword(32'h80));
        m68k_write(24'h20AAAA, 16'h0090);
        m68k_read(24'h000100, w); check("superposition [000100]", w, 16'h00C2);
        m68k_read(24'h000102, w); check("superposition [000102]", w, 16'h00FD);
        m68k_write(24'h20AAAA, 16'h00F0);
        m68k_read(24'h000100, w); check("superposition retiree", w, pword(32'h80));
        lk_reg_wr(8'h01, 32'h0);
        #100;

        // ---- PVC
        $display("--- PVC");
        load_pwords(32'h080000 + 32'h012340/2 + 32'h40, 1);
        lk_reg_wr(8'h0A, 32'h2);
        lk_reg_wr(8'h01, 32'h1);
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("mode jeu PVC", mode, 1);
        m68k_write(24'h2FFFE0, 16'hABCD);      // décompactage
        m68k_read(24'h2FFFE2, w); check("PVC decompactage vert/bleu", w, 16'h191A);   // g={C,b13=1} b={D,b12=0}
        m68k_read(24'h2FFFE4, w); check("PVC decompactage sombre/rouge", w, 16'h0116); // s=1 r={B,b14=0}
        m68k_write(24'h2FFFE8, 16'h1E1F);      // gb
        m68k_write(24'h2FFFEA, 16'h011E);      // sr
        m68k_read(24'h2FFFEC, w);
        check("PVC compactage", w, {1'b1, 1'b0, 1'b0, 1'b1, 4'hF, 4'hF, 4'hF});
        m68k_write(24'h2FFFF2, 16'h0123);      // octets hauts de l'adresse de banque
        m68k_write(24'h2FFFF0, 16'h40FF);      // octet bas -> banque 0x100000 + 0x012340
        m68k_read(24'h200080, w); check("PVC banque [200080]", w, pword(32'h080000 + 32'h012340/2 + 32'h40));
        m68k_read(24'h2FFFF0, w); check("PVC registre FF8 apres banque", w, 16'hA0FE);
        m68k_read(24'h2FFFF2, w); check("PVC registre FF9 apres banque", w, 16'h0123);
        m68k_write(24'h2FE100, 16'h1357);      // RAM de protection (SDRAM)
        m68k_write(24'h2FE102, 16'h2468);
        m68k_read(24'h2FE100, w); check("PVC RAM [2FE100]", w, 16'h1357);
        m68k_read(24'h2FE102, w); check("PVC RAM [2FE102]", w, 16'h2468);
        m68k_write(24'h2FE100, 16'hBEEF);      // relecture immédiate après écriture
        m68k_read(24'h2FE100, w); check("PVC RAM reecrite", w, 16'hBEEF);
        lk_reg_wr(8'h01, 32'h0);

        // ---- PRO-CT0 (Fatal Fury 2) : valeurs attendues calculées avec un modèle
        //      transcrit de MAME (prot_fatfury2.cpp + alpha_8921.cpp)
        $display("--- PRO-CT0");
        lk_reg_wr(8'h0A, 32'h3);
        lk_reg_wr(8'h01, 32'h1);
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("mode jeu PRO-CT0", mode, 1);
        m68k_write(24'h2A5C32, 16'h1234);
        m68k_read(24'h200000, w); check("PRO-CT0 chargement, EVEN=0 H=0", w, 16'h00C3);
        m68k_read(24'h200004, w); check("PRO-CT0 chargement, EVEN=1 H=0", w, 16'h003C);
        m68k_read(24'h200008, w); check("PRO-CT0 chargement, EVEN=0 H=1", w, 16'h0003);
        m68k_read(24'h20000C, w); check("PRO-CT0 chargement, EVEN=1 H=1", w, 16'h0030);
        m68k_write(24'h200000, 16'h0000);
        m68k_read(24'h200000, w); check("PRO-CT0 decalage a droite", w, 16'h0069);
        m68k_write(24'h200008, 16'h0000);
        m68k_write(24'h200008, 16'h0000);
        m68k_read(24'h200008, w); check("PRO-CT0 decalage a gauche, H=1", w, 16'h0061);
        m68k_read(24'h20000C, w); check("PRO-CT0 decalage a gauche, EVEN=1", w, 16'h0016);
        m68k_write(24'h2FFFF2, 16'hBEEF);
        m68k_read(24'h200000, w); check("PRO-CT0 rechargement", w, 16'h00B7);
        m68k_read(24'h200004, w); check("PRO-CT0 rechargement, EVEN=1", w, 16'h007B);
        lk_reg_wr(8'h01, 32'h0);

        // ---- Metal Slug 5 Plus (MAME : write_bankprot_ms5p, mslug5p_prot_r)
        $display("--- Metal Slug 5 Plus");
        load_pwords(32'h000050, 1);
        load_pwords(32'h100000 + 32'h40, 1);
        lk_reg_wr(8'h0A, 32'h4);
        lk_reg_wr(8'h01, 32'h1);
        m68k_write(24'h2FFFE2, 16'h5A5A);
        check("mode jeu MS5P", mode, 1);
        m68k_read(24'h2FFFF0, w); check("MS5P lecture de protection", w, 16'h00A0);
        m68k_read(24'h2FFFFE, w); check("MS5P lecture de protection (fin)", w, 16'h00A0);
        m68k_write(24'h2FFFF4, 16'h0020);      // (0x20 >> 4) Mo = 2 Mo
        m68k_read(24'h200080, w); check("MS5P banque 2 Mo [200080]", w, pword(32'h100000 + 32'h40));
        m68k_write(24'h2FFFF0, 16'h00A0);      // fenêtre à l'octet 0xA0
        m68k_read(24'h200000, w); check("MS5P fenetre a 0xA0 [200000]", w, pword(32'h000050));
        m68k_write(24'h2FFFF0, 16'h0012);      // autre valeur : sans effet
        m68k_read(24'h200000, w); check("MS5P ecriture ignoree", w, pword(32'h000050));
        lk_reg_wr(8'h01, 32'h0);

        errors = errors + u_p.errors + u_v.errors;
        if (errors == 0) $display("RESULTAT tb_prog : SUCCES");
        else             $display("RESULTAT tb_prog : %0d ERREUR(S)", errors);
        $finish;
    end

    initial begin #20_000_000; $display("RESULTAT tb_prog : TIMEOUT"); $finish; end
endmodule
