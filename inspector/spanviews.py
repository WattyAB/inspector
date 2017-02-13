from __future__ import print_function, division

import logging

import pandas as pd

from operator import itemgetter, attrgetter
from collections import defaultdict

from matplotlib.widgets import SpanSelector
from matplotlib.dates import date2num, num2date, DateLocator
from matplotlib.patches import Polygon

from inspector.helpers import pyqtSignal
from matplotlib.backends.qt_compat import QtWidgets, QtCore, QtGui

from inspector.constants import (
    SPAN_ALPHA,
    COLORS,
    DATA_ALPHA,
    LINEWIDTH,
    LABEL_COLOR_MAP,
    XTICK_ROTATION,
    FRACTION_PRESHOWN,
    MINIMUM_Y_RANGE,
)


logger = logging.getLogger('span')


class CompatibleSpanSelector(SpanSelector):
    def ignore(self, event):
        if self.ax.figure.canvas.toolbar.mode != '':
            return True
        else:
            return SpanSelector.ignore(self, event)


class SpanView(QtCore.QObject):
    """
    Baseclass for matplotlib axes supporting dragging of spans
    (outline-view and detail-view)
    Handles coordinate transformations and various object lookup mappings
    """
    sig_redraw_request = pyqtSignal()
    def __init__(self, axes, span_facecolor):
        super(SpanView, self).__init__()
        self.axes = axes
        self.span_plotprops = dict(
            alpha=SPAN_ALPHA,
            facecolor=span_facecolor
        )
        self.selector = CompatibleSpanSelector(
            self.axes,
            self.on_span_select,
            'horizontal',
            useblit=True,
            rectprops=self.span_plotprops.copy(),  # NOTE: copy, will be mutated
        )
        # TODO Use real index-providing datastructure
        self.marking2span = {}
        self.span2marking = {}
        self.span2item = {}
        self.item2spans = defaultdict(lambda: [])
        self.item2line = {}

    def axis_has_datelocator(self, axis):
        return any(map(
            lambda locator: isinstance(locator, DateLocator),
            [axis.get_minor_locator(), axis.get_major_locator()]
        ))

    def from_xaxis(self, value):
        if self.axis_has_datelocator(self.axes.xaxis):
            return num2date(value).replace(tzinfo=None)
        else:
            return value

    def to_xaxis(self, value):
        if self.axis_has_datelocator(self.axes.xaxis):
            return date2num(value)
        else:
            return value

    def get_xlim(self):
        return list(map(self.from_xaxis, self.axes.get_xlim()))

    def set_xlim(self, x0, x1):
        logger.debug('Setting xlim (%s)' %self)
        self.axes.set_xlim(self.to_xaxis(x0), self.to_xaxis(x1))

    def set_ylim(self, y0, y1):
        logger.debug('Setting ylim (%s)' %self)
        self.axes.set_ylim(y0, y1)

    def item_changed(self, item):
        check_state = item.checkState()
        try:
            hash(item)
        except TypeError:
            # NOTE: Why we get non-DataItem items here has
            #       not been investigated thoroughly
            logger.debug('item_changed got non-hashable %s', item)
            return
        line = self.item2line.get(item, None)
        if line and line.get_visible() != check_state:
            self.toggle_visible(item, check_state)

    def toggle_visible(self, item, new_value=None):
        if new_value is not None:
            self.item2line[item].set_visible(new_value)
        else:
            self.item2line[item].set_visible(
                not self.item2line[item].get_visible()
            )
        self.redraw()

    def on_span_select(self, x0, x1):
        raise NotImplementedError('has to be overridden in subclass')

    def make_span(self, x0, x1, color, draw=True, alpha=SPAN_ALPHA):
        logger.debug('Creating span (%s)' %self)
        x0_ordinal, x1_ordinal = list(map(self.to_xaxis, [x0, x1]))
        span = self.axes.axvspan(
            x0_ordinal,
            x1_ordinal,
            color=color,
            alpha=alpha,
            picker=5,
        )
        self.axes.draw_artist(span)
        self.redraw()

        return span

    def redraw(self):
        logger.debug('Requesting redraw (%s)' %self)
        self.sig_redraw_request.emit()

    def data_limits(self):
        seria = [i.series for i in self.items]
        ymin = min([s.min() for s in seria])
        ymax = max([s.max() for s in seria])
        xmin = min([s.index.min() for s in seria])
        xmax = max([s.index.max() for s in seria])
        return (xmin, xmax), (ymin, ymax)

    def remove_item(self, item):
        for span in self.item2spans[item]:
            self.span2item.pop(span)
            marking = self.span2marking.pop(span)
            self.marking2span.pop(marking)
            span.remove()
        self.item2spans.pop(item)
        line = self.item2line.pop(item)
        line.remove()
        self.redraw()

    def add_marking_span(self, item, marking):
        span = self.make_span(
            marking.start,
            marking.end,
            color=LABEL_COLOR_MAP[marking.label],
        )
        self.span2item[span] = item
        self.span2marking[span] = marking
        self.marking2span[marking] = span
        self.item2spans[item].append(span)
        self.item2line[item].add_callback(
            lambda line: span.set_visible(line.get_visible())
        )
        self.redraw()

    def update_span_color(self, mark):
        self.marking2span[mark].set_color(LABEL_COLOR_MAP[mark.label])
        self.redraw()

    def remove_marking_span(self, item, mark):
        span = self.marking2span.pop(mark)
        self.span2marking.pop(span)
        self.span2item.pop(span)
        self.item2spans[item].remove(span)
        span.remove()


class OutlineView(SpanView):
    sig_interval_selected = pyqtSignal(object, object)
    def __init__(self, axes, item_container):
        """
        axes : matplotlib Axes
        item_container : [DataItem]
        """
        super(OutlineView, self).__init__(axes, span_facecolor='blue')
        self.axes.set_title('With no other tool selected, '
                            'press left mouse button and drag')
        self.items = item_container
        self.do_resample_threshold = 8000
        self.resampled_n_points = 2000
        self.current_span = None

    def remove_item(self, item):
        super(OutlineView, self).remove_item(item)
        self.set_axes_limits_from_data()

    def set_axes_limits_from_data(self):
        if not self.items:
            return
        xlim, ylim = self.data_limits()
        self.set_xlim(*xlim)
        self.set_ylim(*ylim)

    def add_item(self, item):
        n_data = len(item.series)
        if n_data < self.do_resample_threshold:
            series = item.series
        elif isinstance(item.series.index, pd.DatetimeIndex):
            if len(item.series) >= 2:
                time_span = (
                    item.series.index[-1] - item.series.index[0]
                ).total_seconds()
                new_period = time_span / self.resampled_n_points
                if time_span / n_data <= 0.1:  # If the avg freq is > 10Hz
                    # Avoid potentially getting <0 * Millis>
                    new_period = max(
                        pd.offsets.Milli(int(new_period * 1000)),
                        pd.offsets.Milli(1)
                    )
                else:
                    new_period = pd.offsets.Second(
                        int(max(new_period, 1))
                    )
                logging.debug('Using new period {} for outline resample'
                              ''.format(new_period))
                series = item.series.resample(new_period).mean()
        else:
            take_every_nth = int(len(item.series) / self.resampled_n_points)
            series = item.series.iloc[::take_every_nth]
        logging.debug(
            'Resampled outline view from {} to {}'.format(
                len(item.series),
                len(series)
            )
        )
        idx = self.items.index(item)
        rgb_tuple = QtGui.QColor(COLORS[min(idx, len(COLORS))]).getRgbF()[:3]
        series.plot(
            ax=self.axes,
            label=item.name,
            x_compat=True,
            picker=5,
            rot=0,
            color=rgb_tuple,
            alpha=DATA_ALPHA,
            linewidth=LINEWIDTH,
        )
        if not self.item2line:
            end_idx = min(50000, len(item.series) // FRACTION_PRESHOWN)
            self.on_span_select(
                self.to_xaxis(item.series.index[0]),
                self.to_xaxis(item.series.index[end_idx])
            )
        self.item2line[item] = self.axes.lines[-1]
        self.set_axes_limits_from_data()
        self.redraw()

    def set_current_span(self, x0, x1):
        if self.current_span is not None:
            self.current_span.remove()
        self.current_span = self.axes.axvspan(x0, x1, **self.span_plotprops)

    def display_maximal_interval(self):
        if not self.items:
            firsts, lasts = [0], [1]
        elif any(map(attrgetter('visible'), self.items)):
            firsts, lasts = zip(*
                [itemgetter(0, -1)(d.series.index) for d in self.items if d.visible]
            )
        else: # Use global data min-max if none are visible
            firsts, lasts = zip(*
                [itemgetter(0, -1)(d.series.index) for d in self.items]
            )
        xmin = self.to_xaxis(min(firsts))
        xmax = self.to_xaxis(max(lasts))
        self.on_span_select(xmin, xmax)

    def on_span_select(self, x0, x1):
        if x0 == x1:
            return

        self.set_current_span(x0, x1)

        xval0 = self.from_xaxis(x0)
        xval1 = self.from_xaxis(x1)
        logger.info("Viewing {} <==> {} ({})".format(xval0, xval1, xval1 - xval0))
        self.sig_interval_selected.emit(xval0, xval1)


class DetailView(SpanView):
    sig_span_selected = pyqtSignal(object, object)
    sig_span_picked = pyqtSignal(object, object, object)
    def __init__(self, axes, item_container):
        super(DetailView, self).__init__(axes, span_facecolor='red')
        self.axes.set_autoscaley_on(False)
        self.items = item_container

    def add_item(self, item):
        if not self.item2line:
            start = item.series.index[0]
            end_idx = min(50000, len(item.series) // FRACTION_PRESHOWN)
            end = item.series.index[end_idx]
        else:
            start, end = self.get_xlim()
        idx = self.items.index(item)
        data_slice = item.series.loc[start:end]
        if data_slice.empty:
            data_slice = item.series.iloc[0:10]
        rgb_tuple = QtGui.QColor(COLORS[min(idx, len(COLORS))]).getRgbF()[:3]
        data_slice.plot(
            ax=self.axes,
            label=item.name,
            x_compat=True,
            picker=5,
            rot=XTICK_ROTATION,
            color=rgb_tuple,
            alpha=DATA_ALPHA,
            linewidth=LINEWIDTH,
        )
        self.item2line[item] = self.axes.lines[-1]
        self.display_interval(start, end)
        self.redraw()

    def toggle_line_drawstyle_steps(self):
        for line in self.item2line.values():
            line.set_drawstyle(
                'default' if line.get_drawstyle() == 'steps' else 'steps'
            )
        self.redraw()

    def toggle_line_vertex_markers(self):
        for line in self.item2line.values():
            line.set_marker('*' if line.get_marker() == 'None' else 'None')
        self.redraw()

    def on_span_select(self, x0, x1):
        if x0 == x1:
            return
        x0_val = self.from_xaxis(x0)
        x1_val = self.from_xaxis(x1)
        self.sig_span_selected.emit(x0_val, x1_val)

    def display_interval(self, x0, x1):
        logger.debug('Displaying interval [%s, %s] (%s)' %(x0,x1,self))
        ymin, ymax = 0, 0
        for item in self.items:
            data_slice = item.series.loc[x0:x1]
            line = self.item2line[item]
            # Extract values as datetime64 instead of pd.Timestamp
            # (in case of datetimeindex, otherwise we can just use .index)
            x_values = data_slice.index.values
            line.set_data(x_values, data_slice)
            if item.visible:
                ymin = min(ymin, data_slice.min())
                ymax = max(ymax, data_slice.max())

        self.set_xlim(x0, x1)
        yspan = max(abs(ymax - ymin), MINIMUM_Y_RANGE)
        self.set_ylim(ymin - yspan * 0.02, ymax + yspan * 0.02)

        self.redraw()

    def on_pick(self, event):
        # Filter any non-Polygons (axvspan:s) or non-visible
        artist = event.artist
        if not isinstance(artist, Polygon) or not artist.get_visible():
            return
        item = self.span2item.get(artist, None)
        if not item:
            logging.error('item for artist unexpectedly not found')
            return
        marking = self.span2marking[artist]
        self.sig_span_picked.emit(item, marking, event)

    def add_marking_span(self, item, marking):
        logger.info('Item: {} Marking: {}'.format(item.name, marking.to_json()))
        super(DetailView, self).add_marking_span(item, marking)