from __future__ import print_function, division

import os
import logging
from functools import wraps

from PyQt4.QtGui import QKeySequence, QAction

import cProfile

def profileit(name):
    def inner(func):
        def wrapper(*args, **kwargs):
            prof = cProfile.Profile()
            retval = prof.runcall(func, *args, **kwargs)
            # Note use of name from outer scope
            prof.dump_stats(name)
            return retval
        return wrapper
    return inner


def print_out(text):
    """Function that currently just wraps print"""
    logging.info(text)


def debug_decorator(fcn, msg):
    logger = logging.getLogger('dbug')
    def debug_logged(*args, **kwargs):
        logger.debug(msg)
        return fcn(*args, **kwargs)
    return debug_logged


def create_action(text, parent, tip=None, shortcut=None, icon=None,
                  connect=None, connect_bool=None, add_to=None,
                  checkable=False):
    action = QAction(text, parent, checkable=checkable)
    if icon:
        action.setIcon(icon)
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))
    if tip:
        action.setStatusTip(tip)
    if add_to:
        add_to.addAction(action)
    if connect_bool:
        slots = (connect_bool if isinstance(connect, (list, tuple))
                              else [connect_bool])
        if os.environ.get('PYDEBUG', None):
            slots = [debug_decorator(cb, 'Triggered: ' + text) for cb in slots]
        # Slots must/should take single bool
        for slot in slots:
            action.triggered[bool].connect(slot)

    if connect:
        slots = (connect if isinstance(connect, (list, tuple))
                         else [connect])
        if os.environ.get('PYDEBUG', None):
            slots = [debug_decorator(cb, 'Triggered: ' + text) for cb in slots]
        # Slots must/should take no arguments
        for slot in slots:
            action.triggered[()].connect(slot)


    return action