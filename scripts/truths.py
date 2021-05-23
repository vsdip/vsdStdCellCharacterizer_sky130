#!/usr/bin/python3
#
# Copyright 2016 Trey Morris
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

import itertools
# from prettytable import PrettyTable
import re


class Gob(object):
    pass


class Truths(object):
    def __init__(self, base=None, phrases=None, ints=True):
        if not base:
            raise Exception('Base items are required')
        self.base = base
        self.phrases = phrases or []
        self.ints = ints

        # generate the sets of booleans for the bases
        self.base_conditions = list(itertools.product([False, True],
                                                      repeat=len(base)))

        # regex to match whole words defined in self.bases
        # used to add object context to variables in self.phrases
        self.p = re.compile(r'(?<!\w)(' + '|'.join(self.base) + ')(?!\w)')

    def calculate(self, *args):
        # store bases in an object context
        g = Gob()
        for a, b in zip(self.base, args):
            setattr(g, a, b)

        # add object context to any base variables in self.phrases
        # then evaluate each
        eval_phrases = []
        for item in self.phrases:
            item = self.p.sub(r'g.\1', item)
            eval_phrases.append(eval(item))

        # add the bases and evaluated phrases to create a single row
        row = [getattr(g, b) for b in self.base] + eval_phrases
        if self.ints:
            return [int(item) for item in row]
        else:
            return row

    def truth_table(self):
        tt = []
        for conditions_set in self.base_conditions:
            tt.append(self.calculate(*conditions_set))
            
            if len(tt) > 1:
                # Checking the change in the output
                # size_condition = len(tt[-1)
                
                if tt[-1][-1] != tt[-2][-1]:
                    
                    last_inst_inputs = tt[-1][:-1]
                    prev_inst_inputs = tt[-2][:-1]
                    length = range(len(last_inst_inputs)) 
                    diff_inputs = [self.base[i] for i in length
                                                if last_inst_inputs[i] != prev_inst_inputs[i]]
                    
                    # Voltages of Other Inputs:
                    if len(diff_inputs) == 1:
                        active_pin = diff_inputs[0]
                        other_pins = {self.base[i]: value for i, value in enumerate(last_inst_inputs[:-1])}
                        
                        if tt[-1][-1] == tt[-1][-2]:
                            pos_unate = True
                        else:
                            pos_unate = False

                        print('Pin: Current: Previous')
                        print(diff_inputs[0], tt[-1][:], tt[-2][:])
                        return pos_unate, other_pins



    # def __str__(self):
    #     t = PrettyTable(self.base + self.phrases)
    #     for conditions_set in self.base_conditions:
    #         t.add_row(self.calculate(*conditions_set))
    #     return str(t)

if __name__ == '__main__':
    print(Truths(['a',' b', 'c', 'd'], ['not ((a or b) ^ (c or d) ) ']).truth_table())