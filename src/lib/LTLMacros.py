#!/usr/bin/env python

"""
This file contains functions for generating commonly-used LTL fragments
that are generally independent of which specification language parser is
being used.
"""

import math
import LTLParser.LTLFormula as LTLFormula 
from collections import defaultdict
import re

def getBitEncodingFragment(element_list, element_name):
    """ Return the LTL fragment for a propositional bitvector assignment
        corresponding to the given element of the given list """

    # TODO: Implement caching?

    num_bits = int(math.ceil(math.log(len(element_list), 2)))
    element_index = element_list.index(element_name)

    bit_string = "{0:0>{1}}".format(bin(element_index)[2:], num_bits)

    return " & ".join(("bit"+str(bit) if v=='1' else
                       "!bit"+str(bit) for bit, v in enumerate(bit_string)))


def getTopologyFragment(region_names, adjacency_hash, use_bits=True):
    """ Return an LTL fragment restricting transitions between regions to be
        limited to those allowed by the topology."""

    adj_formulas = ("[]({}->next({}))".format(r, " | ".join(adjacency_hash[r].keys()))
                    for r in region_names)

    adj_formula = " & \n".join(adj_formulas)

    if use_bits:
        adj_formula = convertRegionNamesToBitVectors(adj_formula, region_names)

    return LTLFormula.distributeNexts(adj_formula) # Be sure to distribute next() operators

def convertRegionNamesToBitVectors(ltl_string, region_names):
    """ Substitute all region names in an LTL formula with the appropriate bit vector fragments.
        WARNING: Bit vector values are dependent on ordering of `region_names`, so ordering
        consistency must be ensured."""

    # TODO: This doesn't belong here; move it somewhere logical (SpecCompiler?)
    ltl_string =  re.sub(r"\b(?:{})\b".format("|".join(region_names)),  # match any region name
                         lambda m: "("+getBitEncodingFragment(region_names, m.group())+")",  # replace with bit-enc
                         ltl_string)

    return LTLFormula.distributeNexts(ltl_string) # Be sure to distribute next() operators

def getInitialRegionFragment(region_names, use_bits=True):
    """ Return an LTL fragment which only admits valid regions in the initial state.
        This may be redundant if an initial region is specified separately,
        but it is here to ensure the system cannot start from an invalid, or empty region. """

    if use_bits:
        valid_settings = (getBitEncodingFragment(region_names, r) for r in region_names)
    else:
        valid_settings = (" & ".join((r2 if r2==r else "!"+r2 for r2 in region_names))
                                                              for r in region_names)

    valid_settings = ("({})".format(s) for s in valid_settings)  # Add parens for clarity

    return "({})".format(" | ".join(valid_settings))

def _adjacencyListToHash(region_names, adj_list):
    """ Convert a list of adjacencies to an adjacency hash (for efficiency).
        WARNING: Assumes all adjacencies are bidirectional, and that
        self-transitions are acceptable. """

    # TODO: This doesn't belong here; move it somewhere logical (Map?)

    adj_hash = defaultdict(dict)

    # Load in adjacencies from list (assume all are bidirectional)
    for r1, r2 in adj_list:
        adj_hash[r1][r2] = True
        adj_hash[r2][r1] = True

    # Allow self-transitions
    for r in region_names:
        adj_hash[r][r] = True

    return adj_hash

def _regionsAreAdjacent(adj_hash, region_name_1, region_name_2):
    """ Wrap adjacency tests so we are data-structure agnostic.
        Returns True if the regions are topologically adjacent; otherwise False. """

    # TODO: This doesn't belong here; move it somewhere logical (Map?)
    return (region_name_1 in adj_hash) and \
           (region_name_2 in adj_hash[region_name_1])



######################
### Testing code: ####
######################

if __name__ == "__main__":
    regions = ("center", "north", "east")
    adjacencies = (("center", "north"), ("center", "east"))

    print "Regions: ", regions

    ### Test getBitEncodingFragment ###
    for region in regions:
        print region, ":", getBitEncodingFragment(regions, region)

    ### Test getInitialRegionFragment ###
    for use_bits in (False, True):
        print getInitialRegionFragment(regions, use_bits=use_bits)

    ### Test getTopologyFragment ###
    for use_bits in (False, True):
        print getTopologyFragment(regions, _adjacencyListToHash(regions, adjacencies),
                                  use_bits=use_bits)

    # TODO: Use LTLParser evaluation to test that restrictions are correct
