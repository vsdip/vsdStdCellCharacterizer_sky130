#!/usr/bin/python3
import logging
from os import path
from os import makedirs
import os
import numpy as np
import re
import subprocess
import csv
import itertools
import argparse

import scripts.truths as truths
import scripts.timing as timing

logging.basicConfig(format='%(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S%p',
                    filename='cdm_esim.log',
                    level=logging.DEBUG)
# User Input Needs
library_directory = ''
library_file = path.join(library_directory, 'sky130nm.lib')
# Power and Ground Pin Defaults
power_volts = '5'
# Timing variables
time_unit= '1n'
cap_unit= 'p'
input_transition_time = '0.01n 0.023n 0.0531329n 0.122474n 0.282311n 0.650743n 1.5n'
output_caps = '0.0005000000p 0.0012632050p 0.0031913740p 0.0080627180p 0.0203697300p 0.0514622900p 0.1300148000p'

def ngpost_timing(act_out_pin, func,signal_source, active_pin):
    """ Generate ngspice control commands for timing_harness"""
    in_pins = ' '.join(input_pins).replace(active_pin, '') + ' ' + active_pin
    working_func = convert_logical(func)
    pos_unate, pins_voltages = truths.Truths(in_pins.split(), [working_func]).truth_table()   
    
    extra_alter_source = []
    missing_voltage_source = []
    
    for in_pin in pins_voltages.keys():
        if pins_voltages[in_pin] == 1: voltage = power_volts
        else: voltage = 0
        
        if in_pin in signal_sources.keys():
            extra_alter_source.append(f'alter @{signal_sources[in_pin]}[PWL] = [ 0 {voltage} ]')
        else:
            missing_voltage_source.append(f'V{in_pin} {in_pin} 0 DC 0')
    
    
    extra_alter_source_str = '\n'.join(extra_alter_source)
    # TODO: Shift this text based template to Jinja Templates if necessary   
    control_str = \
    f"""let run  = 0 \n 
    shell rm {working_folder}/input_transition.txt
    shell rm {working_folder}/cell_fall.txt
    shell rm {working_folder}/cell_rise.txt
    shell rm {working_folder}/fall_transition.txt
    shell rm {working_folder}/rise_transition.txt
    foreach in_delay {input_transition_time}
    * Initiating Text Files in folder data
    echo "input_transition:$in_delay" >> {working_folder}/input_transition.txt
    echo "input_transition:$in_delay" >> {working_folder}/cell_fall.txt
    echo "input_transition:$in_delay" >> {working_folder}/cell_rise.txt
    echo "input_transition:$in_delay" >> {working_folder}/fall_transition.txt
    echo "input_transition:$in_delay" >> {working_folder}/rise_transition.txt
    * 1.666 to match the slew rate
    let actual_rtime = $in_delay*1.666   

    * Input Vector - Load Cap values(index2)
    foreach out_cap {output_caps}
        reset
        
        * Changing the V2 Supply Rise time as per the Input Rise Time vector
        alter @{signal_source}[pulse] = [ 0 {power_volts} 0 $&actual_rtime $&actual_rtime 50ns 100ns ]
        {extra_alter_source_str}
        * Changing the C1 value as per the foreach list
        alter CLOAD $out_cap
        
        tran 0.01n 300ns
        run

        reset
        * Verification of INPUT RISE TIME
        meas tran ts1 when v({active_pin})={float(power_volts)*0.8} RISE=1 
        meas tran ts2 when v({active_pin})={float(power_volts)*0.2} RISE=1
        meas tran ts3 when v({active_pin})={float(power_volts)*0.8} FALL=1 
        meas tran ts4 when v({active_pin})={float(power_volts)*0.2} FALL=1
        let RISE_IN_SLEW = (ts1-ts2)/{time_unit}
        let FALL_IN_SLEW = (ts4-ts3)/{time_unit}
        echo "actual_rise_slew:$&RISE_IN_SLEW" >> {working_folder}/input_transition.txt
        echo "actual_fall_slew:$&FALL_IN_SLEW" >> {working_folder}/input_transition.txt


        print run
        * Measuring Cell Fall Time @ 50% of VDD({float(power_volts)}V) 
        meas tran tinfall when v({active_pin})={float(power_volts)*0.5} FALL=1 
        meas tran tofall when v({act_out_pin})={float(power_volts)*0.5} FALL=1
        let cfall = (tofall-tinfall)/{time_unit}
        if abs(cfall)>20
            meas tran tinfall when v({active_pin})={float(power_volts)*0.5} Rise=1 
            meas tran tofall when v({act_out_pin})={float(power_volts)*0.5} FALL=1
            let cfall = abs(tofall-tinfall)/{time_unit}
        end
        print cfall
        echo "out_cap:$out_cap:cell_fall:$&cfall" >> {working_folder}/cell_fall.txt

        * Measuring Cell Rise Time @ 50% of VDD({float(power_volts)}V) 
        meas tran tinrise when v({active_pin})={float(power_volts)*0.5} RISE=1 
        meas tran torise when v({act_out_pin})={float(power_volts)*0.5} RISE=1
        let crise = (torise-tinrise)/{time_unit}
        if abs(crise)>20
            meas tran tinrise when v({active_pin})={float(power_volts)*0.5} FALL=1 
            meas tran torise when v({act_out_pin})={float(power_volts)*0.5} RISE=1
            let crise = abs(tinrise-torise)/{time_unit}
        end
        print crise
        echo "out_cap:$out_cap:cell_rise:$&crise" >> {working_folder}/cell_rise.txt

        * Measuring Fall transition Time @ 80-20% of VDD({float(power_volts)}V) 
        meas tran ft1 when v({act_out_pin})={float(power_volts)*0.8} FALL=2 
        meas tran ft2 when v({act_out_pin})={float(power_volts)*0.2} FALL=2
        let fall_tran = (ft2-ft1)/{time_unit}
        print fall_tran
        echo "out_cap:$out_cap:fall_transition:$&fall_tran" >> {working_folder}/fall_transition.txt
        
        * Measuring Rise transition Time @ 20-80% of VDD({float(power_volts)}V) 
        meas tran rt1 when v({act_out_pin})={float(power_volts)*0.8} RISE=2 
        meas tran rt2 when v({act_out_pin})={float(power_volts)*0.2} RISE=2
        let rise_tran = ((rt1-rt2)/{time_unit})
        print rise_tran
        echo "out_cap:$out_cap:rise_transition:$&rise_tran" >> {working_folder}/rise_transition.txt
        let run = run + 1
        * plot a y
    end
    end"""

    return control_str

def analysis_truthtable(output_dict, act_out_pin, input_pins, out_func):
    """ Used to compare the truthtable generated by the .sub and output function"""
    header = [data for data in input_pins]
    header.append('SPICE')
    header.append('Function')
    header.append('Result')
    result = [ [[out_func.replace(' ','')]],  [header]]
    file_name = act_out_pin.lower() + '.txt'
    output_file = path.join(cell_directory, 'data', file_name)
    try:
        with open(output_file, "r") as file_object:
            # read file content
            out_txt = file_object.read()
    except:
        print("-ERROR: Simulation halted")
        return 'ERROR in Simulation'
    file_data = out_txt.split('\n')[:-1]
    # print('Function ngSPICE')
    for index, data in enumerate(file_data):
        if index != 0:
            row = [bool(float(dot)) for dot in data.split(' ')]
            input_tuple = tuple(row[:-1])
            out_result = row[-1]
            expected_output = bool(output_dict[input_tuple])
            row.append(expected_output)
            if out_result == expected_output:
                row.append('Matched')
            else:
                row.append('Unmatched')
            row_str = [[str(data) for data in row]]
            result.append(row_str)
    print(result)
    # result_str = [line.split() for line in result]
    return result

def convert_logical(logic_func):
    """ Converts the func as per format needed by the truths module"""
    logic_operator = {'.': '&',
                      '+': '|',
                      '~': 'not',
                      'XOR': '^',
                      'xor': '^'}

    for exp in logic_operator.keys():
        logic_func = logic_func.replace(exp, logic_operator[exp])

    return logic_func

def ngspice_launch(file_loc):
    """Launches NGspice and delete old simulation files from the working_folder"""
    
    data_path = path.join(cell_directory, 'data')
    result_path = path.join(cell_directory, 'result')

    folders = [data_path, result_path]
    for folder in folders:
        try:
            makedirs(folder)
        except OSError:
            print("Creation of the directory %s failed" % folder)
        else:
            print("Successfully created the directory %s " % folder)

    subprocess.call(["ngspice", file_loc])
    print('Finished Simulation')

def gen_control_cmd(act_out_pin):
    input_pins_str = ' '.join(input_pins)
    num_input = len(input_pins)
    for_list = []
    alter_list = []
    for index in range(num_input):
        for_list.append(f'foreach {input_pins[index]}in 0 {power_volts} \n')
        alter_list.append(
            f'alter @{signal_sources[input_pins[index]]}[PWL] = [ 0 ${input_pins[index].lower()}in ] \n')

    for_str = '\t'.join(for_list)
    alter_str = ''.join(alter_list)
    temp_in_pins = ' '.join([f'${in_pin.lower()}in' for in_pin in input_pins])
    end_str = '\n \t'.join(['end' for index in range(num_input)])
    control_txt = \
        f"""
        shell rm {cell_directory}/data/{act_out_pin.lower()}.txt
        echo "{input_pins_str} OUT"  >> {cell_directory}/data/{act_out_pin.lower()}.txt
        {for_str}
        let out_val = {power_volts}
        {alter_str}
                tran 0.01n 1n
        run
        reset 
        let out_last = v({act_out_pin})[length(v({act_out_pin}))-1]
        if out_last < {float(power_volts)/2}
           let out_val = 0
        end
        echo "{temp_in_pins} $&out_val" >> {cell_directory}/data/{act_out_pin.lower()}.txt
        {end_str}
    """
    return control_txt

def Simulation_env(act_out_pin, func, result_type, in_pin = '_'):
    """Creates timing_harness.cir file"""

    harness_name = f"{act_out_pin}_harness.cir"
    if result_type == 'truth_tables':
        harness_name = f"{act_out_pin}_ttables_harness.cir"
        control_text = gen_control_cmd(act_out_pin)
    elif result_type == 'timing':
        # Checking for the input pins which exist in the function
        harness_name = f"{act_out_pin}_{in_pin}_timing_harness.cir"
        signal_source = signal_sources[in_pin]
        control_text = ngpost_timing(act_out_pin, func, signal_source, in_pin)
    
    harness_file = path.join(cell_directory, harness_name)
    
    final_text = \
        f"""
    .include {library_file}
    {cir_txt_temp.replace('.tran', '* .tran').split('.control')[0]}
    CLOAD {act_out_pin} 0 1f
    .control
    {control_text}
    quit
    .endc"""

    with open(harness_file, "w") as file_doc:
        file_doc.write(final_text)

    return harness_file

def gen_ttable(act_out_pin, func, act_in_pin):
    mod_input_pins = [act_in_pin]
    
    for in_pin in input_pins:
        if act_in_pin != in_pin:
            mod_input_pins.append(in_pin)
    
    working_func = convert_logical(func)
    base_conditions = list(itertools.product([False, True], repeat=len(input_pins)))
    output_dict = {}
    if act_out_pin in output_pins:
            for base_condition in base_conditions:
                for index in range(len(mod_input_pins)):
                    exec("%s = %d" %(mod_input_pins[index], base_condition[index]))
                output_dict.update({base_condition: eval(working_func)})

    return output_dict

def gen_alltable_cases():
    """ Generate the truth table for the particular output function"""
    results = []
    for out_func in output_func:

        logging.debug(f'- Output Function: {out_func}')
        act_out_pin = out_func.split('=')[0].replace(' ', '')
        func = out_func.split('=')[1]
        if act_out_pin in output_pins:
            
            output_dict = gen_ttable(act_out_pin, func, input_pins[0])
            # To get Truth Table results
            file_name = Simulation_env(act_out_pin, func,'truth_tables')
            # Launch NGSPICE
            ngspice_launch(file_name)
            # Analyze TruthTable Results
            tt_result = analysis_truthtable(output_dict, act_out_pin, input_pins, out_func)
            results.append(tt_result)
        
            results.append([[[f'Timing Results for {circuit_name}']]])
            # To get Timing Results
            for in_pin in input_pins:
                file_name = Simulation_env(act_out_pin, func, 'timing', in_pin)
                ngspice_launch(file_name)
                results.append(timing_analyzer(in_pin, act_out_pin))
            # print(result)
            

        else:
            print("Output Function assert an error")
            exit(0)

    return results

def read_users_data(user_file_name):
    """ Reads csv data from user_data folder"""
    participants = []
    csv_header = []
    with open(user_file_name) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        line_count = 0

        for row in csv_reader:
            participant_dict = {}

            if line_count == 0:
                print(f' - CSV with these Inputs: {", ".join(row)}')
                csv_header = row
                line_count += 1
            else:
                # print(f'\t{row[0]} works in the {row[1]} department, and was born in {row[2]}.')

                for index, column_name in enumerate(csv_header):
                    participant_dict.update({column_name: row[index]})
                participants.append(participant_dict)
                line_count += 1

    return participants

def spice_analysis(cir_txt):
    # print(cir_txt)
    voltage_sources = {}
    for row in cir_txt.split('\n'):
        # Replacing include statement with proper directory
        if '.include' in row:
            cell_lib_name = row.split(' ')[1]
            if cell_lib_name in sub_files:
                cell_lib_loc = path.join(cell_directory, cell_lib_name)
                cir_txt = cir_txt.replace(f'.include {cell_lib_name}', f'.include {cell_lib_loc}')
                logging.debug(f'{cell_lib_name} exists in {cell_directory}')
            else:
                logging.error(f'{cell_lib_name} do not exist in {cell_directory}')
            if '.lib' in cell_lib_name:
                cell_lib_loc = path.join(cell_directory, cell_lib_name)
                for root, dirs, files in os.walk(cell_directory):
                    if cell_lib_name in files:
                        cir_txt = cir_txt.replace(f'.include {cell_lib_name}', f'.include {cell_lib_loc}')
                    else:
                        cir_txt = cir_txt.replace(f'.include {cell_lib_name}', f'* .include {cell_lib_name}')
    
        # Search for voltage sources
        if re.match('^v[\w\d]+', row):
            row_split = [name for name in row.split('  ')]
            if row_split[0][0].lower() == 'v':
                for input_pin in input_pins:
                    if input_pin in row:
                        voltage_sources.update({input_pin: row_split[0]})

    
    print(voltage_sources)
    return cir_txt, voltage_sources

def analyse_cir_file():
    cir_file_loc = path.join(cell_directory, cir_file[0])
    with open(cir_file_loc, 'r') as cir_obj:
        cir_txt = cir_obj.read()
    
    cir_txt_mod, signal_sources = spice_analysis(cir_txt)
    
    return cir_txt_mod, signal_sources

def mod_sub_files():
    for sub_file in sub_files:
        sub_file_loc = path.join(cell_directory, sub_file)
        with open(sub_file_loc) as sub_obj:
            sub_txt = sub_obj.read()
        mod_sub_txt, sources = spice_analysis(sub_txt)

        with open(sub_file_loc, 'w') as sub_obj:
            sub_obj.seek(0)
            sub_obj.write(mod_sub_txt)
            sub_obj.truncate()

def timing_analyzer(act_in_pin, act_out_pin):
    attributes_names = ['cell_fall', 'cell_rise',
                        'fall_transition', 'rise_transition']
    timing_tables = []
    for attr_name in attributes_names:
        file_name = attr_name + '.txt'
        file_location = path.join(working_folder, file_name)
        in_rises, out_caps, timing_table = timing.read_spicetxt(file_location) 
        in_rises.insert(0, 'Transition Time (Horizontal)/Load Capacitors(Vertical)')
        new_timing_table = []
        for index, cont in enumerate(timing_table):
            new_timing_table.append(np.insert(timing_table[index], 0, out_caps[index]))
        new_timing_table.insert(0, in_rises)
        new_timing_table.insert(0, [f'{attr_name}: {act_in_pin} -> {act_out_pin}'])
        timing_tables.append(new_timing_table)
    return timing_tables

def csv_writer(timing_tables):    
    csv_file_loc = path.join(cell_directory, f'{circuit_name}.csv')
    with open(csv_file_loc, 'w', newline='') as f:
        writer = csv.writer(f)
        for timing_table in timing_tables:
            for timing_t in timing_table:
                writer.writerows(timing_t)

def gen_analog():
    ckt_analog = cir_txt_temp.split('.control')
    input_pins_str = ' '.join(input_pins)
    output_pins_str = ' '.join(output_pins)
    result_loc = path.join(cell_directory, 'result')
    harness_file = path.join(cell_directory, f'{circuit_name}.cir')
    # Not using ps_loc due to hardcopy bug for handling file string as lower case
    ps_loc = path.join(cell_directory, f'{circuit_name}.ps')
    img_loc = path.join(result_loc, f'{circuit_name}.png')
    new_ckt_analog = \
        f""" 
        {ckt_analog[0]}
        .control
        set hcopydevtype=postscript
        set hcopypscolor=1
        set color0=rgb:f/f/f
        set color1=rgb:0/0/0
        {ckt_analog[1].split('.endc')[0]}
        hardcopy {circuit_name}.ps {input_pins_str} {output_pins_str}
        shell gs -dSAFER -dBATCH -dNOPAUSE -dEPSCrop -r600 -sDEVICE=pngalpha -sOutputFile={img_loc} {circuit_name.lower()}.ps
        quit
        .endc
        .end
        """
    with open(harness_file, "w") as file_doc:
        file_doc.write(new_ckt_analog)
    
    return harness_file

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Verifier Tool for NGSPICE SubCkt")

    parser.add_argument('-csv', metavar='--csv_file',
                        help='Enter the user specific csv file', type=str, required=True)

    # # Use for Debugging
    # arg_var = parser.parse_args(
    #     ['-csv', 'example/esim/dummy_csv_for-VSD_CharScript - Sheet1.csv'])

    arg_var = parser.parse_args()

    partipants_list = read_users_data(arg_var.csv)
    for user_data in partipants_list:
        cell_directory = path.split(arg_var.csv)[0]
        student_name = user_data['Student name'].replace(' ', '_')
        email_id = user_data['Email ID']
        org = user_data['Uni/Org/College'].replace(' ', '_')
        circuit_name = user_data['Circuit Name'].replace(' ', '_')
        circuit_type = user_data['Circuit Type']
        spice_file = user_data['Spice File Name']
        power_volts = user_data['Operating Voltage']
        input_pins = user_data['Input pins'].split(',')
        output_pins = user_data['Output pins'].split(',')
        output_func = user_data['Output function'].split(',')
        cir_file = user_data['Server Path to cir.cout']
        sub_files = user_data['Server Path to .sub files'].split(',')
        logging.debug(f'Student: {student_name}')
        
        # Making the cells folder according to unique user email id
        unique_folder = '_'.join(
            [student_name.lower(), email_id.lower().replace('@', ''), org.lower()])
        cell_directory = path.join(
            cell_directory, unique_folder, circuit_name.replace(' ', '_'))
        try:
            makedirs(cell_directory)
            logging.debug(f'Created directory:{cell_directory}')
        except:
            logging.debug(
                f'- "{cell_directory}" directory already exists - Deleting all files inside this folder')
            # Add a code to delete folders inside this file
            for root, dirs, files in os.walk(cell_directory):
                for file in files:
                    os.remove(os.path.join(root, file))
        # Download the .sub and .cir.out files
        subprocess.call(["wget", '-P', cell_directory, cir_file.replace(' ','')])
        for sub_file in sub_files:
            subprocess.call(["wget", '-P', cell_directory, sub_file.replace(' ','')])

        sub_files = [file_ for _, _, files in os.walk(cell_directory) for file_ in files if '.sub' in file_]
        cir_file = [file_ for _, _, files in os.walk(cell_directory) for file_ in files if '.cir.out' in file_]
        
        # Get Input Signal sources designator and library path correction
        if len(cir_file) > 0:
            cir_txt_temp, signal_sources = analyse_cir_file()
        else:
            logging.debug(f"No Cir.out file available for {circuit_name}")

        # Modifying .lib file paths in .sub files
        mod_sub_files()
        if 'dig' in circuit_type.lower():
            logging.debug(f'Digital circuit: {circuit_name}')
            working_folder = path.join(cell_directory, 'data') # Stores spice generated .txt files
            results = gen_alltable_cases()
            csv_writer(results)
            logging.debug(f'Finished -- Digital circuit: {circuit_name}')
        elif 'analog' in circuit_type.lower():
            logging.debug(f'Started -- Analog circuit: {circuit_name}')
            output_func = [f'{output_pins[0]}={input_pins[0]}']
            cir_file_analog = gen_analog()
            ngspice_launch(cir_file_analog)
            logging.debug(f'Finished -- Analog circuit: {circuit_name}')
        # results_str = '\n\n'.join(results)
        # with open(f'{cell_directory}/result/truthtable.txt', 'w') as file_obj:
        #     file_obj.seek(0)
        #     file_obj.write(results_str)
        #     file_obj.truncate()
