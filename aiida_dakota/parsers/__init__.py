# -*- coding: utf-8 -*-
from aiida.common import OutputParsingError


class DAKOTAOutputParsingError(OutputParsingError):
    """Exception raised when there is a parsing error in the DAKOTA parser."""
    pass
