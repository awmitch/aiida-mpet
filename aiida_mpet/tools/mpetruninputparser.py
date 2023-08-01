# -*- coding: utf-8 -*-
"""Utilities to parse Quantum ESPRESSO mpetrun.x input files into AiiDA nodes or builders."""
import copy
import re
import numpy as np

from aiida.orm import Code, Dict
from aiida.common.folders import Folder
from aiida.plugins import CalculationFactory, DataFactory
from qe_tools.parsers import MpetrunInputFile as BaseMpetrunInputFile

from .base import StructureParseMixin


class MpetrunInputFile(StructureParseMixin, BaseMpetrunInputFile):
    """Parser of Quantum ESPRESSO mpetrun.x input file into AiiDA nodes.

    .. note:: This mixes in :class:`~aiida_mpet.tools.base.StructureParseMixin` which adds the functionality
        to parse a :class:`~aiida.nodes.orm.data.structure.StructureData` from the input file, instead of a plain
        dictionary returned by :meth:`qe_tools.parsers.qeinputparser.get_structure_from_qeinput`. Note that one cannot
        directly add this functionality to a sub class of :class:`~qe_tools.parsers.qeinputparser.QeInputFile` and then
        subsequently sub class that here, because the :class:`~qe_tools.parsers.qeinputparser.CpInputFile` is also
        required and sub classing both leads to problems with the MRO.
    """


def create_builder_from_file(input_folder, input_file_name, code, metadata, pseudo_folder_path=None):
    """Create a populated process builder for a `MpetrunCalculation` from a standard MPET input file and pseudo (upf) files.

    :param input_folder: the folder containing the input file
    :type input_folder: aiida.common.folders.Folder or str
    :param input_file_name: the name of the input file
    :type input_file_name: str
    :param code: the code associated with the calculation
    :type code: aiida.orm.Code or str
    :param metadata: metadata values for the calculation (e.g. resources)
    :type metadata: dict
    :param pseudo_folder_path: the folder containing the upf files (if None, then input_folder is used)
    :type pseudo_folder_path: aiida.common.folders.Folder or str or None
    :raises NotImplementedError: if the structure is not ibrav=0
    :return: a builder instance for MpetrunCalculation
    """
    MpetrunCalculation = CalculationFactory('mpet.mpetrun')

    builder = MpetrunCalculation.get_builder()
    builder.metadata = metadata

    if isinstance(code, str):
        code = Code.get_from_string(code)
    builder.code = code

    # read input_file
    if isinstance(input_folder, str):
        input_folder = Folder(input_folder)

    with input_folder.open(input_file_name) as input_file:
        parsed_file = MpetrunInputFile(input_file.read())

    # Then, strip the namelist items that the plugin doesn't allow or sets later.
    # NOTE: If any of the position or cell units are in alat or crystal
    # units, that will be taken care of by the input parsing tools, and
    # we are safe to fake that they were never there in the first place.
    parameters_dict = copy.deepcopy(parsed_file.namelists)
    for namelist, blocked_key in MpetrunCalculation._blocked_keywords:  # pylint: disable=protected-access
        for key in list(parameters_dict[namelist].keys()):
            # take into account that celldm and celldm(*) must be blocked
            if re.sub('[(0-9)]', '', key) == blocked_key:
                parameters_dict[namelist].pop(key, None)
    builder.parameters = Dict(dict=parameters_dict)

    settings_dict = {}

    if settings_dict:
        builder.settings = settings_dict

    return builder
