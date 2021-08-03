# -*- coding: utf-8 -*-
"""`Parser` implementation for the `StudyCalculation` calculation job class."""
import traceback

import numpy

from aiida import orm
from aiida.common import exceptions

from aiida_dakota.utils.mapping import get_logging_container
from .base import Parser
from .parse_raw.study import reduce_symmetries


class StudyParser(Parser):
    """`Parser` implementation for the `StudyCalculation` calculation job class."""

    def parse(self, **kwargs):
        """Parse the retrieved files of a completed `StudyCalculation` into output nodes.

        Two nodes that are expected are the default 'retrieved' `FolderData` node which will store the retrieved files
        permanently in the repository. The second required node is a filepath under the key `retrieved_temporary_files`
        which should contain the temporary retrieved files.
        """
        dir_with_bands = None
        self.exit_code_xml = None
        self.exit_code_stdout = None
        self.exit_code_parser = None

        try:
            settings = self.node.inputs.settings.get_dict()
        except exceptions.NotExistent:
            settings = {}

        # Look for optional settings input node and potential 'parser_options' dictionary within it
        parser_options = settings.get(self.get_parser_settings_key(), None)

        # Verify that the retrieved_temporary_folder is within the arguments if temporary files were specified
        if self.node.get_attribute('retrieve_temporary_list', None):
            try:
                dir_with_bands = kwargs['retrieved_temporary_folder']
            except KeyError:
                return self.exit(self.exit_codes.ERROR_NO_RETRIEVED_TEMPORARY_FOLDER)

        parameters = self.node.inputs.parameters.get_dict()
        parsed_xml, logs_xml = self.parse_xml(dir_with_bands, parser_options)
        parsed_stdout, logs_stdout = self.parse_stdout(parameters, parser_options, parsed_xml)
        parsed_parameters = self.build_output_parameters(parsed_stdout, parsed_xml)

        self.out('output_parameters', orm.Dict(dict=parsed_parameters))

        self.emit_logs([logs_stdout, logs_xml], ignore=ignore)

        # First check for specific known problems that can cause a pre-mature termination of the calculation
        exit_code = self.validate_premature_exit(logs_stdout)
        if exit_code:
            return self.exit(exit_code)

        # If the both stdout and xml exit codes are set, there was a basic problem with both output files and there
        # is no need to investigate any further.
        if self.exit_code_stdout and self.exit_code_xml:
            return self.exit(self.exit_codes.ERROR_OUTPUT_FILES)

        if self.exit_code_stdout:
            return self.exit(self.exit_code_stdout)

        if self.exit_code_xml:
            return self.exit(self.exit_code_xml)

        # First determine issues that can occurr for all calculation types. Note that the generic errors, that are
        # common to all types are done first. If a problem is found there, we return the exit code and don't continue
        for validator in [self.validate_electronic, self.validate_dynamics, self.validate_ionic]:
            exit_code = validator(trajectory, parsed_parameters, logs_stdout)
            if exit_code:
                return self.exit(exit_code)

    def get_calculation_type(self):
        """Return the type of the calculation."""
        return self.node.inputs.parameters.get_attribute('CONTROL', {}).get('calculation', 'scf')

    def validate_premature_exit(self, logs):
        """Analyze problems that will cause a pre-mature termination of the calculation, controlled or not."""
        if 'ERROR_OUT_OF_WALLTIME' in logs['error'] and 'ERROR_OUTPUT_STDOUT_INCOMPLETE' in logs['error']:
            return self.exit_codes.ERROR_OUT_OF_WALLTIME_INTERRUPTED

        for error_label in [
            'ERROR_OUT_OF_WALLTIME',
                ]:
            if error_label in logs['error']:
                return self.exit_codes.get(error_label)


    def parse_xml(self, dir_with_bands=None, parser_options=None):
        """Parse the XML output file.

        :param dir_with_bands: absolute path to directory containing individual k-point XML files for old XML format.
        :param parser_options: optional dictionary with parser options
        :return: tuple of two dictionaries, first with raw parsed data and second with log messages
        """
        from .parse_xml.exceptions import XMLParseError, XMLUnsupportedFormatError
        from .parse_xml.study.parse import parse_xml

        logs = get_logging_container()
        parsed_data = {}

        object_names = self.retrieved.list_object_names()
        xml_files = [xml_file for xml_file in self.node.process_class.xml_filenames if xml_file in object_names]

        if not xml_files:
            if not self.node.get_option('without_xml'):
                self.exit_code_xml = self.exit_codes.ERROR_OUTPUT_XML_MISSING
            return parsed_data, logs

        if len(xml_files) > 1:
            self.exit_code_xml = self.exit_codes.ERROR_OUTPUT_XML_MULTIPLE
            return parsed_data, logs

        try:
            with self.retrieved.open(xml_files[0]) as xml_file:
                parsed_data, logs = parse_xml(xml_file, dir_with_bands)
        except IOError:
            self.exit_code_xml = self.exit_codes.ERROR_OUTPUT_XML_READ
        except XMLParseError:
            self.exit_code_xml = self.exit_codes.ERROR_OUTPUT_XML_PARSE
        except XMLUnsupportedFormatError:
            self.exit_code_xml = self.exit_codes.ERROR_OUTPUT_XML_FORMAT
        except Exception:
            logs.critical.append(traceback.format_exc())
            self.exit_code_xml = self.exit_codes.ERROR_UNEXPECTED_PARSER_EXCEPTION

        return parsed_data, logs

    def parse_stdout(self, parameters, parser_options=None, parsed_xml=None):
        """Parse the stdout output file.

        :param parameters: the input parameters dictionary
        :param parser_options: optional dictionary with parser options
        :param parsed_xml: the raw parsed data from the XML output
        :return: tuple of two dictionaries, first with raw parsed data and second with log messages
        """
        from aiida_dakota.parsers.parse_raw.study import parse_stdout

        logs = get_logging_container()
        parsed_data = {}

        filename_stdout = self.node.get_attribute('output_filename')

        if filename_stdout not in self.retrieved.list_object_names():
            self.exit_code_stdout = self.exit_codes.ERROR_OUTPUT_STDOUT_MISSING
            return parsed_data, logs

        try:
            stdout = self.retrieved.get_object_content(filename_stdout)
        except IOError:
            self.exit_code_stdout = self.exit_codes.ERROR_OUTPUT_STDOUT_READ
            return parsed_data, logs

        try:
            parsed_data, logs = parse_stdout(stdout, parameters, parser_options, parsed_xml)
        except Exception:
            logs.critical.append(traceback.format_exc())
            self.exit_code_stdout = self.exit_codes.ERROR_UNEXPECTED_PARSER_EXCEPTION

        # If the stdout was incomplete, most likely the job was interrupted before it could cleanly finish, so the
        # output files are most likely corrupt and cannot be restarted from
        if 'ERROR_OUTPUT_STDOUT_INCOMPLETE' in logs['error']:
            self.exit_code_stdout = self.exit_codes.ERROR_OUTPUT_STDOUT_INCOMPLETE

        return parsed_data, logs

    @staticmethod
    def build_output_parameters(parsed_stdout, parsed_xml):
        """Build the dictionary of output parameters from the raw parsed data.

        The output parameters are based on the union of raw parsed data from the XML and stdout output files.
        Currently, if both raw parsed data dictionaries contain the same key, the stdout version takes precedence, but
        this should not occur as the `parse_stdout` method should already have solved these conflicts.

        :param parsed_stdout: the raw parsed data dictionary from the stdout output file
        :param parsed_xml: the raw parsed data dictionary from the XML output file
        :return: the union of the two raw parsed data dictionaries
        """
        for key in list(parsed_stdout.keys()):
            if key in list(parsed_xml.keys()):
                if parsed_stdout[key] != parsed_xml[key]:
                    raise AssertionError(
                        '{} found in both dictionaries with different values: {} vs. {}'.format(
                            key, parsed_stdout[key], parsed_xml[key]
                        )
                    )

        parameters = dict(list(parsed_xml.items()) + list(parsed_stdout.items()))

        return parameters

    @staticmethod
    def get_parser_settings_key():
        """Return the key that contains the optional parser options in the `settings` input node."""
        return 'parser_options'
