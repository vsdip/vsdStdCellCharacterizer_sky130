module FA ( A, B, Cin, S, Cout, clk);
    input A, B, Cin, clk;
    output S, Cout;
    wire s1, c1, c2;
    
    sky130_fd_sc_hd__xor2_1 g1(s1, A, B);
    sky130_fd_sc_hd__xor2_1 g2(S, s1, Cin);
    sky130_fd_sc_hd__and2_0 g3(c1, s1, Cin);
    sky130_fd_sc_hd__and2_0 g4(c2, A, B);
    sky130_fd_sc_hd__or2_0 g5(cout, c1,cC2);
endmodule