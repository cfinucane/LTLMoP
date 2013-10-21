# This is a specification definition file for the LTLMoP toolkit.
# Format details are described at the beginning of each section below.


======== SETTINGS ========

Actions: # List of action propositions and their state (enabled = 1, disabled = 0)
NotifyReachedR1, 1

CompileOptions:
convexify: True
parser: structured
fastslow: False
decompose: True
use_region_bit_encoding: True

CurrentConfigName:
SimulatedRobot

Customs: # List of custom propositions

RegionFile: # Relative path of region description file
SimpleExample.regions

Sensors: # List of sensor propositions and their state (enabled = 1, disabled = 0)
Go, 1


======== SPECIFICATION ========

RegionMapping: # Mapping between region names and their decomposed counterparts
r4 = p1
others = 
r1 = p4
r2 = p3
r3 = p2

Spec: # Specification in structured English
visit r1 if and only if you are sensing Go
visit r2 if and only if you are sensing Go
visit r3 if and only if you are sensing Go
visit r4 if and only if you are sensing Go

do NotifyReachedR1 if and only if you are in r1

