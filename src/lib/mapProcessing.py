"""
The MapProcessing module provides functions for performing geometric
manipulations and calculations on maps; this pre-processing prepares
the maps to be used for specification compilation.
"""

import globalConfig
import logging

# TODO: Change the way we handle "region mapping"; it should
#       probably be embedded inside the map itself

def substituteLocativePhrases(spec_text, spec_map):
    """ Detect any non-projective prepositional phrases (e.g. "between r1
        and r2") in the specification, create a new region in the map that
        corresponds to this location, and substitute the phrase with a
        reference to the name of the new region (e.g. "_between_r1_and_r2"). """

    logging.debug("Substituting locative phrases...")
    new_spec_text = spec_text
    new_spec_map = spec_map

    return new_spec_text, new_spec_map

def resolveOverlappingRegions(spec_map):
    """ Splits up any overlapping regions.
        For example: consider a map of only "r1" and "r2", which partially
        overlap. These regions would be replaced by [r1\r2, r1&r2, r2\r1]. """

    logging.debug("Resolving overlapping regions...")
    new_spec_map = spec_map

    return new_spec_map

def decomposeRegionsIntoConvexRegions(spec_map):
    """ Break up any concave regions into convex subregions. """

    logging.debug("Decomposing into convex regions...")
    new_spec_map = spec_map

    return new_spec_map

def calculateTopologicalAdjacencies(spec_map):
    """ For each region, determine which other regions can be reached from
        it directly. Currently, this assumes topological adjacency if and 
        only if two regions have at least one face (or subface) in common. """

    logging.debug("Calculating topological adjacencies...")
    adjacency_list = []

    return adjacency_list


######################
### Testing code: ####
######################

if __name__ == "__main__":
    from regions import RegionFileInterface, Region, Point

    # Create a test map with two squares sitting slightly apart
    # (in both x and y), and a third smaller square contained 
    # entirely in the first

    test_map = RegionFileInterface()
    test_map.regions.append(Region(name="r1", points=[Point(10, 0),
                                                      Point(20, 0),
                                                      Point(20, 0),
                                                      Point(10, 0)]))
    test_map.regions.append(Region(name="r2", points=[Point(50, 0),
                                                      Point(60, 0),
                                                      Point(60, 0),
                                                      Point(50, 0)]))
    test_map.regions.append(Region(name="r3", points=[Point(12, 2),
                                                      Point(18, 2),
                                                      Point(18, 8),
                                                      Point(12, 8)]))

    # Create a test spec that contains a locative phrase
    test_spec = """group places is r2, r3, between r1 and r2
                   visit all places"""

    # Run some tests
    print "Spec:", test_spec
    print "Regions:", test_map.getRegionNames()

    test_spec, test_map = substituteLocativePhrases(test_spec, test_map)
    print "Spec:", test_spec
    print "Regions:", test_map.getRegionNames()

    test_map = resolveOverlappingRegions(test_map)
    print "Regions:", test_map.getRegionNames()

    test_map = decomposeRegionsIntoConvexRegions(test_map)
    print "Regions:", test_map.getRegionNames()

    adj = calculateTopologicalAdjacencies(test_map)
    print "Adjacencies:", adj

    # TODO: mapping
    # TODO: add assertions so this test can be evaluated automatically?
