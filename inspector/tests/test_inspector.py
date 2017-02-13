from __future__ import print_function, division

import sys

from functools import wraps
from unittest import TestCase
from operator import attrgetter

import numpy as np
import pandas as pd

# skeleton from http://johnnado.com/pyqt-qtest-example/
from matplotlib.backends.qt_compat import QtWidgets, QtCore, is_pyqt5

if is_pyqt5():
    from PyQt5.QtTest import QTest
    from PyQt5.QtCore import Qt
else:
    from PyQt4.QtTest import QTest
    from PyQt4.QtCore import Qt


from inspector import Inspector
from inspector.constants import Labels
from inspector import plugins


app = QtWidgets.QApplication([])

failure_ = False
sys._excepthook = sys.excepthook

class ExceptionHandler(QtCore.QObject):

    errorSignal = QtCore.pyqtSignal()
    silentSignal = QtCore.pyqtSignal()

    def __init__(self):
        super(ExceptionHandler, self).__init__()

    def handler(self, exctype, value, traceback):
        global failure_
        self.errorSignal.emit()
        failure_ = (exctype, value, traceback)
        sys._excepthook(exctype, value, traceback)


def check_slot_failure(func):
    @wraps(func)
    def testdecorator(*args, **kwargs):
        global failure_
        func(*args, **kwargs)
        if failure_:
            last_fail = failure_
            failure_ = False
            raise last_fail[0]("Uncaught Exception in slot: '%s'" % last_fail[1])

    return testdecorator


class TestInspector(TestCase):
    def setUp(self):
        self.ins = Inspector()
        exceptionHandler = ExceptionHandler()
        sys.excepthook = exceptionHandler.handler
        self.df_timeseries = pd.DataFrame(
            data=np.random.randn(10,2),
            index=pd.date_range('2016-10-29 22:00:00', periods=10)
        )

    def tearDown(self):
        sys.excepthook = sys._excepthook

    @check_slot_failure
    def test_load_series_array(self):
        self.ins.load_series(np.arange(0,1000,0.1))

    @check_slot_failure
    def test_load_series_dataframe(self):
        self.ins.load_series(self.df_timeseries)
        self.assertEqual(
            len(self.ins.model.items),
            2
        )

    @check_slot_failure
    def test_load_series_timeseries(self):
        n_data = self.ins.view.outline_view.do_resample_threshold + 1
        series = pd.Series(
            data=range(n_data),
            index=pd.date_range('2016-10-29 22:00:00', periods=n_data)
        )
        self.ins.load_series(series)

    @check_slot_failure
    def test_load_bytes(self):
        self.ins.view.load_bytes(self.df_timeseries.to_msgpack())
        self.assertEqual(
            len(self.ins.model.items),
            2
        )

    @check_slot_failure
    def test_load_series_mixed_types(self):
        self.test_load_series_array()
        self.test_load_series_timeseries()
        self.assertEqual(
            len(self.ins.model.items),
            1
        )

    @check_slot_failure
    def test_load_series_mixed_types_reversed_order(self):
        self.test_load_series_timeseries()
        self.test_load_series_array()
        self.assertEqual(
            len(self.ins.model.items),
            1
        )

    @check_slot_failure
    def test_auto_mark_gaps(self):
        index_values = [0, 4, 8, 12, 16, 19]
        metadata = {'metaA': 'foo', 'submetaB': 'bar'}
        self.ins.view.toggle_plugin(plugins.MarkingsIO, True)
        self.ins.load_series([
            {
                'series': pd.Series(index_values, index_values),
                'metadata': metadata
            }
        ])
        mark_io = self.ins.view.plugins[plugins.MarkingsIO.name]
        mark_io.sig_apply_on_visible.emit(
            lambda series, metadata: mark_io.auto_mark_gaps(
                series=series,
                metadata=metadata,
                gap_limit=3,
                label=Labels.DISCARD,
            )
        )
        self.assertEqual(
            len(self.ins.model.items[0].markings),
            4
        )
        self.assertEqual(
            list(map(attrgetter('start'), self.ins.model.items[0].markings)),
            [0, 4, 8, 12],
        )
        self.assertEqual(
            list(map(attrgetter('end'), self.ins.model.items[0].markings)),
            [4, 8, 12, 16],
        )

    @check_slot_failure
    def test_move_interval(self):
        self.ins.load_series(self.df_timeseries)
        self.ins.view.move_interval()
        self.ins.view.move_interval(direction='left')

    @check_slot_failure
    def test_set_marking_label(self):
        self.ins.view.set_marking_label(Labels.DISCARD)

    @check_slot_failure
    def test_remove_selected_list_items(self):
        self.ins.load_series(self.df_timeseries)
        self.ins.view.list_view.setSelectionMode(
            QtWidgets.QAbstractItemView.MultiSelection  # Required for selection in test
        )
        self.ins.view.list_view.selectRow(0)
        self.ins.view.list_view.selectRow(1)
        self.ins.view.remove_selected_list_items()
        self.assertEqual(self.ins.model.items, [])

    @check_slot_failure
    def test_maximize_display_interval(self):
        self.ins.load_series(self.df_timeseries)
        self.ins.view.outline_view.display_maximal_interval()

    @check_slot_failure
    def test_set_label_action(self):
        self.ins.view.actions['label_discard'].trigger()
    