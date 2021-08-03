# -*- coding: utf-8 -*-
"""Tests for the ``calculation launch study`` command."""
from aiida_dakota.cli.calculations.pw import launch_calculation


def test_command_base(run_cli_process_launch_command, fixture_code):
    """Test invoking the calculation launch command with only required inputs."""
    code = fixture_code('dakota.study').store()
    options = ['-X', code.full_label]
    run_cli_process_launch_command(launch_calculation, options=options)
