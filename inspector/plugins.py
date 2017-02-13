from __future__ import print_function, division, unicode_literals

import os
import logging
import pandas as pd
import numpy as np

from operator import attrgetter, itemgetter
from itertools import starmap, chain
from datetime import date, datetime, timedelta

from pandas.tseries.frequencies import to_offset
from inspector.constants import CLEANED, LABEL_COLOR_MAP, Labels
from inspector.helpers import print_out, create_action

from matplotlib.backends.qt_compat import QtWidgets, QtCore

from inspector.helpers import pyqtSignal, Qt

from pkg_resources import iter_entry_points


from mock import Mock
MockMarkingsTable = Mock()


# Plugin libraries are expected to install entry points under this group,
# e.g.
# in foolib/setup.py:setup():
#       name='foo-inspector-plugins',
#       ...
#       entry_points={
#           'inspector.plugins': [
#               'foo_inspector_plugins=foo_inspector_plugins.plugin_module',
#           ],
#       },
PLUGINS_RESOURCE_GROUP = 'inspector.plugins'


_discovered_plugins = {}

def all_plugins():
    assert _discovered_plugins  # discover_plugins() should be called first
    return _discovered_plugins


def discover_plugins():
    global _discovered_plugins
    plugins = {}
    def is_strict_subclass(klass, superklass):
        return isinstance(klass, type) \
                and issubclass(klass, superklass) \
                and (klass is not superklass)
    for obj in globals().values():
        if not is_strict_subclass(obj, PluginBase):
            continue
        else:
            plugins[obj.name] = obj
    for entry_point in iter_entry_points(group=PLUGINS_RESOURCE_GROUP):
        module = entry_point.load()
        for objname in dir(module):
            if objname.startswith('__'):
                continue
            else:
                obj = getattr(module, objname)
            desc = {'obj': obj, 'entry_point': entry_point}
            if not is_strict_subclass(obj, PluginBase):
                logging.debug('Object is not a PluginBase, skipping: %s', desc)
                continue
            if not hasattr(obj, 'name'):
                logging.error('Plugin is missing a name atttribute: %s', desc)
                continue
            if obj.name in plugins:
                logging.error('Could not load plugin because of name conflict',
                              desc)
                continue
            plugins[obj.name] = obj
            logging.debug('Discovered plugin: %s', obj.name)

    _discovered_plugins = plugins

    return plugins


def extract_integers(s):
    """Extract any substrings representing integers in string
    Example:
    >>> extract_integers('foo12 34.55bar')
    [12, 34, 55]
    :param s: str
    :return: list[int]
    """
    non_digits_replaced = [c if c.isdigit() else ' ' for c in s]
    return list(map(
        int,
        ''.join(non_digits_replaced).split()
    ))


class PluginBase(QtCore.QObject):
    """Baseclass for all plugins"""

    @property
    def signals(self):
        raise NotImplementedError()

    @property
    def slot_bindings(self):
        raise NotImplementedError()

    def destroy(self):
        pass


class RandomDataGenerator(PluginBase):
    """
    Generates some days worth of random data with 1 minute frequency

    Commandline example:
    --------------------
        $ inspector --RandomGenerator generate '{"days": 2, "n_series":3}'
    """
    name = 'RandomGenerator'
    sig_new_data = pyqtSignal(object, object, object)

    def __init__(self):
        super(RandomDataGenerator, self).__init__()
        self.logger = logging.getLogger(self.name)
        self.actions = [
            create_action(
                'Generate',
                parent=self,
                connect=self.generate
            ),
        ]
        self.cli_actions = {
            'generate': self.generate,
        }

    @property
    def signals(self):
        return {
            'sig_new_data': self.sig_new_data
        }

    @property
    def slot_bindings(self):
        return {}

    def destroy(self):
        pass

    def generate(self, days=None, n_series=1):
        if not days:
            fields = [
                {'type': 'lineedit',
                 'name': 'days',
                 'label': 'Days to generate',
                 'default': '20',
                 'transformer': lambda x: int(x)},
            ]
            values = SimpleDialog.popup_dialog(fields)
            if values is None:
                self.logger.info("Cancelled, no data generated")
                return
            days = values['days']
        for idx in range(n_series):
            index = pd.date_range(
                start=datetime.utcnow() - timedelta(days=days),
                end=datetime.utcnow(),
                freq='1min',
            )
            data = np.random.randn(len(index)) * 100 + 100
            self.sig_new_data.emit(
                pd.Series(index=index, data=data),
                'Random {} days'.format(days),
                {'time_generated': datetime.utcnow(), 'length': len(data)}
            )


class SimpleDialog(QtWidgets.QDialog):
    def __init__(self, field_specs):
        super(SimpleDialog, self).__init__()
        self.layout = QtWidgets.QVBoxLayout(self)
        self.field_specs = field_specs
        self.fields = {}
        for spec in field_specs:
            if spec['type'] == 'lineedit':
                self.add_QLineEdit(spec)
            elif spec['type'] == 'datetimeedit':
                self.add_QDateTimeEdit(spec)
            else:
                raise ValueError('unrecognized spec: %s' % spec)

        # OK and Cancel buttons
        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self
        )
        self.layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def add_QLineEdit(self, spec):
        widget = QtWidgets.QLineEdit()
        self.fields[spec['name']] = widget
        label_text = spec.get('label', spec['name'])
        self.layout.addWidget(
            QtWidgets.QLabel(label_text)
        )
        self.layout.addWidget(widget)
        if 'default' in spec:
            widget.setText(spec['default'])
        if 'autocomplete-list' in spec:
            widget.setCompleter(
                QtWidgets.QCompleter(spec['autocomplete-list'])
            )

    def add_QDateTimeEdit(self, spec):
        widget = QtWidgets.QDateTimeEdit(
            spec.get('default', datetime.utcnow())
        )
        self.fields[spec['name']] = widget
        widget.setTime(QtCore.QTime(0,0,0))
        widget.setCalendarPopup(True)
        label_text = spec.get('label', spec['name'])
        self.layout.addWidget(
            QtWidgets.QLabel(label_text)
        )
        self.layout.addWidget(widget)

    def get_values(self):
        def QString2pyunicode(qs):
            if not isinstance(qs, str):
                return str(qs.toAscii()).decode('utf8')
            else:
                return qs
        identity = lambda x: x
        values = {}
        for spec in self.field_specs:
            if spec['type'] == 'lineedit':
                text = QString2pyunicode(
                    self.fields[spec['name']].text()
                )
                values[spec['name']] = spec.get('transformer', identity)(text)
            elif spec['type'] == 'datetimeedit':
                values[spec['name']] = self.fields[spec['name']].dateTime()\
                                                                .toPyDateTime()
            else:
                raise Exception('unrecognized widget spec: %s' % spec)

        return values

    @staticmethod
    def popup_dialog(field_spec):
        dialog = SimpleDialog(field_spec)
        result = dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            return dialog.get_values()
        else:
            return None


class MarkingsIO(PluginBase):
    sig_new_markings = pyqtSignal(object, object)
    sig_apply_on_visible = pyqtSignal(object)

    name = 'MarkingsIO'

    def __init__(self, db_table=MockMarkingsTable):
        super(MarkingsIO, self).__init__()
        self.logger = logging.getLogger(self.name)
        self.already_loaded_metadatas = []
        self.db_table = db_table
        self.actions = [
            create_action(
                'Auto-mark gaps',
                parent=self,
                connect=self.auto_mark_gaps_prompt,
            ),
        ]

    @property
    def signals(self):
        return {
            'sig_new_markings': self.sig_new_markings,
            'sig_apply_on_visible': self.sig_apply_on_visible
        }

    @property
    def slot_bindings(self):
        return {
            'sig_save_markings': self.save_markings_to_db,
            'sig_load_markings': self.load_markings_from_db,
        }

    def destroy(self):
        pass

    def upsert_markings(self, metadata, markings):
        """

        :param metadata: dict
        :param markings: [Marking]
        """
        self.db_table.upsert_markings(metadata, markings)
        self.logger.info(
            'Updated/inserted {} markings for {}'.format(len(upserts), metadata)
        )

    def delete_markings(self, metadata, markings):
        """
        :param metadata: dict
        :param markings: [Marking]
        """
        if metadata.get('is_total', False):
            self.logger.info("Skipping 'totals': {}".format(metadata))
            return
        start_end_times = [(m.start, m.end) for m in markings]
        self.db_table.delete_markings(metadata, start_end_times)
        if len(start_end_times) > 0:
            self.logger.info(
                "Deleted {} markings for {}".format(len(start_end_times),
                                                    metadata)
            )

    def save_markings_to_db(self, changed, deleted):
        list(starmap(
            self.upsert_markings,
            changed
        ))
        list(starmap(
            self.delete_markings,
            deleted,
        ))

    def load_markings_from_db(self, metadata, start, end, force=False):
        metadata_tuple = tuple(sorted(metadata.items()))
        if not force:
            if metadata_tuple in self.already_loaded_metadatas:
                msg = "Markings have already been loaded from database once " \
                      "for this data ({}).\n" \
                      "Use force=True to load them on top of the previous " \
                      "ones (completely alright if this is for data that was " \
                      "not visible before, but please avoid writing these " \
                      "duplicates to database!".format(metadata_tuple)
                self.logger.info(
                    "{r}{msg}{w}".format(r='\033[91m', msg=msg, w='\033[0m')
                )
                return
        all_markings = self.db_table.get_markings(metadata)

        is_in_range = lambda x: start <= pd.Timestamp(x) <= end
        markings = filter(
            lambda marking: all(map(
                is_in_range,
                [marking['start'], marking['end']]
            )),
            all_markings,
        )
        formatted_markings = list(map(
            lambda m: {f: m[f] for f in ('start', 'end', 'label', 'note')},
            markings
        ))
        self.emit_new_markings(formatted_markings, metadata)

    def emit_new_markings(self, markings, metadata):
        self.sig_new_markings.emit(markings, metadata)
        self.already_loaded_metadatas.append(
            tuple(sorted(metadata.items()))
        )

    def auto_mark_gaps_prompt(self):
        fields = [
            {'type': 'lineedit',
             'name': 'Gap limit (freqstr)',
             'default': '20s'},
            {'type': 'lineedit',
             'name': 'Label',
             'default': Labels.DISCARD}
        ]
        values = SimpleDialog.popup_dialog(fields)
        if values is None:
            self.logger.info("Cancelled, no data fetched")
        else:
            self.sig_apply_on_visible.emit(
                lambda series, metadata: self.auto_mark_gaps(
                    series=series,
                    metadata=metadata,
                    gap_limit=values['Gap limit (freqstr)'],
                    label=values['Label']
                )
            )

    def auto_mark_gaps(self, series, metadata, label, gap_limit='20s'):
        if isinstance(series.index, pd.DatetimeIndex):
            gap_delta = np.timedelta64(to_offset(gap_limit).nanos, 'ns')
        else:
            gap_delta = float(gap_limit)
        if label not in LABEL_COLOR_MAP:
            self.logger.error('Bad label {}'.format(label))
            return

        gap_indices = np.where(
            np.diff(series.index.values) > gap_delta
        )[0]
        markings = []
        for gap_idx in list(gap_indices):
            gap_x0 = series.index[gap_idx]
            gap_x1 = series.index[gap_idx+1]
            if isinstance(series.index, pd.DatetimeIndex):
                gap_x0 = gap_x0.to_datetime()
                gap_x1 = gap_x1.to_datetime()
            markings.append({
                'start': gap_x0,
                'end': gap_x1,
                'label': label,
                'note': None
            })

        self.sig_new_markings.emit(markings, metadata)
