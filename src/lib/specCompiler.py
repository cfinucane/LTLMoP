import os
import sys
import re
import time
import math
import subprocess
import globalConfig
import logging

import project
import parseLP
from createJTLVinput import createLTLfile, createSMVfile
from copy import deepcopy
import LTLMacros
import mapProcessing

# Bring in extra capabilities from other modules
from analysis import SpecCompilerAnalysisExtensions
from cores.coreUtils import SpecCompilerCoreFindingExtensions

# Hack needed to ensure there's only one
_SLURP_SPEC_GENERATOR = None

class SpecCompiler(object, SpecCompilerAnalysisExtensions, SpecCompilerCoreFindingExtensions):
    """ A SpecCompiler object manages the process of transforming a specification (and map)
        into a strategy. """

    def __init__(self, spec_filename=None):
        # Allocate a blank project object
        self.proj = project.Project()

        # If we've been passed a spec_filename, go ahead and load it now
        if spec_filename is not None:
            self.loadProjectFromFile(spec_filename)

    def loadProjectFromFile(self, spec_filename):
        """ Load an existing project from a .spec file """

        self.proj.loadProject(spec_filename)

        try:
            self._checkIfProjectIsComplete()
        except ValueError as e:
            logging.warning(e)

    def _checkIfProjectIsComplete(self):
        """ Make sure the currently-loaded project contains the bare minimums that we
            need to successfully compile.

            There is no return value; will raise a ValueError if there are any problems."""

        # Check for a map
        if self.proj.rfi is None:
            raise ValueError("Please define regions before compiling.")

        # Make sure the specification is not effectively empty
        spec_text_minus_comments = re.sub(r"#.*$", "", self.proj.specText, flags=re.MULTILINE)
        if spec_text_minus_comments.strip() == "":
            raise ValueError("Please write a specification before compiling.")

    def _decompose(self):
        self.parser = parseLP.parseLP()
        self.parser.main(self.proj.getFilenamePrefix() + ".spec")

        # Remove all references to any obstacle regions at this point
        for r in self.proj.rfi.regions:
            if r.isObstacle:
                # Delete corresponding decomposed regions
                for sub_r in self.parser.proj.regionMapping[r.name]:
                    del self.parser.proj.rfi.regions[self.parser.proj.rfi.indexOfRegionWithName(sub_r)]

                    # Remove decomposed region from any overlapping mappings
                    for k,v in self.parser.proj.regionMapping.iteritems(): 
                        if k == r.name: continue
                        if sub_r in v:
                            v.remove(sub_r)

                # Remove mapping for the obstacle region
                del self.parser.proj.regionMapping[r.name]

        #self.proj.rfi.regions = filter(lambda r: not (r.isObstacle or r.name == "boundary"), self.proj.rfi.regions)
                    
        # save the regions into new region file
        filename = self.proj.getFilenamePrefix() + '_decomposed.regions'

        # FIXME: properly support obstacles in non-decomposed maps?
        if self.proj.compile_options["decompose"]:
            self.parser.proj.rfi.recalcAdjacency()

        self.parser.proj.rfi.writeFile(filename)


        self.proj.regionMapping = self.parser.proj.regionMapping
        self.proj.writeSpecFile()

    def _writeSMVFile(self):
        if self.proj.compile_options["decompose"]:
            numRegions = len(self.parser.proj.rfi.regions)
        else:
            numRegions = len(self.proj.rfi.regions)
        sensorList = self.proj.enabled_sensors
        robotPropList = self.proj.enabled_actuators + self.proj.all_customs + self.proj.internal_props

        # Add in regions as robot outputs
        if self.proj.compile_options["use_region_bit_encoding"]:
            robotPropList.extend(["bit"+str(i) for i in range(0,int(numpy.ceil(numpy.log2(numRegions))))])
        else:
            if self.proj.compile_options["decompose"]:
                robotPropList.extend([r.name for r in self.parser.proj.rfi.regions])
            else:
                robotPropList.extend([r.name for r in self.proj.rfi.regions])

        self.propList = sensorList + robotPropList
        
        createSMVfile(self.proj.getFilenamePrefix(), sensorList, robotPropList)

    def _writeLTLFile(self):

        self.LTL2SpecLineNumber = None

        #regionList = [r.name for r in self.parser.proj.rfi.regions]
        regionList = [r.name for r in self.proj.rfi.regions]
        sensorList = deepcopy(self.proj.enabled_sensors)
        robotPropList = self.proj.enabled_actuators + self.proj.all_customs
        
        text = self.proj.specText

        response = None

        # Create LTL using selected parser
        # TODO: rename decomposition object to something other than 'parser'
        if self.proj.compile_options["parser"] == "slurp":
            # default to no region tags if no simconfig is defined, so we can compile without
            if self.proj.currentConfig is None:
                region_tags = {}
            else:
                region_tags = self.proj.currentConfig.region_tags
 
            # Hack: We need to make sure there's only one of these
            global _SLURP_SPEC_GENERATOR
            
            # Make a new specgenerator and have it process the text
            if not _SLURP_SPEC_GENERATOR:
                # Add SLURP to path for import
                p = os.path.dirname(os.path.abspath(__file__))
                sys.path.append(os.path.join(p, "..", "etc", "SLURP"))
                from ltlbroom.specgeneration import SpecGenerator
                _SLURP_SPEC_GENERATOR = SpecGenerator()
            
            # Filter out regions it shouldn't know about
            filtered_regions = [region.name for region in self.proj.rfi.regions 
                                if not (region.isObstacle or region.name.lower() == "boundary")]
            LTLspec_env, LTLspec_sys, self.proj.internal_props, internal_sensors, results, responses, traceback = \
                _SLURP_SPEC_GENERATOR.generate(text, sensorList, filtered_regions, robotPropList, region_tags)

            oldspec_env = LTLspec_env
            oldspec_sys = LTLspec_sys
 
            for ln, result in enumerate(results):
                if not result:
                    logging.warning("Could not parse the sentence in line {0}".format(ln))

            # Abort compilation if there were any errors
            if not all(results):
                return None, None, responses
        
            # Add in the sensors so they go into the SMV and spec files
            for s in internal_sensors:
                if s not in sensorList:
                    sensorList.append(s)
                    self.proj.all_sensors.append(s)
                    self.proj.enabled_sensors.append(s)                    

            # Conjoin all the spec chunks
            LTLspec_env = '\t\t' + ' & \n\t\t'.join(LTLspec_env)
            LTLspec_sys = '\t\t' + ' & \n\t\t'.join(LTLspec_sys)
            
            if self.proj.compile_options["decompose"]:
                # substitute decomposed region names
                for r in self.proj.rfi.regions:
                    if not (r.isObstacle or r.name.lower() == "boundary"):
                        LTLspec_env = re.sub('\\bs\.' + r.name + '\\b', "("+' | '.join(["s."+x for x in self.parser.proj.regionMapping[r.name]])+")", LTLspec_env)
                        LTLspec_env = re.sub('\\be\.' + r.name + '\\b', "("+' | '.join(["e."+x for x in self.parser.proj.regionMapping[r.name]])+")", LTLspec_env)
                        LTLspec_sys = re.sub('\\bs\.' + r.name + '\\b', "("+' | '.join(["s."+x for x in self.parser.proj.regionMapping[r.name]])+")", LTLspec_sys)
                        LTLspec_sys = re.sub('\\be\.' + r.name + '\\b', "("+' | '.join(["e."+x for x in self.parser.proj.regionMapping[r.name]])+")", LTLspec_sys)

            response = responses

        elif self.proj.compile_options["parser"] == "ltl":
            # delete comments
            text = re.sub(r"#.*$", "", text, flags=re.MULTILINE)

            # split into env and sys parts (by looking for a line of just dashes in between)
            LTLspec_env, LTLspec_sys = re.split(r"^\s*-+\s*$", text, maxsplit=1, flags=re.MULTILINE)

            # split into subformulas
            LTLspec_env = re.split(r"(?:[ \t]*[\n\r][ \t]*)+", LTLspec_env)
            LTLspec_sys = re.split(r"(?:[ \t]*[\n\r][ \t]*)+", LTLspec_sys)

            # remove any empty initial entries (HACK?)
            while '' in LTLspec_env:
                LTLspec_env.remove('')
            while '' in LTLspec_sys:
                LTLspec_sys.remove('')

            # automatically conjoin all the subformulas
            LTLspec_env = '\t\t' + ' & \n\t\t'.join(LTLspec_env)
            LTLspec_sys = '\t\t' + ' & \n\t\t'.join(LTLspec_sys)

            if self.proj.compile_options["decompose"]:
                # substitute decomposed region 
                for r in self.proj.rfi.regions:
                    if not (r.isObstacle or r.name.lower() == "boundary"):
                        LTLspec_env = re.sub('\\b(?:s\.)?' + r.name + '\\b', "("+' | '.join(["s."+x for x in self.parser.proj.regionMapping[r.name]])+")", LTLspec_env)
                        LTLspec_sys = re.sub('\\b(?:s\.)?' + r.name + '\\b', "("+' | '.join(["s."+x for x in self.parser.proj.regionMapping[r.name]])+")", LTLspec_sys)
            else:
                for r in self.proj.rfi.regions:
                    if not (r.isObstacle or r.name.lower() == "boundary"):
                        LTLspec_env = re.sub('\\b(?:s\.)?' + r.name + '\\b', "s."+r.name, LTLspec_env)
                        LTLspec_sys = re.sub('\\b(?:s\.)?' + r.name + '\\b', "s."+r.name, LTLspec_sys)

            traceback = [] # HACK: needs to be something other than None
        elif self.proj.compile_options["parser"] == "structured":
            import parseEnglishToLTL

            if self.proj.compile_options["decompose"]:
                # substitute the regions name in specs
                for m in re.finditer(r'near (?P<rA>\w+)', text):
                    text=re.sub(r'near (?P<rA>\w+)', "("+' or '.join(["s."+r for r in self.parser.proj.regionMapping['near$'+m.group('rA')+'$'+str(50)]])+")", text)
                for m in re.finditer(r'within (?P<dist>\d+) (from|of) (?P<rA>\w+)', text):
                    text=re.sub(r'within ' + m.group('dist')+' (from|of) '+ m.group('rA'), "("+' or '.join(["s."+r for r in self.parser.proj.regionMapping['near$'+m.group('rA')+'$'+m.group('dist')]])+")", text)
                for m in re.finditer(r'between (?P<rA>\w+) and (?P<rB>\w+)', text):
                    text=re.sub(r'between ' + m.group('rA')+' and '+ m.group('rB'),"("+' or '.join(["s."+r for r in self.parser.proj.regionMapping['between$'+m.group('rA')+'$and$'+m.group('rB')+"$"]])+")", text)

                # substitute decomposed region 
                for r in self.proj.rfi.regions:
                    if not (r.isObstacle or r.name.lower() == "boundary"):
                        text = re.sub('\\b' + r.name + '\\b', "("+' | '.join(["s."+x for x in self.parser.proj.regionMapping[r.name]])+")", text)

                regionList = ["s."+x.name for x in self.parser.proj.rfi.regions]
            else:
                for r in self.proj.rfi.regions:
                    if not (r.isObstacle or r.name.lower() == "boundary"):
                        text = re.sub('\\b' + r.name + '\\b', "s."+r.name, text)

                regionList = ["s."+x.name for x in self.proj.rfi.regions]

            spec, traceback, failed, self.LTL2SpecLineNumber, self.proj.internal_props = parseEnglishToLTL.writeSpec(text, sensorList, regionList, robotPropList)

            # Abort compilation if there were any errors
            if failed:
                return None, None, None

            LTLspec_env = spec["EnvInit"] + spec["EnvTrans"] + spec["EnvGoals"]
            LTLspec_sys = spec["SysInit"] + spec["SysTrans"] + spec["SysGoals"]

        else:
            logging.error("Parser type '{0}' not currently supported".format(self.proj.compile_options["parser"]))
            return None, None, None

        if self.proj.compile_options["decompose"]:
            regionList = [x.name for x in self.parser.proj.rfi.regions]
        else:
            regionList = [x.name for x in self.proj.rfi.regions]

        if self.proj.compile_options["use_region_bit_encoding"]:
            # Define the number of bits needed to encode the regions
            numBits = int(math.ceil(math.log(len(regionList),2)))

            # creating the region bit encoding
            bitEncode = bitEncoding(len(regionList),numBits)
            currBitEnc = bitEncode['current']
            nextBitEnc = bitEncode['next']

            # switch to bit encodings for regions
            LTLspec_env = replaceRegionName(LTLspec_env, bitEncode, regionList)
            LTLspec_sys = replaceRegionName(LTLspec_sys, bitEncode, regionList)
        
            if self.LTL2SpecLineNumber is not None:
                for k in self.LTL2SpecLineNumber.keys():
                    new_k = replaceRegionName(k, bitEncode, regionList)
                    if new_k != k:
                        self.LTL2SpecLineNumber[new_k] = self.LTL2SpecLineNumber[k]
                        del self.LTL2SpecLineNumber[k]

        if self.proj.compile_options["decompose"]:
            adjData = self.parser.proj.rfi.transitions
        else:
            adjData = self.proj.rfi.transitions

        # Store some data needed for later analysis
        self.spec = {}
        if self.proj.compile_options["decompose"]:
            self.spec['Topo'] = createTopologyFragment(adjData, self.parser.proj.rfi.regions, use_bits=self.proj.compile_options["use_region_bit_encoding"])
        else: 
            self.spec['Topo'] = createTopologyFragment(adjData, self.proj.rfi.regions, use_bits=self.proj.compile_options["use_region_bit_encoding"])

        # Substitute any macros that the parsers passed us
        LTLspec_env = self.substituteMacros(LTLspec_env)
        LTLspec_sys = self.substituteMacros(LTLspec_sys)

        # If we are not using bit-encoding, we need to
        # explicitly encode a mutex for regions
        if not self.proj.compile_options["use_region_bit_encoding"]:
            # DNF version (extremely slow for core-finding)
            #mutex = "\n\t&\n\t []({})".format(" | ".join(["({})".format(" & ".join(["s."+r2.name if r is r2 else "!s."+r2.name for r2 in self.parser.proj.rfi.regions])) for r in self.parser.proj.rfi.regions]))

            if self.proj.compile_options["decompose"]:
                region_list = self.parser.proj.rfi.regions
            else:
                region_list = self.proj.rfi.regions

            # Almost-CNF version
            exclusions = []
            for i, r1 in enumerate(region_list):
                for r2 in region_list[i+1:]:
                    exclusions.append("!(s.{} & s.{})".format(r1.name, r2.name))
            mutex = "\n&\n\t []({})".format(" & ".join(exclusions))
            LTLspec_sys += mutex

        self.spec.update(self.splitSpecIntoComponents(LTLspec_env, LTLspec_sys))

        # Add in a fragment to make sure that we start in a valid region
        if self.proj.compile_options["decompose"]:
            self.spec['InitRegionSanityCheck'] = createInitialRegionFragment(self.parser.proj.rfi.regions, use_bits=self.proj.compile_options["use_region_bit_encoding"])
        else:
            self.spec['InitRegionSanityCheck'] = createInitialRegionFragment(self.proj.rfi.regions, use_bits=self.proj.compile_options["use_region_bit_encoding"])
        LTLspec_sys += "\n&\n" + self.spec['InitRegionSanityCheck']

        LTLspec_sys += "\n&\n" + self.spec['Topo']

        createLTLfile(self.proj.getFilenamePrefix(), LTLspec_env, LTLspec_sys)
        
        if self.proj.compile_options["parser"] == "slurp":
            self.reversemapping = {self.postprocessLTL(line,sensorList,robotPropList).strip():line.strip() for line in oldspec_env + oldspec_sys}
            self.reversemapping[self.spec['Topo'].replace("\n","").replace("\t","").lstrip().rstrip("\n\t &")] = "TOPOLOGY"

        #for k,v in self.reversemapping.iteritems():
        #    print "{!r}:{!r}".format(k,v)        

        return self.spec, traceback, response

    def substituteMacros(self, text):
        """
        Replace any macros passed to us by the parser.  In general, this is only necessary in cases
        where bitX propositions are needed, since the parser is not supposed to know about them.
        """

        # This creates a mirrored copy of topological constraints for the target we are following
        if "FOLLOW_SENSOR_CONSTRAINTS" in text:
            if not self.proj.compile_options["use_region_bit_encoding"]:
                logging.warning("Currently, bit encoding must be enabled for follow sensor")
            else:
                env_topology = self.spec['Topo'].replace("s.bit", "e.sbit")
                initreg_formula = createInitialRegionFragment(self.parser.proj.rfi.regions, use_bits=True).replace("s.bit", "e.sbit")

                sensorBits = ["sbit{}".format(i) for i in range(0,int(numpy.ceil(numpy.log2(len(self.parser.proj.rfi.regions)))))]
                for p in sensorBits:
                    if p not in self.proj.enabled_sensors:
                        self.proj.enabled_sensors.append(p)
                    if p not in self.proj.all_sensors:   
                        self.proj.all_sensors.append(p)

                text = text.replace("FOLLOW_SENSOR_CONSTRAINTS", env_topology + "\n&\n" + initreg_formula)

        # Stay-there macros.  This can be done using just region names, but is much more concise
        # using bit encodings (and thus much faster to encode as CNF)

        if "STAY_THERE" in text:
            if self.proj.compile_options["decompose"]:
                text = text.replace("STAY_THERE", createStayFormula([r.name for r in self.parser.proj.rfi.regions], use_bits=self.proj.compile_options["use_region_bit_encoding"]))
            else:
                text = text.replace("STAY_THERE", createStayFormula([r.name for r in self.proj.rfi.regions], use_bits=self.proj.compile_options["use_region_bit_encoding"]))

        if "TARGET_IS_STATIONARY" in text:
            text = text.replace("TARGET_IS_STATIONARY", createStayFormula([r.name for r in self.parser.proj.rfi.regions], use_bits=self.proj.compile_options["use_region_bit_encoding"]).replace("s.","e.s"))

        return text

    
    def postprocessLTL(self, text, sensorList, robotPropList):
        # TODO: make everything use this
        if self.proj.compile_options["decompose"]:
            # substitute decomposed region names
            for r in self.proj.rfi.regions:
                if not (r.isObstacle or r.name.lower() == "boundary"):
                    text = re.sub('\\bs\.' + r.name + '\\b', "("+' | '.join(["s."+x for x in self.parser.proj.regionMapping[r.name]])+")", text)
                    text = re.sub('\\be\.' + r.name + '\\b', "("+' | '.join(["e."+x for x in self.parser.proj.regionMapping[r.name]])+")", text)

        if self.proj.compile_options["decompose"]:
            regionList = [x.name for x in self.parser.proj.rfi.regions]
        else:
            regionList = [x.name for x in self.proj.rfi.regions]

        # Define the number of bits needed to encode the regions
        numBits = int(math.ceil(math.log(len(regionList),2)))

        # creating the region bit encoding
        bitEncode = bitEncoding(len(regionList),numBits)
        currBitEnc = bitEncode['current']
        nextBitEnc = bitEncode['next']

        # switch to bit encodings for regions
        if self.proj.compile_options["use_region_bit_encoding"]:
            text = replaceRegionName(text, bitEncode, regionList)

        text = self.substituteMacros(text)

        return text
    
    def splitSpecIntoComponents(self, env, sys):
        spec = {}

        for agent, text in (("env", env), ("sys", sys)):
            for line in text.split("\n"):
                if line.strip() == '': continue

                if "[]<>" in line: 
                    linetype = "goals"
                elif "[]" in line:
                    linetype = "trans"
                else:
                    linetype = "init"

                key = agent.title()+linetype.title()
                if key not in spec:
                    spec[key] = ""

                spec[key] += line + "\n"

        return spec
        
    def _getGROneCommand(self, module):
        # Check that GROneMain, etc. is compiled
        if not os.path.exists(os.path.join(self.proj.ltlmop_root,"etc","jtlv","GROne","GROneMain.class")):
            logging.error("Please compile the synthesis Java code first.  For instructions, see etc/jtlv/JTLV_INSTRUCTIONS.")
            # TODO: automatically compile for the user
            return None

        # Windows uses a different delimiter for the java classpath
        if os.name == "nt":
            delim = ";"
        else:
            delim = ":"

        classpath = delim.join([os.path.join(self.proj.ltlmop_root, "etc", "jtlv", "jtlv-prompt1.4.0.jar"), os.path.join(self.proj.ltlmop_root, "etc", "jtlv", "GROne")])

        cmd = ["java", "-ea", "-Xmx512m", "-cp", classpath, module, self.proj.getFilenamePrefix() + ".smv", self.proj.getFilenamePrefix() + ".ltl"]

        return cmd


    def _synthesize(self, with_safety_aut=False):
        cmd = self._getGROneCommand("GROneMain")
        if cmd is None:
            return (False, False, "")

        if with_safety_aut:    # Generally used for Mopsy
            cmd.append("--safety")

        if self.proj.compile_options["fastslow"]:
            cmd.append("--fastslow")

        subp = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=False)
        
        realizable = False
        realizableFS = False

        output = ""
        for line in subp.stdout:
            output += line
            if "Specification is realizable" in line:
                realizable = True
            if "Specification is realizable with slow and fast actions" in line:
                realizableFS = True
               
        subp.stdout.close()

        return (realizable, realizableFS, output)

    def compile(self, with_safety_aut=False):
        if self.proj.compile_options["decompose"]:
            logging.info("Decomposing...")
            self._decompose()
        logging.info("Writing LTL file...")
        spec, tb, resp = self._writeLTLFile()
        logging.info("Writing SMV file...")
        self._writeSMVFile()

        if tb is None:
            logging.error("Compilation aborted")
            return 

        #self._checkForEmptyGaits()
        logging.info("Synthesizing a strategy...")

        return self._synthesize(with_safety_aut)


if __name__ == "__main__":
    # TODO: testing code
    print "test"
