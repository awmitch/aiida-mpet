# -*- coding: utf-8 -*-
"""Tests for the ``workflow launch study-base`` command."""
from aiida_dakota.cli.workflows.study.base import launch_workflow


def test_command_base(run_cli_process_launch_command, fixture_code):
    """Test invoking the workflow launch command with only required inputs."""
    code = fixture_code('dakota.study').store()
    options = ['-X', code.full_label]
    run_cli_process_launch_command(launch_workflow, options=options)
