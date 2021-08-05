# -*- coding: utf-8 -*-
"""Tools for nodes created by running the `StudyCalculation` class."""
from aiida.common import exceptions
from aiida.tools.calculations import CalculationTools


class StudyCalculationTools(CalculationTools):
    """Calculation tools for `StudyCalculation`.

    Methods implemented here are available on any `CalcJobNode` produced by the `StudyCalculation class through the `tools`
    attribute.
    """

    # pylint: disable=too-few-public-methods
