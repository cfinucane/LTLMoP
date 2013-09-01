"""
The MapProcessing module provides functions for performing geometric
manipulations and calculations on maps; this pre-processing prepares
the maps to be used for specification compilation.
"""

import globalConfig
import logging

from contextlib import contextmanager
from collections import defaultdict
import itertools

from decomposition import removeDuplicatePoints
import Polygon
import regions

# TODO: move some stuff to polygonUtils

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

    return dict(region_name_mapping)

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

        # Start with the boundary region
        boundary_region = spec_map.getRegionByName("boundary")
        free_space_poly = boundary_region.getAsPolygon()

        # Subtract all the other regions
        for r in spec_map.regions:
            if r is not boundary_region:
                free_space_poly -= r.getAsPolygon()

        spec_map.regions.remove(spec_map.getRegionByName("boundary"))
        spec_map.regions.extend((_createNewRegionWithParentFromPoly(spec_map, poly, ["free_space"]) \
                                 for poly in _splitMultiContourPolygon(free_space_poly)))

    return spec_map

def removeObstacles(spec_map):
    """ Subtract any obstacle regions from the map. """

    # TODO: add this step to wiki docs
    with _trackRegionParents(spec_map):
        logging.debug("Removing obstacles...")

        # Get all the obstacle polygons
        obstacle_list = (r.getAsPolygon() for r in spec_map.regions if r.isObstacle)

        # Join all obstacles together to make it easier to subtract
        all_obstacles_poly = reduce(lambda p1, p2: p1+p2, obstacle_list, Polygon.Polygon())

        # Save the old regions that are not obstacles
        original_nonobstacle_regions = [r for r in spec_map.regions if not r.isObstacle]

        # Start building a new map afresh
        spec_map.regions = []

        for r in original_nonobstacle_regions:
            # Subtract the obstacles from the old regions to make one or more new ones
            new_polygons = _splitMultiContourPolygon(r.getAsPolygon() - all_obstacles_poly)
            spec_map.regions.extend((_createNewRegionWithParentFromPoly(spec_map, new_poly, r) \
                                     for new_poly in new_polygons))

    return spec_map

def _createNewRegionWithParentFromPoly(spec_map, poly, parent):
    """ Creates a new region from a polygon `poly`, giving it the lowest "pXXX" name available
        amongst existing regions in `spec_map`.

        If `parent` is a Region object, sets the parents of the new region to inherit those of
        the `parent` region.  Otherwise, sets the parents directly to the value of `parent`. """

    new_region_name = "p{}".format(spec_map.getNextAvailableRegionNumber(prefix="p"))
    new_region = regions.Region.fromPolygon(new_region_name, poly)

    if isinstance(parent, regions.Region):
        new_region.mapProcessingParentRegionNames = parent.mapProcessingParentRegionNames
    else:
        new_region.mapProcessingParentRegionNames = parent

    return new_region

def _splitMultiContourPolygon(poly):
    """ Take a multi-contour polygon and return a list of single-contour
        polygons. """

    # Get a list of any holes in the polygon
    hole_list = (contour for k, contour in enumerate(poly) if poly.isHole(k))

    # Join all holes together to make it easier to subtract
    all_holes_poly = reduce(lambda p1, p2: p1+p2, hole_list, Polygon.Polygon())

    # Make each contour into a separate poly
    poly_list = [Polygon.Polygon(contour) - all_holes_poly \
                 for k, contour in enumerate(poly) \
                 if not poly.isHole(k)]

    # Split up any polygons with overlapping points
    poly_list = itertools.chain.from_iterable((_splitPolygonWithOverlappingPoints(poly) \
                     for poly in poly_list))

    return list(poly_list)

def _splitPolygonWithOverlappingPoints(polygon):
    """
    When there are points overlapping each other in a given polygon
    First decompose this polygon into sub-polygons at the overlapping point
    """

    # TODO: refactor this function
    # TODO: don't ignore holes

    # - recursively break the polygon at any overlap point into two polygons
    # until no overlap points are found
    # - here we are sure there is only one contour in the given polygon

    ptDic = {}
    overlapPtIndex = None
    # look for overlap point and stop when one is found
    for i, pt in enumerate(polygon[0]):
        if pt not in ptDic:
            ptDic[pt] = [i]
        else:
            ptDic[pt].append(i)
            overlapPtIndex = ptDic[pt]
            break

    if overlapPtIndex:
        polyWithoutOverlapNode = []
        # break the polygon into sub-polygons
        newPoly = Polygon.Polygon(polygon[0][overlapPtIndex[0]:overlapPtIndex[1]])
        polyWithoutOverlapNode.extend(_splitPolygonWithOverlappingPoints(newPoly))
        reducedPoly = Polygon.Polygon(removeDuplicatePoints((polygon-newPoly)[0]))
        polyWithoutOverlapNode.extend(_splitPolygonWithOverlappingPoints(reducedPoly))
    else:
        # no overlap point is found
        return [polygon]

    return polyWithoutOverlapNode

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
    # entirely in the first... plus some obstacles and other stuff

    test_map = RegionFileInterface()

    def rectangle(x, y, w, h):
        return [Point(x, y), Point(x+w, y), Point(x+w, y+h), Point(x, y+h)]

    test_map.regions.append(Region(name="boundary", points=rectangle(10, 10, 50, 20)))
    test_map.regions.append(Region(name="r1", points=rectangle(10, 10, 10, 10)))
    test_map.regions.append(Region(name="r2", points=rectangle(50, 20, 10, 10)))
    test_map.regions.append(Region(name="r3", points=rectangle(12, 12, 6, 6)))
    test_map.regions.append(Region(name="r4", points=rectangle(20, 20, 30, 10)))
    test_map.regions.append(Region(name="obstacle1", points=rectangle(45, 15, 10, 10)))
    test_map.getRegionByName("obstacle1").isObstacle = True
    test_map.regions.append(Region(name="obstacle2", points=rectangle(30, 0, 5, 50)))
    test_map.getRegionByName("obstacle2").isObstacle = True

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
    exportIntermediateMap("0_original")

    test_spec, test_map = substituteLocativePhrases(test_spec, test_map)
    print "Spec:", test_spec
    exportIntermediateMap("1_locative_phrases")

    test_map = createRegionsFromFreeSpace(test_map)
    exportIntermediateMap("2_free_space")

    test_map = removeObstacles(test_map)
    exportIntermediateMap("3_obstacles")

    test_map = resolveOverlappingRegions(test_map)
    exportIntermediateMap("4_overlapping")

    test_map = decomposeRegionsIntoConvexRegions(test_map)
    exportIntermediateMap("5_convexify")

    adj = calculateTopologicalAdjacencies(test_map)
    print "Adjacencies:", adj
    
    print "Mapping:", getRegionNameMappingFromMap(test_map)

    # TODO: add assertions so this test can be evaluated automatically?
