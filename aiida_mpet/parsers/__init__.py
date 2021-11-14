# -*- coding: utf-8 -*-
from aiida.common import OutputParsingError


class MPETOutputParsingError(OutputParsingError):
    """Exception raised when there is a parsing error in the MPET parser."""
    pass
