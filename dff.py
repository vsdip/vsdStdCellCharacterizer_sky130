#!/usr/bin/python3
import numpy as np
import json
import re
from os import path
from os import makedirs
import subprocess
import argparse
import scripts.timing as timing
import scripts.merge as merge

# Default Values
input_transition = '0.01n 0.5n 1.5n'
clock_transition = '0.01n 0.5n 1.5n'
input_transition_timing = '0.01n 0.023n 0.0531329n 0.122474n 0.282311n 0.650743n 1.5n'
load_capacitor = '0.0005p 0.0012105800p 0.002931p 0.00709641p 0.0171815p 0.0415991p 0.100718p'
runs = 20  # Bisection method num of iterations
#
merged_file = ''
output_dir = ''


def lef_extract(lef_file):
    """ Extract Pin and Area information from the lef file"""

    try:
        with open(lef_file) as lef_doc:
            data = lef_doc.read()
    except:
        print('>> Check the lef file location provided in config.py')
        exit(0)

    blocks = []
    current_block_name = None
    current_pin_name = None
    block_content = []
    cell_dict = {'cell_name': None,
                 'area': None,
                 'pin': {}
                 }

    for line in data.splitlines():
        tokens = line.split()
        length = len(tokens)
        # Extracting Cell Name
        if line.startswith("MACRO") or line.startswith("SITE"):
            assert current_block_name is None, (current_block_name, line)
            assert not block_content, block_content
            assert length == 2, line
            current_block_name = tokens[1]
            block_content.append(line)
            cell_dict['cell_name'] = current_block_name
        # Extracting Size
        if 'SIZE' in line and length == 5:
            try:
                size = float(tokens[1]) * float(tokens[3])
                cell_dict['area'] = round(size, 4)
            except:
                print(
                    f'\n For lef File:{lef_file}: Size Undefined \n Extract the lef file properly\n')

        # Extracting Pins
        if 'PIN' in line and length == 2:
            current_pin_name = tokens[1]
            cell_dict['pin'].update({current_pin_name: {}})

        # Extracting Direction
        if 'DIRECTION' in line and length == 3 and current_pin_name != None:
            direction_value = tokens[1]
            cell_dict['pin'][current_pin_name].update(
                {'direction': direction_value})

        if 'USE' in line and length == 3 and current_pin_name != None:
            use_value = tokens[1]
            cell_dict['pin'][current_pin_name].update({'use': use_value})

        elif current_block_name is not None:
            block_content.append(line)
            if line.startswith("END"):
                assert line != "END LIBRARY", current_block_name
                tokens = line.split()
                assert len(tokens) == 2, line
                assert tokens[1] == current_block_name, (
                    line, current_block_name)
                blocks.append("\n".join(block_content))
                current_block_name = None
                block_content = []

    assert not current_block_name, current_block_name
    assert not block_content, block_content

    return cell_dict


def display_lef(lef_dict):
    """ Used to display lef extracted information to user for verification of pins"""
    cell_name = lef_dict['cell_name']
    cell_area = lef_dict['area']
    pin_list = list(lef_dict['pin'].keys())
    input_pins_list = [
        pin for pin in pin_list if lef_dict['pin'][pin]['direction'] == 'INPUT']
    output_pins_list = [
        pin for pin in pin_list if lef_dict['pin'][pin]['direction'] == 'OUTPUT']
    power_pins_list = [
        pin for pin in pin_list if lef_dict['pin'][pin]['direction'] == 'INOUT']
    clk_pins_list = [
        pin for pin in pin_list if lef_dict['pin'][pin]['use'] == 'CLOCK']
    input_pins_str = ' '.join(input_pins_list)
    output_pins_str = ' '.join(output_pins_list)
    power_pins_str = ' '.join(power_pins_list)
    print('-----Lef data------')
    print(f'- Cell Name: {cell_name}')
    print(f'- Cell Area: {cell_area}')
    print(f'- Input Pins: {input_pins_str}')
    print(f'- Output Pins: {output_pins_str}')
    print(f'- Power Pins: {power_pins_str}')

    if clk_pins_list:
        clk_pins_str = ' '.join(clk_pins_list)
        print(f'- CLK Pins: {clk_pins_str}')
    # Checking for input pin with signal Use
    input_signal_pin = [
        pin for pin in pin_list if lef_dict['pin'][pin]['use'] == 'SIGNAL'
        and lef_dict['pin'][pin]['direction'] == 'INPUT']

    return pin_list, lef_dict, input_signal_pin, output_pins_list


def read_spice(spice_file):
    """ Reads the .spice file specified in -sp argument
        Returns: Pins (str)
                 Spice Card Name  (str)"""

    with open(spice_file, "r") as file_object:
        # read file content
        spice_txt = file_object.read()

    subckt = [line for line in spice_txt.split(
        '\n') if '.subckt' in line][0].split()
    spice_card = subckt[1]
    pins = ' '.join(subckt[2:])
    print('\n-----SPICE data------')
    print(f'- Card Name: {spice_card}')
    print(f'- Pins: {pins}')
    return pins, spice_card


def pins_verification(spice_pins_str, lef_pins_list):
    """ Checks if same pin name exists in the SPICE as taken in Lef file """
    print('\n-----Pin Verification------')
    spice_pins_list = spice_pins_str.split(' ')
    for s_pin in spice_pins_list:
        if s_pin in lef_pins_list:
            print(f'- {s_pin} exists in lef file')
        else:
            print(f'- [ERROR] {s_pin} doesn\'t exists in lef file')
            exit(0)


def Simulation_env(spice_file, edge_type, netlist_pins, spice_card, act_pin, out_pin, clk_pin, sim_type):
    """Creates *.cir file"""

    include_statements = f".include 'sky130nm.lib' \n.include '{spice_file}'"

    power, signal = voltage_deductions(act_pin, clk_pin, netlist_pins)

    control_text, working_folder = ng_postscript(sim_type, act_pin,
                                                 out_pin, clk_pin, edge_type)
    harness_name = f"{sim_type}_harness.cir"
    harness_file = path.join(output_dir, harness_name)
    final_text = \
        f"""Test Harness  for {spice_card}\n{include_statements}
    .options savecurrents
    X1 {netlist_pins} {spice_card}
    * Power Supplies
    {power}
    * Signal Supplies
    {signal}
    * CLoad
    CLoad {output_pins[0]} 0 1f
    * Control Generations
    .control
    {control_text}
    rusage
    quit
    .endc"""

    with open(harness_file, "w") as file_doc:
        file_doc.write(final_text)

    return harness_file, working_folder


def voltage_deductions(active_pin, clk_pin, netlist_pins):
    """ Setup the Supply voltage and Logic Signal as per the logic function """

    # Setting up Power Supplies Voltages
    VDD = '1.8'
    power_supplies = ['VPWR', 'VDD', 'VPB']
    gnd_supplies = ['VGND', 'VNB', 'VSS']
    power_str = '\n'.join(
        [f'V{net} {net} 0 DC {VDD}' for net in power_supplies if net in netlist_pins])
    gnd_str = '\n'.join(
        [f'V{net} {net} 0 DC 0' for net in gnd_supplies if net in netlist_pins])

    # Setting Up Signal Voltages
    signal_supplies = f'V{active_pin} {active_pin} 0 PULSE(0 {VDD} 6n 0.01n 0.01n 10ns 20ns)'
    # TODO:Correct this using input pin for clock calculations, remove hardcoded VD supply
    clk_supp = f'\nV{clk_pin} {clk_pin} 0 PULSE(0 {VDD} 0 0.01n 0.01n 15ns 30ns)' if active_pin != clk_pin else '\nVD D 0 0'
    signal_supplies += clk_supp
    power_supplies = power_str + '\n' + gnd_str

    return power_supplies, signal_supplies


def ng_postscript(sim_type, active_pin, out_pin, clk_pin, edge_type):
    """ Generate ngspice control commands for timing_harness"""

    if sim_type == 'rise_hold':
        ext_folder = f'data/{active_pin}/hold'
        working_folder = path.join(output_dir, ext_folder)

        control_str = \
            f"""let verbose = 0
    shell rm {working_folder}/rise_hold.txt
    foreach in_transition {input_transition}
    echo "d_tran:$in_transition" >> {working_folder}/rise_hold.txt
    foreach clk_tran {clock_transition}
        let clk_base_t = 6n
        let clk_high_t = clk_base_t + $clk_tran*1.666

        if $in_transition = $clk_tran
            let off_time = 0.4n
        else
            let  off_time = 0.0
        end
        let d_base_t_rise = clk_base_t - 4n
        let d_high_t_rise = d_base_t_rise + $in_transition*1.66
        * Swing Limit
        let lower_t = -3n
        let upper_t = 2n
        let mid_point = (lower_t + upper_t)/2
        let initial = 0
        let runs = {runs}
        let tpd_ref = 0
        dowhile initial < runs
            * Reference Simulation
            if initial = 0
                let mid_point = 6n
            end
            let d_base_t_fall = clk_high_t + mid_point
            let d_high_t_fall = d_base_t_fall + $in_transition*1.666
            alter @V{active_pin}[PWL] = [ 0 1.8 $&d_base_t_rise 1.8 $&d_high_t_rise 0 $&d_base_t_fall 0 $&d_high_t_fall 1.8]
            alter @V{clk_pin}[PWL] = [ 0 0 0.2n 1.8 1.5n 0 $&clk_base_t 0 $&clk_high_t 1.8 ]
            tran 0.005n 20n
            run
            reset
            if verbose = 1
                plot q d clk
            end
            let tpd = 0
            * measurement commands for thold and Propagation Delay(CLK-Q)
            meas tran thold trig v({clk_pin}) val=0.9 RISE=2 targ v({active_pin}) val=0.9 RISE=1
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 FALL=1
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 FALL=2
            * Reference Simulation
            if initial = 0
                let tpd_ref = tpd
                let tpd_ref_dis = tpd_ref/1n
                let mid_point = (lower_t + upper_t)/2
                echo "tpd_ref: $&tpd_ref_dis" >> {working_folder}/rise_hold.txt
            else
                if verbose = 1
                    echo "Iteration: $&initial" >> {working_folder}/rise_hold.txt
                    echo "in_Upper_Bound:$&upper_t:in_Lower_Bound:$&lower_t" >> {working_folder}/rise_hold.txt
                end
            * Changing the upper and lower values as per the results
                let tpd_goal = 1.1*tpd_ref
                let error = (tpd-tpd_goal)/tpd_goal
                if tpd = 0
                    let lower_t = mid_point
                else
                    if tpd_goal < tpd
                        let lower_t = mid_point
                    end
                    if tpd_goal > tpd
                        let upper_t = mid_point
                    end
                end
                * To Stop the loop if error is low
                if error > 0
                    if error < 0.07m
                        let initial = 1000
                    end
                end
            end
            let initial = initial + 1
            let mid_point = (lower_t + upper_t)/2
            let tpd_num=tpd/1n
            let thold_num=thold/1n
            if verbose = 1
                echo "final_Upper_Bound:$&upper_t:final_Upper_Bound_Lower_Bound:$&lower_t" >> {working_folder}/rise_hold.txt
                echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:hold_time:$&thold_num:error_pdelay:$&error" >> {working_folder}/rise_hold.txt
            end
        end
        if verbose = 0
            echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:hold_time:$&thold_num:error_pdelay:$&error" >> {working_folder}/rise_hold.txt
        end
    end
    end
    quit"""

    elif sim_type == 'fall_hold':
        ext_folder = f'data/{active_pin}/hold'
        working_folder = path.join(output_dir, ext_folder)

        control_str = \
            f"""let verbose = 0
    shell rm {working_folder}/fall_hold.txt
    foreach in_transition {input_transition}
    echo "d_tran:$in_transition" >> {working_folder}/fall_hold.txt
    foreach clk_tran {clock_transition}
        let clk_base_t = 6n
        let clk_high_t = clk_base_t + $clk_tran*1.666

        if $in_transition = $clk_tran
            let off_time = 0.4n
        else
            let  off_time = 0.0
        end
        let d_base_t_rise = clk_base_t - 4n
        let d_high_t_rise = d_base_t_rise + $in_transition*1.66
        * Swing Limit
        let lower_t = -3n
        let upper_t = 2n
        let mid_point = (lower_t + upper_t)/2
        let initial = 0
        let runs = {runs}
        let tpd_ref = 0
        dowhile initial < runs
            * Reference Simulation
            if initial = 0
                let mid_point = 6n
            end
            let d_base_t_fall = clk_high_t + mid_point
            let d_high_t_fall = d_base_t_fall + $in_transition*1.666
            alter @V{active_pin}[PWL] = [ 0 0 $&d_base_t_rise 0 $&d_high_t_rise 1.8 $&d_base_t_fall 1.8 $&d_high_t_fall 0]
            alter @V{clk_pin}[PWL] = [ 0 0 0.2n 1.8 1.5n 0 $&clk_base_t 0 $&clk_high_t 1.8 ]
            tran 0.005n 20n
            run
            reset
            if verbose = 1
                plot q d clk
            end
            let tpd = 0
            * measurement commands for thold and Propagation Delay(CLK-Q)
            meas tran thold trig v({clk_pin}) val=0.9 RISE=2 targ v({active_pin}) val=0.9 FALL=1
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 RISE=1
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 RISE=2
            * Reference Simulation
            if initial = 0
                let tpd_ref = tpd
                let tpd_ref_dis = tpd_ref/1n
                let mid_point = (lower_t + upper_t)/2
                echo "tpd_ref: $&tpd_ref_dis" >> {working_folder}/fall_hold.txt
            else
                if verbose = 1
                    echo "Iteration: $&initial" >> {working_folder}/fall_hold.txt
                    echo "in_Upper_Bound:$&upper_t:in_Lower_Bound:$&lower_t" >> {working_folder}/fall_hold.txt
                end
            * Changing the upper and lower values as per the results
                let tpd_goal = 1.1*tpd_ref
                let error = (tpd-tpd_goal)/tpd_goal
                if tpd = 0
                    let lower_t = mid_point
                else
                    if tpd_goal < tpd
                        let lower_t = mid_point
                    end
                    if tpd_goal > tpd
                        let upper_t = mid_point
                    end
                end
                * To Stop the loop if error is low
                if error > 0
                    if error < 0.07m
                        let initial = 1000
                    end
                end
            end
            let initial = initial + 1
            let mid_point = (lower_t + upper_t)/2
            let tpd_num=tpd/1n
            let thold_num=thold/1n
            if verbose = 1
                echo "final_Upper_Bound:$&upper_t:final_Upper_Bound_Lower_Bound:$&lower_t" >> {working_folder}/fall_hold.txt
                echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:hold_time:$&thold_num:error_pdelay:$&error" >> {working_folder}/fall_hold.txt
            end
        end
        if verbose = 0
            echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:hold_time:$&thold_num:error_pdelay:$&error" >> {working_folder}/fall_hold.txt
        end
    end
    end
    quit"""

    elif sim_type == 'rise_setup':
        ext_folder = f'data/{active_pin}/setup'
        working_folder = path.join(output_dir, ext_folder)

        control_str = \
            f"""let verbose = 0
            shell rm {working_folder}/rise_setup.txt 
    foreach in_transition {input_transition}
    echo "d_tran:$in_transition" >> {working_folder}/rise_setup.txt
    foreach clk_tran {clock_transition}
        let d_base_t = 6n
        let d_high_t = d_base_t + $in_transition*1.666 
        
        if $in_transition = $clk_tran
            let off_time = 0.4n
        else
            let  off_time = 0.0
        end
        let clk_base_t = d_base_t + $in_transition*1.666 + off_time
        let clk_high_t = clk_base_t + $clk_tran*1.666 
        let lower_t = -4n
        let upper_t = 5n
        let mid_point = (lower_t + upper_t)/2
        let initial = 0
        let runs = {runs}
        let tpd_ref = 0
        dowhile initial < runs
            * Reference Simulation
            if initial = 0
                let mid_point = -2n
            end 
            let d_base_t_prime = d_base_t + mid_point
            let d_high_t_prime = d_base_t_prime + $in_transition*1.666 
            alter @V{active_pin}[PWL] = [ 0 0 $&d_base_t_prime 0 $&d_high_t_prime 1.8 ]
            alter @V{clk_pin}[PWL] = [ 0 0 0.2n 1.8 1.5n 0 $&clk_base_t 0 $&clk_high_t 1.8 ]
            tran 0.005n 20n
            run
            reset
            * plot q d clk
            let tpd = 0
            * measurement commands for Tsetup and Propagation Delay(CLK-Q)
            meas tran tsetup trig v({active_pin}) val=0.9 RISE=1 targ v({clk_pin}) val=0.9 RISE=2
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 RISE=1
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 RISE=2
            * Reference Simulation 
            if initial = 0
                let tpd_ref = tpd
                let tpd_ref_dis = tpd_ref/1n
                let mid_point = (lower_t + upper_t)/2
                if verbose = 0
                echo "tpd_ref: $&tpd_ref_dis" >> {working_folder}/rise_setup.txt
                end
            else
                if verbose = 1
                    echo "Iteration: $&initial" >> {working_folder}/rise_setup.txt
                    echo "in_Upper_Bound:$&upper_t:in_Lower_Bound:$&lower_t" >> {working_folder}/rise_setup.txt
                end
            * Changing the upper and lower values as per the results
                let tpd_goal = 1.1*tpd_ref
                let error = (tpd-tpd_goal)/tpd_goal
                if tpd = 0
                    let upper_t = mid_point
                else 
                    if tpd_goal > tpd
                        let lower_t = mid_point
                    end
                    if tpd_goal < tpd
                        let upper_t = mid_point
                    end
                end
                * To Stop the loop if error is low
                if error > 0 
                    if error < 0.07m
                        let initial = 1000
                    end
                end
            end
            let initial = initial + 1
            let mid_point = (lower_t + upper_t)/2
            let tpd_num=tpd/1n
            let tsetup_num=tsetup/1n
            if verbose = 1
                echo "final_Upper_Bound:$&upper_t:final_Upper_Bound_Lower_Bound:$&lower_t" >> {working_folder}/rise_setup.txt
                echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:setup_time:$&tsetup_num:error_pdelay:$&error" >> {working_folder}/rise_setup.txt
            end 
        end
        if verbose = 0
            echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:setup_time:$&tsetup_num:error_pdelay:$&error" >> {working_folder}/rise_setup.txt
        end
    end
    end    
    quit"""

    elif sim_type == 'fall_setup':
        ext_folder = f'data/{active_pin}/setup'
        working_folder = path.join(output_dir, ext_folder)

        control_str = \
            f"""let verbose = 0
            shell rm {working_folder}/fall_setup.txt 
    foreach in_transition {input_transition}
    echo "d_tran:$in_transition" >> {working_folder}/fall_setup.txt
    foreach clk_tran {clock_transition}
        let d_base_t = 6n
        let d_high_t = d_base_t + $in_transition*1.666 
        
        if $in_transition = $clk_tran
            let off_time = 0.4n
        else
            let  off_time = 0.0
        end
        let clk_base_t = d_base_t + $in_transition*1.666 + off_time
        let clk_high_t = clk_base_t + $clk_tran*1.666 
        let lower_t = -4n
        let upper_t = 5n
        let mid_point = (lower_t + upper_t)/2
        let initial = 0
        let runs = {runs}
        let tpd_ref = 0
        dowhile initial < runs
            * Reference Simulation
            if initial = 0
                let mid_point = -2n
            end 
            let d_base_t_prime = d_base_t + mid_point
            let d_high_t_prime = d_base_t_prime + $in_transition*1.666 
            alter @V{active_pin}[PWL] = [ 0 1.8 $&d_base_t_prime 1.8 $&d_high_t_prime 0 ]
            alter @V{clk_pin}[PWL] = [ 0 0 0.2n 1.8 1.5n 0 $&clk_base_t 0 $&clk_high_t 1.8 ]
            tran 0.005n 20n
            run
            reset
            * plot q d clk
            let tpd = 0
            * measurement commands for Tsetup and Propagation Delay(CLK-Q)
            meas tran tsetup trig v({active_pin}) val=0.9 FALL=1 targ v({clk_pin}) val=0.9 RISE=2
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 FALL=1
            meas tran tpd trig v({clk_pin}) val=0.9 RISE=2 targ v({out_pin}) val=0.9 FALL=2
            * Reference Simulation 
            if initial = 0
                let tpd_ref = tpd
                let tpd_ref_dis = tpd_ref/1n
                let mid_point = (lower_t + upper_t)/2
                if verbose = 0
                echo "tpd_ref: $&tpd_ref_dis" >> {working_folder}/fall_setup.txt
                end
            else
                if verbose = 1
                    echo "Iteration: $&initial" >> {working_folder}/fall_setup.txt
                    echo "in_Upper_Bound:$&upper_t:in_Lower_Bound:$&lower_t" >> {working_folder}/fall_setup.txt
                end
            * Changing the upper and lower values as per the results
                let tpd_goal = 1.1*tpd_ref
                let error = (tpd-tpd_goal)/tpd_goal
                if tpd = 0
                    let upper_t = mid_point
                else 
                    if tpd_goal > tpd
                        let lower_t = mid_point
                    end
                    if tpd_goal < tpd
                        let upper_t = mid_point
                    end
                end
                * To Stop the loop if error is low
                if error > 0 
                    if error < 0.07m
                        let initial = 1000
                    end
                end
            end
            let initial = initial + 1
            let mid_point = (lower_t + upper_t)/2
            let tpd_num=tpd/1n
            let tsetup_num=tsetup/1n
            if verbose = 1
                echo "final_Upper_Bound:$&upper_t:final_Upper_Bound_Lower_Bound:$&lower_t" >> {working_folder}/fall_setup.txt
                echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:setup_time:$&tsetup_num:error_pdelay:$&error" >> {working_folder}/fall_setup.txt
            end 
        end
        if verbose = 0
            echo "clk_tran:$clk_tran:pdelay_clkout:$&tpd_num:setup_time:$&tsetup_num:error_pdelay:$&error" >> {working_folder}/fall_setup.txt
        end
    end
    end    
    quit"""
    elif sim_type == 'dt_opwr':
        ext_folder = f'data/{out_pin}/timing'
        working_folder = path.join(output_dir, ext_folder)
        control_str = \
            f"""
    shell rm {working_folder}/input_transition.txt
    shell rm {working_folder}/cell_fall.txt
    shell rm {working_folder}/cell_rise.txt
    shell rm {working_folder}/fall_transition.txt
    shell rm {working_folder}/rise_transition.txt
    shell rm {working_folder}/rise_power.txt
    shell rm {working_folder}/fall_power.txt
    let run  = 0 
    foreach in_delay {input_transition_timing}
    * Initiating Text Files in folder data
    echo "input_transition:$in_delay" >> {working_folder}/input_transition.txt
    echo "input_transition:$in_delay" >> {working_folder}/cell_fall.txt
    echo "input_transition:$in_delay" >> {working_folder}/cell_rise.txt
    echo "input_transition:$in_delay" >> {working_folder}/fall_transition.txt
    echo "input_transition:$in_delay" >> {working_folder}/rise_transition.txt
    echo "input_transition:$in_delay" >> {working_folder}/rise_power.txt
    echo "input_transition:$in_delay" >> {working_folder}/fall_power.txt
    * 1.666 to match the slew rate
    let actual_rtime = $in_delay*1.666   

    * Input Vector - Load Cap values(index2)
    foreach out_cap {load_capacitor}
        reset
        
        * Changing the V2 Supply Rise time as per the Input Rise Time vector
        alter @V{clk_pin}[pulse] = [ 0 1.8 0 $&actual_rtime $&actual_rtime 15ns 30ns ]
        
        * Changing the C1 value as per the foreach list
        alter CLOAD $out_cap
        
        tran 0.01n 100ns
        run

        reset
        * Verification of INPUT RISE TIME
        meas tran ts1 when v({clk_pin})=1.44 RISE=1 
        meas tran ts2 when v({clk_pin})=0.36 RISE=1
        meas tran ts3 when v({clk_pin})=1.44 FALL=1 
        meas tran ts4 when v({clk_pin})=0.36 FALL=1
        let RISE_IN_SLEW = (ts1-ts2)/1e-09
        let FALL_IN_SLEW = (ts4-ts3)/1e-09
        echo "actual_rise_slew:$&RISE_IN_SLEW" >> {working_folder}/input_transition.txt
        echo "actual_fall_slew:$&FALL_IN_SLEW" >> {working_folder}/input_transition.txt


        print run
        * Measuring Cell Fall Time @ 50% of VDD(1.8V) 
        meas tran cfall trig v({clk_pin}) val=0.9 rise=3 targ v({out_pin}) val=0.9 fall=1
        let cfall = cfall/1e-09
        print cfall
        echo "out_cap:$out_cap:cell_fall:$&cfall" >> {working_folder}/cell_fall.txt

        * Measuring Cell Rise Time @ 50% of VDD(1.8V)
        meas tran crise trig v({clk_pin}) val=0.9 rise=2 targ v({out_pin}) val=0.9 rise=1
        let crise = crise/1e-09
        print crise
        echo "out_cap:$out_cap:cell_rise:$&crise" >> {working_folder}/cell_rise.txt

        * Measuring Fall transition Time @ 80-20% of VDD(1.8V)
        meas tran fall_tran trig v({out_pin}) val=1.44 fall=1 targ v({out_pin}) val=0.36 fall=1
        meas tran fall_tran trig v({out_pin}) val=1.44 fall=1 targ v({out_pin}) val=0.36 fall=2
        let fall_tran = fall_tran/1n
        print fall_tran
        echo "out_cap:$out_cap:fall_transition:$&fall_tran" >> {working_folder}/fall_transition.txt
        
        * Measuring Rise transition Time @ 20-80% of VDD(1.8V) 
        meas tran rt1 when v({out_pin})=1.44 RISE=1 
        meas tran rt2 when v({out_pin})=0.36 RISE=1
        let rise_tran = ((rt1-rt2)/1e-09)
        print rise_tran
        echo "out_cap:$out_cap:rise_transition:$&rise_tran" >> {working_folder}/rise_transition.txt
        let pos_unate = 1
        if pos_unate
            * Measuring Rising Power if Positive Unate
            meas tran pt1 when v({clk_pin})=0.9 RISE=2
            meas tran pt2 when v({out_pin})=1.79 RISE=1
            * To avoid error due to peaks
            if pt1 > pt2 
                meas tran pt2 when v({clk_pin})=1.79 RISE=3
            end
            let pwr_stc1 = (@CLOAD[i])*{out_pin} 
            meas tran pwr_swt1 INTEG pwr_stc1 from=pt1 to=pt2
            let pwr_swt1 = pwr_swt1/1p
            echo "out_cap:$out_cap:power_switch:$&pwr_swt1" >> {working_folder}/rise_power.txt

            * Measuring Falling Power if Positive Unate
            meas tran pt1 when v({clk_pin})=0.9 RISE=2
            meas tran pt2 when v({out_pin})=0.1 FALL=1
            meas tran pt2 when v({out_pin})=0.1 FALL=2
            let pwr_stc2 = (@CLOAD[i])*{out_pin} - (@(VVPWR#branch)*VPWR)
            meas tran pwr_swt2 INTEG pwr_stc2 from=pt1 to=pt2
            let pwr_swt2 = pwr_swt2/1p
            echo "out_cap:$out_cap:power_switch:$&pwr_swt2" >> {working_folder}/fall_power.txt
        end
        * plot clk d+2 q+4
    end
    end
    rusage \nquit"""

    elif sim_type == 'input_caps':
        ext_folder = f'data/{active_pin}/input_caps'
        working_folder = path.join(output_dir, ext_folder)
        control_str = \
            f""" shell rm {working_folder}/input_pins_caps.txt
            foreach case 1.8 0
    if $case=0
        * Fall Condition
        reset
        alter @V{active_pin}[PWL] = [ 0 1.8 1.25n 0.9 2.5n 0 ]
        tran 0.01n 2.5n
        run
        let fall_caps = abs(avg(v{active_pin}#branch))*2.5n/(1.8)
        let fall_cap = fall_caps[length(fall_caps)-1]/1p
        echo "{active_pin}:fall_capacitance:$&fall_cap" >> {working_folder}/input_pins_caps.txt
    else
        * Rise Condition
        reset
        alter @V{active_pin}[PWL] = [ 0ns 0 1.25ns 0.9 2.5ns 1.8 ]
        tran 0.01n 2.5n
        run
        let rise_caps = abs(avg(v{active_pin}#branch))*2.5n/(1.8)
        let rise_cap = rise_caps[length(rise_caps)-1]/1p
        echo "{active_pin}:rise_capacitance:$&rise_cap" >> {working_folder}/input_pins_caps.txt 
    end
    end"""

    return control_str, working_folder


def ngspice_lunch(file_loc, working_folder, skip_sim):
    """Launches NGspice and delete old simulation files from the working_folder"""
    if not skip_sim:
        try:
            makedirs(working_folder)
        except OSError:
            print("Creation of the directory %s failed" % working_folder)
        else:
            print("Successfully created the directory %s " % working_folder)

        subprocess.call(["ngspice", '-b', '-r rawfile.raw', file_loc])
        print('Finished Simulation')
    else:
        print(
            f'Simulation file run: {file_loc} \nSkiped as per the -fs_sim tag')


def format_seq_timing(txt_loc, edge_type=1):
    """format the hold and setup time as per .lib requirement """
    attr_names = ['rise_hold', 'fall_hold', 'rise_setup', 'fall_setup']
    lut_table_list = []
    seq_timing_type = ''

    if edge_type == 1:
        clk_type = 'rising'
    else:
        clk_type = 'falling'

    for attr_name in attr_names:
        if 'hold' in txt_loc and 'hold' in attr_name:
            seq_timing_type = 'hold'
            file_name = attr_name + '.txt'
            file_location = path.join(txt_loc, file_name)
            clk_tran, d_tran, seq_timing = timing.read_seq_timing(
                file_location)
            if 'rise_hold' in attr_name:
                lut_table = timing.gen_lib(clk_tran, d_tran, seq_timing,
                                           attr_name='rise_constraint',
                                           type_sim='dff')
                lut_table_list.append(lut_table)
            if 'fall_hold' in attr_name:
                lut_table = timing.gen_lib(clk_tran, d_tran, seq_timing,
                                           attr_name='fall_constraint',
                                           type_sim='dff')
                lut_table_list.append(lut_table)

        elif 'setup' in txt_loc and 'setup' in attr_name:
            seq_timing_type = 'setup'
            file_name = attr_name + '.txt'
            file_location = path.join(txt_loc, file_name)
            clk_tran, d_tran, seq_timing = timing.read_seq_timing(
                file_location)
            if 'rise_setup' in attr_name:
                lut_table = timing.gen_lib(clk_tran, d_tran, seq_timing,
                                           attr_name='rise_constraint',
                                           type_sim='dff')
                lut_table_list.append(lut_table)
            if 'fall_setup' in attr_name:
                lut_table = timing.gen_lib(clk_tran, d_tran, seq_timing,
                                           attr_name='fall_constraint',
                                           type_sim='dff')
                lut_table_list.append(lut_table)

    timing_str = \
        f"""timing () {{
                {lut_table_list[1]}
                related_pin : "CLK";
                {lut_table_list[0]}
                sim_opt : "runlvl=5 accurate=1";
                timing_type : "{seq_timing_type}_{clk_type}";
                violation_delay_degrade_pct : 10.000000000;
            }} """

    return timing_str


def ff_block_gen(clock_pin, edge_type, next_state_func):
    """ Used to to generate ff {} block
        As of now, limited to simple DFF without Async pins
    """
    if edge_type == 1:
        clock_type = clock_pin
    else:
        clock_type = clock_pin + '\''

    str_ff = \
        f"""ff ("IQ","IQ_N") {{
            clocked_on : "{clock_type}";
            next_state : "{next_state_func}";
        }} """
    return str_ff


def timing_lib(cell_directory, card, timing_list, power_swt_list, inpin_list, cell_dict, cell_footprint, ff_block_str):
    """ Generate .lib file """

    cell_lib_file = path.join(cell_directory, 'timing.lib')
    timing_txt = '\n\t\t\t'.join(timing_list)
    power_swt_txt = '\n\t\t\t'.join(power_swt_list)
    input_pin_txt = '\n\t\t'.join(inpin_list)
    cell_area = cell_dict['area']
    cell_name = cell_dict['cell_name']
    cell_card = f"""cell ("{cell_name}") {{
        area: {cell_area};
        cell_footprint: "{cell_footprint}";
        {ff_block_str}
        pg_pin ("VGND"){{
            pg_type : "primary_ground";
            voltage_name : "VGND";
        }}
        pg_pin ("VNB") {{
            pg_type : "primary_ground";
            voltage_name : "VNB";
        }}
        pg_pin ("VPB") {{
            pg_type : "primary_power";
            voltage_name : "VPB";
        }}
        pg_pin ("VPWR") {{
            pg_type : "primary_power";
            voltage_name : "VPWR";
        }}
        {input_pin_txt}
        pin ("{output_pins[0]}") {{
            direction: "output";
            function: "IQ";
            power_down_function : "(!VPWR + VGND)";
            related_ground_pin : "VGND";
            related_power_pin : "VPWR";
            {power_swt_txt}
            {timing_txt}  
        }}
    }}    
    """
    with open(cell_lib_file, "w") as file_doc:
        file_doc.write(cell_card)

    print(f'Check:  {cell_lib_file}')
    # To Merge File with the Base file
    if merged_file != '':
        merge_obj = merge.MergeLib(
            base_file=merged_file, cells_file=cell_lib_file, output_file=merged_file)
        status = merge_obj.add_cells()
        if status:
            print(f'Updated Liberty File: {merged_file}')
        else:
            print(f'Manually add the timing lib using {cell_lib_file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Simple D Flip-Flop Timing characterization")

    parser.add_argument('-lef', metavar='--lef_file',
                        help='Enter the D Flip Flop .lef file location', type=str, required=True)
    parser.add_argument('-sp', metavar='--SPICE',
                        help='Enter the Spice file with extracted PEX spice file', type=str, required=True)
    parser.add_argument('-lib', metavar='--output_lib',
                        help='Enter the output lib file to merge this cell', type=str, default='')
    parser.add_argument('-fs_sim', metavar='--skip_sim',
                        help='Assign 1 in order to skip the simulation, Use this only if Simulation data exists in "data" folder', type=bool, default=False)

    # Use for Debugging
    # arg_var = parser.parse_args(
    #     ['-lef', 'custom_stdcell/dftxp_1x/sky130_vsddfxtp_1.lef',
    #      '-sp', 'custom_stdcell/dftxp_1x/sky130_vsddfxtp_1.spice',
    #      '-fs_sim', '1'])
    arg_var = parser.parse_args()
    output_dir = path.split(arg_var.sp)[0]

    lef_pins_list, lef_dict, input_pins, output_pins = display_lef(
        lef_extract(arg_var.lef))
    spice_pins_str, spice_card = read_spice(arg_var.sp)
    pins_verification(spice_pins_str, lef_pins_list)

    # User Input for CLK edge trigger type
    print('\n[User Input] \nType of edge trigger \nEnter 1 for Positive Edge Triggered and 2 for Negative Edge Triggered')
    edge_type = input()
    try:
        edge_type = int(edge_type)
    except:
        print('[Error] Enter the edge trigger as per the options')

    # Flip-Flop Output Function
    print('\n[User Input] \nEnter Next State function of the Flip-Flop:')
    next_clk = input()
    # Cell Foot-Print
    print('\n[User Input] \nEnter Cell footprint name (example: dfxtp, dfxtn):')
    cell_footprint = input()

    clk_pin = 'CLK'  # Temporary Coded

    timing_list = []
    power_swt_list = []
    pins_list = []

    for act_pin in input_pins:
        for out_pin in output_pins:

            # Hold Timing Harness
            cir_file, cir_folder = Simulation_env(arg_var.sp, edge_type,
                                                  spice_pins_str, spice_card,
                                                  act_pin, out_pin, clk_pin,
                                                  sim_type='rise_hold')

            ngspice_lunch(cir_file, cir_folder, arg_var.fs_sim)

            cir_file, cir_folder = Simulation_env(arg_var.sp, edge_type,
                                                  spice_pins_str, spice_card,
                                                  act_pin, out_pin, clk_pin,
                                                  sim_type='fall_hold')

            ngspice_lunch(cir_file, cir_folder, arg_var.fs_sim)
            hold_timing = format_seq_timing(cir_folder, edge_type)

            # Setup Timing Harness
            cir_file, cir_folder = Simulation_env(arg_var.sp, edge_type,
                                                  spice_pins_str, spice_card,
                                                  act_pin, out_pin, clk_pin,
                                                  sim_type='rise_setup')

            ngspice_lunch(cir_file, cir_folder, arg_var.fs_sim)
            cir_file, cir_folder = Simulation_env(arg_var.sp, edge_type,
                                                  spice_pins_str, spice_card,
                                                  act_pin, out_pin, clk_pin,
                                                  sim_type='fall_setup')

            ngspice_lunch(cir_file, cir_folder, arg_var.fs_sim)
            setup_timing = format_seq_timing(cir_folder, edge_type)

            # Delay Timing and output power(approx)
            cir_file, cir_folder = Simulation_env(arg_var.sp, edge_type,
                                                  spice_pins_str, spice_card,
                                                  act_pin, out_pin, clk_pin,
                                                  sim_type='dt_opwr')

            ngspice_lunch(cir_file, cir_folder, arg_var.fs_sim)

            clk_type = 'rising_edge' if edge_type == 1 else 'falling_edge'
            timing_info, power_swt_info = timing.timing_generator(cir_folder,
                                                                  unate='non_unate',
                                                                  related_pin='CLK',
                                                                  timing_type=clk_type)

            timing_list.append(timing_info)
            power_swt_list.append(power_swt_info)
            # Input Capacitance
            cir_file, cir_folder = Simulation_env(arg_var.sp, edge_type,
                                                  spice_pins_str, spice_card,
                                                  act_pin, out_pin, clk_pin,
                                                  sim_type='input_caps')
            ngspice_lunch(cir_file, cir_folder, arg_var.fs_sim)

            extra_data = f'{setup_timing}\n\t\t\t{hold_timing}'
            # Caution: 1.5n is hardcoded for now( Maximum input transition time)
            pin_info_input = timing.input_pins_seq(cir_folder, act_pin,
                                                   '1.5', extra_data,
                                                   clock_check=False)
            pins_list.append(pin_info_input)
    # CLK
    cir_file, cir_folder = Simulation_env(arg_var.sp, edge_type,
                                          spice_pins_str, spice_card,
                                          clk_pin, out_pin, clk_pin,
                                          sim_type='input_caps')
    ngspice_lunch(cir_file, cir_folder, arg_var.fs_sim)
    pin_info_clk = timing.input_pins_seq(cir_folder, clk_pin,
                                         '1.5', clock_check=True)
    pins_list.append(pin_info_clk)
    ff_block = ff_block_gen(clk_pin, edge_type, next_clk)
    merged_file = arg_var.lib
    timing_lib(output_dir, spice_card, timing_list, power_swt_list,
               pins_list, lef_dict, cell_footprint, ff_block)
