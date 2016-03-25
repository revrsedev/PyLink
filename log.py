"""
log.py - PyLink logging module.

This module contains the logging portion of the PyLink framework. Plugins can
access the global logger object by importing "log" from this module
(from log import log).
"""

import logging
import sys
import os

from conf import conf, confname

stdout_level = conf['logging'].get('stdout') or 'INFO'

# Set the logging directory to $CURDIR/log, creating it if it doesn't
# already exist
curdir = os.path.dirname(os.path.realpath(__file__))
logdir = os.path.join(curdir, 'log')
os.makedirs(logdir, exist_ok=True)

_format = '%(asctime)s [%(levelname)s] %(message)s'
logformatter = logging.Formatter(_format)

# Set up logging to STDERR
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logformatter)
stdout_handler.setLevel(stdout_level)

# Get the main logger object; plugins can import this variable for convenience.
log = logging.getLogger()
log.addHandler(stdout_handler)

# This is confusing, but we have to set the root logger to accept all events. Only this way
# can other loggers filter out events on their own, instead of having everything dropped by
# the root logger. https://stackoverflow.com/questions/16624695
log.setLevel(1)

def makeFileLogger(filename, level=None):
    """
    Initializes a file logging target with the given filename and level.
    """
    # Use log names specific to the current instance, to prevent multiple
    # PyLink instances from overwriting each others' log files.
    target = os.path.join(logdir, '%s-%s.log' % (confname, filename))

    filelogger = logging.FileHandler(target, mode='w')
    filelogger.setFormatter(logformatter)

    # If no log level is specified, use the same one as STDOUT.
    level = level or stdout_level
    filelogger.setLevel(level)

    log.addHandler(filelogger)

    return filelogger

# Set up file logging now, creating a file logger for each block.
files = conf['logging'].get('files')
if files:
    for filename, config in files.items():
        makeFileLogger(filename, config.get('loglevel'))

class PyLinkChannelLogger(logging.Handler):
    """
    Log handler to log to channels in PyLink.
    """
    def __init__(self, irc, channel, level=None):
        super(PyLinkChannelLogger, self).__init__()
        self.irc = irc
        self.channel = channel

        # Set whether we've been called already. This is used to prevent recursive
        # loops when logging.
        self.called = False

        # Use a slightly simpler message formatter - logging to IRC doesn't need
        # logging the time.
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        self.setFormatter(formatter)

        # HACK: Use setLevel twice to first coerse string log levels to ints,
        # for easier comparison.
        level = level or log.getEffectiveLevel()
        self.setLevel(level)

        # Log level has to be at least 20 (INFO) to prevent loops due
        # to outgoing messages being logged
        loglevel = max(self.level, 20)
        self.setLevel(loglevel)

    def emit(self, record):
        """
        Logs a record to the configured channels for the network given.
        """
        # Only start logging if we're finished bursting, and our main client is in
        # a stable condition.
        # 1) irc.pseudoclient must be initialized already
        # 2) IRC object must be finished bursting
        # 3) Target channel must exist
        # 4) Main PyLink client must be in this target channel
        # 5) This function hasn't been called already (prevents recursive loops).
        if hasattr(self.irc, 'pseudoclient') and self.irc.connected.is_set() \
                and self.channel in self.irc.channels and self.irc.pseudoclient.uid in \
                self.irc.channels[self.channel].users and not self.called:

            self.called = True
            msg = self.format(record)

            # Send the message. If this fails, abort. No more messages will be
            # sent from this logger until the next sending succeeds.
            for line in msg.splitlines():
                try:
                    self.irc.msg(self.channel, line)
                except:
                    return
                else:
                    self.called = False

