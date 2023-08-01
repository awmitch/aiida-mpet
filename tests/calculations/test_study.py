# -*- coding: utf-8 -*-
"""Tests for the `MpetrunCalculation` class."""

import pytest

from aiida import orm
from aiida.common import datastructures
from aiida.common.warnings import AiidaDeprecationWarning
from aiida.common.exceptions import InputValidationError
from aiida_mpet.utils.resources import get_default_options
from aiida_mpet.calculations.helpers import MpetInputValidationError


def test_mpetrun_default(fixture_sandbox, generate_calc_job, generate_inputs_mpetrun, file_regression):
    """Test a default `MpetrunCalculation`."""
    entry_point_name = 'mpet.mpetrun'

    inputs = generate_inputs_mpetrun()
    calc_info = generate_calc_job(fixture_sandbox, entry_point_name, inputs)

    cmdline_params = ['-in', 'aiida.in']
    retrieve_list = ['aiida.out', './out/aiida.save/data-file-schema.xml', './out/aiida.save/data-file.xml']
    retrieve_temporary_list = [['./out/aiida.save/K*[0-9]/eigenval*.xml', '.', 2]]

    # Check the attributes of the returned `CalcInfo`
    assert isinstance(calc_info, datastructures.CalcInfo)
    assert isinstance(calc_info.codes_info[0], datastructures.CodeInfo)
    assert sorted(calc_info.codes_info[0].cmdline_params) == cmdline_params
    assert sorted(calc_info.local_copy_list) == sorted(local_copy_list)
    assert sorted(calc_info.retrieve_list) == sorted(retrieve_list)
    assert sorted(calc_info.retrieve_temporary_list) == sorted(retrieve_temporary_list)
    assert sorted(calc_info.remote_symlink_list) == sorted([])

    with fixture_sandbox.open('aiida.in') as handle:
        input_written = handle.read()

    # Checks on the files written to the sandbox folder as raw input
    assert sorted(fixture_sandbox.get_content_list()) == sorted(['aiida.in', 'out'])
    file_regression.check(input_written, encoding='utf-8', extension='.in')