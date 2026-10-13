// -----------------------------------------------------------------------------
// SRAM asynchrone 8 bits (ex. IS61WV10248, 10 ns) partagée entre 3 clients :
//   0 : couche fixe (S)   1 : Z80 (M1)   2 : écritures du chargeur
// Priorité fixe 0 > 1 > 2. Lecture = 3 cycles (30 ns à 100 MHz),
// écriture = 4 cycles.
// -----------------------------------------------------------------------------
module sram_ctrl #(
    parameter AW = 20
) (
    input  wire          clk,
    input  wire          rst,

    input  wire          r0_req,
    input  wire [AW-1:0] r0_addr,
    output reg           r0_ack,      // donnée valide sur rdata
    input  wire          r1_req,
    input  wire [AW-1:0] r1_addr,
    output reg           r1_ack,
    output reg  [7:0]    rdata,

    input  wire          w_req,
    input  wire [AW-1:0] w_addr,
    input  wire [7:0]    w_data,
    output reg           w_ack,

    output reg  [AW-1:0] sr_a,
    output reg  [7:0]    sr_d_o,
    output reg           sr_d_oe,
    input  wire [7:0]    sr_d_i,
    output reg           sr_ce_n,
    output reg           sr_oe_n,
    output reg           sr_we_n
);
    localparam IDLE = 2'd0, RD = 2'd1, WR = 2'd2, GAP = 2'd3;  // GAP : laisse le client retirer sa requête
    reg [1:0] st = IDLE;
    reg [1:0] cnt;
    reg       who;

    always @(posedge clk) begin
        r0_ack <= 1'b0;
        r1_ack <= 1'b0;
        w_ack  <= 1'b0;
        if (rst) begin
            st <= IDLE; sr_ce_n <= 1'b1; sr_oe_n <= 1'b1; sr_we_n <= 1'b1; sr_d_oe <= 1'b0;
        end else case (st)
        IDLE: begin
            sr_ce_n <= 1'b1; sr_oe_n <= 1'b1; sr_we_n <= 1'b1; sr_d_oe <= 1'b0;
            cnt <= 2'd0;
            if (r0_req || r1_req) begin
                who     <= !r0_req;
                sr_a    <= r0_req ? r0_addr : r1_addr;
                sr_ce_n <= 1'b0;
                sr_oe_n <= 1'b0;
                st      <= RD;
            end else if (w_req) begin
                sr_a    <= w_addr;
                sr_d_o  <= w_data;
                sr_d_oe <= 1'b1;
                sr_ce_n <= 1'b0;
                st      <= WR;
            end
        end
        RD: begin
            cnt <= cnt + 2'd1;
            if (cnt == 2'd2) begin
                rdata <= sr_d_i;
                if (who) r1_ack <= 1'b1; else r0_ack <= 1'b1;
                sr_ce_n <= 1'b1; sr_oe_n <= 1'b1;
                st <= GAP;
            end
        end
        WR: begin
            cnt <= cnt + 2'd1;
            case (cnt)
            2'd0: sr_we_n <= 1'b0;
            2'd2: sr_we_n <= 1'b1;
            2'd3: begin
                w_ack <= 1'b1; sr_ce_n <= 1'b1; sr_d_oe <= 1'b0; st <= GAP;
            end
            default: ;
            endcase
        end
        GAP: st <= IDLE;
        endcase
    end
endmodule
