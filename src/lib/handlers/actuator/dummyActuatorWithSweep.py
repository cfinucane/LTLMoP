#!/usr/bin/env python
"""
=========================================
dummyActuatorWithSweep.py - Dummy Actuator Handler + Sweep
=========================================
"""

import time
import threading
from lib.handlers.motionControl.is_inside import *

class actuatorHandler:
    def __init__(self, proj, shared_data):
        self.proj = proj
        self.moveTarget = None
        moveThread = threading.Thread(target = self.doMove)
        moveThread.start()

    def doMove(self):
        while 1:
            if self.moveTarget is not None:
                arrived = self.proj.motion_handler.gotoRegion(self.moveTarget, self.moveTarget, last=True)
                time.sleep(0.02)
            else:
                time.sleep(0.1)

    def setActuator(self, name, val):
        """
        """

        if val:
            time.sleep(0.1)  # Fake some time lag for the actuator to enable

        print "(ACT) Actuator %s is now %s!" % tuple(map(str, (name, val)))

        if name == "sweep":
            if int(val) == 1:
                pose = self.proj.pose_handler.getPose()

                # Figure out what region we're in
                for i, r in enumerate(self.proj.rfi.regions):
                    pointArray = [self.proj.coordmap_map2lab(x) for x in r.getPoints()]
                    vertices = mat(pointArray).T 

                    if is_inside([pose[0], pose[1]], vertices):
                        #print "I think I'm in " + r.name
                        #print pose
                        thisregion = i
                        break

                self.moveTarget = thisregion
            else:
                self.moveTarget = None



