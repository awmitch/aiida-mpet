# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,redefined-outer-name
"""Tests for the `StudyParser`."""
import pytest

from aiida import orm
from aiida.common import AttributeDict


@pytest.fixture
def generate_inputs(generate_structure):
    """Return only those inputs that the parser will expect to be there."""

    def _generate_inputs(parameters=None, settings=None, metadata=None):
        #TODO
        parameters = {'CONTROL': {'calculation': calculation_type}, **(parameters or {})}

        return AttributeDict({
            'parameters': orm.Dict(dict=parameters),
            'settings': orm.Dict(dict=settings),
            'metadata': metadata or {}
        })

    return _generate_inputs


def test_study_default(fixture_localhost, generate_calc_job_node, generate_parser, generate_inputs, data_regression):
    """Test a `dakota` calculation.

    The output is created by running a dead simple study.
    """
    name = 'default'
    entry_point_calc_job = 'dakota.study'
    entry_point_parser = 'dakota.study'

    node = generate_calc_job_node(entry_point_calc_job, fixture_localhost, name, generate_inputs())
    parser = generate_parser(entry_point_parser)
    results, calcfunction = parser.parse_from_node(node, store_provenance=False)

    assert calcfunction.is_finished, calcfunction.exception
    assert calcfunction.is_finished_ok, calcfunction.exit_message
    assert not orm.Log.objects.get_logs_for(node), [log.message for log in orm.Log.objects.get_logs_for(node)]
    assert 'output_parameters' in results

    data_regression.check({
        'output_parameters': results['output_parameters'].get_dict()
    })