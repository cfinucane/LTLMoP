#!/usr/bin/env python
"""
ParseLP contains functions for parsing locative prepositional phrases
in specifications, and creating appropriate new regions on a map.
"""

import re
import math
import regions
import Polygon

#################
### Constants ###
#################

DEFAULT_NEAR_DISTANCE = 50  # px

###############################
### LP Processing Functions ###
###############################

def _regionNameFromPhrase(phrase):
    """ Given a locative phrase, return a name for the new corresponding
        region that will be created. """

    # Substitute all spaces with underscores, and then prepend an underscore
    new_region_name = "_" + re.sub(r"\s+", "_", phrase)

    return new_region_name

def _createNewLPRegion(spec_map, phrase, parameters):
    """ Create a new locative-phrase region corresponding to `phrase`,
        with parameters `parameters`, and add it to `spec_map`.

        Returns the name of the newly-created region."""

    # Find a name for the new region
    new_region_name = _regionNameFromPhrase(phrase)

    # If an appropriate region already exists, don't create another one
    if spec_map.indexOfRegionWithName(new_region_name) >= 0:
        return new_region_name

    # Create the new region
    region_A = spec_map.getRegionByName(parameters["rA"])
    if parameters["op"] == "near":
        new_region = _createLPRegionNear(region_A,
                                         DEFAULT_NEAR_DISTANCE,
                                         mode="overEstimate",
                                         name=new_region_name)
    elif parameters["op"] == "within":
        distance = int(parameters["dist"])
        new_region = _createLPRegionNear(region_A,
                                         distance,
                                         mode="overEstimate",
                                         name=new_region_name)
    elif parameters["op"] == "between":
        # Do an extra check to look for mirrored between statement
        region_B = spec_map.getRegionByName(parameters["rB"])
        mirrored_region_name = _regionNameFromPhrase("between {} and {}".format(region_B.name, region_A.name))
        if spec_map.indexOfRegionWithName(mirrored_region_name) > 0:
            # We don't need to create a new region
            return mirrored_region_name

        new_region = _createLPRegionBetween(region_A, region_B, name=new_region_name)

    # Add the new region to the map
    spec_map.regions.append(new_region)

    return new_region_name

def processLocativePhrases(spec_text, spec_map):
    """ Detect any non-projective prepositional phrases (e.g. "between r1
        and r2") in the specification, create a new region in the map that
        corresponds to this location, and substitute the phrase with a
        reference to the name of the new region (e.g. "_between_r1_and_r2"). """

    # Define regexes
    regexp_near = re.compile(r'(?P<op>near) (?P<rA>\w+)')
    regexp_within = re.compile(r'(?P<op>within) (?P<dist>\d+) (from|of) (?P<rA>\w+)')
    regexp_between = re.compile(r'(?P<op>between) (?P<rA>\w+) and (?P<rB>\w+)')

    # Create a callback function for the regular expression substitutions
    def _createNewLPRegionFromMatchObject(m):
        """ Wrapper for _createNewLPRegion() that takes a re.MatchObject """
        return _createNewLPRegion(spec_map, m.group(), m.groupdict())

    # Process each type of phrase
    for regexp in (regexp_near, regexp_within, regexp_between):
        spec_text = regexp.sub(_createNewLPRegionFromMatchObject, spec_text)

    return spec_text, spec_map

#####################################
### Region manipulation functions ###
#####################################

# TODO: Rewrite using numpy

def _createLPRegionNear(region, distance, mode='underEstimate', name='newRegion'):
    """
    Given a region object and a distance value, return a new region object which covers
    the area that is within the 'distance' away from the given region.
    """

    if distance < 0:
        print "The distance cannot be negative."
        return

    center = region.getCenter()
    new_region_points = []

    if mode == 'overEstimate':
        for pt in region.getPoints():
            twoFaces = [face for face in region.getFaces() if pt in face] # faces that connected by pt

            face1_pt1_new, face1_pt2_new = _findPointsNear(twoFaces[0], center, distance)
            face2_pt1_new, face2_pt2_new = _findPointsNear(twoFaces[1], center, distance)

            if math.sqrt((face1_pt1_new.x-pt.x)**2+(face1_pt1_new.y-pt.y)**2) > \
               math.sqrt((face1_pt2_new.x-pt.x)**2+(face1_pt2_new.y-pt.y)**2):
                pt1 = face1_pt2_new
            else:
                pt1 = face1_pt1_new

            if math.sqrt((face2_pt1_new.x-pt.x)**2+(face2_pt1_new.y-pt.y)**2) > \
               math.sqrt((face2_pt2_new.x-pt.x)**2+(face2_pt2_new.y-pt.y)**2):
                pt2 = face2_pt2_new
            else:
                pt2 = face2_pt1_new

            pt1_new, pt2_new = _findPointsNear((pt1, pt2), center, distance - \
                                 math.sqrt(distance**2-((pt1.x-pt2.x)**2+(pt1.y-pt2.y)**2)/4))

            newTwoFaces = [(face1_pt1_new, face1_pt2_new),
                           (face2_pt1_new, face2_pt2_new)]

            interPoint = _faceAndFaceIntersection(newTwoFaces[0], tuple(sorted((pt1_new, pt2_new))))
            new_region_points.append(interPoint)
            interPoint = _faceAndFaceIntersection(newTwoFaces[1], tuple(sorted((pt1_new, pt2_new))))
            new_region_points.append(interPoint)

    # Force the points to be in the right order
    new_region_poly = Polygon.Utils.convexHull(Polygon.Polygon(new_region_points))

    return regions.Region.fromPolygon(name, new_region_poly)

def _findPointsNear(face, center, distance):
    # find slope of the face line
    pt1, pt2 = face
    x1, y1 = pt1
    x2, y2 = pt2

    if x1 == x2: # vertical line
        if center[0] > x1:
            x1_new = x1-distance
            x2_new = x2-distance
        else:
            x1_new = x1+distance
            x2_new = x2+distance
        y1_new = y1
        y2_new = y2
    elif y1 == y2: # horizontal line
        if center[1] > y1:
            y1_new = y1-distance
            y2_new = y2-distance
        else:
            y1_new = y1+distance
            y2_new = y2+distance
        x1_new = x1
        x2_new = x2
    else:
        faceSlope = (y1-y2)/(x1-x2*1.0)
        # find slope that is orthogonal to the face
        orthSlope = (-1.0)/faceSlope

        # figure out which direction the boundary should be shifted to
        offsetX = distance*math.sqrt(1/(1+orthSlope**2))
        offsetY = distance*math.sqrt(1/(1+1/orthSlope**2))
        if orthSlope > 0:
            direction1 = math.sqrt((x1+offsetX-center[0])**2+(y1+offsetY-center[1])**2)
            direction2 = math.sqrt((x1-offsetX-center[0])**2+(y1-offsetY-center[1])**2)
            if direction1 > direction2:
                x1_new = x1+offsetX
                y1_new = y1+offsetY
                x2_new = x2+offsetX
                y2_new = y2+offsetY
            else:
                x1_new = x1-offsetX
                y1_new = y1-offsetY
                x2_new = x2-offsetX
                y2_new = y2-offsetY
        else:
            direction1 = math.sqrt((x1+offsetX-center[0])**2+(y1-offsetY-center[1])**2)
            direction2 = math.sqrt((x1-offsetX-center[0])**2+(y1+offsetY-center[1])**2)
            if direction1 > direction2:
                x1_new = x1+offsetX
                y1_new = y1-offsetY
                x2_new = x2+offsetX
                y2_new = y2-offsetY
            else:
                x1_new = x1-offsetX
                y1_new = y1+offsetY
                x2_new = x2-offsetX
                y2_new = y2+offsetY

    return regions.Point(int(x1_new), int(y1_new)), \
           regions.Point(int(x2_new), int(y2_new))

def _faceAndFaceIntersection(face1, face2):
    # http://www.topcoder.com/tc?module=Static&d1=tutorials&d2=geometry2
    a = [(face[1][1] - face[0][1]) for face in [face1, face2]]
    b = [(face[0][0] - face[1][0]) for face in [face1, face2]]
    c = [a[0]*face1[0][0]+b[0]*face1[0][1],
         a[1]*face2[0][0]+b[1]*face2[0][1]]

    det = a[0]*b[1] - a[1]*b[0]

    if(det == 0):
        print "Lines are parallel"
    else:
        x = float(b[1]*c[0] - b[0]*c[1])/det
        y = float(a[0]*c[1] - a[1]*c[0])/det

    return regions.Point(x, y)

def _createLPRegionBetween(regionA, regionB, name='newRegion'):
    """
    Find the region between two given regions (doesn't include the given regions)
    """

    polyA = regionA.getAsPolygon()
    polyB = regionB.getAsPolygon()

    betw_AB = Polygon.Utils.convexHull(polyA + polyB) - polyA - polyB

    return regions.Region.fromPolygon(name, betw_AB)
