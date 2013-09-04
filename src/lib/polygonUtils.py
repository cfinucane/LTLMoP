"""
PolygonUtils contains some functions to help wrangle unwieldy polygons
"""

import Polygon
import itertools
import decomposition

def flattenToList(iterable):
    return list(itertools.chain.from_iterable(iterable))

def splitMultiContourPolygon(poly):
    """ Take a multi-contour polygon and return a list of single-contour
        polygons. """

    # Get a list of any holes in the polygon
    hole_list = (Polygon.Polygon(contour) for k, contour in enumerate(poly) if poly.isHole(k))

    # Join all holes together to make it easier to subtract
    all_holes_poly = reduce(lambda p1, p2: p1+p2, hole_list, Polygon.Polygon())

    # Make each contour into a separate poly
    poly_list = [Polygon.Polygon(contour) - all_holes_poly \
                 for k, contour in enumerate(poly) \
                 if not poly.isHole(k)]

    # Split up any polygons with overlapping points
    poly_list = flattenToList((splitPolygonWithOverlappingPoints(poly) \
                     for poly in poly_list))

    return list(poly_list)

def splitPolygonWithOverlappingPoints(polygon):
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
        polyWithoutOverlapNode.extend(splitPolygonWithOverlappingPoints(newPoly))
        reducedPoly = Polygon.Polygon(decomposition.removeDuplicatePoints((polygon-newPoly)[0]))
        polyWithoutOverlapNode.extend(splitPolygonWithOverlappingPoints(reducedPoly))
    else:
        # no overlap point is found
        return [polygon]

    return polyWithoutOverlapNode
