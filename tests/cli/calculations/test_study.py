# -*- coding: utf-8 -*-
"""Tests for the ``calculation launch mpetrun`` command."""
from aiida_mpet.cli.calculations.pw import launch_calculation


def test_command_base(run_cli_process_launch_command, fixture_code):
    """Test invoking the calculation launch command with only required inputs."""
    code = fixture_code('mpet.mpetrun').store()
    options = ['-X', code.full_label]
    run_cli_process_launch_command(launch_calculation, options=options)
