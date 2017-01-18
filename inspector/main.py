#!/usr/bin/python
from __future__ import print_function, division

import sys
import os
import logging
logger = logging.getLogger('main')

import numpy as np
import pandas as pd

from datetime import datetime

from PyQt4 import QtGui
from PyQt4.QtGui import QApplication

from model import Model
from view import View

# import sip
# sip.setapi('QVariant', 2)



# ==============================================================================
# Monkey-patch pandas.tools.plotting._get_xlim to avoid IndexError
# ==============================================================================
def _get_xlim(lines):
    left, right = np.inf, -np.inf
    for l in lines:
        x = l.get_xdata(orig=False)
        left = min(x[0] if len(x) else left, left)
        right = max(x[-1] if len(x) else right, right)
    return left, right

from pandas import tools
tools.plotting._get_xlim = _get_xlim


def get_ipython_if_any():
    try:
        from IPython import get_ipython
    except ImportError:
        return None

    return get_ipython()


class Inspector(object):
    def __init__(self, data=None, call_exec=False, loglevel=logging.INFO,
                 interactive=True):
        """

        :param data: Series | Dataframe | [Series] | {str: Series} | None
        :param call_exec: bool
            Block by calling app.exec_() and exit on close.
            Use call_exec=False if running interactively from python prompt.
        :param files: [str]
            List of files to load

        """
        global QtGui
        logging.basicConfig(
            level=loglevel,
            format="%(asctime)s %(levelname)-8s [%(name)s] : %(message)s"
        )
        logger.debug('Initializing Inspector ...')
        # Make sure that we use any pre-existing QApplication instance
        if interactive:
            shell = get_ipython_if_any()
            if shell and not shell._inputhook.__module__.endswith('.qt'):
                shell.enable_gui('qt')
                logger.info("Enabled 'qt' gui in current ipython shell")
        app = QApplication.instance()
        self.app = app or QApplication(sys.argv)
        QtGui.qApp = self.app

        self.model = Model()
        self.view = View(self.model, data=data, interactive=interactive)
        if call_exec:
            sys.exit(self.app.exec_())

    def load_series(self, series_container, name=None):
        """
        Load series into the inspector

        :param series_container: Series | Dataframe | [Series] | {object: Series}
        :param name: str | None
        """
        self.view.load_seria(series_container, name=name)


def example_series(datetimeindex=True):
    x = np.arange(1000, 49005.0, 1)
    y = np.sin(2*np.pi*x/600) + 0.5*np.random.randn(len(x))
    d=pd.DataFrame(
        data=np.vstack((y,y*2)).T,
        index=map(datetime.utcfromtimestamp, x) if datetimeindex else x,
        columns=[(1,'a_name','aserial'), (2,'b_name','bserial')]
    )
    d.columns = map(str, d.columns)
    return d


def quicktest():
    inspector = Inspector()
    for name, series in example_series(datetimeindex=False).iteritems():
        inspector.load_series(series, name)
    return inspector


def main():
    loglvl = logging.DEBUG if os.environ.get('PYDEBUG', None) else logging.INFO
    inspector = Inspector(call_exec=True, loglevel=loglvl, interactive=False)
    return inspector

if __name__ == '__main__':
    inspector = main()
