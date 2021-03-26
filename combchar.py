#!/usr/bin/python3
from config import *
from os import path
from os import makedirs
import os, re
import scripts.truths as truths
import scripts.timing as timing
import subprocess
import scripts.merge as merge

logic_operator = {'and':'&',
                  'or': '|',
                  'not': '!'}
output_pins = 'Y' # Default Y Considered as Output 

def ng_postscript(meas_type, active_pin, pos_unate):
    """ Generate ngspice control commands for timing_harness"""
    
    if meas_type == 'timing':
        
        working_folder = path.join(output_folder,'timing')

        # To change the calculation of switching power as per the unate type
        pos, neg = 0, 0
        if pos_unate: pos = 1
        else: neg = 1

        # TODO: Shift this text based template to Jinja Templates if necessary   
        control_str = \
    f"""let run  = 0 \n foreach in_delay {input_transition_time}
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
    foreach out_cap {output_caps}
        reset
        
        * Changing the V2 Supply Rise time as per the Input Rise Time vector
        alter @V{active_pin}[pulse] = [ 0 {VDD} 0 $&actual_rtime $&actual_rtime 50ns 100ns ]
        
        * Changing the C1 value as per the foreach list
        alter CLOAD $out_cap
        
        tran {sim_step} 300ns
        run

        reset
        * Verification of INPUT RISE TIME
        meas tran ts1 when v({active_pin})=1.44 RISE=1 
        meas tran ts2 when v({active_pin})=0.36 RISE=1
        meas tran ts3 when v({active_pin})=1.44 FALL=1 
        meas tran ts4 when v({active_pin})=0.36 FALL=1
        let RISE_IN_SLEW = (ts1-ts2)/{time_unit}
        let FALL_IN_SLEW = (ts4-ts3)/{time_unit}
        echo "actual_rise_slew:$&RISE_IN_SLEW" >> {working_folder}/input_transition.txt
        echo "actual_fall_slew:$&FALL_IN_SLEW" >> {working_folder}/input_transition.txt


        print run
        * Measuring Cell Fall Time @ 50% of VDD(1.8V) 
        meas tran tinfall when v({active_pin})=0.9 FALL=1 
        meas tran tofall when v({output_pins[0]})=0.9 FALL=1
        let cfall = (tofall-tinfall)/{time_unit}
        if abs(cfall)>20
            meas tran tinfall when v({active_pin})=0.9 Rise=1 
            meas tran tofall when v({output_pins[0]})=0.9 FALL=1
            let cfall = abs(tofall-tinfall)/{time_unit}
        end
        print cfall
        echo "out_cap:$out_cap:cell_fall:$&cfall" >> {working_folder}/cell_fall.txt

        * Measuring Cell Rise Time @ 50% of VDD(1.8V) 
        meas tran tinrise when v({active_pin})=0.9 RISE=1 
        meas tran torise when v({output_pins[0]})=0.9 RISE=1
        let crise = (torise-tinrise)/{time_unit}
        if abs(crise)>20
            meas tran tinrise when v({active_pin})=0.9 FALL=1 
            meas tran torise when v({output_pins[0]})=0.9 RISE=1
            let crise = abs(tinrise-torise)/{time_unit}
        end
        print crise
        echo "out_cap:$out_cap:cell_rise:$&crise" >> {working_folder}/cell_rise.txt

        * Measuring Fall transition Time @ 80-20% of VDD(1.8V) 
        meas tran ft1 when v({output_pins[0]})=1.44 FALL=2 
        meas tran ft2 when v({output_pins[0]})=0.36 FALL=2
        let fall_tran = (ft2-ft1)/{time_unit}
        print fall_tran
        echo "out_cap:$out_cap:fall_transition:$&fall_tran" >> {working_folder}/fall_transition.txt
        
        * Measuring Rise transition Time @ 20-80% of VDD(1.8V) 
        meas tran rt1 when v({output_pins[0]})=1.44 RISE=2 
        meas tran rt2 when v({output_pins[0]})=0.36 RISE=2
        let rise_tran = ((rt1-rt2)/{time_unit})
        print rise_tran
        echo "out_cap:$out_cap:rise_transition:$&rise_tran" >> {working_folder}/rise_transition.txt
        * Set unate to 1 for positive_unate and 0 for negative_unate
        let pos_unate = {pos}
        let neg_unate = {neg} 
        if pos_unate
            * Measuring Rising Power if Positive Unate
            meas tran pt1 when v({active_pin})=0.1 RISE=2
            meas tran pt2 when v({output_pins[0]})=1.79 RISE=2
            * To avoid error due to peaks
            if pt1 > pt2 
                meas tran pt2 when v({output_pins[0]})=1.79 RISE=3
            end
            let pwr_stc1 = (@CLOAD[i])*v({output_pins[0]}) 
            meas tran pwr_swt1 INTEG pwr_stc1 from=pt1 to=pt2
            let pwr_swt1 = pwr_swt1/1p
            echo "out_cap:$out_cap:power_switch:$&pwr_swt1" >> {working_folder}/rise_power.txt

            * Measuring Falling Power if Positive Unate
            meas tran pt1 when v({active_pin})=1.79 FALL=2
            meas tran pt2 when v({output_pins[0]})=0.1 FALL=2
            let pwr_stc2 = (@CLOAD[i])*v({output_pins[0]}) - (@(VVPWR#branch)*VPWR)
            meas tran pwr_swt2 INTEG pwr_stc2 from=pt1 to=pt2
            let pwr_swt2 = pwr_swt2/1p
            echo "out_cap:$out_cap:power_switch:$&pwr_swt2" >> {working_folder}/fall_power.txt
        end
        if neg_unate
            * Measuring Rising Power if Negative Unate
            meas tran pt1 when v({active_pin})=1.75 FALL=2
            meas tran pt2 when v({output_pins[0]})=1.75 RISE=2
            if pt1 > pt2
                meas tran pt1 when v({active_pin})=1.75 FALL=3
            end
            let pwr_stc1 = (@CLOAD[i])*v({output_pins[0]})
            meas tran pwr_swt1 INTEG pwr_stc1 from=pt1 to=pt2
            let pwr_swt1 = pwr_swt1/1p
            echo "out_cap:$out_cap:power_switch:$&pwr_swt1" >> {working_folder}/rise_power.txt

            * Measuring Falling Power if Negative Unate
            meas tran pt1 when v({active_pin})=0.1 RISE=2
            meas tran pt2 when v({output_pins[0]})=0.1 RISE=2
            let pwr_stc2 = (@CLOAD[i])*v({output_pins[0]}) - (@(VVPWR#branch)*VPWR)
            meas tran pwr_swt2 INTEG pwr_stc2 from=pt1 to=pt2
            let pwr_swt2 = pwr_swt2/1p
            echo "out_cap:$out_cap:power_switch:$&pwr_swt2" >> {working_folder}/fall_power.txt
        end
        let run = run + 1
        * plot a y
    end
    end"""
    
    elif meas_type == 'input_caps':
        working_folder = path.join(output_folder,'input_caps')
        control_str = \
    f"""foreach case 1.8 0
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

def voltage_deductions(in_pins, out_pins, logic_function, active_pin, netlist_pins):
    """ Setup the Supply voltage and Logic Signal as per the logic function """

    in_pins = in_pins.replace(active_pin, '') + ' ' + active_pin
    
    pos_unate, pins_voltages = truths.Truths(in_pins.split(), [logic_function]).truth_table()
    # Setting up Power Supplies Voltages
    power_supplies = ['VPWR', 'VDD', 'VPB']
    gnd_supplies = ['VGND', 'VNB', 'VSS']
    power_str = '\n'.join([f'V{net} {net} 0 DC {VDD}' for net in power_supplies if net in netlist_pins])
    gnd_str = '\n'.join([f'V{net} {net} 0 DC 0' for net in gnd_supplies if net in netlist_pins])
    
    # Setting Up Signal Voltages
    active_pin_voltage = f'V{active_pin} {active_pin} 0 PULSE(0 {VDD} 0 0.01n 0.01n 50ns 100ns)'
    other_pins_voltage = []
    for net, logic in pins_voltages.items():
        if logic == 0:
            other_pins_voltage.append(f'V{net} {net} 0 DC 0')
        elif logic == 1:
            other_pins_voltage.append(f'V{net} {net} 0 DC {VDD}')
    
    other_pins_vol_str = '\n'.join(other_pins_voltage)
    
    power_supplies = power_str + '\n' + gnd_str
    signal_supplies = active_pin_voltage + '\n' + other_pins_vol_str
    
    return power_supplies, signal_supplies, pos_unate

def read_spice():
    """ Reads the .spice file specified in config.py 
        Returns: Pins (str) 
                 Spice Card Name  (str)"""
    
    with open(spice_file, "r") as file_object:
    # read file content
        spice_txt = file_object.read()
    
    subckt = [line for line in spice_txt.split('\n') if '.subckt' in line][0].split()
    spice_card = subckt[1]
    pins = ' '.join(subckt[2:])
    
    return pins, spice_card 

def Simulation_env(netlist_pins, spice_card, active_pin, sim_type = 'timing'):
    """Creates timing_harness.cir file"""
    
    include_statements = f".include '{library_file}' \n.include '{spice_file}'"
    input_pin_str = ' '.join(input_pins)
    power, signal, pos_unate = voltage_deductions(input_pin_str, output_pins[0], logic_function, active_pin, netlist_pins)
    control_text, working_folder = ng_postscript(sim_type, active_pin, pos_unate)
    harness_name = f"{sim_type}_harness.cir"
    harness_file = path.join(cell_directory, harness_name)
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

    return harness_file, working_folder, pos_unate

def ngspice_lunch(file_loc, working_folder):
    """Launches NGspice and delete old simulation files from the working_folder"""
    
    try:
        makedirs(working_folder)
    except OSError:
        print ("Creation of the directory %s failed" % working_folder)
        try:
            for root, dirs, files in os.walk(working_folder):
                for file in files:
                    os.remove(os.path.join(root, file))
            # print(f'Deleted Files in {working_folder}')
        except OSError:
            print(f'Manually delete Files in {working_folder}')
            exit()
    else:
        print ("Successfully created the directory %s " % working_folder)

    subprocess.call(["ngspice", '-b', '-r rawfile.raw' , file_loc])
    print('Finished Simulation')

def conv_logical(logic_func):
    for exp in logic_operator.keys():
        logic_func = logic_func.replace(exp, logic_operator[exp])
    return logic_func

def pwr_pin_text(pwr_pins):
    """Creates the pg_pin instacne for the cell"""
    # Setting up Power Supplies Voltages
    power_supplies = ['VPWR', 'VDD', 'VPB']
    gnd_supplies = ['VGND', 'VNB', 'VSS']
    pwr_pins_list = []
    for pwr_pin in pwr_pins:
        if pwr_pin in power_supplies: pg_type = 'primary_power'
        elif pwr_pin in gnd_supplies: pg_type =  'primary_ground'
        else: print(f'Check the pg_type of {pwr_pin} pin')
        pin_txt = \
            f"""pg_pin ("{pwr_pin}") {{
                pg_type : "{pg_type}";
                voltage_name : "{pwr_pin}";
            }} """
        pwr_pins_list.append(pin_txt)
    
    return pwr_pins_list

def timing_lib(card, timing_list, power_swt_list, inpin_list, cell_dict):
    """ Generate .lib file """
    
    pwr_pins = [pin for pin in pin_list if cell_dict['pin'][pin]['use'] in ['POWER', 'GROUND']]
    pwr_pin_list = pwr_pin_text(pwr_pins)

    logic_func = conv_logical(logic_function)
    cell_lib_file = path.join(cell_directory, 'timing.lib')
    timing_txt = '\n\t\t\t'.join(timing_list)
    power_swt_txt = '\n\t\t\t'.join(power_swt_list)
    input_pin_txt = '\n\t\t'.join(inpin_list) 
    pwr_pin_txt = '\n\t\t'.join(pwr_pin_list)
    cell_area = cell_dict['area']
    cell_card = f"""cell ("{card}") {{
        area: {cell_area};
        {pwr_pin_txt}
        {input_pin_txt}
        pin ("{output_pins[0]}") {{
            direction: "output";
            function: "{logic_func}";
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
    merge_obj = merge.MergeLib(base_file=lib_file, cells_file=cell_lib_file, output_file=merged_file_file)
    status = merge_obj.add_cells()
    if status:
        print(f'Updated Liberty File: {merged_file_file}')
    else:
        print(f'Manually add the timing lib using {cell_lib_file}')

def lef_extract(lef_file = 'custom_stdcell/nand2_1x/vsdcell_nand2_1x.lef'):
    """ Extract Pin information from the lef file"""
    
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
            except: print(f'\n For lef File:{lef_file}: Size Undefined \n Extract the lef file properly\n')
        
        # Extracting Pins   
        if 'PIN' in line and length == 2:
            current_pin_name = tokens[1]
            cell_dict['pin'].update({current_pin_name:{}})

        # Extracting Direction  
        if 'DIRECTION' in line and length == 3 and current_pin_name != None:
            direction_value = tokens[1]
            cell_dict['pin'][current_pin_name].update({'direction':direction_value})

        if 'USE' in line and length == 3 and current_pin_name != None:
            use_value = tokens[1]
            cell_dict['pin'][current_pin_name].update({'use':use_value})

        elif current_block_name is not None:
            block_content.append(line)
            if line.startswith("END"):
                assert line != "END LIBRARY", current_block_name
                tokens = line.split()
                assert len(tokens) == 2, line
                assert tokens[1] == current_block_name, (line, current_block_name)
                blocks.append("\n".join(block_content))
                current_block_name = None
                block_content = []

    assert not current_block_name, current_block_name
    assert not block_content, block_content
    
    return cell_dict

if __name__ == '__main__':
    pins, card = read_spice()
    timing_list = []
    power_swt_list = []
    pins_list = []
    cell_dict = lef_extract(lef_file)
    pin_list = list(cell_dict['pin'].keys())
    input_pins =  [pin for pin in pin_list if cell_dict['pin'][pin]['direction'] == 'INPUT']
    output_pins = [pin for pin in pin_list if cell_dict['pin'][pin]['direction'] == 'OUTPUT']
    
    for active_pin in input_pins:

        # Launching Timing simulation
        timing_cir_file, timing_folder, pos_unate = Simulation_env(pins, card, active_pin, sim_type='timing')
        ngspice_lunch(timing_cir_file, timing_folder)
        # Launching Input Capacitance simulation
        caps_cir_file, caps_folder, pos_unate = Simulation_env(pins, card, active_pin, sim_type='input_caps')
        ngspice_lunch(caps_cir_file, caps_folder)
        
        undte_value = 'positive_unate' if pos_unate == True else 'negative_unate'
        pin_info = timing.input_pins(caps_folder, active_pin, '1.5') 
        pins_list.append(pin_info)
        timing_info, power_swt_info = timing.timing_generator(timing_folder, unate=undte_value, related_pin=active_pin)
        timing_list.append(timing_info)
        power_swt_list.append(power_swt_info)

    timing_lib(card, timing_list, power_swt_list,pins_list, cell_dict)   
       
