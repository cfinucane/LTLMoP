#!/usr/bin/env python


""" ================================================
    hsubConfigObjects.py - Defines necessary config objects for
    handlerSubsystem.py
    ================================================

    This module defines objects for handler system.
    It also provides interface that deal with handler and config files
"""

import os, sys, re
import fileMethods
import inspect, types
from numpy import linalg, array, finfo, mat
from copy import deepcopy
import ast
import json
import traceback
import globalConfig, logging
import importlib
import handlers.handlerTemplates as ht
from hsubParsingUtils import parseCallString


###################################################
# Define individual objects for handler subsystem #
###################################################
class MethodParameterConfig(object):
    """
    An argument to a handler method
    Contains name, description, type, value, and default as determined
    by performing introspection on the individual handler modules
    """

    @classmethod
    def fromString(cls, para_string):
        """
        Create a MethodParameterConfig from a single line of a comment from a
        handler method.

        para_string: string specifying the properties of the parameter
        """

        # Regular expression to help us out
        # NOTE: The description does not permit parentheses
        argRE = re.compile('^\s*(?P<argName>\w+)\s*\(\s*(?P<type>\w+)\s*\)\s*:\s*(?P<description>[^\(]+)\s*(?P<settings>\(.+\))?\s*$', re.IGNORECASE)

        # Try to match
        m = argRE.search(para_string)

        if m is None:
            raise ValueError("Not a properly-formatted parameter description.")

        new_obj = cls(name=m.group('argName'),
                      para_type=m.group('type'),
                      desc=m.group('description'))

        if m.group('settings') is not None:
            # To make valid Python syntax, we just need to prepend
            # a dummy function name before the settings string
            try:
                call_desc, _ = parseCallString("dummy_function"+m.group("settings"),
                                               mode="single")
            except SyntaxError as e:
                raise SyntaxError("Error while parsing settings for parameter {!r}: {}".format(m.group('argName'), e))

            settings = call_desc[0].args

            # Set all of the settings
            for k, v in settings.iteritems():
                if k.lower() not in ['default', 'min_val', 'max_val', 'options', 'min', 'max']:
                    raise SyntaxError("Unrecognized setting name {!r} for parameter {!r}".format(k.lower(), m.group('argName')))

                setattr(new_obj, k.lower(), v)

        new_obj.resetValue()

        return new_obj

    def __init__(self, name="", para_type="", desc="", default=None, max_val=None, min_val=None, value=None):
        self.name = name                # name of the parameter
        self.para_type = para_type      # type of the parameter
        self.desc = desc                # description of the parameter
        self.default = default          # the default values of the parameter
        self.max_val = max_val          # the max value allowed for the parameter
        self.min_val = min_val          # the min value allowed for the parameter
        self.value = value              # the value user set for the parameter

    def __repr__(self):
        """
        Overwrite string representation function
        """
        strRepr = ""
        # Only show the atrributes we are interested in
        keyList = ['name', 'para_type', 'default', 'max_val', 'min_val', 'value']
        for key in keyList:
            strRepr = strRepr + ("{0:12}{1}\n".format("<"+key+">:", getattr(self, key, 'NOT DEFINED')))
        reprString = "\n -- Method Parameter <{0}> -- \n".format(self.name) + \
                    strRepr + " -- End of Method Parameter <{0}> -- \n".format(self.name)
        return reprString

    def setValue(self, value):
        """
        This function makes sure all parameter are set according to the desired type
        """

        # Change None para_type to empty string to avoid None.lower()
        if self.para_type == None: self.para_type = ""

        if self.para_type.lower() in ['float', 'double']:
            try:
                self.value = float(value)
            except ValueError:
                logging.error("Invalid float value: {0} for parameter {1}".format(value, self.name))
        elif self.para_type.lower() in ['int', 'integer']:
            try:
                self.value = int(value)
            except ValueError:
                logging.error("Invalid int value: {0} for parameter {1}".format(value, self.name))
        elif self.para_type.lower() == 'bool' or self.para_type.lower() == 'boolean':
            if str(value).lower() in ['1', 'true', 't']:
                self.value = True
            elif str(value).lower() in ['0', 'false', 'f']:
                self.value = False
        elif self.para_type.lower() == 'region':
            try:
                self.value = value.strip("'\"")
            except ValueError:
                logging.error("Invalid region value: {0} for parameter {1}".format(value, self.name))
        elif self.para_type.lower() in ['str', 'string']:
            try:
                self.value = str(value).strip('\"\'')
            except ValueError:
                logging.error("Invalid string value: {0} for parameter {1}".format(value, self.name))
        elif self.para_type.lower() == 'choice':
            try:
                self.value = ast.literal_eval(value)
            except ValueError:
                logging.error("Invalid choice value: {0} for parameter {1}".format(value, self.name))
        elif self.para_type.lower() == 'multichoice':
            try:
                self.value = ast.literal_eval(value)
            except ValueError:
                logging.error("Invalid multichoice value: {0} for parameter {1}".format(value, self.name))
        else:
            logging.error("Cannot set the value of parameter {0}, because its type {1} cannot be recognized.".format(self.name, self.para_type))

    def getValue(self):
        return self.value

    def resetValue(self):
        # Reset the parameter value to its default value.
        # If the default value is not define, then the value is set to None
        if self.default == None:
            self.value = None
        else:
            self.setValue(self.default)


class HandlerMethodConfig(object):
    """
    A method object
    Each object represents one method of a given handler
    """
    def __init__(self, name="", handler=None, comment="", para=None, omit_para=None):
        self.name = name            # name of the method
        self.handler = handler      # which handler the method belongs to
        self.comment = comment      # comment of the method
        self.para = para            # list of method parameter config of this method
        self.omit_para = omit_para  # list of parameter names that are omitted
        self.method_reference = None # a reference to this method

        # To avoid recursive setting
        if self.para is None:
            self.para = []
        # To avoid recursive setting
        if self.omit_para is None:
            self.omit_para = []

    def __repr__(self):
        """
        Overwrite string representation function
        """
        strRepr = ""
        # Only show the atrributes we are interested in
        keyList = ['name', 'handler', 'para']
        for key in keyList:
            if key == 'para':
                strRepr = strRepr + ("{0:12}{1}\n".format("<"+key+">:", \
                        ','.join([p.name for p in getattr(self, key, [])])))
            elif key == 'handler':
                strRepr = strRepr + ("{0:12}{1}\n".format("<"+key+">:", \
                        getattr(getattr(self, key, 'NOT DEFINED'), 'name', 'NOT DEFINED')))
            else:
                strRepr = strRepr + ("{0:12}{1}\n".format("<"+key+">:", \
                        getattr(self, key, 'NOT DEFINED')))
        reprString = "\n --Handler Method <{0}> -- \n".format(self.name) + \
                    strRepr + " -- End of Handler Method <{0}> -- \n".format(self.name)
        return reprString


    def getParaByName(self, name):
        # get the parameter object with given name
        try:
            return next(p for p in self.para if p.name == name)
        except StopIteration:
            raise ValueError("Could not find parameter of name '{0}' in method '{1}'".format(name, self.name))

    def updateParaFromString(self, para_str):
        """
        update all parameter config object of this method config object with info from given string
        """
        # if the input string has parentheses around it
        para_str = para_str.strip('\(\)')

        # parse the string and set the value accordingly
        for para_name, para_value in re.findall(r'(?P<key>\w+)\s*=\s*(?P<val>"[^"]*"|\'[^\']*\'|[^,]+)', para_str):
            para_value = para_value.strip("\"\'")
            para_config = self.getParaByName(para_name)
            para_config.setValue(para_value)

    def updateParaFromDict(self, para_dict):
        """
        update all parameter config object of this method config object with info from given dictionary
        """

        for para_name, para_value in para_dict.iteritems():
            para_config = self.getParaByName(para_name)
            para_config.setValue(para_value)

    def getArgDict(self):
        """
        Prepare a dictionary {arg_name:arg_value} based on the method_config.

        return a dictionary that holds the argument name and value
        """

        return {p.name: p.getValue() for p in self.para}

    def execute(self, **extra_args):
        """
        call the reference of this method with stored parameter values
        value of extra argument can be given by extra_args
        """
        if self.method_reference is None:
            raise ValueError("No reference of method {} is set.".format(self.name))

        # Get the args we store internally
        arg_dict = self.getArgDict()

        # Add any extra args
        arg_dict.update(extra_args)

        return self.method_reference(**arg_dict)

    def fromMethod(self, method, handler_config):
        """
        Create a HandlerMethodConfig from the python method object

        method: python method object
        handler_config: instance of HandlerConfig where this HandlerMethodConfig locates
        """

        self.name = method.__name__
        self.handler = handler_config

        # parse the description of the function
        doc = inspect.getdoc(method)
        if doc is not None:
            for line in doc.split('\n'):

                # If it is an empty line, ignore it
                if re.search('^(\s*)$', line):
                    continue

                # If there is a newline at the end, remove it
                if re.search('\n$', line):
                    line = re.sub('\n$', '', line)

                # If the line defines an argument variable
                try:
                    self.para.append(MethodParameterConfig.fromString(line))
                except ValueError:
                    # If the line comments the function
                    self.comment += line + "\n"
                except SyntaxError as e:
                    raise SyntaxError("Error parsing parameter description in method {!r}: {}".format(self.name, e))

        self.comment = self.comment.strip()

        # check what Python thinks are the parameters of the method
        para_names = set(inspect.getargspec(method)[0])

        # make sure we have a description for every non-ignored parameter
        for n in para_names - self.handler.ignore_parameters:
            try:
                self.getParaByName(n)
            except ValueError:
                raise SyntaxError("Parameter {!r} of method {!r} is missing definition in method comment.".format(n, self.name))

class HandlerConfig(object):
    """
    A handler object!
    """
    def __init__(self, name="", h_type=None, shared="", methods=None, robot_type=""):
        self.name = name                # name of the handler
        self.h_type = h_type            # type of the handler e.g. motionControl or drive
        self.methods = methods          # list of method objects in this handler
        # To avoid recursive setting
        if self.methods is None:
            self.methods = []
        self.robot_type = robot_type    # type of the robot using this handler for robot specific handlers
        self.ignore_parameters = set(['self', 'initial', 'executor', 'shared_data', 'actuatorVal'])
                                        # list of name of parameter that should be ignored where parse the handler methods

    def __repr__(self):
        """
        Overwrite string presentation function
        """
        strRepr = ""
        # Only show the atrributes we are interested in
        keyList = ['name', 'h_type', 'methods', 'robot_type']
        for key in keyList:
            if key == 'methods':
                strRepr = strRepr + ("{0:13}{1}\n".format("<"+key+">:", ','.join([p.name for p in getattr(self, key, [])])))
            else:
                strRepr = strRepr + ("{0:13}{1}\n".format("<"+key+">:", getattr(self, key, 'NOT DEFINED')))
        reprString = "\n --Handler <{0}> -- \n".format(self.name) + \
                    strRepr + " -- End of Handler <{0}> -- \n".format(self.name)
        return reprString

    def getMethodByName(self, name):
        for m in self.methods:
            if m.name == name:
                return m
        logging.error("Could not find method of name '{0}' in handler '{1}'".format(name, self.name))
        raise ValueError

    def toString(self):
        """
        Return the string representation of the handler object
        """
        # prepare the input for initiation
        init_method_config = self.getMethodByName('__init__')

        method_input = []
        for para_config in init_method_config.para:
            if para_config.para_type.lower() in ['str', 'string', 'region']:
                if para_config.value is not None:
                    method_input.append('%s=%s'%(para_config.name, '\"'+para_config.value+'\"'))
            else:
                method_input.append('%s=%s'%(para_config.name, str(para_config.value)))

        # build the string starting from the type of the robot
        method_string = self.robot_type
        if self.robot_type == 'share':
            # only add the handler type if the robot type is `share`
            method_string += '.' + ht.getHandlerTypeName(self.h_type)

        method_string += ('.' + self.name + '(' + ','.join(method_input) + ')')

        return method_string

    def getType(self):
        return self.h_type

    def setType(self, h_type):
        self.h_type = h_type
        return self

    @classmethod
    def loadHandlerClass(self, handler_module_path):
        """
        load the handler class object for a given handler module
        return handlername, handlertype and the class object
        """

        # add lib to the module name if it is not there already
        if not handler_module_path.startswith('lib.'): handler_module_path = 'lib.' + handler_module_path
        handler_module_name = handler_module_path.rpartition('.')[2]
        # Try to load the handler file
        logging.debug("Inspecting handler: {}".format(handler_module_name))
        try:
            handler_module = importlib.import_module(handler_module_path)
        except Exception as e:
            logging.warning("Failed to import handler {0} : {1}".format(handler_module_name, e))
            if not isinstance(e, ImportError):
                logging.debug(traceback.format_exc())
            raise ImportError


        # Find the class object that specifies the handler
        handler_class = inspect.getmembers(handler_module, lambda c: inspect.isclass(c) and \
                                                                   c.__module__ == handler_module_path and \
                                                                   ht.Handler in inspect.getmro(c))

        # Raise error if there are no handler_class found in the handler file
        if len(handler_class) < 1:
            logging.warning("No handler class found in file {}. Abort importing.".format(handler_module_name))
            raise ImportError
        # Warn if there are multiple handler classes in one handler file
        if len(handler_class) > 1:
            logging.warning("Multiple handler classes found in file {}. Randomly choose one to import.".format(handler_module_name))
        handler_class = handler_class[0][1]
        if handler_class.__name__.lower() != handler_module_name.lower():
            logging.warning("File name: {0} mismatch with class name: {1}.".format(handler_class.__name__, handler_module_name))

        name = handler_module_name
        h_type = inspect.getmro(handler_class)[1] # direct parent

        return name, h_type, handler_class

    def loadHandlerMethod(self, handler_module_path, onlyLoadInit=False):
        """
        Load method info (name, arg...) in the given handler file
        If onlyLoadInit is True, only the info of __init__ method will be loaded
        If over_write_h_type is given, then over write the handler type with it
        """
        # load the handler class first
        name, h_type, handler_class = self.loadHandlerClass(handler_module_path)

        # update the handler name and type info
        # handler name is the name of the file
        # handler type is the corresponding handler object defined in handlerTemplates.py
        self.name = name
        self.h_type = h_type

        # get all methods in this handler
        handler_methods = inspect.getmembers(handler_class, inspect.ismethod)

        # parse each method into method object
        for method_name, method in handler_methods:
            # only parse the method not start with underscore (exclude __inti__)
            # only parse the __init__ method if required
            if ((not onlyLoadInit and (not str(method_name).startswith('_')) or str(method_name)=='__init__') ):
                method_config = HandlerMethodConfig(name=method_name)
                try:
                    method_config.fromMethod(method, self)
                except SyntaxError as e:
                    raise ht.LoadingError("Error while inspecting method {!r} of handler {!r}: {}".format(method_name, handler_module_path, e))

                # add this method into the method list of the handler
                self.methods.append(method_config)

class RobotConfig(object):
    """
    A Robot config object
    """
    def __init__(self, r_name = "", r_type = "", handlers = None):
        self.name = r_name              # name of the robot
        self.r_type = r_type            # type of the robot
        self.handlers = handlers        # dictionary of handler object for this robot
        # To avoid recursive setting
        if self.handlers is None:
            self.handlers = {}
        self.calibration_matrix = None  # 3x3 matrix for converting coordinates, stored as lab->map
        self.successfully_loaded = ""   # a string either empty or " (Not successfully loaded)"

    def __repr__(self):
        """
        Overwrite string representation function
        """
        strRepr = ""
        # Only show the atrributes we are interested in
        keyList = ['name', 'r_type', 'handlers']
        for key in keyList:
            if key == 'handlers':
                handler_configs = getattr(self, key, {})
                temp_str_list = []
                for h_type in handler_configs.keys():
                    temp_str_list.append("{0:13}{1:23}{2}".format('', ht.getHandlerTypeName(h_type) + ':', \
                                                             handler_configs[h_type].name))
                strRepr = strRepr + ("{0}{1}\n".format("<"+key+">:\n", '\n'.join(temp_str_list)))
            else:
                strRepr = strRepr + ("{0:13}{1}\n".format("<"+key+">:", getattr(self, key, 'NOT DEFINED')))
        reprString = "\n --Robot <{0}> -- \n".format(self.name) + \
                    strRepr + " -- End of Robot <{0}> -- \n".format(self.name)
        return reprString

    def getHandlerByName(self, name):
        """
        Returns the handler config of the give name.
        """
        for handler_type_class, handler_config in self.handlers.iteritems():
            if handler_config.name == name:
                return handler_config

        logging.error("Cannot find handler {!r} for robot {!r}.".format(name, self.name))
        return None

    def getHandlerOfRobot(self, h_type):
        """Get the handler config object of this robot specified by h_type
        h_type is the handler class object specified in lib/handlers/handlerTemplates.py"""

        if h_type in self.handlers.keys():
            return self.handlers[h_type]
        # if cannot find the specified handler, then return None
        logging.debug('Cannot find the specified handler type {!r} in robot {!r}({}).'\
                .format(h_type, self.name, self.r_type))
        return None

    def getCoordMaps(self):
        """
        Returns forward (map->lab) and reverse (lab->map) coordinate mapping functions, in that order
        """

        if self.calibration_matrix is None:
            logging.warning("Robot {} has no calibration data.  Using identity matrix.".format(self.name))
            T = eye(3)
        else:
            T = self.calibration_matrix

        # Check for singular matrix
        if abs(linalg.det(T)) < finfo(float).eps:
            logging.warning("Singular calibration matrix.  Ignoring, and using identity matrix.")
            T = eye(3)

        #### Create the coordmap functions
        coordmap_map2lab = lambda pt: (linalg.inv(T) * mat([pt[0], pt[1], 1]).T).T.tolist()[0][0:2]
        coordmap_lab2map = lambda pt: (T * mat([pt[0], pt[1], 1]).T).T.tolist()[0][0:2]

        return coordmap_map2lab, coordmap_lab2map

    def _setSuccess(self, success = False):
        """
        Set whether if this robot is successfully loaded or not
        """
        if success:
            self.successfully_loaded = ""
        else:
            self.successfully_loaded = " (Not successfully loaded)"

    def fromFile(self, file_path, hsub = None):
        """
        Given a robot file, load the robot info in it
        The file_path needs to be the path starting from lib/
        """

        logging.debug("Loading robot file {!r}".format(os.path.basename(file_path).split('.')[0]))
        try:
            # try to load the robot file
            robot_data = fileMethods.readFromFile(file_path)
        except IOError:
            ht.LoadingError("Cannot load the information")
            self._setSuccess()
        else:
            # now load the robot config from the dictionary data
            self.fromData(robot_data, hsub)

    def fromData(self, robot_data, hsub = None):
        """
        Given a dictionary of robot handler information, returns a robot object holding all the information
        The dictionary is in the format returned by the readFromFile function
        If the necessary handler of the robot is not specified or can't be loaded, return None
        """
        # make sure we have an instance of handlerSubsystem
        if hsub is None:
            raise TypeError("Need an instance of handlerSubsystem to parse robot data")

        # update robot name and type
        try:
            self.name = robot_data['RobotName'][0]
        except (KeyError, IndexError):
            raise ht.LoadingError("Cannot find robot name")
            self._setSuccess()

        try:
            self.r_type = robot_data['Type'][0]
        except (KeyError, IndexError):
            raise ht.LoadingError("Cannot find robot type")
            self._setSuccess()

        # update robot calibration matrix
        try:
            mat_str = ''.join(robot_data['CalibrationMatrix'])
            if mat_str.strip() == "": raise KeyError()
        except KeyError:
            # Some robot does not have calibration matrix
            pass
        else:
            try:
                # Convert the string form array to array. Trying not to use eval for security problem
                mat_str = mat_str.replace("array(", "")
                mat_str = mat_str.replace(")", "")
                self.calibration_matrix = array(ast.literal_eval(mat_str))
                if mat_str == "None" or mat_str == "": self.calibration_matrix = array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
            except SyntaxError:
                raise ht.LoadingError("Invalid calibration data found for robot {0}({1})".format(self.name, self.r_type))
                self._setSuccess()

        # load handler configs
        for key, val in robot_data.iteritems():
            if key.endswith('Handler'):
                # find which type of the handler
                try:
                    handler_type = ht.getHandlerTypeClass(key)
                except KeyError:
                    logging.warning('Cannot recognize handler type {!r} for robot {}({})'.format(key, self.name, self.r_type))
                    self._setSuccess()
                    continue

                # use regex to help us parse the string
                handler_re = re.compile(r"(?P<robot>\w+)\.((?P<h_type>\w+)\.)?(?P<h_name>\w+)\((?P<args>[^\)]*)\)")

                for handler_config_str in val:
                    result = handler_re.match(handler_config_str)
                    if result:
                        # this is a valid handler config description

                        # since the robot part of the handler description can be either a robot type or name
                        # set the robot type of the handler to be this robot type if the robot name matches
                        robot_type = self.r_type if result.group('robot') == self.name else result.group('robot')
                        if (robot_type != 'share') and (robot_type.lower() != self.r_type.lower()):
                            # this is a handler for a wrong robot
                            logging.warning('The handler config description: \n \t {!r} \n \
                                            is for robot {}, but is located in data for robot {}({})' \
                                            .format(handler_config_str, robot_type, self.name, self.r_type))
                            continue

                        # if the description also specifies the handler type in it
                        # we need to make sure it matches with the handler type we get from section name
                        if result.group('h_type'):
                            # get the handler type as class object
                            try:
                                handler_type_from_str = ht.getHandlerTypeClass(result.group('h_type'))
                            except KeyError:
                                logging.warning('Cannot recognize handler type {!r} in config description: \n \t {!r} \n \
                                                for robot {}({})'.format(result.group('h_type'), handler_config_str, self.name, self.r_type))
                                self._setSuccess()
                                continue
                            if handler_type_from_str != handler_type:
                                # the handler type from the description does not match the one from section name
                                logging.warning('Misplaced handler description: \n \t {!r} \n \
                                                in handler type {!r} for robot {}({})' \
                                                .format(result.group(handler_config_str, handler_type, self.name, self.r_type)))
                                # we still want to put this handler config into the right type
                                handler_type = handler_type_from_str
                        elif robot_type == 'share':
                            # This is a shared handler but no handler type information is given
                            logging.warning('Handler type info missing for {!r} handler in config description: \n \t {!r} \n \
                                            for robot {}({})'.format(robot_type, handler_config_str, self.name, self.r_type))
                            self._setSuccess()
                            continue

                        handler_name = result.group('h_name')
                        # now let's get the handler config object based on the info we have got

                        handler_config = hsub.getHandlerConfigDefault(robot_type, handler_type, handler_name)

                        # if it is successfully fetched, we save it at the corresponding handler type of this robot
                        if handler_config is None:
                            self._setSuccess()
                            continue

                        # TODO: is it necessary to check if self.handlers is a dict
                        if not isinstance(self.handlers, dict): self.handlers = {}

                        # load all parameter values and overwrite the ones in the __init__ method of default handler config object
                        try:
                            init_method_config = handler_config.getMethodByName('__init__')
                        except ValueError:
                            logging.warning('Cannot update default parameters of default handler config {!r}'.format(handler_config.name))
                        else:
                            init_method_config.updateParaFromString(result.group('args'))

                        # save it into the dictionary
                        if handler_type not in self.handlers.keys():
                            # This type of handler has not been loaded yet
                            self.handlers[handler_type] = handler_config
                        else:
                            # This type of handler has been loaded, for now, we will NOT overwrite it with new entry
                            # A warning will be shown
                            logging.warning('Multiple handler configs are detected for handler type {!r} of robot {}({}). \
                                    Will only load the first one.'.format(key, self.name, self.r_type))
                            break
                    else:
                        logging.warning('Cannot recognize handler config description: \n \t {!r} \n \
                                        for handler type {!r} of robot {}({})'.format(handler_config_str, key, self.name, self.r_type))
                        self._setSuccess()
                        continue

class ExperimentConfig(object):
    """
    A config file object!
    """
    def __init__(self, name="", robots = None, prop_mapping = {}, initial_truths = None , main_robot = "", region_tags = {}, file_name = ""):
        self.name = name                    # name of the config file
        self.robots = robots                # list of robot object used in this config file
        self.prop_mapping = prop_mapping    # dictionary for storing the propositions mapping
        self.initial_truths = initial_truths# list of initially true propoisitions
        self.main_robot = main_robot        # name of robot for moving in this config
        self.region_tags = region_tags      # dictionary mapping tag names to region groups, for quantification
        self.file_name = file_name          # full path filename of the config

        # To avoid recursive setting
        if self.robots is None:
            self.robots = []
        # To avoid recursive setting
        if self.initial_truths is None:
            self.initial_truths = []

    def __repr__(self):
        """
        Overwrite string representation function
        """
        strRepr = ""
        # Only show the atrributes we are interested in
        keyList = ['name', 'robots', 'main_robot', 'initial_truths', 'prop_mapping', 'file_name']
        for key in keyList:
            if key in ['robots', 'initial_truths']:
                strRepr = strRepr + ("{0:18}{1}\n".format("<"+key+">:", ','.join([getattr(p, 'name', p) for p in getattr(self, key, [])])))
            elif key == 'prop_mapping':
                prop_mapping = getattr(self, key, {})
                strRepr = strRepr + "{0}{1}\n".format("<"+key+">:\n", \
                '\n'.join(["{0:18}{1}".format('', prop+' = ' + prop_mapping[prop]) for prop in prop_mapping.keys()]))
            else:
                strRepr = strRepr + ("{0:18}{1}\n".format("<"+key+">:", getattr(self, key, 'NOT DEFINED')))
        reprString = "\n --Config <{0}> -- \n".format(self.name) + \
                    strRepr + " -- End of Config <{0}> -- \n".format(self.name)
        return reprString
        strRepr = []
        # Get all attribute names and values
        for key, val in self.__dict__.iteritems():
            # only show if the value is not none or empty
            if val: strRepr.append("{0}:{1}".format(key, val))
        # if all attributes have values of None or empty
        if not strRepr:
            reprString = "All attributes have values of None or empty."
        else:
            reprString = "\n".join(strRepr)
        return "Config Object -- \n" + reprString + "\n"

    def getRobotByName(self,  name):
        for r in self.robots:
            if r.name == name:
                return r
        logging.error("Could not find robot of name '{0}' in config '{1}'.".format(name, self.name))
        return None

    def fromFile(self, file_path, hsub = None):
        """
        Given an experiment config file, load the info
        """

        # Add extension to the name if there isn't one.
        if not file_path.endswith('.config'):
            file_path = file_path + '.config'

        logging.debug("Loading config file: {!r}".format(os.path.basename(file_path).split('.')[0]))
        try:
            # try to load the config file
            config_data = fileMethods.readFromFile(file_path)
        except IOError:
            ht.LoadingError("Cannot load the information")
        else:
            # now load the robot config from the dictionary data
            self.fromData(config_data, hsub)
            # update the file_path
            self.file_name = file_path

    def fromData(self, config_data, hsub = None):
        """
        Given a dictionary of experiment config information, returns an ExperimentConfig object holding all the information
        The dictionary is in the format returned by the readFromFile function
        """
        # make sure we have an instance of handlerSubsystem
        if hsub is None:
            raise TypeError("Need an instance of handlerSubsystem to parse experiment config data")
        try:
            self.name = config_data['General Config']['Name'][0]
        except (KeyError, IndexError):
            raise ht.LoadingError("Missing general config information")

        # parse the string for sensor and actuator prop mapping
        for prop_type in ['sensor', 'actuator']:
            if prop_type.title() + '_Proposition_Mapping' in config_data['General Config']:
                for mapping in config_data['General Config'][prop_type.title() + '_Proposition_Mapping']:
                    try:
                        prop, func = [s.strip() for s in mapping.split('=', 1)]
                    except IOError:
                        raise ht.LoadingError("Wrong {} mapping -- {!r}".format(prop_type, mapping))
                    else:
                        self.prop_mapping[prop] = func
            else:
                raise ht.LoadingError("Cannot find {} proposition mapping".format(prop_type))

        if 'Initial_Truths' in config_data['General Config']:
            # parse the initially true propositions
            for prop_name in config_data['General Config']['Initial_Truths']:
                self.initial_truths.append(prop_name)
        else:
            raise ht.LoadingError("Cannot find initial truth proposition")

        if 'Region_Tags' in config_data['General Config']:
            # parse the region tags
            try:
                self.region_tags = json.loads("".join(config_data['General Config']['Region_Tags']))
            except ValueError:
                logging.warning("Wrong region tags")

        # Load main robot name
        try:
            self.main_robot = config_data['General Config']['Main_Robot'][0]
        except (IndexError, KeyError):
            logging.warning("Cannot find main robot name in config file {}".format(self.file_name))

        # load robot configs
        robot_data = []
        for config_key, config_value in config_data.iteritems():
            if config_key.startswith('Robot'):
                robot_data.append(config_value)

        if robot_data == []:
            logging.warning("Missing robot data in config file {}".format(self.file_name))
        else:
            # using the parsing function to parse the data
            for data in robot_data:
                robot_config = RobotConfig()
                try:
                    robot_config.fromData(data, hsub)
                except ht.LoadingError, msg:
                    logging.warning(str(msg) + ' in robot data .')
                    continue
                except TypeError:
                    # missing hsub
                    continue
                else:
                    self.robots.append(robot_config)

        # Missing main robot.
        # if the main robot for this config cannot be loaded, raise an error
        if self.main_robot not in [r.name for r in self.robots]:
            ht.LoadingError("Missing main robot config object")

    def saveConfig(self):
        """
        Save the config object.
        Return True for successfully saved, False for not
        """
        # TODO: check if the config is complete

        # the file name is default to be the config name with underscore
        if self.name == "":
            self.name = 'Untitled configuration'
        file_name = self.name.replace(' ', '_')

        # Add extension to the name
        file_name = file_name+'.config'

        # Add the path to the file name
        file_name = os.path.join(os.path.dirname(self.file_name), file_name)
        self.file_name = file_name

        data = {'General Config':{'Name':self.name}}

        # proposition mapping
        sensorMappingList = []
        actuatorMappingList = []
        for prop, fun in self.prop_mapping.iteritems():
            if 'sensor' in fun.lower():
                sensorMapping = prop + ' = ' + fun
                sensorMappingList.append(sensorMapping)
            elif 'actuator' in fun.lower():
                actuatorMapping = prop + ' = ' + fun
                actuatorMappingList.append(actuatorMapping)
            else:
                logging.warning("Cannot recognize prop mapping: {}".format(prop+" = "+fun))

        data['General Config']['Sensor_Proposition_Mapping'] = sensorMappingList
        data['General Config']['Actuator_Proposition_Mapping'] = actuatorMappingList
        data['General Config']['Main_Robot'] = self.main_robot
        data['General Config']['Initial_Truths'] = self.initial_truths
        data['General Config']['Region_Tags'] = json.dumps(self.region_tags)

        for i, robot in enumerate(self.robots):
            header = 'Robot'+str(i+1)+' Config'
            data[header] = {}
            data[header]['RobotName'] = robot.name
            data[header]['Type'] = robot.r_type

            data[header]['CalibrationMatrix'] = repr(robot.calibration_matrix)
            # TODO: change to string function
            try:
                for handler_type_name in  ht.getAllHandlerTypeName(short_name = False):
                    handler_type_class = ht.getHandlerTypeClass(handler_type_name)
                    if handler_type_class in robot.handlers.keys():
                        data[header][handler_type_name] = robot.handlers[handler_type_class].toString()
            except AttributeError:
                logging.warning("Cannot save handlers for robot {}({}). Please make sure they are all successfully loaded. Aborting saving."\
                        .format(robot.name, robot.r_type))
                return False


        comments = {"FILE_HEADER": "This is a configuration definition file in folder \"%s\".\n" % os.path.dirname(self.file_name)+
                    "Format details are described at the beginning of each section below.\n",
                    "PoseHandler": "Input value for robot pose handler, refer to file inside the handlers/pose folder",
                    "DriveHandler": "Input value for robot drive handler, refer to file inside the handlers/drive folder",
                    "MotionControlHandler": "Input value for robot motion control handler, refer to file inside the handlers/motionControl folder",
                    "LocomotionCommandHandler": "Input value for robot locomotion command handler, refer to file inside the handlers/robots/Type folder",
                    "InitHandler": "Input value for robot init handler, refer to the init file inside the handlers/robots/Type folder",
                    "SensorHandler": "Sensor handler file in robots/Type folder",
                    "ActuatorHandler": "Actuator handler file in robots/Type folder",
                    "RobotName": "Robot Name",
                    "Type": "Robot type",
                    "CalibrationMatrix": "3x3 matrix for converting coordinates, stored as lab->map",
                    "Actuator_Proposition_Mapping": 'Mapping between actuator propositions and actuator handler functions',
                    "Sensor_Proposition_Mapping": "Mapping between sensor propositions and sensor handler functions",
                    "Name": 'Configuration name',
                    "Main_Robot":'The name of the robot used for moving in this config',
                    "Initial_Truths": "Initially true propositions",
                    "Region_Tags": "Mapping from tag names to region groups, for quantification"}

        fileMethods.writeToFile(file_name, data, comments)
        return True

if __name__ == '__main__':
    """ # For testing parsing handler
    m = HandlerConfig()
    try:
        m.parseHandler('handlers.basicSim.basicSimLocomotionCommand')
    except ImportError:
        logging.warning('Cannot import file {}'.format('init'))
    print m
    for method in m.methods:
        print method
    """
    robot_config = RobotConfig()
    try:
        robot_config.fromData({'RobotName':['jim'], 'Type':['jimtype'], 'CalibrationMatrix':'[1, 2, 3]'})
    except ht.LoadingError, msg:
        print msg
