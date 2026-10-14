// -----------------------------------------------------------------------------
// Banques de couche fixe des cartes NEO-CMC (ROM S de 512 Ko).
//
// Le jeu écrit les numéros de banque en VRAM 0x7500-0x75FF, c'est-à-dire
// dans les colonnes 40 à 47 de la carte de la couche fixe, hors écran. Le
// LSPC lit ces colonnes à chaque ligne et les présente sur le bus P comme
// des numéros de tuile ordinaires (P[11:0]) au verrou PCK2B : la cartouche
// les capture au passage.
//
// Repérage de la colonne (déduit du LSPC du cœur MiSTer NeoGeo, modules
// videosync / slow_cycle) : à chaque ligne, le LSPC lit la colonne 63 puis
// les colonnes 0 à 46, deux impulsions PCK2B par colonne (P15 = demi-tuile),
// soit 96 impulsions ; le numéro de ligne (P[14:12], P12 change à chaque
// ligne) change à la lecture de la colonne 63. Le premier PCK2B qui montre
// un nouveau P[14:12] est donc la colonne 63, demi-tuile P15.
//
// Type 2 (KOF 2000, SVC Chaos, KOF 2003 ; MAME : FIX_BANKTYPE_KOF2000) :
//   banque de la tuile x de la rangée y = bits (11-2k, 10-2k) du mot de la
//   colonne 40 + x/6, rangée y-1 (k = x mod 6), inversés. Capturés à la
//   dernière ligne (7) de la rangée y-1, après ses colonnes visibles.
// Type 1 (Garou, Metal Slug 3/4 ; MAME : FIX_BANKTYPE_GAROU) : drapeau 0x200
//   en colonne 40/41, banque (0xFFxx, bits 1:0 inversés) en colonne 44/45 de
//   la même rangée. La cartouche ne voit pas le numéro de rangée à l'écran :
//   la banque est appliquée dès qu'elle est vue et reste en place jusqu'au
//   changement suivant (exact pour une banque constante, approché pour les
//   changements par rangée de Garou). Banque 3 par défaut, comme MAME.
//
// Sortie bank valide 2 cycles après ev. À VALIDER sur matériel.
// -----------------------------------------------------------------------------
module cmc_fix (
    input  wire        clk,
    input  wire        rst,
    input  wire [1:0]  mode,      // 0 : aucune, 1 : type 1, 2 : type 2
    input  wire        ev,        // un verrou PCK2B (domaine clk)
    input  wire [15:0] p,         // valeur verrouillée, stable à ev
    output reg  [1:0]  bank = 2'd0,
    output reg  [5:0]  col_dbg = 6'd0
);
    reg  [2:0]  line_prev = 3'd0;
    reg  [6:0]  idx = 7'd0;       // impulsion dans la ligne (0 = colonne 63, 1re moitié)
    reg  [5:0]  col = 6'd0;       // colonne lue (63, puis 0..46)
    reg  [2:0]  grp = 3'd0;       // colonne / 6 (type 2)
    reg  [2:0]  sub = 3'd0;       // colonne mod 6
    reg         second = 1'b0;    // 2e impulsion de la colonne
    reg  [15:0] p_q = 16'h0;
    reg         st1 = 1'b0;

    reg  [11:0] w2 [0:7];         // mots des colonnes 40-46 (inversés) ; 7 inutilisé
    reg  [1:0]  bank1 = 2'd3;
    reg         flag40 = 1'b0, flag41 = 1'b0;

    integer i;
    initial for (i = 0; i < 8; i = i + 1) w2[i] = 12'h0;

    // étape 1 : position de l'impulsion
    always @(posedge clk) begin
        st1 <= ev;
        if (ev) begin
            p_q       <= p;
            line_prev <= p[14:12];
            if (p[14:12] != line_prev) begin
                idx    <= {6'd0, p[15]};
                col    <= 6'd63;
                second <= p[15];
                grp    <= 3'd7;          // colonne 63 : hors des 40 colonnes
                sub    <= 3'd5;          // la suivante sera 0 / 0
            end else begin
                idx    <= idx + 7'd1;
                second <= ~second;
                if (second) begin        // nouvelle colonne
                    col <= (col == 6'd63) ? 6'd0 : col + 6'd1;
                    if (sub == 3'd5) begin sub <= 3'd0; grp <= grp + 3'd1; end
                    else sub <= sub + 3'd1;
                end
            end
        end
        if (rst) begin idx <= 7'd0; col <= 6'd0; second <= 1'b0; end
    end

    // étape 2 : capture des mots de banque et choix de la banque
    wire [11:0] w_cur  = w2[grp];
    wire [1:0]  bank2  = w_cur[11 - 2 * sub -: 2];
    always @(posedge clk) begin
        if (st1) begin
            col_dbg <= col;
            if (mode == 2'd2 && second && p_q[14:12] == 3'd7 && col >= 6'd40 && col <= 6'd46)
                w2[col - 6'd40] <= ~p_q[11:0];
            if (mode == 2'd1 && second) begin
                if (col == 6'd40) flag40 <= (p_q[11:0] == 12'h200);
                if (col == 6'd41) flag41 <= (p_q[11:0] == 12'h200);
                if (((col == 6'd44 && flag40) || (col == 6'd45 && flag41)) && &p_q[11:8])
                    bank1 <= ~p_q[1:0];
            end
            case (mode)
            2'd1:    bank <= bank1;
            2'd2:    bank <= (col < 6'd40) ? bank2 : 2'd0;
            default: bank <= 2'd0;
            endcase
        end
        if (rst) begin bank1 <= 2'd3; flag40 <= 1'b0; flag41 <= 1'b0; end
    end
endmodule
