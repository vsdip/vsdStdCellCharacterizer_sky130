import re

class MergeLib():
    def __init__(self, base_file, cells_file, output_file):

        with open(base_file) as base_doc:
            self.base_doc = base_doc.read()
        
        with open(cells_file) as cell_doc:
            self.cell_doc = cell_doc.read()

        self.removed_last_bracket = False
        self.output_file = output_file

    def cells_list(self):
        """Generates the list of cells"""
        # self.cell_list_base = []
        # self.cell_list_act = []

        pattern = "cell \(.*?\)"
        
        cell_list_base = [cell for cell in re.findall(pattern, self.base_doc) if 'cell ()' not in cell] # List of cells present in base lib
        cellformat_base = [cell.replace('(','\(').replace(')','\)') for cell in cell_list_base] # Formated string for regex pattern
        cells_group_base = [re.search(cell, self.base_doc) for cell in cellformat_base] # Group of regex matches
        cells_dict_base = {base_cell.group(0):{'index': index, 'start': base_cell.start(), 'end': base_cell.end()} for index, base_cell in enumerate(cells_group_base)}

        cell_list_act = [cell for cell in re.findall(pattern, self.cell_doc) if 'cell ()' not in cell] # List of cells present in the active lib
        common_cells = [cell for cell in cell_list_act if cell in cell_list_base] # Common cells needs to be deleted

        return cells_dict_base, cell_list_act, common_cells

    def delete_cells(self):
        """Deletes common cells from the base to add the new cell data from the new lib file """
        cells_dict_base, cell_list_act, common_cells = self.cells_list()
        while(len(common_cells) != 0):
            cell_index = cells_dict_base[common_cells[0]]['index']
            if cell_index != len(cells_dict_base)-1:
                cell_start = cells_dict_base[common_cells[0]]['start']
                next_cell_start = [values['start'] for cell_name, values in cells_dict_base.items() if values['index'] == (cell_index+1)][0]
                cell_content = self.base_doc[cell_start: next_cell_start]
                self.base_doc = self.base_doc.replace(cell_content, '')
            else:
                cell_start = cells_dict_base[common_cells[0]]['start']
                cell_content = self.base_doc[cell_start:]
                self.base_doc = self.base_doc.replace(cell_content, '')
                self.removed_last_bracket = True
            cells_dict_base, cell_list_act, common_cells = self.cells_list()

    def add_cells(self):
        """Add cells at the bottom of the base lib file after deleting all common cells"""
        # To delete all common cells
        self.delete_cells()
        if self.removed_last_bracket:
            new_lib = self.base_doc + self.cell_doc + '\n}\n'
        else:
            end_part = self.base_doc[-4:] 
            if '}' in  end_part:
                new_lib = self.base_doc[0:-4] + '\n\t\t' + self.cell_doc + '\n}\n'
        # print(new_lib)
        try:    
            with open(self.output_file, "w") as file_doc:
                file_doc.write(new_lib)
            return True
        except:
            return False

if __name__ == '__main__':
    base = 'sta_results/sky130_fd_sc_hd__tt_025C_1v80.lib'
    cell = 'custom_stdcell/and3_2x/timing.lib'
    file_obj = MergeLib(base, cell)
    file_obj.add_cells()
    # print(file_obj.cell_doc)
    pass