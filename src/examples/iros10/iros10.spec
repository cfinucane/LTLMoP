# This is a specification definition file for the LTLMoP toolkit.
# Format details are described at the beginning of each section below.
# Note that all values are separated by *tabs*.


======== EXPERIMENT CONFIG 0 ========

Calibration: # Coordinate transformation between map and experiment: XScale, XOffset, YScale, YOffset
0.0145090906457,-7.97493804517,-0.0163607845119,5.97177404282

InitialRegion: # Initial region number
4

InitialTruths: # List of initially true propositions

Lab: # Lab configuration file
playerstage.lab

Name: # Name of the experiment
PlayerStage

RobotFile: # Relative path of robot description file
pioneer_stage.robot


======== EXPERIMENT CONFIG 1 ========

Calibration: # Coordinate transformation between map and experiment: XScale, XOffset, YScale, YOffset
0.00667619043562,0.519140956528,-0.00536700273334,2.25351186904

InitialRegion: # Initial region number
2

InitialTruths: # List of initially true propositions

Lab: # Lab configuration file
playerstage.lab

Name: # Name of the experiment
ASL

RobotFile: # Relative path of robot description file
pioneer_stage.robot


======== SETTINGS ========

Actions: # List of actions and their state (enabled = 1, disabled = 0)
gotoPOI,1
beep,1

Customs: # List of custom propositions

RegionFile: # Relative path of region description file
iros10.regions

Sensors: # List of sensors and their state (enabled = 1, disabled = 0)
gotoPOIDone,1
detectPOI,1

currentExperimentName:
PlayerStage


======== SPECIFICATION ========

RegionMapping:

living=p4
deck=p7
porch=p3
dining=p6
bedroom=p8
others=
kitchen=p5

Spec: # Specification in simple English
# Initial conditions
Env starts with false
Robot starts in porch with false

group Targets is porch, bedroom

do gotoPOI if and only if you are sensing detectPOI
if you were activating gotoPOI or you are activating gotoPOI then stay there

if you are not activating gotoPOI then visit all Targets

do beep if and only if you are sensing gotoPOIDone

