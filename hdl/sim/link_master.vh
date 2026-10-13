// Tâches "maître RP2350" pour la liaison 4 bits (inclus dans les bancs de test).
// Nécessite : reg lk_sck ; reg lk_cs0, lk_cs1 (deux FPGA sur le même bus) ;
//             reg lk_sel (FPGA visé) ; reg [3:0] lk_drv ; reg lk_drv_en ;
//             wire [3:0] lk_io (bus partagé) ; real LK_HALF (demi-période, ns)

task lk_nib_out(input [3:0] n);
    begin
        lk_drv = n;  lk_drv_en = 1'b1;
        #(LK_HALF) lk_sck = 1'b1;
        #(LK_HALF) lk_sck = 1'b0;
    end
endtask

task lk_byte_out(input [7:0] b);
    begin
        lk_nib_out(b[7:4]);
        lk_nib_out(b[3:0]);
    end
endtask

task lk_byte_in(output [7:0] b);
    begin
        lk_drv_en = 1'b0;
        #(LK_HALF) lk_sck = 1'b1; b[7:4] = lk_io;
        #(LK_HALF) lk_sck = 1'b0;
        #(LK_HALF) lk_sck = 1'b1; b[3:0] = lk_io;
        #(LK_HALF) lk_sck = 1'b0;
    end
endtask

task lk_begin; begin if (lk_sel) lk_cs1 = 1'b0; else lk_cs0 = 1'b0; #(LK_HALF); end endtask
task lk_end;   begin lk_drv_en = 1'b0; #(LK_HALF) lk_cs0 = 1'b1; lk_cs1 = 1'b1; #(4*LK_HALF); end endtask

task lk_reg_wr(input [7:0] r, input [31:0] v);
    begin
        lk_begin;
        lk_byte_out(8'h01); lk_byte_out(r);
        lk_byte_out(v[31:24]); lk_byte_out(v[23:16]); lk_byte_out(v[15:8]); lk_byte_out(v[7:0]);
        lk_end;
    end
endtask

task lk_reg_rd(input [7:0] r, output [31:0] v);
    reg [7:0] b0, b1, b2, b3;
    begin
        lk_begin;
        lk_byte_out(8'h02); lk_byte_out(r);
        lk_drv_en = 1'b0;
        lk_byte_in(b0);           // octet de retournement (ignoré)
        lk_byte_in(b0); lk_byte_in(b1); lk_byte_in(b2); lk_byte_in(b3);
        v = {b0, b1, b2, b3};
        lk_end;
    end
endtask

task lk_mem_wr_begin(input [7:0] space, input [31:0] addr);
    begin
        lk_begin;
        lk_byte_out(8'h10); lk_byte_out(space);
        lk_byte_out(addr[31:24]); lk_byte_out(addr[23:16]); lk_byte_out(addr[15:8]); lk_byte_out(addr[7:0]);
    end
endtask

task lk_mem_rd_begin(input [7:0] space, input [31:0] addr);
    reg [7:0] dummy;
    begin
        lk_begin;
        lk_byte_out(8'h11); lk_byte_out(space);
        lk_byte_out(addr[31:24]); lk_byte_out(addr[23:16]); lk_byte_out(addr[15:8]); lk_byte_out(addr[7:0]);
        lk_byte_in(dummy);
    end
endtask
