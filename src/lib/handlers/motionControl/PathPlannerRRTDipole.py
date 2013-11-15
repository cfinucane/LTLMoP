"""
TODO:
    # Implement shortcut smoothing
    # Introduce non-circular robot
    # Introduce closest node measure
    ----------------------------
    # Improved closest node measure
    # Fix plotting issue (look at close enough)
    # Implement CONNECT heuristic
    # Sped up the control calculations
    # straight line
    # Fix obstacle collision issues
    # Change getControls method to remove arrays
    # Try to expand to N closest not just closest
    # Plot robot at start position
    # Improved path smoothing to account for closeEnoughDipole()
    -------------------------------
    # Implement regular RRT with connect heuristic in 2D
    # Create Dijkstra for the 2D path
    # Create a method that inputs dipoles into the 2D path
    # Craete a method that tries to smooth corners in the 2d path
    # Implement A* for smoothing
    # Allow 2D to dipole have multiple shifts
    --------------------------------
    Place robot within the full map
    Fix discrepancies with actual path traveled 
        calculated from closeEnoughDipole()
    Implement multiple goals
    Add new maps
    Create handler
    Make use of rrtPath calculations
    Improve smoothing speed
    Decide if backwards or not (work around)
    Handler option for backing up
    Consider squaring differences in closeness measure
    Change diff angle to be relative to angle1
    drawPathDipoleControl should be something like path to 2d 
    fix issue with DEBUGGER mode
"""

from __future__ import division

import cProfile
from random import random
from time import sleep, clock

import Polygon
from numpy.linalg import norm

import Polygon.Shapes as pShapes
import matplotlib.pyplot as plt
import numpy as np
from Queue import PriorityQueue


def diffAngles(angle1, angle2):
    """ Returns difference between -pi and pi. Relative to angle2.
    """
    return (angle1 - angle2 + np.pi)%(2*np.pi) - np.pi


class MapRRT:
    
    def __init__(self, boundary, allObstacles):
        ''' An object with the outline of the map, a list of obstacles,
        and the poses that the robot starts and ends on.
        
        :param boundary: shape
        :param allObstacles: list of polygons
        :param startPose: numpy 3D array
        :param endPose: numpy 3D array
        '''
        self.boundary = boundary
        self.allObstacles = allObstacles
        
        self.cFree = Polygon.Polygon(boundary)
        for obst in allObstacles:
            self.cFree -= obst
            
            
class RobotRRT:
    
    def __init__(self, pose, outline, radius=None):
        """ An object that represents the robot location and outline.
        
        :param pose: numpy 3D array
        :param outline: Polygon describing the space occupied by the robot at 
                        the current pose 
        :param radius: radius of a circle encompasing the robot and centered at
                        pose. Only used for 2D RRT
        """
        self.pose = pose
        self.shape = outline
        self.radius = radius
        
        
    def moveRobotTo(self, newPose):
        """ Updates the robot pose and outline to match the new pose
        
        :param newPose: numpy 3D array
        """
        dirV = newPose[:2] - self.pose[:2]
        angleDiff = diffAngles(newPose[2], self.pose[2])
        self.shape.shift(dirV[0], dirV[1])
        self.pose = np.array(newPose)
        self.shape.rotate(angleDiff, newPose[0], newPose[1])
        
        
    def copy(self):
        return RobotRRT(np.array(self.pose), Polygon.Polygon(self.shape))


class PlotterRRT:
    
    def __init__(self, figure, axes):
        """ An object to facilitate plotting common structures on the given 
        matplotlib figure and axes.
        """
        self.fig = figure
        self.ax = axes


    def drawPolygon(self, poly, color='k', width=1):
        """ Draw the outline of a polygon object
        """
        vertices = np.array(poly[0] + [poly[0][0]])
        self.ax.plot(vertices[:,0], vertices[:,1], 
                 color=color, linewidth=width)
        plt.draw()
    
    
    def drawTree(self, tree, color='k', width=1):
        """ For drawing trees created in RRT
        """
        for node in tree:
            parent = node.parent
            if parent != None:
                self.drawEdge(node, parent, color, width)
    
                
    def drawEdge(self, node1, node2, color='k', width=1):
        """ Draw the edge that connects two nodes from the RRT
        """
        self.ax.plot([node1.x, node2.x], [node1.y, node2.y], 
                 'o-', color=color, linewidth=width)
        plt.draw()
    
    
    def drawStartAndGoalPoints(self, startPoint, goalPoint):
        """ Places a green marker at the start point and a red one at the end
        point
        
        :param startPoint: numpy 2D array
        :param gialPoint: numpy 2D array
        """
        self.ax.plot(startPoint[0], startPoint[1], 'go')
        self.ax.plot(goalPoint[0], goalPoint[1], 'ro')
        plt.draw()
        
        
    def drawStartAndGoalRobotShape(self, startPose, goalPose, robot):
        """ Plot the robots outline at the start and end pose
        
        :param startPose: numpy 3D array
        :param endPose: numpy 3D array
        :param robot: a RobotRRT object
        """
        robotTemp = robot.copy()
        
        robotTemp.moveRobotTo(startPose)   
        self.drawPolygon(robotTemp.shape, color='g', width=2)
        
        robotTemp.moveRobotTo(goalPose)   
        self.drawPolygon(robotTemp.shape, color='r', width=2)

    
    def drawMap(self, fullMap):
        """ Draw the map with boundary and obstacles
        
        :param fullMap: a MapRRT object
        """
        self.drawPolygon(fullMap.boundary, color='k', width=3)
         
        # Obstacles
        for obst in fullMap.allObstacles:
            self.drawPolygon(obst, color='b', width=3)
        
        plt.draw()
    
    
    def drawNodePath2D(self, path, color='k', width=1):
        """ Draw the path assuming that nodes are connected by straight lines
        
        :param path: a list of nodes
        """
        points = [node.XY for node in path]
        self.drawDipolePath2D(points, color=color, width=width)
    
    
    def drawDipolePath2D(self, path, color='k', width=1):
        """ Draw the path assuming that dipoles are connected by straight lines
        
        :param path: a list of dipoles
        """
        points = np.array(path)
        self.ax.plot(points[:,0], points[:,1], color=color, linewidth=width)
        plt.draw()
        
        
    def showMapAndTrees(self, fullMap, allTrees):
        """ Draw and plot the fullMap and trees. Mainly used to help debug
        
        :param fullMap: a MapRRT object
        :param allTrees: a list of trees from the RRT
        """
        self.drawMap(fullMap)
        
        for tree in allTrees:
            self.drawTree(tree, color='k', width=1)
            
        plt.show()
    
    
class DipolarController:
    
    def __init__(self, k1=.5, k2=1.5, lambdaValue=3):
        """ A class that uses the dipolar controller from the paper: Model 
        Predictive Control for the Navigation of a Nonholonomic Vehicle with 
        Field-of-View Constraints
        
        :param k1: Linear velocity
        :param k2: Angular velocity gain
        :param lambdaValue: Dipole's field shape
        Parameters are further explained in the literature
        """
        self.k1 = k1
        self.k2 = k2
        self.lam = lambdaValue
    

    def getFieldAt(self, poseCurr, poseDes):
        """ Calculate the dipolar field at poseCurr that is generated from 
        the dipole at poseDes
        
        :param poseCurr: numpy 3D array. The current pose
        :param poseDes: numpy 3D array. The desired pose
        :return: fieldXVector, fieldYVector
        """
        rX = poseCurr[0] - poseDes[0]
        rY = poseCurr[1] - poseDes[1]
        pX = np.cos(poseDes[2])
        pY = np.sin(poseDes[2])
        
        a1 = self.lam*(pX*rX + pY*rY)
        a2 = rX*rX + rY*rY
        
        return (a1*rX - a2*pX, a1*rY - a2*pY)
        
    
    def getControlls(self, poseCurr, poseDes, posePrev, delT):                         # No Backup
        """ Get the dipolar controls that will take the robot from poseCurr to
        poseDes.
        
        :param poseCurr: numpy 3D array. The current pose
        :param poseDes: numpy 3D array. The desired pose
        :param poseDes: numpy 3D array. The previous pose
        :param delT: The time elapsed since posePrev
        :return: linearVelocity, angularVelocity
        """
        rX = poseCurr[0] - poseDes[0]
        rY = poseCurr[1] - poseDes[1]    
        ang = poseCurr[2]
        u = -self.k1 * np.sign(rX*np.cos(ang) + rY*np.sin(ang)) + \
            np.tanh(rX*rX + rY*rY)
           
        dipoleField = self.getFieldAt(poseCurr, poseDes)
        dipoleFieldPrev = self.getFieldAt(posePrev, poseDes)
        phi = np.arctan2(dipoleField[1], dipoleField[0])
        phiPrev = np.arctan2(dipoleFieldPrev[1], dipoleFieldPrev[0])
           
        w = -self.k2*diffAngles(ang, phi) + diffAngles(phi, phiPrev)/delT
    
        return u, w  
    
    
    def integrateForwards(self, posePrev, u, w, delT):

        """ Calculate the robots new position based on the previous position,
        controls, and time elapsed.
        
        :param poseDes: numpy 3D array. The previous pose
        :param u: linear velocity
        :param w: angular velocity
        :param delT: time elapsed
        :return: poseN: the new pose of the robot
        """
        poseN = np.array(posePrev)
        
        delAng = w*delT
        dist = u*delT
        
        if np.abs(delAng) < .0000001:
            poseN[0] = poseN[0] + dist*np.cos(posePrev[2])   
            poseN[1] = poseN[1] + dist*np.sin(posePrev[2])
        else:
            # Radius of circle and length of displacement vector
            rad = dist/delAng;
            vecL = np.sqrt( (rad*np.sin(delAng))**2 + (rad - rad*np.cos(delAng))**2) * np.sign(dist)
            
            poseN[0] = poseN[0] + vecL*np.cos(delAng/2 + poseN[2])
            poseN[1] = poseN[1] + vecL*np.sin(delAng/2 + poseN[2])
            poseN[2] = (poseN[2] + delAng)%(2*np.pi)
            
        return poseN
  
  
class Node:
    
    def __init__(self, x=0, y=0, theta=0, XY=None, pose=None, parent=None):
        """ An object to represent poses and connections amongst them. If 
        instantiated, the value of later parameters will override the 
        previous (ex. pose can override all) 

        :param x: The x coordinate
        :param y: The y coordinate
        :param theta: The orientation in radians
        :param XY: List with x and y 
        :param pose: List with x, y, and theta
        :param parent: The node from which it stems
        """
        # TODO: LEFT OFF HERE   
        self.x = x
        self.y = y
        self.theta = theta
        
        if XY != None:
            self.x = XY[0]
            self.y = XY[1]
        if pose != None:
            self.x = pose[0]
            self.y = pose[1]
            self.theta = pose[2]

        self.parent = parent
        self.XY = np.array([self.x, self.y])
        self.pose = np.array([self.x, self.y, self.theta])
  

class PlannerRRT:
    
    def __init__(self, fullMap, robot, plotter=None):
        """ An RRT path planner that takes into account orientation 
        requirements.
        
        Note: Dipoles and poses are always numpy arrays with x, y, and theta.

        :param fullMap: A MapRRT object
        :param robot: A robotRRT object
        :param plotter: A PlotterRRT object. If plotting is desired
        """
                
        # TODO: CHECK TO SEE WHICH SHOULD BE KEPT HERE
        # DEBUGING TOOLS
        self.DEBUGER = False        # Debugger is on
        self.PLOT_TREE = False      # Plot RRT tree as it is grown
        self.PLOT_TREE_FAIL = False # Plot RRT tree in case of timeout
        
        self.fullMap = fullMap
        self.robot = robot
        self.dipControl = DipolarController(k1=.5, k2=1.5, lambdaValue=3)
        self.plotter = plotter
        
        
    def get2DPathLength(self, path):
        """ Get the length of a path along the set of 2D waypoints.
        
        :param path: A list of points or poses as numpy arrays.
        """
        distances = [norm(path[i][:2] - path[i+1][:2]) 
                     for i in range(len(path)-1)]
        return sum(distances)

        
    def sampleDipole(self):
        """ Returns a random dipole within the map's C-Free
        """
        randPoint = self.fullMap.cFree.sample(random)
        randAng = 2 * np.pi * random()
        return np.array([randPoint[0], randPoint[1], randAng])
    
    
    def getDipoleDistanceHeur(self, dipoleStart, dipoleEnd):
        """ Calculate a heuristic distance from dipoleStart to dipoleEnd. The
        distance is a linear combination of the euclidean distance between
        dipoles, orientation difference between dipoles, orientation difference
        between dipoleStart and the field at dipoleStart from dipoleEnd, and the
        how far infront or behind dipoleStart is from the line orthogonal to 
        to and passing through dipoleEnd. 
        """
        # Weights
        W_EUCL = 5              # Euclidian distance
        W_ORIENT = 1            # Difference between orientations
        W_FIELD = 1             # Difference between orientation and field
        W_FRONT_BEHIND = 0      # In front or behind
        
        dirV = dipoleStart[:2] - dipoleEnd[:2]
        euclD = norm(dirV)
        
        angleDiff = np.abs(diffAngles(dipoleEnd[2], dipoleStart[2]))
        
        dipoleField = self.dipControl.getFieldAt(dipoleStart, dipoleEnd)
        fieldAngle = np.arctan2(dipoleField[1], dipoleField[0])
        fieldDiff = np.abs(diffAngles(fieldAngle, dipoleStart[2]))
        
        dipoleT = np.array(dipoleStart[:2])/norm(dipoleStart[:2])
        relativePos = np.dot(dipoleT, dirV)
        
        totalDist = W_EUCL*euclD + W_ORIENT*angleDiff + \
                    W_FIELD*fieldDiff + W_FRONT_BEHIND*relativePos
        
        return totalDist
    
    
    def getNClosestIndicesDipole(self, dipole, tree, N=1):
        """ Uses the distance heuristic to return a list with the indices 
        of the N closest nodes within the tree to dipole.    
        """
        distances = [self.getDipoleDistanceHeur(dipole, nodeX.pose) 
                     for nodeX in tree]
        closestIndices = sorted(range(len(distances)), key=lambda i: distances[i])
        return closestIndices[:N]
    
    
    def getDipoleToDipolePath(self, dipoleStart, dipoleEnd, timeout = .5):
        """ Returns (connected, path) where connected is True if a collision
        free path was found, and path is the list of poses. 
        
        :param timeout: The maximum time to spend in this function
        """
        DT = .1         # The time interval for controls and forward integration
        
        poseCurr = np.array(dipoleStart)
        posePrev = poseCurr
        path = [poseCurr]
        
        timeStart = clock()
        while (clock() - timeStart) < timeout:
            u, w = self.dipControl.getControlls(poseCurr, dipoleEnd, posePrev, DT)
            posePrev = poseCurr
            poseCurr = self.dipControl.integrateForwards(posePrev, u, w, DT)
            path.append(poseCurr)
            
            # Check for collision
            self.robot.moveRobotTo(poseCurr)
            if not self.fullMap.cFree.covers(self.robot.shape):
                return (False, path)
            
            # If reached goal return the final state
            if self.closeEnoughDipole(poseCurr, dipoleEnd):
                return (True, path)
            
        # Timed out. This warning can be removed if bothersome.
        print "DEBUG: Warning getDipoleToDipolePath timed out."
        
        return (False, path)
    
    
    def closeEnoughDipole(self, currPose, endPose):
        """ Returns true if the euclidean and angular distances between currPose
        and endPose is below the set threshold.
        """
        DIST_THRESH = .25
        ANG_THRESH = .5
        
        dist = norm(currPose[:2] - endPose[:2])
        angDiff = np.abs(diffAngles(currPose[2], endPose[2]))
        
        if dist < DIST_THRESH and angDiff < ANG_THRESH:
            return True
        else:
            return False
    
    
    # TODO: Method has not been used in a long time. Must be updated.
    def extendTreeDipole(self, tree, dipole):
        """ Tries to extend the tree in the direction of the sampled dipole by
        one leaf.
        """
        MAX_DIST = 1
        
        # Choose the dipole to extend from
        closestNodeIndex = self.getNClosestIndicesDipole(dipole, tree, N=1)[0]
        closestNode = tree[closestNodeIndex]
        
        dirV = dipole[:2] - closestNode.XY
        dist = norm(dirV)
        if dist > MAX_DIST:
            dipole = np.array(dipole)
            dipole[:2] = closestNode.XY + (dirV/dist)*MAX_DIST
        
        pathFound, _ = self.getDipoleToDipolePath(closestNode.pose, dipole)
        
        if pathFound:
            tree.append(Node(pose=dipole, parent=closestNode))
            
            return True
        else:
            return False
    
    
    def extendTreeDipoleConnect(self, tree, dipole):
        """ Finds the closest node in three to dipole and tries to extend from 
        that node towards dipole in intervals of MAX_DIST for as many 
        iterations as possible. Will consider the top NUM_CONSIDERED nodes to see
        if any will make progress and extend from one of them. New nodes are added
        to tree.
        """
        MAX_DIST = 1
        NUM_CONSIDERED = 5
        
        # Get the index of the closest nodes to dipole
        closestNodeIndex = self.getNClosestIndicesDipole(dipole, tree, 
                                                         N=NUM_CONSIDERED)
        
        # If no progress is made then try the next closest
        startTreeLen = len(tree)
        for i in closestNodeIndex:
            closestNode = tree[i]
        
            dirV = dipole[:2] - closestNode.XY
            dirAng = np.arctan2(dirV[1], dirV[0])
            dist = norm(dirV)
            numIntervals = int(dist/MAX_DIST)
            dirV = dirV/dist*MAX_DIST               # Normalize to step size
            
            # Try to connect to dipole in intervals
            collided = False
            parentT = closestNode
            dipoleCurr = np.array(parentT.pose)
            dipoleNext = np.array(dipoleCurr)
            dipoleNext[2] = dirAng      
            for _ in range(numIntervals):
                dipoleNext[:2] += dirV[:2]  
                
                connected, pathT = self.getDipoleToDipolePath(dipoleCurr, dipoleNext)
                if not connected:
                    collided = True
                    break
                
                currNode = Node(pose=pathT[-1], parent=parentT)
                
                tree.append(currNode)
                parentT = currNode
                dipoleCurr = currNode.pose
            
            # Attempt to connect to the last node
            if not collided:
                connected, pathT = self.getDipoleToDipolePath(dipoleCurr, dipole)
                if connected:
                    currNode = Node(pose=pathT[-1], parent=parentT)
                    tree.append(currNode)
                    
            # If the tree has grown then progress was made. Dont go to next neighbors
            if len(tree) > startTreeLen:
                return
    
    
    def getRRTDipoleControlPath(self, startPose, endPose):
        """ Returns a path from startPose to endPose in the form of a list of
        Nodes. Uses a dipole controller to connect nodes in the RRT.
        """
        GOAL_BIAS = .2          # Percentage of attempt to connect to endPose
        MAX_ITTER = 700         # Maximum number of tree itterations
        
        startPose = np.array(startPose).astype(float)
        endPose = np.array(endPose).astype(float)
    
        tree = [Node(pose=startPose, parent=None)]
        
        oldTreeLength = 1
        
        for currIter in range(MAX_ITTER):
            
            # Select dipole to drive towards
            randNumber = random()
            if randNumber <= GOAL_BIAS:
                randDipole = endPose
            else:
                randDipole = self.sampleDipole()
            
            # Try to extend the tree
    #         extended = extendTreeDipole(tree, randDipole, fullMap)
            self.extendTreeDipoleConnect(tree, randDipole)
            
            numNewNodes = len(tree) - oldTreeLength
            oldTreeLength = len(tree)
            
            if self.PLOT_TREE and self.plotter != None:
                print "Tree: iteration: " + str(currIter)
                if numNewNodes > 0:
                    if self.DEBUGER:
                        self.plotter.drawMap(self.fullMap)
                        self.plotter.drawTree(tree, color='k', width=1)
                        plt.show()
                    else:
                        self.plotter.drawTree(tree[-numNewNodes:], color='k', 
                                              width=2)
                        self.plotter.drawStartAndGoalPoints(startPose, endPose)
                    
            # Reached end
            if self.closeEnoughDipole(tree[-1].pose, endPose):
                
                print "Tree total iterations: " + str(currIter)
                
                path = []
                currNode = tree[-1]
                while currNode != None:
                    path.append(currNode)
                    currNode = currNode.parent
                path.reverse()
                return path
        
        if self.PLOT_TREE_FAIL:
            plt.ioff()
            self.plotter.drawMap(self.fullMap)
            self.plotter.drawTree(tree, color='k', width=1)
            plt.show()
            
        return None
    
    
    def getShortcutPathDipole(self, path):
        """ Use the shortcut heuristic to return a shorter path in the form of
        a list of Nodes. Implements Dijkstras to find new connections in the 
        given path
        
        :param path: A list of Nodes
        """
        numEdges = 0                # Keep track of number of edges calculated
        
        numNodesTotal = len(path)
        
        nodeIQueue = PriorityQueue()        # Node to expand (distance, nodeIndex)
        visited = [False]*numNodesTotal
        distances = {}                      # (nodeIndex:distanceFromStart)
        
        # Initialize 
        nodeIQueue.put((0,0))
        distances[0] = 0
        path[0].parent = None
        
        while not nodeIQueue.empty():
            currNodeI = nodeIQueue.get()
            currNodeI = currNodeI[1]
            if visited[currNodeI]:
                continue
            currDist = distances[currNodeI]
            currNode = path[currNodeI]
            visited[currNodeI] = True
            
            # Check if reached Goal
            if currNodeI == numNodesTotal-1:
                
                print "ShortcutDipole numEdges: " + str(numEdges)
                
                shortPath = []
                while currNode != None:
                    shortPath.append(currNode)
                    currNode = currNode.parent
                shortPath.reverse()
                return shortPath
            
            # Go through all the non visited nodes
            for neighborI in range(numNodesTotal):
                if visited[neighborI]:
                    continue
                neighNode = path[neighborI]
                
                numEdges += 1
                
                # Calculate alternative distance 
                pathFound, pathDi = self.getDipoleToDipolePath(currNode.pose, 
                                                               neighNode.pose)
                if not pathFound:
                    continue
                pathDi += [neighNode.pose]
                distAlternative = currDist + self.get2DPathLength(pathDi)
                
                # If shorter than recorded update
                if distAlternative < distances.get(neighborI, float('inf')):
                    nodeIQueue.put((distAlternative, neighborI))
                    distances[neighborI] = distAlternative
                    neighNode.parent = currNode
                   
        # No path was found 
        return None 


    def getDipolePathTraveled(self, path):
        """ Takes a path as a list of nodes and runs the dipolar controler to
        return a close approximation of the path traveled as a list of dipoles
        """
        pathTraveled = [path[0].pose]
        for i in range(len(path)-1):
            _, pathDi = self.getDipoleToDipolePath(path[i].pose, path[i+1].pose)
            pathDi.append(path[i+1].pose)
            pathTraveled += pathDi
        return pathTraveled        
        

class TestRRT:    
    
    def __init__(self):
        self.DEBUGER = False            # Debugger is on
        self.PLOT_TREE = True           # Live tree
        self.PLOT_RRT_PATH = True
        self.PLOT_SHORT_PATH = False
        self.PLOT_SHORT_PATH = True
        self.PLOT_TREE_FAIL = True      # Plot final tree if it times out
    
    
    def getSampleMapRRT(self, mapIndex):
        """ Return a (startPose, endPose, map) .Map index defines which of the 
        maps will be returned.
        
        0: Map with random object positions. No path guaranteed.
        1: Simple box map
        2: Box map with box obstacle
        3: Map with multiple obstacles.
        """
        startPose = None
        endPose = None
        boundary = None
        allObstacles = []
    
        # MAP Random
        if mapIndex == 0:
            startPose = np.array([1, 1, 0])
            endPose = np.array([19, 19, np.pi])
             
            boundary = pShapes.Rectangle(20, 20) 
            
            obstacle1 = pShapes.Rectangle(5, 5)
            obstacle1.shift(random()*20, random()*20)
            obstacle2 = pShapes.Rectangle(5, 8)
            obstacle2.shift(random()*20, random()*20)
            obstacle3 = pShapes.Rectangle(9, 3)
            obstacle3.shift(random()*20, random()*20)
            allObstacles = [obstacle1, obstacle2, obstacle3]
    
        # MAP 1
        elif mapIndex == 1:
            startPose = np.array([1, 1, 0])
            endPose = np.array([8, 8, np.pi])
              
            boundary = pShapes.Rectangle(9, 9) 
            
            allObstacles = []
            
        # MAP 2
        elif mapIndex == 2:
            startPose = np.array([1, 1, 0])
            endPose = np.array([8, 8, np.pi])
              
            boundary = pShapes.Rectangle(9, 9) 
            
            obstacle1 = pShapes.Rectangle(5, 5)
            obstacle1.shift(2, 2)
            allObstacles = [obstacle1]
        
        # MAP 3
        elif mapIndex == 3:
            startPose = np.array([1, 1, 0])
            endPose = np.array([19, 19, np.pi])
             
            boundary = pShapes.Rectangle(20, 20) 
            
            obstacle1 = pShapes.Rectangle(5, 5)
            obstacle1.shift(2, 2)
            obstacle2 = pShapes.Rectangle(5, 8)
            obstacle2.shift(12, 6)
            obstacle3 = pShapes.Rectangle(9, 3)
            obstacle3.shift(0, 12)
            allObstacles = [obstacle1, obstacle2, obstacle3]
                
        else:
            return None
                
        testMap = MapRRT(boundary, allObstacles)    
        return startPose, endPose, testMap
    
    
    def runRRTDipoleControlAndShortcut(self):
        """ Run the dipolar RRT/shortcut and plot according to parameters 
        specified in this class' init function.
        """
        if not self.DEBUGER:
            plt.ion()
            
        startPose, endPose, testMap = self.getSampleMapRRT(3)
        
        robotOutline = Polygon.Polygon([(-.25,0), (.25,0), (0,.5)])
        robot = RobotRRT(np.array([0,.2,np.pi/2]), robotOutline)
        
        figure, axes = plt.subplots()
        plotter = PlotterRRT(figure, axes)
        plotter.drawMap(testMap)
        axes.grid()
        
        plotter.drawStartAndGoalRobotShape(startPose, endPose, robot)
        
        planner = PlannerRRT(testMap, robot, plotter)
        planner.DEBUGER = self.DEBUGER
        planner.PLOT_TREE = self.PLOT_TREE
        planner.PLOT_TREE_FAIL = self.PLOT_TREE_FAIL
        
        rrtPath = planner.getRRTDipoleControlPath(startPose, endPose)
        
        if rrtPath == None:
            print "Did not find path in given time."
            return
        
        if self.PLOT_RRT_PATH:
            pathT = planner.getDipolePathTraveled(rrtPath)
            plotter.drawDipolePath2D(pathT, color='g', width=3)
            
        print "Smoothing Path"
        shortPath = planner.getShortcutPathDipole(rrtPath)
        print "Done Smoothing Path"
        
        if self.PLOT_SHORT_PATH:
            pathT = planner.getDipolePathTraveled(shortPath)
            plotter.drawDipolePath2D(pathT, color='r', width=3)
            
        print "Showing Final Results"
        plt.ioff()
        plt.show()


    def runRRTDipoleControlAndShortcutNoPlot(self):     
        """ Use this method to time the implementation and/or profile it
        """       
        startPose, endPose, testMap = self.getSampleMapRRT(3)
        
        robotOutline = Polygon.Polygon([(-.25,0), (.25,0), (0,.5)])
        robot = RobotRRT(np.array([0,.2,np.pi/2]), robotOutline)
        
        planner = PlannerRRT(testMap, robot)
        planner.DEBUGER = False
        planner.PLOT_TREE = False
        planner.PLOT_TREE_FAIL = False
        
        rrtPath = planner.getRRTDipoleControlPath(startPose, endPose)
        
        if rrtPath == None:
            print "Did not find path in given time."
            return
            
        planner.getShortcutPathDipole(rrtPath)
        

if __name__ == "__main__":
    print "Starting"
    timeS = clock()
    
    test = TestRRT()
    test.runRRTDipoleControlAndShortcut()    
#     test.runRRTDipoleControlAndShortcutNoPlot()    
#     cProfile.run("test.runRRTDipoleControlAndShortcutNoPlot()") 
    
    print "Done: " + str(clock()-timeS)



