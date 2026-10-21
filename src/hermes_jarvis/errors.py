"""Errors that are the user's to fix (bad config, port in use, ...). The command line prints the message, not a traceback."""


class UserError(Exception):
    """A problem with the setup, described in words the user can act on."""
