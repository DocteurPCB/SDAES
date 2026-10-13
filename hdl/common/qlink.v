// -----------------------------------------------------------------------------
// qlink : liaison série 4 bits (type QSPI) RP2350 -> FPGA
//
// Le RP2350 est maître. SCK, CS_n et IO[3:0] sont sur-échantillonnés par
// l'horloge système (>= 5x la fréquence SCK). Toutes les entrées passent par
// la même chaîne de synchronisation, ce qui garantit que la donnée lue au
// front montant de SCK détecté correspond bien à ce front.
//
// Trame (CS_n bas), octets transmis en 2 quartets, poids fort d'abord :
//   0x01 REG_WR : reg[8] val[32, MSB d'abord]
//   0x02 REG_RD : reg[8] dummy[8] -> le FPGA renvoie val[32]
//   0x10 MEM_WR : espace[8] adr[32] puis octets de données (adr auto-incr.)
//   0x11 MEM_RD : espace[8] adr[32] dummy[8] -> le FPGA renvoie les octets
//                 (uniquement pour les espaces en BRAM, latence 2 cycles)
// Le FPGA change ses sorties juste après un front montant de SCK ; le maître
// échantillonne au front montant suivant (voir docs/04-liaison-rp2350.md).
// -----------------------------------------------------------------------------
module qlink (
    input  wire        clk,
    input  wire        rst,

    input  wire        sck_i,
    input  wire        cs_n_i,
    input  wire [3:0]  io_i,
    output reg  [3:0]  io_o,
    output reg         io_oe,

    // Registres
    output reg  [7:0]  reg_addr,
    output reg         reg_wr,      // impulsion
    output reg  [31:0] reg_wdata,
    input  wire [31:0] reg_rdata,   // combinatoire selon reg_addr
    output reg         reg_rd,      // impulsion à la capture de reg_rdata

    // Mémoire
    output reg  [7:0]  mem_space,
    output wire [31:0] mem_addr,     // 26 bits utiles (64 Mo)
    output reg         mem_wr,      // impulsion, un octet
    output reg  [7:0]  mem_wdata,
    output reg         mem_rd,      // impulsion ; mem_rdata valide 2 cycles après
    input  wire [7:0]  mem_rdata,

    output reg         xfer_end     // impulsion à la remontée de CS_n
);
    localparam CMD_REG_WR = 8'h01, CMD_REG_RD = 8'h02,
               CMD_MEM_WR = 8'h10, CMD_MEM_RD = 8'h11;

    localparam ST_CMD = 4'd0, ST_REGA = 4'd1, ST_REGD = 4'd2, ST_TURN = 4'd3,
               ST_SPACE = 4'd4, ST_ADDR = 4'd5, ST_WDATA = 4'd6, ST_RDATA = 4'd7,
               ST_IGNORE = 4'd8;

    // --- synchronisation (même profondeur pour toutes les entrées) ---
    reg [2:0] sck_s = 3'b000;
    reg [1:0] cs_s  = 2'b11;
    reg [3:0] io_s1 = 4'h0, io_s2 = 4'h0;
    always @(posedge clk) begin
        sck_s <= {sck_s[1:0], sck_i};
        cs_s  <= {cs_s[0], cs_n_i};
        io_s1 <= io_i;
        io_s2 <= io_s1;
    end
    wire sck_rise = sck_s[1] & ~sck_s[2];
    wire cs_act   = ~cs_s[1];
    reg  cs_act_d = 1'b0;

    reg  [3:0]  state = ST_CMD;
    reg  [7:0]  cmd = 8'h00;
    reg         nib_lo = 1'b0;     // 0 : on attend le quartet fort
    reg  [3:0]  nib_hi = 4'h0;
    reg  [2:0]  cnt = 3'd0;
    reg  [31:0] shift_o = 32'h0;
    reg  [3:0]  onib_cnt = 4'd0;   // quartets restants à émettre
    reg  [25:0] waddr = 26'h0;
    reg  [25:0] mem_addr_r = 26'h0;
    assign mem_addr = {6'd0, mem_addr_r};
    reg  [2:0]  rd_pipe = 3'b000;
    reg  [7:0]  rd_buf = 8'h00;
    // registre de lecture recopié à chaque cycle : reg_addr est stable depuis
    // un octet complet quand la valeur est émise (hors chemin critique)
    reg  [31:0] rdata_q = 32'h0;
    always @(posedge clk) rdata_q <= reg_rdata;

    // octet complet reçu : traité au cycle suivant (étage de registre, le
    // sur-échantillonnage laisse plusieurs cycles par quartet)
    reg        byte_done = 1'b0;
    reg  [7:0] byte_in = 8'h00;
    always @(posedge clk) begin
        byte_done <= cs_act & sck_rise & nib_lo;
        byte_in   <= {nib_hi, io_s2};
    end

    always @(posedge clk) begin
        reg_wr   <= 1'b0;
        reg_rd   <= 1'b0;
        mem_wr   <= 1'b0;
        mem_rd   <= 1'b0;
        xfer_end <= 1'b0;
        cs_act_d <= cs_act;
        rd_pipe  <= {rd_pipe[1:0], mem_rd};
        if (rd_pipe[1]) rd_buf <= mem_rdata;

        if (rst || !cs_act) begin
            state  <= ST_CMD;
            nib_lo <= 1'b0;
            io_oe  <= 1'b0;
            if (cs_act_d && !cs_act) xfer_end <= 1'b1;
        end else begin
            if (sck_rise) begin
                nib_lo <= ~nib_lo;
                if (!nib_lo) nib_hi <= io_s2;
                // émission : un quartet par front montant
                if (io_oe) begin
                    io_o    <= shift_o[31:28];
                    shift_o <= {shift_o[27:0], 4'h0};
                end
            end

            if (byte_done) begin
                case (state)
                ST_CMD: begin
                    cmd <= byte_in;
                    cnt <= 3'd0;
                    case (byte_in)
                        CMD_REG_WR, CMD_REG_RD: state <= ST_REGA;
                        CMD_MEM_WR, CMD_MEM_RD: state <= ST_SPACE;
                        default:                state <= ST_IGNORE;
                    endcase
                end
                ST_REGA: begin
                    reg_addr <= byte_in;
                    state    <= (cmd == CMD_REG_WR) ? ST_REGD : ST_TURN;
                end
                ST_REGD: begin
                    reg_wdata <= {reg_wdata[23:0], byte_in};
                    cnt       <= cnt + 3'd1;
                    if (cnt == 3'd3) begin
                        reg_wr <= 1'b1;
                        state  <= ST_IGNORE;
                    end
                end
                ST_SPACE: begin
                    mem_space <= byte_in;
                    state     <= ST_ADDR;
                end
                ST_ADDR: begin
                    waddr <= {waddr[17:0], byte_in};
                    cnt   <= cnt + 3'd1;
                    if (cnt == 3'd3) begin
                        if (cmd == CMD_MEM_WR) begin
                            state <= ST_WDATA;
                        end else begin
                            // lance la lecture du premier octet pendant le dummy
                            mem_addr_r <= {waddr[17:0], byte_in};
                            waddr    <= {waddr[17:0], byte_in} + 26'd1;
                            mem_rd   <= 1'b1;
                            state    <= ST_TURN;
                        end
                    end
                end
                ST_WDATA: begin
                    mem_addr_r <= waddr;
                    mem_wdata <= byte_in;
                    mem_wr    <= 1'b1;
                    waddr     <= waddr + 26'd1;
                end
                ST_TURN: begin
                    // fin de l'octet de retournement : on commence à émettre
                    io_oe <= 1'b1;
                    if (cmd == CMD_REG_RD) begin
                        io_o    <= rdata_q[31:28];
                        shift_o <= {rdata_q[27:0], 4'h0};
                        reg_rd  <= 1'b1;
                        state   <= ST_IGNORE;
                    end else begin
                        io_o     <= rd_buf[7:4];
                        shift_o  <= {rd_buf[3:0], 28'h0};
                        mem_addr_r <= waddr;
                        waddr    <= waddr + 26'd1;
                        mem_rd   <= 1'b1;
                        state    <= ST_RDATA;
                    end
                end
                ST_RDATA: begin
                    // l'octet précédent vient d'être émis entièrement
                    io_o     <= rd_buf[7:4];
                    shift_o  <= {rd_buf[3:0], 28'h0};
                    mem_addr_r <= waddr;
                    waddr    <= waddr + 26'd1;
                    mem_rd   <= 1'b1;
                end
                default: ;
                endcase
            end
        end
    end
endmodule
