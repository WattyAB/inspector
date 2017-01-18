from __future__ import print_function, division

import logging
logger = logging.getLogger('modl')

import time

import numpy as np
import pandas as pd

from pandas.tseries.frequencies import to_offset
from datetime import datetime, timedelta
from operator import attrgetter, itemgetter

from PyQt4.QtCore import pyqtSignal, Qt, QObject, pyqtBoundSignal
from PyQt4.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush

from constants import (
    COLORS,
    DATA_ALPHA,
    LABEL_COLOR_MAP,
    Labels,
    DEFAULT_GAP_LIMIT,
)

XAXIS_TIME = 'time'
XAXIS_NUMBER = 'number'

class Model(QObject):
    """
    Contains state of current loaded items (data), and exposes methods (slots)
    and signals for manipulating the items.
    """
    sig_item_added = pyqtSignal(object)
    sig_item_removed = pyqtSignal(object)
    sig_marking_added = pyqtSignal(object, object)
    sig_marking_removed = pyqtSignal(object, object)
    sig_save_markings = pyqtSignal(object, object)
    sig_item_interval_tagged = pyqtSignal(object, object, object, object)
    sig_load_markings = pyqtSignal(object, object, object)
    sig_marking_label_updated = pyqtSignal(object)

    @property
    def signals(self):
        """Return attribute signals having 'sig_' as their prefix"""
        signals = {}
        for attrname in dir(self):
            if (attrname.startswith('sig_') and
                    isinstance(getattr(self, attrname), pyqtBoundSignal)):
                signals[attrname] = getattr(self, attrname)
        return signals

    def __init__(self):
        super(Model, self).__init__()
        self.items = []
        self.item_model = QStandardItemModel(self)
        self.current_label = None
        self.xaxis_unit = None # Default value, will be set upon first data
        self.total_items_ever_added = 0

    def set_current_label(self, value):
        if value not in LABEL_COLOR_MAP:
            raise ValueError('unknown label {}'.format(value))
        else:
            self.current_label = value

    def add_dataitem(self, series, name=None, metadata=None):
        """
        Add dataitem to model

        Parameters
        ----------
        series : pandas.Series
        name : object | str | None
        """
        row_idx = min(len(self.items), len(COLORS)) if self.items else 0
        if not isinstance(series, pd.Series):
            logger.error('Cannot add item of type {}: {}'
                         ''.format(type(series), str(series)[:100]))
            return
        if name is None:
            if series.name is None:
                name = '{} - {}'.format(COLORS[row_idx], len(series))
                logger.warn('Found no name for series, using color and '
                            'number of values: "{}"'.format(name))
            else:
                series.name = str(series.name)
                name = series.name
        name = str(name)
        if series.empty:
            logger.error('series {} is empty, cannot add to view'.format(name))
            return

        # Set xaxis_unit variable if this is the first data ever added
        if self.total_items_ever_added == 0:
            if isinstance(series.index, pd.DatetimeIndex):
                self.xaxis_unit = XAXIS_TIME
            else:
                self.xaxis_unit = XAXIS_NUMBER

        if isinstance(series.index, pd.DatetimeIndex):
            if not self.xaxis_unit_is_time():
                logger.warning("Cannot add series with datetimeindex when "
                               "x-axis type is not datetime")
                return
        elif self.xaxis_unit_is_time():
            logger.warning("Cannot add series without datetimeindex when "
                           "x-axis type is datetime")
            return

#       NOTE: Item color examples: http://ynonperek.com/q.t-mvc-customize-items
        item_color = QColor(COLORS[row_idx])
        item_color.setAlphaF(DATA_ALPHA)

        item = DataItem(series, name, metadata=metadata)
        item.setCheckState(Qt.Checked)
        item.setCheckable(True)

        self.items.append(item)
        self.total_items_ever_added += 1

        colorpatch_item = QStandardItem('')
        colorpatch_item.setData(
            QBrush(item_color),
            Qt.BackgroundColorRole
        )

        self.item_model.setItem(row_idx, 0, colorpatch_item)
        self.item_model.setItem(row_idx, 1, item)

        self.sig_item_added.emit(item)

    def remove_dataitem(self, item):
        """
        Remove dataitem from model
        """
        self.items.remove(item)
        self.item_model.removeRow(item.row())
        self.sig_item_removed.emit(item)

    def remove_marking(self, item, marking):
        item.remove_marking(marking)
        self.sig_marking_removed.emit(item, marking)
        logger.info(
            "Removed '{name}' {start} <==> {end} ({td}) {label}  | note: {note}"
            "".format(
                name=item.name,
                label=marking.label,
                start=marking.start,
                end=marking.end,
                td=marking.end - marking.start,
                note=marking.note
            )
        )

    def tag_items(self, tag, only_visible):
        for item in self.get_items(only_visible=only_visible):
            self.tag_full_item_interval(item, tag=tag)

    def tag_full_item_interval(self, item, tag):
        self.sig_item_interval_tagged.emit(
            item.metadata,
            item.series.first_valid_index(),
            item.series.last_valid_index(),
            tag,
        )

    def tag_items_between_outer_markings(self, tag, only_visible):
        for item in self.get_items(only_visible=only_visible):
            self.tag_item_interval_between_outer_markings(item, tag=tag)

    def tag_item_interval_between_outer_markings(self, item, tag):
        if not item.markings:
            return
        start = min(map(attrgetter('start'), item.markings))
        end = max(map(attrgetter('end'), item.markings))
        self.sig_item_interval_tagged.emit(item.metadata, start, end, tag)

    def remove_rows(self, rows):
        for row_idx in reversed(sorted(rows)):
            item = self.item_model.item(row_idx, 1)
            self.remove_dataitem(item)

    def set_items_visible(self, how='invert'):
        for item in self.items:
            if how == 'invert':
                item.setCheckState(
                    Qt.Unchecked if item.checkState() else Qt.Checked
                )
            elif isinstance(how, bool):
                item.setCheckState(Qt.Checked if how else Qt.Unchecked)
            else:
                raise ValueError('unknown value for argument: {}'.format(how))

    def visible_items(self):
        """
        Returns:
        --------
        [DataItem]
        """
        return filter(attrgetter('visible'), self.items)

    def xaxis_unit_is_time(self):
        return self.xaxis_unit == XAXIS_TIME

    def get_items(self, only_visible=False):
        return (self.visible_items() if only_visible else self.items)

    def save_markings(self, only_visible=True):
        changed = []
        deleted = []
        for item in (self.visible_items() if only_visible else self.items):
            changed.append((item.metadata, item.markings))
            deleted.append((item.metadata, item.deleted_markings))
        self.sig_save_markings.emit(changed, deleted)

    def _filter_matching_metadata(self, metadata, items):
        keys = metadata.keys()
        keys_set = set(keys)
        values = tuple(metadata.values())
        matching_items = []
        for item in items:
            if item.metadata and keys_set.issubset(item.metadata.keys()):
                if tuple(itemgetter(*keys)(item.metadata)) == values:
                    matching_items.append(item)

        return matching_items

    def new_markings_from_description(self, markings, marking_metadata):
        """
        :param markings: [{}]
            Example:
        :param marking_metadata: dict
            Example: {'super_id': 3, 'sub_id': '000D55667788']
        """
        if len(marking_metadata) == 0:
            logger.error("Won't add marking if not item metadata is given "
                         "and matches some dataitem present. "
                         "({})".format(markings[:1]))
            return
        matching_items = self._filter_matching_metadata(
            marking_metadata,
            self.items
        )
        for item in matching_items:
            for marking in markings:
                self.new_marking_for_item(
                    item,
                    *itemgetter('start', 'end', 'label', 'note')(marking)
                )

    def load_markings(self, only_visible=True):
        for item in  (self.visible_items() if only_visible else self.items):
            # Supply listeners (plugins) with metadata to identify data,
            # and start & end values to allow them to filter markings properly
            self.sig_load_markings.emit(
                item.metadata,
                item.series.index[0],
                item.series.index[-1],
            )

    def apply_on_visible(self, callback):
        for item in self.visible_items():
            callback(item.series, item.metadata)

    def new_marking_for_item(self, item, start, end, label, note=None):
        mark = Marking(start, end, label, note=note)
        item.add_marking(mark)
        logger.info("Marked {} <==> {} ({})".format(start, end, end - start))
        self.sig_marking_added.emit(item, mark)

    def new_marking(self, start, end, only_visible=True):
        if not self.current_label:
            logger.info('No label mode selected. Select one and try again')
            return
        targets = self.visible_items() if only_visible else self.items
        for item in targets:
            self.new_marking_for_item(item, start, end, self.current_label)

    def update_marking_label(self, marking):
        if not self.current_label:
            logger.error('Current label not set')
            return
        marking.label = self.current_label
        self.sig_marking_label_updated.emit(marking)

    def delete_all_markings_for_visible(self):
        for item in self.visible_items():
            for mark in item.markings[:]:
                self.remove_marking(item, mark)

    def delete_markings_in_interval(self, x0, x1, only_visible=True):
        for item in self.get_items(only_visible=only_visible):
            for mark in item.markings[:]:
                if (x0 < mark.start < x1) and (x0 < mark.end < x1):
                    self.remove_marking(item, mark)


class DataItem(QStandardItem):
    """
    Class containing the data plotted, together with markings made on that
    data and metadata


    Be careful of any attribute name collisions from QStandardItem (ie: .data)
    """
    def __init__(self, series, name, metadata=None):
        """
        :param series: pd.Series
        :param name: str
        :param metadata: dict | None
            'is_total' : True
                Signify that this item contains mains data
            Will be sent alongside with raw data or markings when exporting
            markings or data to, e.g. a database-plugin.
        """
        super(DataItem, self).__init__(name)
        self.series = series
        self.name = name
        self.metadata = metadata or {}
        self.markings = []
        self.deleted_markings = []

    def add_marking(self, marking):
        """
        :param mark: Marking
        """
        self.markings.append(marking)

    def remove_marking(self, marking):
        self.markings.remove(marking)
        self.deleted_markings.append(marking)

    @property
    def visible(self):
        return self.checkState() == Qt.Checked


class Marking(object):
    """
    Lightweight class for storing information about a labeled time interval
    """
    def __init__(self, start, end, label, note=None):
        """
        :param start: datetime | float
        :param end: datetime | float
        :param label: str
        :param note: str | None
        """
        self.start = start
        self.end = end
        self.label = label
        self.note = note

    def to_json(self):
        attrs = ['start', 'end', 'label', 'note']
        return dict([(attr, str(getattr(self, attr))) for attr in attrs])

