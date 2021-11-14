# -*- coding: utf-8 -*-
"""`CalcJob` implementation for the mpet code of Mpet."""
import os

from aiida import orm
from aiida.common.lang import classproperty
from aiida.plugins import factories

from aiida_mpet.calculations import BaseMpetrunInputGenerator


class MpetrunCalculation(BaseMpetrunInputGenerator):
    """`CalcJob` implementation for the mpet code of Mpet."""

    _automatic_namelists = {
        'default': ['Sim Params', 'Electrodes', 'Particles', 'Conductivity', 'Geometry', 'Electrolyte', 'Material', 'Reactions']
    }

    # Keywords that cannot be set by the user but will be set by the plugin
    _blocked_keywords = [
        #('CONTROL', 'pseudo_dir'),
    ]

    # Not using symlink in mpetrun to allow multiple nscf to run on top of the same scf
    _default_symlink_usage = False

    _ENABLED_PARALLELIZATION_FLAGS = ('npool', 'nband', 'ntg', 'ndiag')
    """
    @classproperty
    def xml_filepaths(cls):
        # Return a list of XML output filepaths relative to the remote working directory that should be retrieved.
        # pylint: disable=no-self-argument,not-an-iterable
        filepaths = []

        for filename in cls.xml_filenames:
            filepath = os.path.join(cls._OUTPUT_SUBFOLDER, f'{cls._PREFIX}.save', filename)
            filepaths.append(filepath)

        return filepaths
    """
    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        # yapf: disable
        super().define(spec)
        #('metadata.options.parser_name', valid_type=str, default='mpet.mpetrun')
        spec.input('metadata.options.without_xml', valid_type=bool, required=False, help='If set to `True` the parser '
            'will not fail if the XML file is missing in the retrieved folder.')


        spec.output('output_parameters', valid_type=orm.Dict,
            help='The `output_parameters` output node of the successful calculation.')
        spec.default_output_node = 'output_parameters'
        """
        # Unrecoverable errors: required retrieved files could not be read, parsed or are otherwise incomplete
        spec.exit_code(301, 'ERROR_NO_RETRIEVED_TEMPORARY_FOLDER',
            message='The retrieved temporary folder could not be accessed.')
        spec.exit_code(302, 'ERROR_OUTPUT_STDOUT_MISSING',
            message='The retrieved folder did not contain the required stdout output file.')
        spec.exit_code(303, 'ERROR_OUTPUT_XML_MISSING',
            message='The retrieved folder did not contain the required required XML file.')
        spec.exit_code(304, 'ERROR_OUTPUT_XML_MULTIPLE',
            message='The retrieved folder contained multiple XML files.')
        spec.exit_code(305, 'ERROR_OUTPUT_FILES',
            message='Both the stdout and XML output files could not be read or parsed.')
        spec.exit_code(310, 'ERROR_OUTPUT_STDOUT_READ',
            message='The stdout output file could not be read.')
        spec.exit_code(311, 'ERROR_OUTPUT_STDOUT_PARSE',
            message='The stdout output file could not be parsed.')
        spec.exit_code(312, 'ERROR_OUTPUT_STDOUT_INCOMPLETE',
            message='The stdout output file was incomplete probably because the calculation got interrupted.')
        spec.exit_code(320, 'ERROR_OUTPUT_XML_READ',
            message='The XML output file could not be read.')
        spec.exit_code(321, 'ERROR_OUTPUT_XML_PARSE',
            message='The XML output file could not be parsed.')
        spec.exit_code(322, 'ERROR_OUTPUT_XML_FORMAT',
            message='The XML output file has an unsupported format.')
        spec.exit_code(340, 'ERROR_OUT_OF_WALLTIME_INTERRUPTED',
            message='The calculation stopped prematurely because it ran out of walltime but the job was killed by the '
                    'scheduler before the files were safely written to disk for a potential restart.')
        spec.exit_code(350, 'ERROR_UNEXPECTED_PARSER_EXCEPTION',
            message='The parser raised an unexpected exception.')
        """
        # Significant errors but calculation can be used to restart
        #spec.exit_code(400, 'ERROR_OUT_OF_WALLTIME',
        #    message='The calculation stopped prematurely because it ran out of walltime.')
        
        # yapf: enable
    @classmethod
    def input_helper(cls, *args, **kwargs):
        """Validate the provided keywords and prepare the inputs dictionary in a 'standardized' form.

        The standardization converts ints to floats when required, or if the flag `flat_mode` is specified,
        puts the keywords in the right namelists.

        This function calls :py:func:`aiida_mpet.calculations.helpers.mpetrun_input_helper`, see its docstring for
        further information.
        """
        from . import helpers
        return helpers.mpetrun_input_helper(*args, **kwargs)
