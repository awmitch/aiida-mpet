# -*- coding: utf-8 -*-
"""Tests for the ``workflow launch mpetrun-base`` command."""
from aiida_mpet.cli.workflows.mpetrun.base import launch_workflow


def test_command_base(run_cli_process_launch_command, fixture_code):
    """Test invoking the workflow launch command with only required inputs."""
    code = fixture_code('mpet.mpetrun').store()
    options = ['-X', code.full_label]
    run_cli_process_launch_command(launch_workflow, options=options)
