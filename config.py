from os import path

# File Configurations
library_directory = ''
library_file = path.join(library_directory, 'sky130nm.lib')
cell_directory = 'example/sky130_fd_sc_hd__buf_1/'
spice_file = path.join(cell_directory, "sky130_fd_sc_hd__buf_1.spice")
lef_file = path.join(cell_directory, "sky130_fd_sc_hd__buf_1.lef")
output_folder =  path.join(cell_directory, "data")

# Simulation Setup
VDD = '1.8'
time_unit = 1e-9 # 1ns
cap_unit = 1e-12 # 1pF
temp = '25C' # TODO: Need to add this into the timing_harness.cir
# With 0.01ns it take approx 2min for 7*7 cases at two input pin part
sim_step = '0.01n' # Controls the speed of Characterization (make sure to have step less than the minimum Input slew rate)

# Input Vectors
input_transition_time = '0.01n 0.023n 0.0531329n 0.122474n 0.282311n 0.650743n 1.5n' # Only put the unit(do not include sec suffix)
output_caps = '0.0005000000p 0.0012632050p 0.0031913740p 0.0080627180p 0.0203697300p 0.0514622900p 0.1300148000p' # Only put the unit(do not include Farad suffix)
logic_function = '(A)' # Use keyword 'not', 'and' , 'or'

# Liberty Base File Location
lib_file = 'sta_results/sky_mod1.lib'
merged_file_file = 'sta_results/sky_mod2.lib'