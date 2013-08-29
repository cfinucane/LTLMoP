"""
The MapProcessing module provides functions for performing geometric
manipulations and calculations on maps; this pre-processing prepares
the maps to be used for specification compilation.
"""

import globalConfig
from contextlib import contextmanager
from collections import defaultdict
import logging

@contextmanager
def _trackRegionParents(spec_map):
    """ We need to keep track of the name that a person would use to refer
        to each region when writing a specification (i.e., the name of the
        original region that this region came from as opposed to an internal
        name generated during map processing) """

    # BEFORE PROCESSING: ensure that the region parents are marked
    for r in spec_map.regions:
        # If no parents are defined yet, assume that this is the
        # first time we are processing the map, and therefore we
        # should treat the current name as the root name
        if not hasattr(r, "mapProcessingParentRegionNames"):
            r.mapProcessingParentRegionNames = [r.name]

    # Let the processing proceed
    yield spec_map

    # AFTER PROCESSING: if one-to-one mappings exist, rename the regions
    # back to their root name, to maximize legibility
    for root_name, children_names in getRegionNameMappingFromMap(spec_map).iteritems():
        # Check if root has exactly one child
        if len(children_names) != 1:
            continue

        child_region = spec_map.getRegionByName(children_names[0])
        if len(child_region.mapProcessingParentRegionNames) == 1:   # Child has only one root
            child_region.name = root_name  # Rename

def getRegionNameMappingFromMap(spec_map):
    """ Returns a dictionary mapping names of root regions (i.e. region names
        as originally defined by the user) to a list of the names of corresponding
        child regions created during map processing. """

    region_name_mapping = defaultdict(list)
    for child_region in spec_map.regions:
        for root_name in child_region.mapProcessingParentRegionNames:
            region_name_mapping[root_name].append(child_region.name)

    return region_name_mapping

def substituteLocativePhrases(spec_text, spec_map):
    """ Detect any non-projective prepositional phrases (e.g. "between r1
        and r2") in the specification, create a new region in the map that
        corresponds to this location, and substitute the phrase with a
        reference to the name of the new region (e.g. "_between_r1_and_r2"). """

    with _trackRegionParents(spec_map):
        logging.debug("Substituting locative phrases...")
        new_spec_text = spec_text
        new_spec_map = spec_map

    return new_spec_text, new_spec_map

def createRegionsFromFreeSpace(spec_map):
    """ If there is any space enclosed by the boundary that is not associated
        with a defined region, create one or more new regions to make the map
        into a true partitioning of the workspace. """

    # TODO: add this step to wiki docs
    with _trackRegionParents(spec_map):
        logging.debug("Creating regions from free space...")
        new_spec_map = spec_map

    return new_spec_map

def removeObstacles(spec_map):
    """ Subtract any obstacle regions from the map. """

    # TODO: add this step to wiki docs
    with _trackRegionParents(spec_map):
        logging.debug("Removing obstacles...")
        new_spec_map = spec_map

    return new_spec_map

def resolveOverlappingRegions(spec_map):
    """ Splits up any overlapping regions.
        For example: consider a map of only "r1" and "r2", which partially
        overlap. These regions would be replaced by [r1\r2, r1&r2, r2\r1]. """

    with _trackRegionParents(spec_map):
        logging.debug("Resolving overlapping regions...")
        new_spec_map = spec_map

    return new_spec_map

def decomposeRegionsIntoConvexRegions(spec_map):
    """ Break up any concave regions into convex subregions. """

    with _trackRegionParents(spec_map):
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

    def rectangle(x, y, w, h):
        return [Point(x, y), Point(x+w, y), Point(x+w, y+h), Point(x, y+h)]

    test_map.regions.append(Region(name="boundary", points=rectangle(10, 10, 50, 20)))
    test_map.regions.append(Region(name="r1", points=rectangle(10, 10, 10, 10)))
    test_map.regions.append(Region(name="r2", points=rectangle(50, 20, 10, 10)))
    test_map.regions.append(Region(name="r3", points=rectangle(12, 12, 6, 6)))
    test_map.regions.append(Region(name="obstacle", points=rectangle(45, 15, 10, 10)))
    test_map.getRegionByName("obstacle").isObstacle = True

    # Create a test spec that contains a locative phrase
    test_spec = """group places is r2, r3, between r1 and r2
                   visit all places"""

    # Run some tests
    def exportIntermediateMap(test_name):
        print "Regions:", test_map.getRegionNames()
        out_filename = "mapProcessingTestResult_" + test_name + ".svg"
        test_map.exportToSVG(out_filename)
        print "Wrote intermediate map to {}.".format(out_filename)

    print "Spec:", test_spec
    exportIntermediateMap("original")

    test_spec, test_map = substituteLocativePhrases(test_spec, test_map)
    print "Spec:", test_spec
    exportIntermediateMap("locative_phrases")

    test_map = createRegionsFromFreeSpace(test_map)
    exportIntermediateMap("free_space")

    test_map = removeObstacles(test_map)
    exportIntermediateMap("obstacles")

    test_map = resolveOverlappingRegions(test_map)
    exportIntermediateMap("overlapping")

    test_map = decomposeRegionsIntoConvexRegions(test_map)
    exportIntermediateMap("convexify")

    adj = calculateTopologicalAdjacencies(test_map)
    print "Adjacencies:", adj
    
    print "Mapping:", getRegionNameMappingFromMap(test_map)

    # TODO: add assertions so this test can be evaluated automatically?
