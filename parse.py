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
                parsed_data, logs = self.parse_xml_file(xml_file)
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



    def parse_xml_file(xml_file):
        """Parse the content of XML output file written by `study.x` and `cp.x` with the new schema-based XML format.

        :param xml: parsed XML
        :returns: tuple of two dictionaries, with the parsed data and log messages, respectively
        """

        from xmlschema.etree import ElementTree
        xml_parsed = ElementTree.parse(xml_file)


        e_bohr2_to_coulomb_m2 = 57.214766  # e/a0^2 to C/m^2 (electric polarization) from Wolfram Alpha

        logs = get_logging_container()

        schema_filepath = get_schema_filepath(xml)

        try:
            xsd = XMLSchema(schema_filepath)
        except URLError:

            # If loading the XSD file specified in the XML file fails, we try the default
            schema_filepath_default = get_default_schema_filepath()

            try:
                xsd = XMLSchema(schema_filepath_default)
            except URLError:
                raise XMLParseError(
                    f'Could not open or parse the XSD files {schema_filepath} and {schema_filepath_default}'
                )
            else:
                schema_filepath = schema_filepath_default

        # Validate XML document against the schema
        # Returned dictionary has a structure where, if tag ['key'] is "simple", xml_dictionary['key'] returns its content.
        # Otherwise, the following keys are available:
        #
        #  xml_dictionary['key']['$'] returns its content
        #  xml_dictionary['key']['@attr'] returns its attribute 'attr'
        #  xml_dictionary['key']['nested_key'] goes one level deeper.

        xml_dictionary, errors = xsd.to_dict(xml, validation='lax')
        if errors:
            logs.error.append(f'{len(errors)} XML schema validation error(s) schema: {schema_filepath}:')
            for err in errors:
                logs.error.append(str(err))

        xml_version = StrictVersion(xml_dictionary['general_info']['xml_format']['@VERSION'])
        inputs = xml_dictionary.get('input', {})
        outputs = xml_dictionary['output']

        lattice_vectors = [
            [x * CONSTANTS.bohr_to_ang for x in outputs['atomic_structure']['cell']['a1']],
            [x * CONSTANTS.bohr_to_ang for x in outputs['atomic_structure']['cell']['a2']],
            [x * CONSTANTS.bohr_to_ang for x in outputs['atomic_structure']['cell']['a3']],
        ]

        has_electric_field = inputs.get('electric_field', {}).get('electric_potential', None) == 'sawtooth_potential'
        has_dipole_correction = inputs.get('electric_field', {}).get('dipole_correction', False)

        if 'occupations' in inputs.get('bands', {}):
            try:
                occupations = inputs['bands']['occupations']['$']  # yapf: disable
            except TypeError:  # "string indices must be integers" -- might have attribute 'nspin'
                occupations = inputs['bands']['occupations']
        else:
            occupations = None

        starting_magnetization = []
        magnetization_angle1 = []
        magnetization_angle2 = []

        for specie in outputs['atomic_species']['species']:
            starting_magnetization.append(specie.get('starting_magnetization', 0.0))
            magnetization_angle1.append(specie.get('magnetization_angle1', 0.0))
            magnetization_angle2.append(specie.get('magnetization_angle2', 0.0))

        constraint_mag = 0
        spin_constraints = inputs.get('spin_constraints', {}).get('spin_constraints', None)
        if spin_constraints == 'atomic':
            constraint_mag = 1
        elif spin_constraints == 'atomic direction':
            constraint_mag = 2
        elif spin_constraints == 'total':
            constraint_mag = 3
        elif spin_constraints == 'total direction':
            constraint_mag = 6

        lsda = inputs.get('spin', {}).get('lsda', False)
        spin_orbit_calculation = inputs.get('spin', {}).get('spinorbit', False)
        non_colinear_calculation = outputs['magnetization']['noncolin']
        do_magnetization = outputs['magnetization'].get('do_magnetization', False)

        # Time reversal symmetry of the system
        if non_colinear_calculation and do_magnetization:
            time_reversal = False
        else:
            time_reversal = True

        # If no specific tags are present, the default is 1
        if non_colinear_calculation or spin_orbit_calculation:
            nspin = 4
        elif lsda:
            nspin = 2
        else:
            nspin = 1

        symmetries = []
        lattice_symmetries = []  # note: will only contain lattice symmetries that are NOT crystal symmetries
        inversion_symmetry = False

        # See also PW/src/setup.f90
        nsym = outputs.get('symmetries', {}).get('nsym', None)  # crystal symmetries
        nrot = outputs.get('symmetries', {}).get('nrot', None)  # lattice symmetries

        for symmetry in outputs.get('symmetries', {}).get('symmetry', []):

            # There are two types of symmetries, lattice and crystal. The pure inversion (-I) is always a lattice symmetry,
            # so we don't care. But if the pure inversion is also a crystal symmetry, then then the system as a whole
            # has (by definition) inversion symmetry; so we set the global property inversion_symmetry = True.
            symmetry_type = symmetry['info']['$']
            symmetry_name = symmetry['info']['@name']
            if symmetry_type == 'crystal_symmetry' and symmetry_name.lower() == 'inversion':
                inversion_symmetry = True

            sym = {
                'rotation': [
                    symmetry['rotation']['$'][0:3],
                    symmetry['rotation']['$'][3:6],
                    symmetry['rotation']['$'][6:9],
                ],
                'name': symmetry_name,
            }

            try:
                sym['t_rev'] = '1' if symmetry['info']['@time_reversal'] else '0'
            except KeyError:
                sym['t_rev'] = '0'

            try:
                sym['equivalent_atoms'] = symmetry['equivalent_atoms']['$']
            except KeyError:
                pass

            try:
                sym['fractional_translation'] = symmetry['fractional_translation']
            except KeyError:
                pass

            if symmetry_type == 'crystal_symmetry':
                symmetries.append(sym)
            elif symmetry_type == 'lattice_symmetry':
                lattice_symmetries.append(sym)
            else:
                raise XMLParseError(f'Unexpected type of symmetry: {symmetry_type}')

        if (nsym != len(symmetries)) or (nrot != len(symmetries) + len(lattice_symmetries)):
            logs.warning.append(
                'Inconsistent number of symmetries: nsym={}, nrot={}, len(symmetries)={}, len(lattice_symmetries)={}'.
                format(nsym, nrot, len(symmetries), len(lattice_symmetries))
            )

        xml_data = {
            #'pp_check_flag': True, # Currently not printed in the new format.
            # Signals whether the XML file is complete
            # and can be used for post-processing. Everything should be in the XML now, but in
            # any case, the new XML schema should mostly protect from incomplete files.
            'lkpoint_dir': False,  # Currently not printed in the new format.
            # Signals whether kpt-data are written in sub-directories.
            # Was generally true in the old format, but now all the eigenvalues are
            # in the XML file, under output / band_structure, so this is False.
            'charge_density': './charge-density.dat',  # A file name. Not printed in the new format.
            # The filename and path are considered fixed: <outdir>/<prefix>.save/charge-density.dat
            # TODO: change to .hdf5 if output format is HDF5 (issue #222)
            'rho_cutoff_units': 'eV',
            'wfc_cutoff_units': 'eV',
            'fermi_energy_units': 'eV',
            'k_points_units': '1 / angstrom',
            'symmetries_units': 'crystal',
            'constraint_mag': constraint_mag,
            'magnetization_angle2': magnetization_angle2,
            'magnetization_angle1': magnetization_angle1,
            'starting_magnetization': starting_magnetization,
            'has_electric_field': has_electric_field,
            'has_dipole_correction': has_dipole_correction,
            'lda_plus_u_calculation': 'dftU' in outputs,
            'format_name': xml_dictionary['general_info']['xml_format']['@NAME'],
            'format_version': xml_dictionary['general_info']['xml_format']['@VERSION'],
            # TODO: check that format version: a) matches the XSD schema version; b) is updated as well
            #       See line 43 in Modules/qexsd.f90
            'creator_name': xml_dictionary['general_info']['creator']['@NAME'].lower(),
            'creator_version': xml_dictionary['general_info']['creator']['@VERSION'],
            'non_colinear_calculation': non_colinear_calculation,
            'do_magnetization': do_magnetization,
            'time_reversal_flag': time_reversal,
            'symmetries': symmetries,
            'lattice_symmetries': lattice_symmetries,
            'do_not_use_time_reversal': inputs.get('symmetry_flags', {}).get('noinv', None),
            'spin_orbit_domag': do_magnetization,
            'fft_grid': [value for _, value in sorted(outputs['basis_set']['fft_grid'].items())],
            'lsda': lsda,
            'number_of_spin_components': nspin,
            'no_time_rev_operations': inputs.get('symmetry_flags', {}).get('no_t_rev', None),
            'inversion_symmetry':
            inversion_symmetry,  # the old tag was INVERSION_SYMMETRY and was set to (from the code): "invsym    if true the system has inversion symmetry"
            'number_of_bravais_symmetries': nrot,  # lattice symmetries
            'number_of_symmetries': nsym,  # crystal symmetries
            'wfc_cutoff': inputs.get('basis', {}).get('ecutwfc', -1.0) * CONSTANTS.hartree_to_ev,
            'rho_cutoff': outputs['basis_set']['ecutrho'] * CONSTANTS.hartree_to_ev,  # not always printed in input->basis
            'smooth_fft_grid': [value for _, value in sorted(outputs['basis_set']['fft_smooth'].items())],
            'dft_exchange_correlation': inputs.get('dft', {}).get('functional',
                                                                None),  # TODO: also parse optional elements of 'dft' tag
            # WARNING: this is different between old XML and new XML
            'spin_orbit_calculation': spin_orbit_calculation,
            'q_real_space': outputs['algorithmic_info']['real_space_q'],
        }

        # alat is technically an optional attribute according to the schema,
        # but I don't know what to do if it's missing. atomic_structure is mandatory.
        output_alat_bohr = outputs['atomic_structure']['@alat']
        output_alat_angstrom = output_alat_bohr * CONSTANTS.bohr_to_ang

        # Band structure
        if 'band_structure' in outputs:
            band_structure = outputs['band_structure']

            smearing_xml = None

            if 'smearing' in outputs['band_structure']:
                smearing_xml = outputs['band_structure']['smearing']
            elif 'smearing' in inputs:
                smearing_xml = inputs['smearing']

            if smearing_xml:
                degauss = smearing_xml['@degauss']

                # Versions below 19.03.04 (Quantum ESPRESSO<=6.4.1) incorrectly print degauss in Ry instead of Hartree
                if xml_version < StrictVersion('19.03.04'):
                    degauss *= CONSTANTS.ry_to_ev
                else:
                    degauss *= CONSTANTS.hartree_to_ev

                xml_data['degauss'] = degauss
                xml_data['smearing_type'] = smearing_xml['$']

            num_k_points = band_structure['nks']
            num_electrons = band_structure['nelec']
            num_atomic_wfc = band_structure['num_of_atomic_wfc']
            num_bands = band_structure.get('nbnd', None)
            num_bands_up = band_structure.get('nbnd_up', None)
            num_bands_down = band_structure.get('nbnd_dw', None)

            if num_bands is None and num_bands_up is None and num_bands_down is None:
                raise XMLParseError('None of `nbnd`, `nbnd_up` or `nbdn_dw` could be parsed.')

            # If both channels are `None` we are dealing with a non spin-polarized or non-collinear calculation
            elif num_bands_up is None and num_bands_down is None:
                spins = False

            # If only one of the channels is `None` we raise, because that is an inconsistent result
            elif num_bands_up is None or num_bands_down is None:
                raise XMLParseError('Only one of `nbnd_up` and `nbnd_dw` could be parsed')

            # Here it is a spin-polarized calculation, where for study.x the number of bands in each channel should be identical.
            else:
                spins = True
                if num_bands_up != num_bands_down:
                    raise XMLParseError(f'different number of bands for spin channels: {num_bands_up} and {num_bands_down}')

                if num_bands is not None and num_bands != num_bands_up + num_bands_down:
                    raise XMLParseError(
                        'Inconsistent number of bands: nbnd={}, nbnd_up={}, nbnd_down={}'.format(
                            num_bands, num_bands_up, num_bands_down
                        )
                    )

                if num_bands is None:
                    num_bands = num_bands_up + num_bands_down  # backwards compatibility;

            k_points = []
            k_points_weights = []
            ks_states = band_structure['ks_energies']
            for ks_state in ks_states:
                k_points.append([kp * 2 * np.pi / output_alat_angstrom for kp in ks_state['k_point']['$']])
                k_points_weights.append(ks_state['k_point']['@weight'])

            if not spins:
                band_eigenvalues = [[]]
                band_occupations = [[]]
                for ks_state in ks_states:
                    band_eigenvalues[0].append(ks_state['eigenvalues']['$'])
                    band_occupations[0].append(ks_state['occupations']['$'])
            else:
                band_eigenvalues = [[], []]
                band_occupations = [[], []]
                for ks_state in ks_states:
                    band_eigenvalues[0].append(ks_state['eigenvalues']['$'][0:num_bands_up])
                    band_eigenvalues[1].append(ks_state['eigenvalues']['$'][num_bands_up:num_bands])
                    band_occupations[0].append(ks_state['occupations']['$'][0:num_bands_up])
                    band_occupations[1].append(ks_state['occupations']['$'][num_bands_up:num_bands])

            band_eigenvalues = np.array(band_eigenvalues) * CONSTANTS.hartree_to_ev
            band_occupations = np.array(band_occupations)

            if not spins:
                parser_assert_equal(
                    band_eigenvalues.shape, (1, num_k_points, num_bands), 'Unexpected shape of band_eigenvalues'
                )
                parser_assert_equal(
                    band_occupations.shape, (1, num_k_points, num_bands), 'Unexpected shape of band_occupations'
                )
            else:
                parser_assert_equal(
                    band_eigenvalues.shape, (2, num_k_points, num_bands_up), 'Unexpected shape of band_eigenvalues'
                )
                parser_assert_equal(
                    band_occupations.shape, (2, num_k_points, num_bands_up), 'Unexpected shape of band_occupations'
                )

            if not spins:
                xml_data['number_of_bands'] = num_bands
            else:
                # For collinear spin-polarized calculations `spins=True` and `num_bands` is sum of both channels. To get the
                # actual number of bands, we divide by two using integer division
                xml_data['number_of_bands'] = num_bands // 2

            for key, value in [('number_of_bands_up', num_bands_up), ('number_of_bands_down', num_bands_down)]:
                if value is not None:
                    xml_data[key] = value

            if 'fermi_energy' in band_structure:
                xml_data['fermi_energy'] = band_structure['fermi_energy'] * CONSTANTS.hartree_to_ev

            if 'two_fermi_energies' in band_structure:
                xml_data['fermi_energy_up'], xml_data['fermi_energy_down'] = [
                    energy * CONSTANTS.hartree_to_ev for energy in band_structure['two_fermi_energies']
                ]

            bands_dict = {
                'occupations': band_occupations,
                'bands': band_eigenvalues,
                'bands_units': 'eV',
            }

            xml_data['number_of_atomic_wfc'] = num_atomic_wfc
            xml_data['number_of_k_points'] = num_k_points
            xml_data['number_of_electrons'] = num_electrons
            xml_data['k_points'] = k_points
            xml_data['k_points_weights'] = k_points_weights
            xml_data['bands'] = bands_dict

        try:
            monkhorst_pack = inputs['k_points_IBZ']['monkhorst_pack']
        except KeyError:
            pass  # not using Monkhorst pack
        else:
            xml_data['monkhorst_pack_grid'] = [monkhorst_pack[attr] for attr in ['@nk1', '@nk2', '@nk3']]
            xml_data['monkhorst_pack_offset'] = [monkhorst_pack[attr] for attr in ['@k1', '@k2', '@k3']]

        if occupations is not None:
            xml_data['occupations'] = occupations

        if 'boundary_conditions' in outputs and 'assume_isolated' in outputs['boundary_conditions']:
            xml_data['assume_isolated'] = outputs['boundary_conditions']['assume_isolated']

        # This is not printed by DAKOTA 6.3, but will be re-added before the next version
        if 'real_space_beta' in outputs['algorithmic_info']:
            xml_data['beta_real_space'] = outputs['algorithmic_info']['real_space_beta']

        conv_info = {}
        conv_info_scf = {}
        conv_info_opt = {}
        # NOTE: n_scf_steps refers to the number of SCF steps in the *last* loop only.
        # To get the total number of SCF steps in the run you should sum up the individual steps.
        # TODO: should we parse 'steps' too? Are they already added in the output trajectory?
        for key in ['convergence_achieved', 'n_scf_steps', 'scf_error']:
            try:
                conv_info_scf[key] = outputs['convergence_info']['scf_conv'][key]
            except KeyError:
                pass
        for key in ['convergence_achieved', 'n_opt_steps', 'grad_norm']:
            try:
                conv_info_opt[key] = outputs['convergence_info']['opt_conv'][key]
            except KeyError:
                pass
        if conv_info_scf:
            conv_info['scf_conv'] = conv_info_scf
        if conv_info_opt:
            conv_info['opt_conv'] = conv_info_opt
        if conv_info:
            xml_data['convergence_info'] = conv_info

        if 'status' in xml_dictionary:
            xml_data['exit_status'] = xml_dictionary['status']
            # 0 = convergence reached;
            # -1 = SCF convergence failed;
            # 3 = ionic convergence failed
            # These might be changed in the future. Also see PW/src/run_studyscf.f90

        try:
            berry_phase = outputs['electric_field']['BerryPhase']
        except KeyError:
            pass
        else:
            # This is what I would like to do, but it's not retro-compatible
            # xml_data['berry_phase'] = {}
            # xml_data['berry_phase']['total_phase']         = berry_phase['totalPhase']['$']
            # xml_data['berry_phase']['total_phase_modulus'] = berry_phase['totalPhase']['@modulus']
            # xml_data['berry_phase']['total_ionic_phase']      = berry_phase['totalPhase']['@ionic']
            # xml_data['berry_phase']['total_electronic_phase'] = berry_phase['totalPhase']['@electronic']
            # xml_data['berry_phase']['total_polarization']           = berry_phase['totalPolarization']['polarization']['$']
            # xml_data['berry_phase']['total_polarization_modulus']   = berry_phase['totalPolarization']['modulus']
            # xml_data['berry_phase']['total_polarization_units']     = berry_phase['totalPolarization']['polarization']['@Units']
            # xml_data['berry_phase']['total_polarization_direction'] = berry_phase['totalPolarization']['direction']
            # parser_assert_equal(xml_data['berry_phase']['total_phase_modulus'].lower(), '(mod 2)',
            #                    "Unexpected modulus for total phase")
            # parser_assert_equal(xml_data['berry_phase']['total_polarization_units'].lower(), 'e/bohr^2',
            #                    "Unsupported units for total polarization")
            # Retro-compatible keys:
            polarization = berry_phase['totalPolarization']['polarization']['$']
            polarization_units = berry_phase['totalPolarization']['polarization']['@Units']
            polarization_modulus = berry_phase['totalPolarization']['modulus']
            parser_assert(
                polarization_units in ['e/bohr^2', 'C/m^2'],
                f"Unsupported units '{polarization_units}' of total polarization"
            )
            if polarization_units == 'e/bohr^2':
                polarization *= e_bohr2_to_coulomb_m2
                polarization_modulus *= e_bohr2_to_coulomb_m2

            xml_data['total_phase'] = berry_phase['totalPhase']['$']
            xml_data['total_phase_units'] = '2pi'
            xml_data['ionic_phase'] = berry_phase['totalPhase']['@ionic']
            xml_data['ionic_phase_units'] = '2pi'
            xml_data['electronic_phase'] = berry_phase['totalPhase']['@electronic']
            xml_data['electronic_phase_units'] = '2pi'
            xml_data['polarization'] = polarization
            xml_data['polarization_module'] = polarization_modulus  # should be called "modulus"
            xml_data['polarization_units'] = 'C / m^2'
            xml_data['polarization_direction'] = berry_phase['totalPolarization']['direction']
            # TODO: add conversion for (e/Omega).bohr (requires to know Omega, the volume of the cell)
            # TODO (maybe): Not parsed:
            # - individual ionic phases
            # - individual electronic phases and weights

        # TODO: We should put the `non_periodic_cell_correction` string in (?)
        atoms = [[atom['@name'], [coord * CONSTANTS.bohr_to_ang
                                for coord in atom['$']]]
                for atom in outputs['atomic_structure']['atomic_positions']['atom']]
        species = outputs['atomic_species']['species']
        structure_data = {
            'atomic_positions_units':
            'Angstrom',
            'direct_lattice_vectors_units':
            'Angstrom',
            # ??? 'atoms_if_pos_list': [[1, 1, 1], [1, 1, 1]],
            'number_of_atoms':
            outputs['atomic_structure']['@nat'],
            'lattice_parameter':
            output_alat_angstrom,
            'reciprocal_lattice_vectors': [
                outputs['basis_set']['reciprocal_lattice']['b1'], outputs['basis_set']['reciprocal_lattice']['b2'],
                outputs['basis_set']['reciprocal_lattice']['b3']
            ],
            'atoms':
            atoms,
            'cell': {
                'lattice_vectors': lattice_vectors,
                'volume': cell_volume(*lattice_vectors),
                'atoms': atoms,
            },
            'lattice_parameter_xml':
            output_alat_bohr,
            'number_of_species':
            outputs['atomic_species']['@ntyp'],
            'species': {
                'index': [i + 1 for i, specie in enumerate(species)],
                'pseudo': [specie['pseudo_file'] for specie in species],
                'mass': [specie['mass'] for specie in species],
                'type': [specie['@name'] for specie in species]
            },
        }

        xml_data['structure'] = structure_data

        return xml_data, logs