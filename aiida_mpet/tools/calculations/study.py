# -*- coding: utf-8 -*-
"""Tools for nodes created by running the `MpetrunCalculation` class."""
from aiida.common import exceptions
from aiida.tools.calculations import CalculationTools


class MpetrunCalculationTools(CalculationTools):
    """Calculation tools for `MpetrunCalculation`.

    Methods implemented here are available on any `CalcJobNode` produced by the `MpetrunCalculation class through the `tools`
    attribute.
    """

    # pylint: disable=too-few-public-methods
