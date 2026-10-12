`timescale 1ns/1ps
module tb;
parameter real I2C_HALF=25;
reg sys_clk=0,i2c_clk=0,rst=1;
always #50 sys_clk=~sys_clk;
always #I2C_HALF i2c_clk=~i2c_clk;
reg [13:0] csr_adr=0;
reg [31:0] csr_dat_w=0;
wire [31:0] csr_dat_r;
reg csr_re=0,csr_we=0;
reg target_sda=0,target_scl=0;
wire scl_oe,sda_oe,scl=~(scl_oe|target_scl),sda=~(sda_oe|target_sda);
integer falls=0,results=0,i;
reg [31:0] status,data;
dut d(.sys_clk(sys_clk),.sys_rst(rst),.i2c_clk(i2c_clk),.i2c_rst(rst),
 .csr_adr(csr_adr),.csr_re(csr_re),.csr_we(csr_we),.csr_dat_w(csr_dat_w),.csr_dat_r(csr_dat_r),
 .scl_oe(scl_oe),.sda_oe(sda_oe),.scl_i(scl),.sda_i(sda));
task write_register(input [13:0] address,input [31:0] value);
 begin
  @(negedge sys_clk); csr_adr=address; csr_dat_w=value; csr_we=1;
  @(negedge sys_clk); csr_we=0;
 end
endtask
task read_register(input [13:0] address,output [31:0] value);
 begin
  @(negedge sys_clk); csr_adr=address; csr_re=1;
  @(posedge sys_clk); #1; value=csr_dat_r;
  @(negedge sys_clk); csr_re=0;
 end
endtask
initial begin
 repeat(4) @(negedge sys_clk);
 rst=0;
 write_register(5,0); // Standard speed.
 repeat(10) @(negedge sys_clk);
 write_register(0,1); // Active.
 write_register(1,256); // TX=0, RX=1.
 write_register(2,80); // Address 0x50.
 read_register(4,status);
 if(!status[0]) $fatal(1,"TX FIFO must have room");
 write_register(3,0); // Exactly one transfer request.
 for(i=0;i<1300;i=i+1) begin
  read_register(4,status);
  if(status[1]) begin
   read_register(3,data);
   results=results+1;
   $display("RESULT %0d %08h %08h",results,data,status);
  end
 end
 $display("COUNT %0d",results);
 $finish;
end
// Pin-level target. Ignore zero-time delta transitions while combinational HDL settles.
integer bit_count=0, read_index=0;
reg started=0, addr_phase=1, read_mode=0, ignored=0;
reg [7:0] received=0, read_data=8'h96;
reg prev_scl=1, prev_sda=1;
always @(scl or sda) begin
 #0.001;
 if(!rst && (scl!=prev_scl || sda!=prev_sda)) begin
  $display("EDGE %0t %0d %0d",$time,scl,sda);
  if(scl && prev_scl && sda!=prev_sda) begin
   if(!sda) begin
    $display("START %0t",$time);
    started=1; addr_phase=1; read_mode=0; ignored=0; bit_count=0; received=0;
   end else if(started) begin
    $display("STOP %0t",$time);
    started=0;
   end
  end else if(started && scl!=prev_scl) begin
   if(scl) begin
    if(bit_count<8) begin
     received={received[6:0],sda}; bit_count=bit_count+1;
     if(bit_count==8) $display("BYTE %0t %0d %02h",$time,addr_phase ? 0 : read_mode ? 2 : 1,received);
    end else begin
     $display("ACK %0t %0d",$time,sda); bit_count=9;
     if(read_mode && !addr_phase && sda) ignored=1;
    end
   end else begin
    falls=falls+1;
    if(bit_count==9) begin
     if(addr_phase) begin
      addr_phase=0; read_mode=received[0]; ignored=(received[7:1]!=7'h50); read_index=0;
     end else if(read_mode) read_index=read_index+1;
     bit_count=0; received=0;
    end
    case(read_index)
     0:read_data=8'h96; 1:read_data=8'h3c; 2:read_data=8'ha5;
     3:read_data=8'h5a; default:read_data=8'h81;
    endcase
    if(ignored) target_sda=0;
    else if(bit_count==8) target_sda=!read_mode || addr_phase;
    else if(read_mode && !addr_phase) target_sda=~read_data[7-bit_count];
    else target_sda=0;
   end
  end
 end
 prev_scl=scl; prev_sda=sda;
end
endmodule
