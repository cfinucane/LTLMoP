#!/usr/bin/env python
"""
==========================================================================
gotoActuator.py - Actuator for going to an arbitrary point within a region
==========================================================================
"""

import time, math, sys
import threading
from numpy import *
from numpy.linalg import norm
from lib.handlers.motionControl.is_inside import *

#MAX_SPEED_TRANS = 0.2
MAX_SPEED_TRANS = 50
MAX_SPEED_ROT = 0.6
THRESHOLD_TRANS = 0.1 # 10 cm
THRESHOLD_ROT = math.pi/18 # 10 degrees

class actuatorHandler:
    def __init__(self, proj, shared_data):
        self.proj = proj
        self.targetPose = None
        self.targetPose = append(self.proj.coordmap_map2lab([793,272]), 0)
        self.moveState = "idle"
        moveThread = threading.Thread(target = self.doMove)
        moveThread.start()

    def doMove(self):
        while 1:
            if self.moveState == "translate":
                # Check if we've arrived at our destination
                pose = self.proj.pose_handler.getPose()
                diff = (self.targetPose[0]-pose[0], self.targetPose[1]-pose[1])
                arrived = norm(diff) < THRESHOLD_TRANS

                if arrived:
                    self.proj.drive_handler.setVelocity(0, 0)
                    self.moveState = "rotate" 
                else:
                    # Set the velocity vector to the difference between pose and target
                    v = diff

                    # Clip maximum speed
                    if norm(v) > MAX_SPEED_TRANS:
                        v = MAX_SPEED_TRANS * array(v)/norm(v)

                    self.proj.drive_handler.setVelocity(v[0], v[1])

                    time.sleep(0.5)
            elif self.moveState == "rotate":
                # Check if we've finished rotating
                pose = self.proj.pose_handler.getPose()
                diff = self.targetPose[2] - pose[2]
                arrived = abs(diff) < THRESHOLD_ROT

                if arrived:
                    self.proj.loco_handler.sendCommand([0,0])
                    self.moveState = "idle" 
                    self.proj.sensor_handler.sensorValue["gotoPOIDone"] = True
                else:
                    # Set our rotational velocity proportional to the offset from the target angle
                    w = diff

                    # Clip maximum speed
                    if abs(w) > MAX_SPEED_ROT:
                        w = sign(w) * MAX_SPEED_ROT

                    self.proj.loco_handler.sendCommand([0,w])

                    time.sleep(0.05)
            else:
                time.sleep(0.1)

    def _regionFromPose(self, pose):
        for i, r in enumerate(self.proj.rfi.regions):
            pointArray = [self.proj.coordmap_map2lab(x) for x in r.getPoints()]
            vertices = mat(pointArray).T 

            if is_inside([pose[0], pose[1]], vertices):
                return i

        return None

    def setActuator(self, name, val):
        print "(ACT) Actuator %s is now %s!" % tuple(map(str, (name, val)))

        if name == "gotoPOI":
            self.proj.sensor_handler.sensorValue["gotoPOIDone"] = False
            if int(val) == 1:
                if self.targetPose is None:
                    print "(ACT) WARNING: No targetPose set in actuator handler before actuator call."
                    return

                # Make sure that the target point is inside our current region,
                # lest we run the risk of violating a safety requirement
                pose = self.proj.pose_handler.getPose()

                current_region = self._regionFromPose(pose) 
                target_region = self._regionFromPose(self.targetPose)

                if current_region != target_region:
                    if target_region is None:
                        target_region_name = "the middle of nowhere"
                    else:
                        target_region_name = self.proj.rfi.regions[target_region].name

                    print "(ACT) WARNING: Cannot safely visit POI outside of current region (it appears to be in %s).  Ignoring!" % target_region_name
                    return
            
                self.moveState = "translate"
            else:
                self.moveState = "idle"
        else:
            time.sleep(0.1)  # Fake some time lag for the actuator to enable



