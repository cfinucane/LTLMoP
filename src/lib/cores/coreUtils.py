
import math, re, sys, random, os, subprocess, time
from copy import copy, deepcopy
from logic import to_cnf
from multiprocessing import Pool
import threading
import itertools
import logging
import random

USE_MULTIPROCESSING = False

def runMap(function, inputs):
    """ Wrapper for single- and multi-threaded versions of map, to make
        it easy to disable multiprocessing for debugging purposes
    """

    logging.debug("Starting map ({}-threaded): {}".\
                  format("multi" if USE_MULTIPROCESSING else "single", function.__name__))

    if USE_MULTIPROCESSING:
        pool = Pool()
        outputs = pool.map(function, inputs, chunksize = 1)   
        pool.terminate()
    else:
        outputs = map(function, inputs)   

    logging.debug("Finished map: {}".format(function.__name__))

    return outputs

def conjunctsToCNF(conjuncts, propList):
    #takes a list of LTL formulas and a list of propositions used in them,
    #and converts them into DIMACS CNF format replacing each proposition
    #with its index in the list. 
    #returns:
    #         mapping: a mapping from LTL formulas to CNF clause numbers
    #         cnfMapping: a mapping from LTL formulas to CNFs 
    #         cnfClauses: CNFS corresponding to initial and transition formulas
    #                     (represents one-step unrolling)
    #         transClauses: CNFS corresponding to transition formulas
    #                     (useful for further unrolling later)
    #         goalClauses: CNFS corresponding to goal formulas
    #                     (useful for checking goals at each time step)
    
    propListNext = map(lambda s: 'next_'+s, propList)
    
    props = {propList[x]:x+1 for x in range(0,len(propList))}
    propsNext = {propListNext[x]:len(propList)+x+1 for x in range(0,len(propListNext))}
    mapping = {conjuncts[x]:[] for x in range(0,len(conjuncts))}
    
    cnfClauses = []
    transClauses = []
    goalClauses = []
    n = 0 #counts number of clauses generated for mapping LTL to line numbers
    p = len(props)+len(propsNext)  
    
    
    allCnfs = runMap(lineToCnf, conjuncts)   
    
    #associate original LTL conjuncts with CNF clauses
    cnfMapping = {line:cnf.split("&") for cnf, line in zip(allCnfs,conjuncts) if cnf}  
    for cnf, lineOld in zip(allCnfs,conjuncts):     
      if cnf: 
        allClauses = cnf.split("&");
        for clause in allClauses:    
            clause = re.sub('[()]', '', clause)   
            clause = re.sub('[|]', '', clause)           
            clause = re.sub('~', '-', clause)    
            #replace prop names with var numbers
            for k in propsNext.keys():
                clause = re.sub("\\b"+k+"\\b",str(propsNext[k]), clause)
            for k in props.keys():
                clause = re.sub("\\b"+k+"\\b",str(props[k]), clause)   
            #add trailing 0   
            if "<>" in lineOld:
                goalClauses.append(clause.strip()+" 0\n")
            elif "[]" in lineOld:
                transClauses.append(clause.strip()+" 0\n")
                cnfClauses.append(clause.strip()+" 0\n")                                
            else:
                cnfClauses.append(clause.strip()+" 0\n")         
            
        if not "<>" in lineOld:
            #for non-goal (i.e. trans and init) formulas, extend mapping with line nos.
            #the guilty goal is always put last, so we don't need the clause nos.
            mapping[lineOld].extend(range(n+1,n+1+len(allClauses)))    
            n = n + len(allClauses)
                        
    return mapping, cnfMapping, cnfClauses, transClauses, goalClauses
    

def cnfToConjuncts(cnfIndices, mapping, cnfMapping):
    #takes a list of cnf line numbers and returns the corresponding LTL
    conjuncts = []
    
    for k in mapping.keys():
        if not set(mapping[k]).isdisjoint(cnfIndices):
#            print [cnfMapping[k][i%len(cnfMapping[k])] for i in mapping[k] if i in cnfIndices]
#            print [d for d in zip(mapping[k],cnfMapping[k]) if d[0] in cnfIndices]
            print "from conjunct ",k
            for i in range(len(mapping[k])):
                if mapping[k][i] in set(mapping[k]).intersection(cnfIndices):
                    print cnfMapping[k][i%len(cnfMapping[k])], ' at time step ', i/len(cnfMapping[k])
                           
            conjuncts.append(k)  
            #print k , (set(mapping[k]).intersection(cnfIndices))
    return conjuncts


def lineToCnf(line):
        #converts a single LTL formula into CNF form 
        line = stripLTLLine(line)
        if line!='':
            line = re.sub('s\.','',line)
            line = re.sub('e\.','',line)   
            line = re.sub(r'(next\(\s*!)', r'(!next_', line)         
            line = re.sub(r'(next\(\s*)', r'(next_', line)
            line = re.sub('!', '~', line)
            #line = re.sub('&\s*\n', '', line)
            line = re.sub('[\s]+', ' ', line)        
            line = re.sub('\<-\>', '<=>', line)
            line = re.sub('->', '>>', line)
            line = line.strip() 
            cnf = str(to_cnf(line))            
            return cnf
        else:
            return None        
        
        
    
def stripLTLLine(line, useNext=False):
        #strip white text and LTL operators           
        line = re.sub('[\t\n]*','',line)    
        line = re.sub('\<\>','',line)  
        line = re.sub('\[\]','',line)  
        line = line.strip()
        #trailing &
        line = re.sub('&\s*$','',line)   
        if useNext:
            line = re.sub('s\.','next_s.',line)
            line = re.sub('e\.','next_e.',line)                     
        return line
        
def subprocessReadThread(fd, out):
            for line in fd:                                                                              
               out.append(line) 
                
        
def findGuiltyLTLConjunctsWrapper(x):        
        return findGuiltyLTLConjuncts(*x)


        
def findGuiltyLTLConjuncts(cmd, depth, numProps, init, trans, goals, mapping,  cnfMapping, conjuncts, ignoreDepth): 
        #returns the ltl conjuncts returned as an unsat core when unrolling trans depth times from init and 
        #checking goal at final time step
        #note that init contains one-step unrolling of trans already
        
        mapping = deepcopy(mapping)
        #precompute p and n
        p = (depth+2)*(numProps)
        #the +2 is because init contains one trans already 
        #(so effectively there are depth+1 time steps and one final "next" time step)        
        
        n = (depth)*(len(trans)) + len(init) + len(goals)
        if ignoreDepth == 0:
            ignoreBound = 0
        else:
            ignoreBound = len(init) + (ignoreDepth)*len(trans)
            
        output = []
        
        #find minimal unsatisfiable core by calling picomus
        if cmd is None:
            return (False, False, [], "")   
                
        #start a reader thread        
        subp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=False)                                            
        readThread =  threading.Thread(target = subprocessReadThread, args=(subp.stdout,output))
        readThread.daemon = True
        readThread.start()
        
        
        #send header
        input = ["p cnf "+str(p)+" "+str(n)+"\n"]
        subp.stdin.write(input[0])                     
        subp.stdin.writelines(init)             
        input.extend(init)
        
        #Duplicating transition clauses for depth greater than 1         
        numOrigClauses = len(trans)  
        #the depth tells you how many time steps of trans to use
        #depth 0 just checks init with goals
        
        
        for i in range(1,depth+1):
                    for clause in trans:
                        newClause = ""
                        for c in clause.split():
                            intC = int(c)
                            newClause= newClause + str(cmp(intC,0)*(abs(intC)+numProps*i)) +" "                            
                        newClause=newClause+"\n"                                                         
                        #send this clause
                        subp.stdin.write(newClause)
                        input.append(newClause)
                        
                    j = 0    
                    for line in conjuncts:
                        if "[]" in line and "<>" not in line:                      
                            numVarsInTrans = (len(mapping[line]))/(i+1)
                            mapping[line].extend(map(lambda x: x+numOrigClauses, mapping[line][-numVarsInTrans:]))
                            j = j + 1
                    #transClauses.extend(transClausesNew)  
                    
        #create goal clauses
        dg = map(lambda x: ' '.join(map(lambda y: str(cmp(int(y),0)*(abs(int(y))+numProps*(depth))), x.split())) + '\n', goals)        
        #send goalClauses
        subp.stdin.writelines(dg)
        input.extend(dg)
        #send EOF
        subp.stdin.close()
        
                                
        #update mapping with newly added clause line numbers
        nMinusG = n - len(goals)
        for line in conjuncts:
            if "<>" in line:
                mapping[line] = range(nMinusG+1,nMinusG+len(goals)+1)
                
        
        readThread.join()
        
    

        
                
                                                                                      
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

#        #Write output to file (mainly for debugging purposes)
#        satFileName = "debug"+str(random.randint(0,1000))+".sat"
#        outputFile = open(satFileName,'w')
#        outputFile.write("\n".join(output))
#        logging.debug("wrote {}".format(satFileName))
#        outputFile.close()
#        
#        #Write input to file (mainly for debugging purposes)
#        satFileName = "input"+str(random.randint(0,1000))+".sat"
#        inputFile = open(satFileName,'w')
#        inputFile.write("\n".join(input))
#        logging.debug("wrote {}".format(satFileName))
#        inputFile.close()
            
        if any(["WARNING: core extraction disabled" in s for s in output]):
            # never again
            logging.error("************************************************")
            logging.error("*** ERROR: picomus needs to be compiled with ***")
            logging.error("*** trace support, or things will misbehave. ***")
            logging.error("***                                          ***")
            logging.error("*** Recompile with ./configure --trace       ***")
            logging.error("************************************************")
            return []

        if any(["UNSATISFIABLE" in s for s in output]):
            logging.info("Unsatisfiable core found at depth {}".format(depth))
        elif any(["SATISFIABLE" in s for s in output]):
            logging.info("Satisfiable at depth {}".format(depth))
            return []
        else:
            logging.error("Picosat error: {!r}".format(output))
        
        """cnfIndices = []
        for line in output.split('\n'):
                if re.match('^v', line):
                    index = int(line.strip('v').strip())
                    if index!=0:
                        cnfIndices.append(index)
            """
        #pythonified the above
        #get indices of contributing clauses
        cnfIndices = filter(lambda y: y!=0, map((lambda x: int(x.strip('v').strip())), filter(lambda z: re.match('^v', z), output)))
        
        #get corresponding LTL conjuncts
        guilty = cnfToConjuncts([idx for idx in cnfIndices if idx > ignoreBound], mapping, cnfMapping)
            
        return guilty
    
 
def unsatCoreCasesWrapper(x): 
    return unsatCoreCases(*x) 
    
def unsatCoreCases(cmd, propList, topo, badInit, conjuncts, maxDepth, numRegions):
     #returns the minimal unsatisfiable core (LTL formulas) given
     #        cmd: picosat command
     #        propList: list of proposition names used
     #        topo: LTL formula describing topology
     #        badInit: formula describing bad initial states
     #        conjuncts: remaining LTL formulas highlighted by preliminary analysis
     #        maxDepth: determines how many time steps we unroll 
     #        numRegions: used to determine minimum depth to prevent false alarms (every depth between numRegions+1 and maxDepth is checked)
       
        numProps = len(propList)
        #initial depth is set to the number of regions. This ensures that we unroll at least as 
        #far as needed to physically get to the goal
        depth = numRegions
        
        #first try without topo and init, see if it is satisfiable
        ignoreDepth = 0    
        mapping, cnfMapping, init, trans, goals = conjunctsToCNF([badInit]+conjuncts, propList)
        
        logging.info("Trying to find core without topo or init") 

        guiltyList = runMap(findGuiltyLTLConjunctsWrapper, itertools.izip(itertools.repeat(cmd),
                                                                          range(1, maxDepth + 1),
                                                                          itertools.repeat(numProps),
                                                                          itertools.repeat(init),
                                                                          itertools.repeat(trans), 
                                                                          itertools.repeat(goals),
                                                                          itertools.repeat(mapping),
                                                                          itertools.repeat(cnfMapping),
                                                                          itertools.repeat(conjuncts),
                                                                          itertools.repeat(ignoreDepth)))

        #allGuilty = map((lambda (depth, cnfs): self.guiltyParallel(depth+1, cnfs, mapping)), list(enumerate(allCnfs)))
            
        allGuilty = set([item for sublist in guiltyList for item in sublist])
            
        if all(guiltyList):
            logging.info("Unsat core found without topo or init")
            return trans, allGuilty
        else:
            ignoreDepth = len([g for g in guiltyList if g])
            depth += ignoreDepth
        
        logging.info("ignore depth {}".format(ignoreDepth))
            
        #then try just topo and init and see if it is unsatisfiable. If so, return core.
        logging.info("Trying to find core with just topo and init") 
        mapping,  cnfMapping, init, trans, goals = conjunctsToCNF([topo, badInit], propList)
       
                    
        guilty = findGuiltyLTLConjuncts(cmd,maxDepth,numProps,init,trans,goals,mapping,cnfMapping,[topo, badInit],0)
        
                #allGuilty = map((lambda (depth, cnfs): self.guiltyParallel(depth+1, cnfs, mapping)), list(enumerate(allCnfs)))
            #print "ENDING PICO MAP"
 
        if guilty:
            logging.info("Unsat core found with just topo and init")
            return trans, guilty
        
        #if the problem is in conjunction with the topo but not just topo, keep increasing the depth until something more than just topo is returned
        mapping,  cnfMapping, init, trans, goals = conjunctsToCNF([topo,badInit] + conjuncts, propList)
        
        logging.info("Trying to find core with everything")
        

        guiltyList = runMap(findGuiltyLTLConjunctsWrapper, itertools.izip(itertools.repeat(cmd),
                                                                          range(maxDepth, maxDepth + 1),
                                                                          itertools.repeat(numProps),
                                                                          itertools.repeat(init),
                                                                          itertools.repeat(trans),
                                                                          itertools.repeat(goals),
                                                                          itertools.repeat(mapping),
                                                                          itertools.repeat(cnfMapping),
                                                                          itertools.repeat([topo, badInit] + conjuncts),
                                                                          itertools.repeat(ignoreDepth)))

        #allGuilty = map((lambda (depth, cnfs): self.guiltyParallel(depth+1, cnfs, mapping)), list(enumerate(allCnfs)))
        
        guilty = [item for sublist in guiltyList for item in sublist]        
        
        guiltyMinusGoal = [g for g in guilty if '<>' not in g]

        # don't use ignoreDepth for deadlock
        if len(goals) == 0:
           ignoreDepth = 0 
                        
        justTopo = set([topo, badInit]).issuperset(guiltyMinusGoal)
        depth = maxDepth + 1
        
        #while justTopo and depth < maxDepth:
            
            #guilty = findGuiltyLTLConjuncts(cmd,depth,numProps,init,trans,goals,mapping,cnfMapping,[topo, badInit]+conjuncts, ignoreDepth)
            ##allGuilty = map((lambda (depth, cnfs): self.guiltyParallel(depth+1, cnfs, mapping)), list(enumerate(allCnfs)))
            ##print "ENDING PICO MAP"
            
            
            #guiltyMinusGoal = [g for g in guilty if '<>' not in g]
            #if not set([topo, badInit]).issuperset(set(guiltyMinusGoal)):
                #justTopo = False
            #else:
                #depth+=1
            ##get contributing conjuncts from CNF indices            
            ##guilty = cnfToConjuncts(allIndices, mapping)
        
        logging.info("Unsat core found with all parts")
        
        return trans, guilty
    
def stateToLTL(state, useEnv=1, useSys=1, use_next=False):
        def decorate_prop(prop, polarity):
            if int(polarity) == 0:
                prop = "!"+prop
            if use_next:
                prop = "next({})".format(prop)
            return prop
            
       
        sys_state = " & ".join([decorate_prop("s."+p, v) for p,v in state.inputs.iteritems()])
        env_state = " & ".join([decorate_prop("e."+p, v) for p,v in state.outputs.iteritems()])
                
        if useEnv:
            if useSys:
                return env_state + " & " + sys_state
            else:
                return env_state
        elif useSys:
            return sys_state
        else:
            return ""
            
        
class SpecCompilerCoreFindingExtensions(object): 
    def _coreFinding(self, to_highlight, unsat, badInit):
        #returns list of formulas that cause unsatisfiability/unrealizability (based on unsat flag).
        #takes as input sentences marked for highlighting, and formula describing bad initial states 
        #from JTLV.
        
        #find number of states in automaton/counter for unsat/unreal core max unrolling depth ("recurrence diameter")
        proj_copy = deepcopy(self.proj)
        proj_copy.rfi = self.parser.proj.rfi
        proj_copy.sensor_handler = None
        proj_copy.actuator_handler = None
        proj_copy.h_instance = None
        
        num_bits = int(numpy.ceil(numpy.log2(len(self.parser.proj.rfi.regions))))  # Number of bits necessary to encode all regions
        region_props = ["bit" + str(n) for n in xrange(num_bits)]

        aut = fsa.Automaton(proj_copy)
        aut.loadFile(self.proj.getFilenamePrefix()+".aut", self.proj.enabled_actuators + self.proj.all_customs + region_props, self.proj.enabled_sensors, [])
       
        
        #find deadlocked states in the automaton (states with no out-transitions)
        deadStates = [s for s in aut.states if not s.transitions]
        #find states that can be forced by the environment into the deadlocked set
        forceDeadStates = [(s, e) for s in aut.states for e in deadStates if e in s.transitions]
        #LTL representation of these states and the deadlock-causing environment move in the next time step       
        forceDeadlockLTL = map(lambda (s,e): " & ".join([stateToLTL(s), stateToLTL(e, 1, 1, True)]), forceDeadStates)
        
        
        #find livelocked goal and corresponding one-step propositional formula (by stripping LTL operators)     
        desiredGoal = [h_item[2] for h_item in to_highlight if h_item[1] == "goals"]
        
        
        if desiredGoal:
            desiredGoal = desiredGoal[0]
            #Don't actually need LTL        
            #desiredGoalLTL = stripLTLLine(self.ltlConjunctsFromBadLines([h_item for h_item in to_highlight if h_item[1] == "goals"], False)[0],True)
        
        
            
        def preventsDesiredGoal(s):
                rank_str = s.transitions[0].rank
                m = re.search(r"\(\d+,(-?\d+)\)", rank_str)
                if m is None:
                    logging.error("Error parsing jx in automaton.  Are you sure the spec is unrealizable?")
                    return
                jx = int(m.group(1))         
                return (jx == desiredGoal)
                    
        
        #find livelocked states in the automaton (states with desired sys rank)           
        livelockedStates = filter(preventsDesiredGoal, [s for s in aut.states if s.transitions])
        #find states that can be forced by the environment into the livelocked set
        forceLivelockedStates = [(fro, to) for fro in aut.states for to in livelockedStates if to in s.transitions]
        
        #LTL representation of these states and the livelocked goal  
        #forceLivelockLTL = map(lambda s: " & ".join([stateToLTL(s), desiredGoalLTL]), livelockedStates) ###Don't actually need to add goal -- will be added in 'conjuncts'
        forceLivelockLTL = map(lambda (s1,s2): " & ".join([stateToLTL(s1, 1, 1), stateToLTL(s2, 1, 0, True)]), forceLivelockedStates)
        #forceLivelockLTL = map(stateToLTL, livelockedStates)
        
        numStates = len(aut.states)
        numRegions = len(self.parser.proj.rfi.regions)
        
        if forceDeadlockLTL:
            deadlockFlag = True
            badStatesLTL = forceDeadlockLTL
        else:
            #this means livelock
            deadlockFlag = False            
            badStatesLTL = forceLivelockLTL
            
        #################################
        #                               #
        # get conjuncts to be minimized #
        #                               #
        #################################
        
        #topology
        topo =self.spec['Topo'].replace('\n','')
        topo = topo.replace('\t','')
        
        #have to use all initial conditions if no single bad initial state given
        useInitFlag = badInit is None
        
        #other highlighted LTL formulas
        conjuncts = self.ltlConjunctsFromBadLines(to_highlight, useInitFlag)
        
        #filter out props that are actually used
        #self.propList = [p for p in self.propList if [c for c in conjuncts if p in c] or [c for c in badStatesLTL if p in c and not unsat] or p in topo]
                    
        cmd = self._getPicosatCommand() 
            
        if unsat:
            guilty = self.unsatCores(cmd, topo,badInit,conjuncts,15,15)#returns LTL  
        else:
            guilty = self.unrealCores(cmd, topo, badStatesLTL, conjuncts, deadlockFlag)#returns LTL   
        return guilty
        
        
        

    def unsatCores(self, cmd, topo, badInit, conjuncts,maxDepth,numRegions):
        #returns list of guilty LTL formulas
        #takes LTL formulas for topo, badInit and conjuncts separately because they are used in various combinations later
        #numStates and numRegions are used to determine unroll depth later
        
        if not conjuncts and badInit == "":
            #this means that the topology is unsatisfiable by itself (not common since we auto-generate)
            return topo
        else:
            #try the different cases of unsatisfiability (need to pass in command and proplist to coreUtils function)
            self.trans, guilty = unsatCoreCases(cmd, self.propList, topo, badInit, conjuncts,maxDepth,numRegions)
                    
        return guilty
                

        
    def unrealCores(self, cmd, topo, badStatesLTL, conjuncts, deadlockFlag):
        #returns list of guilty LTL formulas FOR THE UNREALIZABLE CASE
        #takes LTL formulas representing the topology and other highlighted conjuncts as in the unsat case.
        #also takes a list of deadlocked/livelocked states (as LTL/propositional formulas)        
        #returns LTL formulas that appear in the guilty set for *any* deadlocked or livelocked state,
        #i.e. formulas that cause deadlock/livelock in these states
        
        #try the different cases of unsatisfiability (need to pass in command and proplist to coreUtils function)
        if deadlockFlag:
            initDepth = 1
            maxDepth = 1            
        else:
            initDepth = 1
            maxDepth = 1                             
        
    #        TODO: see if there is a way to call pool.map with processes that also use pools
    #
    #        sys.stdout = StringIO.StringIO()
    #        
    #        pool = Pool()
    #        guiltyList = pool.map(unsatCoreCasesWrapper, itertools.izip(itertools.repeat(cmd), itertools.repeat(self.propList), itertools.repeat(topo), badStatesLTL, itertools.repeat(conjuncts), itertools.repeat(initDepth), itertools.repeat(maxDepth)))            
    #        pool.terminate()
    #        
    #        sys.stdout = sys.__stdout__

        guiltyList = map(lambda d: unsatCoreCases(cmd, self.propList, topo, d, conjuncts, initDepth, maxDepth), badStatesLTL)
        
        guilty = reduce(set.union,map(set,[g for t, g in guiltyList]))
                 
        return guilty


        

        
    def _getPicosatCommand(self):
        # look for picosat

        paths = [p for p in glob.glob(os.path.join(self.proj.ltlmop_root,"lib","cores","picosat-*")) if os.path.isdir(p)]
        if len(paths) == 0:
            logging.error("Where is your sat solver? We use Picosat.")
            # TODO: automatically compile for the user
            return None
        else:
            logging.debug("Found Picosat in " + paths[0])

        if os.name == "nt":
            cmd = os.path.join(paths[0],"picomus.exe")
        else:
            cmd = [os.path.join(paths[0],"picomus")]

        return cmd


        
                

    def ltlConjunctsFromBadLines(self, to_highlight, useInitFlag):
        #given the lines to be highlighted by the initial analysis, returns 
        #a list of LTL formulas that, when conjuncted, cause unsatisfiability
        #topology conjuncts are separated out
               
        conjuncts = []
                
        for h_item in to_highlight:
            tb_key = h_item[0].title() + h_item[1].title()

            newCs = []
            if h_item[1] == "goals":
                #special treatment for goals: (1) we already know which one to highlight, and (2) we need to check both tenses
                #TODO: separate out the check for present and future tense -- what if you have to toggle but can still do so infinitely often?
                #newCs = ivd[self.traceback[tb_key][h_item[2]]].split('\n')                 
                goals = self.spec[tb_key].split('\n')
                newCs = [goals[h_item[2]]]
                newCsOld = newCs
                
            elif h_item[1] == "trans" or h_item[1] == "init" and useInitFlag:
                newCs =  self.spec[tb_key].replace("\t", "\n").split("\n")
                
            conjuncts.extend(newCs)
        
        return conjuncts
