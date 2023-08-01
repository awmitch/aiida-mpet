# -*- coding: utf-8 -*-
"""Unit tests for the :py:mod:`~aiida_mpet.utils.restart` module."""
import pytest

from aiida.engine import ProcessBuilder
from aiida_mpet.utils import restart


def generate_inputs():
    """Return a dictionary of inputs for a `CalcJobNode` fixture to be created."""
    from aiida import orm
    return {'parameters': orm.Dict(dict={}), 'settings': orm.Dict(dict={})}

def test_restart_mpetrun(fixture_localhost, generate_calc_job_node):
    """Test the `get_builder_restart` for a completed `MpetrunCalculation`."""
    entry_point_calc_job = 'mpet.mpetrun'
    node = generate_calc_job_node(entry_point_calc_job, fixture_localhost, 'default', generate_inputs())

    builder = restart.get_builder_restart(node)
    parameters = builder.parameters.get_dict()

    assert isinstance(builder, ProcessBuilder)
    assert parameters['CONTROL']['restart_mode'] == 'restart'

    # Force `from_scratch`
    builder = restart.get_builder_restart(node, from_scratch=True)
    parameters = builder.parameters.get_dict()

    assert isinstance(builder, ProcessBuilder)
    assert parameters['CONTROL']['restart_mode'] == 'from_scratch'
