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
import copy

import regions
import polygonUtils
import decomposition
import parseLP
import Polygon

@contextmanager
def _trackRegionRoots(spec_map):
    """ We need to keep track of the name that a person would use to refer
        to each region when writing a specification (i.e., the name(s) of the
        original "root" region(s) that a region came from as opposed to the
        internal names generated during map processing).

        In order to ensure proper accounting, map processing operations
        should generally take place inside this context manager. """

    ### BEFORE PROCESSING: ###

    # Ensure that the region roots are marked
    _ensureRegionRootsAreMarked(spec_map)

    ### Let the processing proceed ###
    yield spec_map

    ### AFTER PROCESSING: ###

    # Ensure that the region roots are marked, again
    # (since new regions may have been added)
    _ensureRegionRootsAreMarked(spec_map)

    # Rename subregions in order, starting with "p1"
    # (It's much easier to do this here, than to try to be careful
    # about this during each map processing operation)
    for k, region in enumerate(spec_map.regions):
        region.name = "p{}".format(k+1)

    # If one-to-one mappings exist, rename the regions back to their root name,
    # in order to maximize legibility
    for root_name, children_names in getRegionNameMappingFromMap(spec_map).iteritems():
        # Check if root has exactly one child
        if len(children_names) != 1:
            continue

        child_region = spec_map.getRegionByName(children_names[0])
        if len(child_region.mapProcessingRootRegionNames) == 1:   # Child has only one root
            child_region.name = root_name  # Rename

def _ensureRegionRootsAreMarked(spec_map):
    """ Ensure that all regions in `spec_map` have roots marked.

        If any are unmarked, assume that this is the first time we are
        processing the map, and therefore we should treat the current name
        as the root name. """

    for r in spec_map.regions:
        if not hasattr(r, "mapProcessingRootRegionNames"):
            r.mapProcessingRootRegionNames = [r.name]

def getRegionNameMappingFromMap(spec_map):
    """ Returns a dictionary mapping names of root regions (i.e. region names
        as originally defined by the user) to a list of the names of corresponding
        child regions created during map processing. """

    # Just in case the map hasn't been previously processed
    _ensureRegionRootsAreMarked(spec_map)

    region_name_mapping = defaultdict(list)
    for child_region in spec_map.regions:
        for root_name in child_region.mapProcessingRootRegionNames:
            region_name_mapping[root_name].append(child_region.name)

    return dict(region_name_mapping)

def substituteLocativePhrases(spec_text, spec_map):
    """ Detect any non-projective prepositional phrases (e.g. "between r1
        and r2") in the specification, create a new region in the map that
        corresponds to this location, and substitute the phrase with a
        reference to the name of the new region (e.g. "_between_r1_and_r2"). """

    with _trackRegionRoots(spec_map):
        logging.debug("Substituting locative phrases...")
        spec_text, spec_map = parseLP.processLocativePhrases(spec_text, spec_map)

    return spec_text, spec_map

def createRegionsFromFreeSpace(spec_map):
    """ If there is any space enclosed by the boundary that is not associated
        with a defined region, create one or more new regions to make the map
        into a true partitioning of the workspace. """
    # TODO: add this step to wiki docs

    # This operation is meaningless without a boundary region
    if spec_map.indexOfRegionWithName("boundary") < 0:
        raise ValueError("Cannot create free-space region with no boundary defined")

    with _trackRegionRoots(spec_map):
        logging.debug("Creating regions from free space...")

        # Start with the boundary region
        boundary_region = spec_map.getRegionByName("boundary")
        free_space_poly = boundary_region.getAsPolygon()

        # Subtract all the other regions
        for r in spec_map.regions:
            if r is not boundary_region:
                free_space_poly -= r.getAsPolygon()

        # Remove the boundary
        spec_map.regions.remove(boundary_region)

        # Add in the new free-space regions
        spec_map.regions.extend(_createNewRegionsWithParentFromPoly(free_space_poly, ["free_space"]))

    return spec_map

def clipRegionsToBoundary(spec_map):
    """ Remove any parts of regions that are sticking outside of the boundary. """
    # TODO: add this step to wiki docs

    # This operation is meaningless without a boundary region
    if spec_map.indexOfRegionWithName("boundary") < 0:
        raise ValueError("Cannot clip regions to boundary with no boundary defined")

    with _trackRegionRoots(spec_map):
        logging.debug("Clipping regions to boundary...")

        boundary_region_poly = spec_map.getRegionByName("boundary").getAsPolygon()

        # Intersect all regions with the boundary
        new_regions = []
        for r in spec_map.regions:
            r_poly = r.getAsPolygon()
            new_region_poly = boundary_region_poly & r_poly
            new_regions.extend(_createNewRegionsWithParentFromPoly(new_region_poly, [r]))

        spec_map.regions = new_regions

    return spec_map

def removeObstacles(spec_map):
    """ Subtract any obstacle regions from the map. """
    # TODO: add this step to wiki docs

    with _trackRegionRoots(spec_map):
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
            new_polygon = r.getAsPolygon() - all_obstacles_poly
            spec_map.regions.extend(_createNewRegionsWithParentFromPoly(new_polygon, [r]))

    return spec_map

def _createNewRegionsWithParentFromPoly(poly, parents):
    """ Creates one or more new regions from a polygon `poly`.

        `parent` is a list of Region objects and/or names, of which this new
        region should be considered a subregion. For Region objects, the new
        region will inherit their roots; names, on the other hand, will be added
        to the root list directly. """

    # Calculate the list of roots that the new region(s) should have
    new_region_roots = []
    for parent in parents:
        if isinstance(parent, regions.Region):
            new_region_roots.extend(parent.mapProcessingRootRegionNames)
        else:
            new_region_roots.append(parent)

    # Create a new region for each non-self-overlapping contour in the polygon
    new_regions = []
    for p in polygonUtils.splitMultiContourPolygon(poly):
        # We can name all the regions the same thing, as they will be renamed
        # by the _trackRegionRoots() context-manager later
        new_region = regions.Region.fromPolygon("map_processing_temp_region", p)

        # If any parent is an obstacle, we probably are too...
        new_region.isObstacle = any((isinstance(parent, regions.Region) and \
                                     parent.isObstacle for parent in parents))

        # Use copy.copy() here to make sure different lists are used
        new_region.mapProcessingRootRegionNames = copy.copy(new_region_roots)

        new_regions.append(new_region)

    return new_regions


def resolveOverlappingRegions(spec_map):
    """ Splits up any overlapping regions.
        For example: consider a map of only "r1" and "r2", which partially
        overlap. These regions would be replaced by [r1\r2, r1&r2, r2\r1]. """

    with _trackRegionRoots(spec_map):
        logging.debug("Resolving overlapping regions...")

        # We won't be able to modify our list in-place
        original_regions = copy.copy(spec_map.regions)

        # Start building a new map afresh
        spec_map.regions = [spec_map.regions[0]]
        occupied_space = spec_map.regions[0].getAsPolygon()

        # TODO: Attempt to document this algorithm (Jim?)
        for r in original_regions[1:]:
            spec_map.regions = polygonUtils.flattenToList((_getIntersectionAndDifferenceRegions(r2, r) \
                                                           for r2 in spec_map.regions))

            non_overlapping_part = r.getAsPolygon() - occupied_space
            if non_overlapping_part.nPoints() != 0:
                spec_map.regions.extend(_createNewRegionsWithParentFromPoly(non_overlapping_part, [r]))
                occupied_space += r.getAsPolygon()

    return spec_map

def _getIntersectionAndDifferenceRegions(r1, r2):
    """ Returns regions corresponding to (r1 & r2) and (r1 - r2),
        if they are non-empty.

        Used in splitting up overlapping regions. """

    # TODO: redo with Regions using Polygons as internal data structure

    r1_poly = r1.getAsPolygon()
    r2_poly = r2.getAsPolygon()

    # Perform set operations
    intersection = r1_poly & r2_poly
    r1_minus_r2 = r1_poly - r2_poly

    # Create new regions from any non-empty results, with proper parentage
    new_regions = []
    if intersection.nPoints() != 0:
        new_regions.extend(_createNewRegionsWithParentFromPoly(intersection, [r1, r2]))
    if r1_minus_r2.nPoints() != 0:
        new_regions.extend(_createNewRegionsWithParentFromPoly(r1_minus_r2, [r1]))

    return new_regions

def decomposeRegionsIntoConvexRegions(spec_map):
    """ Break up any concave regions into convex subregions. """

    with _trackRegionRoots(spec_map):
        logging.debug("Decomposing into convex regions...")

        new_regions = []
        for r in spec_map.regions:
            poly = r.getAsPolygon()

            # Separate region into outer polygon and hole polygons
            # TODO: Make decomposition.py do this
            hole_list = [Polygon.Polygon(contour) for k, contour in enumerate(poly) \
                         if poly.isHole(k)]
            poly = Polygon.Utils.fillHoles(poly)

            # Call the MP5 algorithm
            decomposer = decomposition.decomposition(poly, hole_list)
            for new_poly in decomposer.MP5():
                new_regions.extend(_createNewRegionsWithParentFromPoly(new_poly, [r]))

        spec_map.regions = new_regions

    return spec_map

def calculateTopologicalAdjacencies(spec_map):
    """ For each region, determine which other regions can be reached from
        it directly. Currently, this assumes topological adjacency if and
        only if two regions have at least one face (or subface) in common. """

    logging.debug("Calculating topological adjacencies...")

    # Construct a list of pairs of names of connected regions
    adjacency_list = [(r1.name, r2.name) for \
                      r1, r2 in _findRegionsWithSharedFaces(spec_map)]

    # Make all transitions bidirectional
    adjacency_list.extend([(y, x) for x, y in adjacency_list])

    return adjacency_list

def _findRegionsWithSharedFaces(spec_map):
    """ Return a list of pairs of regions with shared faces. """

    adjacency_list = []

    for r1, r2 in itertools.combinations(spec_map.regions, 2):
        # Ignore overlap in identical regions
        if r1.getAsPolygon() == r2.getAsPolygon():
            continue

        # If r1 and r2 have any shared faces, assume a connection
        if len(_getFacesSharedByRegions(r1, r2)) > 0:
            adjacency_list.append((r1, r2))

    return adjacency_list

def _getFacesSharedByRegions(r1, r2):
    """ Return a list of faces that regions `r1` and `r2` have in common. """

    # Construct sets of each region's faces
    r1_faces = set((f for f in r1.getFaces(includeHole=True)))
    r2_faces = set((f for f in r2.getFaces(includeHole=True)))

    # Find shared faces by simple set intersection
    shared_faces = list(r1_faces & r2_faces)

    return shared_faces



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

    test_map.regions.append(Region(name="boundary", points=rectangle(100, 100, 500, 200)))
    test_map.regions.append(Region(name="r1", points=rectangle(100, 100, 100, 100)))
    test_map.regions.append(Region(name="r2", points=rectangle(500, 200, 100, 100)))
    test_map.regions.append(Region(name="r3", points=rectangle(120, 120, 60, 60)))
    test_map.regions.append(Region(name="r4", points=rectangle(200, 200, 300, 100)))
    test_map.regions.append(Region(name="obstacle1", points=rectangle(450, 150, 100, 100)))
    test_map.getRegionByName("obstacle1").isObstacle = True
    test_map.regions.append(Region(name="obstacle2", points=rectangle(300, 0, 50, 500)))
    test_map.getRegionByName("obstacle2").isObstacle = True

    # Create a test spec that contains a locative phrase
    test_spec = """group places is within 30 of r2, r3, between r1 and r2
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

    test_map = clipRegionsToBoundary(test_map)
    exportIntermediateMap("2_clip")

    test_map = createRegionsFromFreeSpace(test_map)
    exportIntermediateMap("3_free_space")

    test_map = removeObstacles(test_map)
    exportIntermediateMap("4_obstacles")

    test_map = resolveOverlappingRegions(test_map)
    exportIntermediateMap("5_overlapping")

    test_map = decomposeRegionsIntoConvexRegions(test_map)
    exportIntermediateMap("6_convexify")

    adj = calculateTopologicalAdjacencies(test_map)
    print "Adjacencies:", adj

    print "Mapping:", getRegionNameMappingFromMap(test_map)

    # Export .regions file for further inspection
    #test_map.recalcAdjacency()
    #for r in test_map.regions:
        #r.recalcBoundingBox()
    #test_map.writeFile("mapProcessingTest.regions")

    # TODO: add assertions so this test can be evaluated automatically?
