"""Failures the user can act on."""


class UserError(Exception):
    """A failure that the command line reports as one line, with a non-zero exit and no traceback.

    Its message says what is wrong and, where it helps, what to use instead.
    """
