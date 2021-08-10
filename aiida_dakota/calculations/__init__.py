# -*- coding: utf-8 -*-
"""Base `CalcJob` for implementations for dakota of Dakota."""
import abc
import os
import copy
import numbers
import warnings
from functools import partial
from types import MappingProxyType

from aiida import orm
from aiida.common import datastructures, exceptions
from aiida.common.lang import classproperty
from aiida.common.warnings import AiidaDeprecationWarning
from aiida.plugins import DataFactory

from aiida_dakota.utils.convert import convert_input_to_namelist_entry
from .base import CalcJob
from .helpers import DAKOTAInputValidationError

class BaseStudyInputGenerator(CalcJob):
    """Base `CalcJob` for implementations for dakota of Dakota."""

    _DEFAULT_INPUT_FILE = 'aiida.in'
    _DEFAULT_OUTPUT_FILE = 'aiida.out'
    _ENVIRON_INPUT_FILE_NAME = 'environ.in'

    # A mapping {flag_name: help_string} of parallelization flags
    # possible in DAKOTA codes. The flags that are actually implemented in a
    # given code should be specified in the '_ENABLED_PARALLELIZATION_FLAGS'
    # tuple of each calculation subclass.
    _PARALLELIZATION_FLAGS = MappingProxyType(
        dict(
            nimage="The number of 'images', each corresponding to a different self-consistent or "
            'linear-response calculation.',
            npool="The number of 'pools', each taking care of a group of k-points.",
            nband="The number of 'band groups', each taking care of a group of Kohn-Sham orbitals.",
            ntg="The number of 'task groups' across which the FFT planes are distributed.",
            ndiag="The number of 'linear algebra groups' used when parallelizing the subspace "
            'diagonalization / iterative orthonormalization. By default, no parameter is '
            'passed to Dakota, meaning it will use its default.',
            nhw="The 'nmany' FFT bands parallelization option."
        )
    )

    _ENABLED_PARALLELIZATION_FLAGS = tuple()

    _PARALLELIZATION_FLAG_ALIASES = MappingProxyType(
        dict(
            nimage=('ni', 'nimages', 'npot'),
            npool=('nk', 'npools'),
            nband=('nb', 'nbgrp', 'nband_group'),
            ntg=('nt', 'ntask_groups', 'nyfft'),
            ndiag=('northo', 'nd', 'nproc_diag', 'nproc_ortho'),
            nhw=('nh', 'n_howmany', 'howmany')
        )
    )

    # Additional files that should always be retrieved for the specific plugin
    _internal_retrieve_list = []

    # Name lists to print by calculation type
    _automatic_namelists = {}

    # Blocked keywords that are to be specified in the subclass
    _blocked_keywords = {}

    # In restarts, will not copy but use symlinks
    _default_symlink_usage = True

    # In restarts, it will copy from the parent the following
    #_restart_copy_from = os.path.join(_OUTPUT_SUBFOLDER, '*')

    # In restarts, it will copy the previous folder in the following one
    #_restart_copy_to = _OUTPUT_SUBFOLDER

    # Default verbosity; change in subclasses
    _default_verbosity = 'high'

    """
    @classproperty
    def xml_filenames(cls):
        #Return a list of XML output filenames that can be written by a calculation.

        #Note that this includes all potential filenames across all known versions of Dakota
        
        # pylint: disable=no-self-argument
        return [cls._DATAFILE_XML_POST_6_2, cls._DATAFILE_XML_PRE_6_2]
    """

    @abc.abstractmethod
    @classproperty
    def xml_filepaths(cls):  # pylint: disable=no-self-argument
        """Return a list of XML output filepaths relative to the remote working directory that should be retrieved."""

    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        # yapf: disable
        super().define(spec)
        spec.input('metadata.options.input_filename', valid_type=str, default=cls._DEFAULT_INPUT_FILE)
        spec.input('metadata.options.output_filename', valid_type=str, default=cls._DEFAULT_OUTPUT_FILE)
        spec.input('metadata.options.withmpi', valid_type=bool, default=True)  # Override default withmpi=False
        spec.input('parameters', valid_type=orm.Dict,
            help='The input parameters that are to be used to construct the input file.')
        spec.input('settings', valid_type=orm.Dict, required=False,
            help='Optional parameters to affect the way the calculation job and the parsing are performed.')
        spec.input('parent_folder', valid_type=orm.RemoteData, required=False,
            help='An optional working directory of a previously completed calculation to restart from.')
        # yapf: enable
        spec.input(
            'parallelization',
            valid_type=orm.Dict,
            required=False,
            help=(
                'Parallelization options. The following flags are allowed:\n' + '\n'.join(
                    f'{flag_name:<7}: {cls._PARALLELIZATION_FLAGS[flag_name]}'
                    for flag_name in cls._ENABLED_PARALLELIZATION_FLAGS
                )
            ),
            validator=cls._validate_parallelization
        )

    @classmethod
    def _validate_parallelization(cls, value, port_namespace):  # pylint: disable=unused-argument
        if value:
            value_dict = value.get_dict()
            unknown_flags = set(value_dict.keys()) - set(cls._ENABLED_PARALLELIZATION_FLAGS)
            if unknown_flags:
                return (
                    f"Unknown flags in 'parallelization': {unknown_flags}, "
                    f'allowed flags are {cls._ENABLED_PARALLELIZATION_FLAGS}.'
                )
            invalid_values = [val for val in value_dict.values() if not isinstance(val, numbers.Integral)]
            if invalid_values:
                return f'Parallelization values must be integers; got invalid values {invalid_values}.'

    def prepare_for_submission(self, folder):
        """Create the input files from the input nodes passed to this instance of the `CalcJob`.

        :param folder: an `aiida.common.folders.Folder` to temporarily write files on disk
        :return: `aiida.common.datastructures.CalcInfo` instance
        """
        # pylint: disable=too-many-branches,too-many-statements
        if 'settings' in self.inputs:
            #settings = _uppercase_dict(self.inputs.settings.get_dict(), dict_name='settings')
            settings =self.inputs.settings.get_dict()
        else:
            settings = {}

        local_copy_list = []
        remote_copy_list = []
        remote_symlink_list = []

        # Create the subfolder for the output data (sometimes Dakota codes crash if the folder does not exist)
        #folder.get_subfolder(self._OUTPUT_SUBFOLDER, create=True)

        arguments = [
            self.inputs.parameters,
            settings,
        ]

        input_filecontent = self._generate_STUDYinputdata(*arguments)

        with folder.open(self.metadata.options.input_filename, 'w') as handle:
            handle.write(input_filecontent)

        # operations for restart
        symlink = settings.pop('PARENT_FOLDER_SYMLINK', self._default_symlink_usage)  # a boolean
        if symlink:
            if 'parent_folder' in self.inputs:
                # I put the symlink to the old parent ./out folder
                remote_symlink_list.append((
                    self.inputs.parent_folder.computer.uuid,
                    os.path.join(self.inputs.parent_folder.get_remote_path(),
                                 self._restart_copy_from), self._restart_copy_to
                ))
        else:
            # copy remote output dir, if specified
            if 'parent_folder' in self.inputs:
                remote_copy_list.append((
                    self.inputs.parent_folder.computer.uuid,
                    os.path.join(self.inputs.parent_folder.get_remote_path(),
                                 self._restart_copy_from), self._restart_copy_to
                ))

        # Create an `.EXIT` file if `only_initialization` flag in `settings` is set to `True`
        if settings.pop('ONLY_INITIALIZATION', False):
            with folder.open(f'{self._PREFIX}.EXIT', 'w') as handle:
                handle.write('\n')



        calcinfo = datastructures.CalcInfo()

        calcinfo.uuid = str(self.uuid)
        # Start from an empty command line by default
        cmdline_params = self._add_parallelization_flags_to_cmdline_params(cmdline_params=settings.pop('CMDLINE', []))

        # we commented calcinfo.stin_name and added it here in cmdline_params
        # in this way the mpirun ... dakota ... < aiida.in
        # is replaced by mpirun ... dakota ... -in aiida.in
        # in the scheduler, _get_run_line, if cmdline_params is empty, it
        # simply uses < calcinfo.stin_name
        codeinfo = datastructures.CodeInfo()
        codeinfo.cmdline_params = (list(cmdline_params) + ['-in', self.metadata.options.input_filename])
        codeinfo.stdout_name = self.metadata.options.output_filename
        codeinfo.code_uuid = self.inputs.code.uuid
        calcinfo.codes_info = [codeinfo]

        calcinfo.local_copy_list = local_copy_list
        calcinfo.remote_copy_list = remote_copy_list
        calcinfo.remote_symlink_list = remote_symlink_list

        # Retrieve by default the output file and the xml file
        calcinfo.retrieve_list = []
        calcinfo.retrieve_list.append(self.metadata.options.output_filename)
        #calcinfo.retrieve_list.extend(self.xml_filepaths)
        calcinfo.retrieve_list += settings.pop('ADDITIONAL_RETRIEVE_LIST', [])
        calcinfo.retrieve_list += self._internal_retrieve_list

        # We might still have parser options in the settings dictionary: pop them.
        _pop_parser_options(self, settings)

        if settings:
            unknown_keys = ', '.join(list(settings.keys()))
            raise exceptions.InputValidationError(f'`settings` contained unexpected keys: {unknown_keys}')

        return calcinfo

    def _add_parallelization_flags_to_cmdline_params(self, cmdline_params):
        """Get the command line parameters with added parallelization flags.

        Adds the parallelization flags to the given `cmdline_params` and
        returns the updated list.

        Raises an `InputValidationError` if multiple aliases to the same
        flag are given in `cmdline_params`, or the same flag is given
        both in `cmdline_params` and the explicit `parallelization`
        input.
        """
        cmdline_params_res = copy.deepcopy(cmdline_params)
        # The `cmdline_params_normalized` are used only here to check
        # for existing parallelization flags.
        cmdline_params_normalized = []
        for param in cmdline_params:
            cmdline_params_normalized.extend(param.split())

        if 'parallelization' in self.inputs:
            parallelization_dict = self.inputs.parallelization.get_dict()
        else:
            parallelization_dict = {}
        # To make the order of flags consistent and "nice", we use the
        # ordering from the flag definition.
        for flag_name in self._ENABLED_PARALLELIZATION_FLAGS:
            all_aliases = list(self._PARALLELIZATION_FLAG_ALIASES[flag_name]) + [flag_name]
            aliases_in_cmdline = [alias for alias in all_aliases if f'-{alias}' in cmdline_params_normalized]
            if aliases_in_cmdline:
                if len(aliases_in_cmdline) > 1:
                    raise exceptions.InputValidationError(
                        f'Conflicting parallelization flags {aliases_in_cmdline} '
                        "in settings['CMDLINE']"
                    )
                if flag_name in parallelization_dict:
                    raise exceptions.InputValidationError(
                        f"Parallelization flag '{aliases_in_cmdline[0]}' specified in settings['CMDLINE'] conflicts "
                        f"with '{flag_name}' in the 'parallelization' input."
                    )
                else:
                    warnings.warn(
                        "Specifying the parallelization flags through settings['CMDLINE'] is "
                        "deprecated, use the 'parallelization' input instead.", AiidaDeprecationWarning
                    )
                    continue
            if flag_name in parallelization_dict:
                flag_value = parallelization_dict[flag_name]
                cmdline_params_res += [f'-{flag_name}', str(flag_value)]
        return cmdline_params_res

    @staticmethod
    def _generate_STUDY_input_tail(*args, **kwargs):
        """Generate tail of input file.

        By default, nothing specific is generated.
        This method can be implemented again in derived classes, and it will be called by _generate_STUDYinputdata
        """
        # pylint: disable=unused-argument,invalid-name
        return ''

    @classmethod
    def _generate_STUDYinputdata(cls, parameters, settings, use_fractional=False):  # pylint: disable=invalid-name
        """Create the input file in string format for a dakota calculation for the given inputs."""
        # pylint: disable=too-many-branches,too-many-statements
        from aiida.common.utils import get_unique_filename
        import re


        # I put the first-level keys as uppercase (i.e., namelist and card names)
        # and the second-level keys as lowercase
        # (deeper levels are unchanged)
        #input_params = _uppercase_dict(parameters.get_dict(), dict_name='parameters')
        input_params = parameters.get_dict()
        #input_params = {k: _lowercase_dict(v, dict_name=k) for k, v in input_params.items()}

        # I remove unwanted elements (for the moment, instead, I stop; to change when we setup a reasonable logging)
        for blocked in cls._blocked_keywords:
            namelist = blocked[0].upper()
            flag = blocked[1].lower()
            defaultvalue = None
            if len(blocked) >= 3:
                defaultvalue = blocked[2]
            if namelist in input_params:
                # The following lines is meant to avoid putting in input the
                # parameters like celldm(*)
                stripped_inparams = [re.sub('[(0-9)]', '', _) for _ in input_params[namelist].keys()]
                if flag in stripped_inparams:
                    raise exceptions.InputValidationError(
                        "You cannot specify explicitly the '{}' flag in the '{}' "
                        'namelist or card.'.format(flag, namelist)
                    )
                if defaultvalue is not None:
                    if namelist not in input_params:
                        input_params[namelist] = {}
                    input_params[namelist][flag] = defaultvalue

        # Set some variables (look out at the case! NAMELISTS should be uppercase,
        # internal flag names must be lowercase)
        #input_params.setdefault('CONTROL', {})
        #input_params['CONTROL']['pseudo_dir'] = cls._PSEUDO_SUBFOLDER

        
        # ============ I prepare the input site data =============

        # =================== NAMELISTS AND CARDS ========================
        try:
            namelists_toprint = settings.pop('NAMELISTS')
            if not isinstance(namelists_toprint, list):
                raise exceptions.InputValidationError(
                    "The 'NAMELISTS' value, if specified in the settings input "
                    'node, must be a list of strings'
                )
        except KeyError:  # list of namelists not specified; do automatic detection
            """
            try:
                control_nl = input_params['CONTROL']
                calculation_type = control_nl['calculation']
            except KeyError as exception:
                raise exceptions.InputValidationError(
                    "No 'calculation' in CONTROL namelist."
                    'It is required for automatic detection of the valid list '
                    'of namelists. Otherwise, specify the list of namelists '
                    "using the NAMELISTS key inside the 'settings' input node."
                ) from exception
            """
            calculation_type = 'default'
            try:
                namelists_toprint = cls._automatic_namelists[calculation_type]
            except KeyError as exception:
                raise exceptions.InputValidationError(
                    "Unknown 'calculation' value in "
                    'CONTROL namelist {}. Otherwise, specify the list of '
                    "namelists using the NAMELISTS inside the 'settings' input "
                    'node'.format(calculation_type)
                ) from exception

        inputfile = ''
        for namelist_name in namelists_toprint:
            inputfile += f'{namelist_name}\n'
            # namelist content; set to {} if not present, so that we leave an empty namelist
            namelist = input_params.pop(namelist_name, {})
            for key, value in sorted(namelist.items()):
                inputfile += convert_input_to_namelist_entry(key, value)
            inputfile += '\n'


        # Generate additional cards bases on input parameters and settings that are subclass specific
        tail = cls._generate_STUDY_input_tail(input_params=input_params, settings=settings)
        if tail:
            inputfile += f'\n{tail}'

        if input_params:
            raise exceptions.InputValidationError(
                'The following namelists are specified in input_params, but are '
                'not valid namelists for the current type of calculation: '
                '{}'.format(','.join(list(input_params.keys())))
            )

        return inputfile

    @staticmethod
    def _if_pos(fixed):
        """Return 0 if fixed is True, 1 otherwise.

        Useful to convert from the boolean value of fixed_coords to the value required by Quantum Espresso as if_pos.
        """
        if fixed:
            return 0

        return 1


def _lowercase_dict(dictionary, dict_name):
    return _case_transform_dict(dictionary, dict_name, '_lowercase_dict', str.lower)


def _uppercase_dict(dictionary, dict_name):
    return _case_transform_dict(dictionary, dict_name, '_uppercase_dict', str.upper)


def _case_transform_dict(dictionary, dict_name, func_name, transform):
    from collections import Counter

    if not isinstance(dictionary, dict):
        raise TypeError(f'{func_name} accepts only dictionaries as argument, got {type(dictionary)}')
    new_dict = dict((transform(str(k)), v) for k, v in dictionary.items())
    if len(new_dict) != len(dictionary):
        num_items = Counter(transform(str(k)) for k in dictionary.keys())
        double_keys = ','.join([k for k, v in num_items if v > 1])
        raise exceptions.InputValidationError(
            "Inside the dictionary '{}' there are the following keys that "
            'are repeated more than once when compared case-insensitively: {}.'
            'This is not allowed.'.format(dict_name, double_keys)
        )
    return new_dict


def _pop_parser_options(calc_job_instance, settings_dict, ignore_errors=True):
    """Delete any parser options from the settings dictionary.

    The parser options key is found via the get_parser_settings_key() method of the parser class specified as a metadata
    input.
    """
    from aiida.plugins import ParserFactory
    from aiida.common import EntryPointError
    try:
        parser_name = calc_job_instance.inputs['metadata']['options']['parser_name']
        parser_class = ParserFactory(parser_name)
        parser_opts_key = parser_class.get_parser_settings_key().upper()
        return settings_dict.pop(parser_opts_key, None)
    except (KeyError, EntryPointError, AttributeError) as exc:
        # KeyError: input 'metadata.options.parser_name' is not defined;
        # EntryPointError: there was an error loading the parser class form its entry point
        #   (this will probably cause errors elsewhere too);
        # AttributeError: the parser class doesn't have a method get_parser_settings_key().
        if ignore_errors:
            pass
        else:
            raise exc
