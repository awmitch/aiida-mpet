# -*- coding: utf-8 -*-
"""Tests for immigrating `StudyCalculation`s."""
import os

import numpy as np

from aiida_dakota.tools.studyinputparser import create_builder_from_file


def test_create_builder(fixture_sandbox, fixture_code, generate_calc_job, filepath_tests):
    """Test the `create_builder_from_file` method that parses an existing `dakota` folder into a process builder.

    The input file used is the one generated for `tests.calculations.test_study.test_study_default`.
    """
    entry_point_name = 'dakota.study'
    code = fixture_code(entry_point_name)

    metadata = {
        'options': {
            'resources': {
                'num_machines': 1,
                'num_mpiprocs_per_machine': 32,
            },
            'max_memory_kb': 1000,
            'max_wallclock_seconds': 60 * 60 * 12,
            'withmpi': True,
        }
    }

    in_folderpath = os.path.join(filepath_tests, 'calculations', 'test_study')

    builder = create_builder_from_file(in_folderpath, 'test_study_default.in', code, metadata)

    # In certain versions of `aiida-core` the builder comes with the `stash` namespace by default.
    builder['metadata']['options'].pop('stash', None)

    assert builder['code'] == code
    assert builder['metadata'] == metadata
    
    #TODO
    assert builder['parameters'].get_dict() == {
        'CONTROL': {
            'calculation': 'scf',
            'verbosity': 'high'
        },
        'SYSTEM': {
            'ecutrho': 240.0,
            'ecutwfc': 30.0,
            'ibrav': 0,
        }
    }

    generate_calc_job(fixture_sandbox, entry_point_name, builder)
