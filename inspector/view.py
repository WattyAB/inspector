from __future__ import print_function, division, unicode_literals

# stdlib imports
import os
import pickle  # Could use cPickle if python2 
import logging
import json
import argparse
import gzip

from time import time
from datetime import datetime
from operator import itemgetter, methodcaller
from numbers import Number
from functools import partial

# 3rd-party imports
import numpy as np
import pandas as pd

# Matplotlib and Qt imports
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.backend_bases import key_press_handler

from matplotlib.backends.qt_compat import QtWidgets, QtCore, QtGui, is_pyqt5

if is_pyqt5():
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg \
                                                            as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT \
                                                            as NavigationToolbar
else:
    from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg \
                                                            as FigureCanvas
    from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT \
                                                            as NavigationToolbar

from inspector.helpers import pyqtSignal, Qt

# Project imports
from inspector.spanviews import DetailView, OutlineView
from inspector.plugins import discover_plugins, all_plugins
from inspector.helpers import print_out, create_action, debug_decorator
from inspector.constants import (
    SPAN_ALPHA,
    LABEL_COLOR_MAP,
    BACKGROUND_COLOR,
    FIG_FACECOLOR,
    CLEANED,
    AXISBG,
    Labels,
)


def msgpack_lz4_to_series(data):
    try:
        import msgpack
        import lz4
    except ImportError:
        logging.info('To load lz4-msgpacked data, '
                     'install packages "python-msgpack" and "lz4"')
        raise
    content = msgpack.loads(lz4.decompress(data))
    series_load = lambda d: pd.Series(
        data=d['values'],
        index=d['index'] if d['index'][-1] <= 1e9 \
                         else pd.DatetimeIndex(d['index']),
        name=d['id']
    )
    seria = list(map(series_load, content))

    return seria


logger = logging.getLogger('view')


class View(QtWidgets.QMainWindow):
    """The main widget where all graphical elements are set up, signals
    are connected to slots, plugins loaded, etc.

    Attributes
    ----------
    avail_slots_by_signal : { signal_name : [ slot_obj ] }
        Plugins may supply a dictionary like { signal_name : signal_obj },
        and entries there will be matched and connected to slots in this dict.
        I.e. this dictionary defines the list of signal names that plugins may
        emit, and the signals will be connected to appropriate slots.
    avail_signals : { signal_name : signal_obj }
        Names of signals which plugins can request their slots being
        connected to. Populated with signals from `model` for now.
        See `View.toogle_plugin` for usage.

    """
    def __init__(self, model, interactive, data=None):
        """
        :param model: model.Model
        :param interactive: bool
            Boolean indicating if we are running in an interactive setting
            such as an ipython session. Helpful for deciding to parse CLI args,
            or not.
        :param data:
            Some type of array container, e.g. pandas.DataFrame,
            see `View.load_seria`

        """
        super(View, self).__init__()
        self.actions = {}
        self.model = model

        self.avail_slots_by_signal = {}
        self.avail_slots_by_signal['sig_new_data'] = [self.model.add_dataitem]
        self.avail_slots_by_signal['sig_new_markings'] = [
            self.model.new_markings_from_description
        ]
        self.avail_slots_by_signal['sig_apply_on_visible'] = [
            self.model.apply_on_visible,
        ]

        self.avail_signals = {}
        # Populate initially with signals from model
        for k, v in self.model.signals.items():
            self.avail_signals[k] = v

        self.draw_timer = QtCore.QTimer()
        self.init_ui()
        self.canvas_redraw()

        if not interactive:
            QtCore.QTimer.singleShot(0, self.parse_sysargs)
        if data is not None:
            logger.debug('Scheduling load-data callback')
            QtCore.QTimer.singleShot(0, lambda: self.load_seria(data))

#         option_list
#         statusbox


    def parse_sysargs(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('files', nargs='*')
        for plugin_name, _ in all_plugins().items():
            parser.add_argument('--%s' %plugin_name, required=False, nargs='*')
        args = parser.parse_args()
        if args.files:
            self.load_files(args.files)
        for plugin_name, _ in all_plugins().items():
            subargs = getattr(args, plugin_name.replace('-','_'))
            if subargs is None or not isinstance(subargs, list):
                continue
            elif len(subargs) > 2:
                logger.error('CLI arguments parsing error: Too many '
                             'arguments: {}'.format(plugin_name, subargs))
                continue
            else:
                self.actions['toggle_plugin_' + plugin_name].trigger()
            if plugin_name not in self.plugins:
                logger.error('Plugin %s unexpectedly not found among loaded '
                             'plugins: %s', plugin_name, self.plugins)
                continue
            if not hasattr(self.plugins[plugin_name], 'cli_actions'):
                if subargs:
                    logger.error(
                        'CLI arguments parsing error: Plugin "{}" '
                        'does not have any CLI actions defined. '
                        'These arguments will be ignored: {}'
                        ''.format(plugin_name, subargs)
                    )
                continue
            if subargs:
                cmd = subargs[0]
                cmd_kwargs = json.loads(subargs[1]) if len(subargs) > 1 else {}
                logger.debug('Calling {}:{} with {}'
                             ''.format(plugin_name, cmd, cmd_kwargs))
                self.plugins[plugin_name].cli_actions[cmd](
                    **cmd_kwargs
                )

    def init_ui(self):
        self.win = QtWidgets.QWidget()
        self.win.setObjectName('window_widget')
        self.win.setStyleSheet("background-color:{};".format(BACKGROUND_COLOR))
        self.setGeometry(300, 300, 1224, 720)

        self.list_view = self.setup_list_view(self.model.item_model)
        logger.debug('Set up done: List view')

        self.marking_label = self.setup_marking_label()

        (
        self.fig,
        self.canvas,
        self.mpl_toolbar,
        ) = self.setup_figure()
        logger.debug('Set up done: Figure')
        (
        self.outline_view,
        self.detail_view,
        ) = self.setup_views(self.fig, self.model.items)
        logger.debug('Set up done: Views')
        self.setup_connections()
        logger.debug('Set up done: Connections')
        # Compose layout
        #
        # Left side
        self.frame_left = QtWidgets.QFrame()
        self.frame_left.setObjectName('frame_left')
        self.grid_left = QtWidgets.QGridLayout()
        self.grid_left.setSpacing(20)
        self.frame_left.setLayout(self.grid_left)
        self.grid_left.addWidget(self.marking_label, 0, 0, 2, 1)
        self.grid_left.addItem(
            QtWidgets.QSpacerItem(1,1),
            2, 0, 1, 1
        )
        self.help_item_model = QtGui.QStandardItemModel()
#         self.help_list = QListView()
        class CustListView(QtWidgets.QListView):
            def sizeHint(self, *args, **kwargs):
                return QtCore.QSize(100, 400)
        self.help_list = CustListView()
        self.help_list.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )
        self.help_list.setModel(self.help_item_model)
        self.grid_left.addWidget(self.help_list, 2, 0, 1, 1)
        self.grid_left.addWidget(self.list_view, 4, 0, 4, 1)

        # Right side
        self.frame_right = QtWidgets.QFrame()
        self.frame_right.setObjectName('frame_right')
        self.frame_right.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.vbox_right = QtWidgets.QVBoxLayout()
        self.frame_right.setLayout(self.vbox_right)
        list(map(
            self.vbox_right.addWidget,
            [self.mpl_toolbar, self.canvas]
        ))

        # Vertical splitter
        self.vsplit = QtWidgets.QSplitter(self.win)
        self.vsplit.addWidget(self.frame_left)
        self.vsplit.addWidget(self.frame_right)
        self.vsplit.setStretchFactor(1, 2)

        self.hbox = QtWidgets.QHBoxLayout()
        self.hbox.addWidget(self.vsplit)
        self.win.setLayout(self.hbox)

#         self.grid = QGridLayout()
#         self.grid.setSpacing(10)
#         self.grid.addWidget(self.marking_label, 0, 0)
# #         self.grid.addWidget(self.list_view, 3, 0, 2, 1)
#         self.grid.addWidget(self.canvas, 1, 2, 4, 6)
#         self.grid.addWidget(self.mpl_toolbar, 0, 2, 1, 6)

#         self.win.setLayout(self.grid)
        self.setCentralWidget(self.win)
        self.setWindowTitle('Inspector')

        self.setup_menus_and_actions()

        self.setup_populate_help_list()

        self.statusBar().showMessage('Ready')
        self.show()

    def setup_menus_and_actions(self):
        self.file_menu = self.menuBar().addMenu('&File')
        self.view_menu = self.menuBar().addMenu('&View')
        self.label_menu = self.menuBar().addMenu('&Label')
        self.setup_all_actions()

        self.plugins = {}
        # TODO plugin enabled state should really live in Model instead
        self.setup_plugin_menus()

    def setup_plugin_menus(self):
        self.plugin_menus = {}
        discover_plugins()
        for name, class_ in sorted(all_plugins().items()):
            menu = self.menuBar().addMenu(name)
            self.actions['toggle_plugin_' + name] = create_action(
                text='Enabled'.format(name),
                parent=self,
                connect_bool=partial(self.toggle_plugin, class_),
                add_to=menu,
                checkable=True,
            )
            self.plugin_menus[name] = menu

    def setup_populate_help_list(self):
        def populate_from_menu(menu):
            for act in menu.actions():
                if hasattr(act, 'short'):
                    shortcut_text = act.short.key().toString()
                else:
                    shortcut_text = ''
                text = '{:s}\t{:s}: {:s}'.format(
                    shortcut_text,
                    menu.title().replace('&',''),
                    act.text().replace('&',''),
                )
                self.help_item_model.appendRow(QtGui.QStandardItem(text))
        for menu_ in [self.file_menu, self.view_menu, self.label_menu]:
            populate_from_menu(menu_)

    def setup_marking_label(self):
        marking_label = QtWidgets.QLabel('Current label-mode: ?')
        marking_label.setAlignment(Qt.AlignCenter)
        marking_label.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.MinimumExpanding,
        )
        return marking_label

    def set_marking_label(self, label):
        logging.debug('Setting marking label to %s %s', self, label)
        color = QtGui.QColor(LABEL_COLOR_MAP.get(label, 'white'))
        color.setAlphaF(SPAN_ALPHA)
        self.marking_label.setStyleSheet(
            "background-color: rgba{};".format(tuple(color.getRgb()))
        )
        self.marking_label.setText('Current label-mode: {}'.format(label))
        self.model.set_current_label(label)

    def setup_all_actions(self):
        self.setup_file_actions()
        self.setup_view_actions()
        self.setup_label_actions()
        logger.debug('All actions set up')

    def setup_label_actions(self):
        key_label_mapping = {
            'b': Labels.BFILL,
            'n': Labels.FFILL,
            'd': Labels.DISCARD,
            'z': Labels.ZERO,
            'j': Labels.GOOD,
            'c': Labels.COMMENT,
            'w': Labels.LINEAR_FILL,
        }
        assert(len(key_label_mapping) == len(LABEL_COLOR_MAP))

        # Have to be careful so that the lambda get redefined each loop:
        # http://martinfitzpatrick.name/article/transmit-extra-data-with-signals-in-pyqt/
        for key, label in key_label_mapping.items():
            logging.debug('Adding action for key -> label %s:%s', key, label)
            if is_pyqt5():
                # NOTE: The reason why the callback gets an extra arg (False)
                #       in pyqt5 is not clear. Could perhaps be found in docs.
                setter_callback = lambda _, lb=label: self.set_marking_label(lb)
            else:
                setter_callback = lambda lb=label: self.set_marking_label(lb)
            self.actions['label_'+label] = create_action(
                '&'+label,
                parent=self,
                shortcut='Ctrl+'+key,
                connect=setter_callback,
                add_to=self.label_menu,
            )

    def setup_file_actions(self):
        self.actions['exit'] = create_action(
            '&Exit',
            parent=self,
            tip='Exit application',
            shortcut='Ctrl+Q',
            icon=QtGui.QIcon('exit.png'),
            connect=QtWidgets.qApp.quit,
            add_to=self.file_menu
        )
        self.actions['remove_interval_markings'] = create_action(
            '&Remove markings in displayed interval',
            parent=self,
            connect=self.delete_visible_markings_in_displayed_interval,
            add_to=self.file_menu,
            shortcut='Ctrl+R'
        )

        self.actions['load_markings'] = create_action(
            '&Load markings for visible series',
            parent=self,
            connect=lambda: self.model.load_markings(only_visible=True),
            add_to=self.file_menu,
        )
        self.actions['save_markings'] = create_action(
            'Save &markings for visible series',
            parent=self,
            connect=lambda: self.model.save_markings(only_visible=True),
            add_to=self.file_menu
        )
        self.actions['save_interval_cleaned'] = create_action(
            'Save visible series as cleaned',
            parent=self,
            connect=lambda: self.model.tag_items(
                tag=CLEANED,
                only_visible=True
            ),
            add_to=self.file_menu,
        )
        self.actions['save_interval_cleaned_between_markings'] = create_action(
            'Save visible series as cleaned between outer markings',
            parent=self,
            connect=lambda: self.model.tag_items_between_outer_markings(
                tag=CLEANED,
                only_visible=True
            ),
            add_to=self.file_menu,
        )

    def setup_view_actions(self):
        create_view_action = partial(
            create_action,
            parent=self,
            add_to=self.view_menu
        )
        self.actions['invert'] = create_view_action(
            '&Invert visible',
            shortcut='i',
            connect=lambda: self.model.set_items_visible(),
        )
        self.actions['hide_all'] = create_view_action(
            '&Hide all',
            shortcut='h',
            connect=lambda: self.model.set_items_visible(how=False),
        )
        self.actions['markers'] = create_view_action(
            'Toggle vertex &markers',
            shortcut='m',
            connect=[self.detail_view.toggle_line_vertex_markers],
        )
        self.actions['markers'] = create_view_action(
            'Toggle &step drawstyle',
            shortcut='s',
            connect=[self.detail_view.toggle_line_drawstyle_steps],
        )
        self.actions['move_left'] = create_view_action(
            'Move &left',
            shortcut=Qt.Key_Minus,
            connect=lambda: self.move_interval('left'),
        )
        self.actions['move_right'] = create_view_action(
            'Move &right',
            shortcut=Qt.Key_Space,
            connect=lambda: self.move_interval('right'),
        )
        self.actions['remove_series'] = create_view_action(
            '&Remove series',
            shortcut=Qt.Key_Delete,
            connect=self.remove_selected_list_items,
        )
        self.actions['maximize_interval'] = create_view_action(
            'M&aximize display interval',
            shortcut=Qt.Key_K,
            connect=self.outline_view.display_maximal_interval,
        )

    def setup_connections(self):
        sources_to_targets = {
            self.draw_timer.timeout: self.canvas_redraw,

            self.list_view.sig_dropped: self.load_files,

            # Data unchecked / added / removed
            self.model.item_model.itemChanged: self.detail_view.item_changed,

            self.model.sig_item_added: [self.detail_view.add_item,
                                        self.outline_view.add_item,
                                        self.add_list_item,],

            self.model.sig_item_removed: [self.detail_view.remove_item,
                                          self.outline_view.remove_item,],

            self.detail_view.sig_redraw_request: self.request_canvas_redraw,

            # New marking chain
            self.detail_view.sig_span_selected: self.model.new_marking,

            self.detail_view.sig_span_picked: self.marking_picked,

            self.outline_view.sig_redraw_request: self.request_canvas_redraw,

            self.model.sig_marking_added: [self.outline_view.add_marking_span,
                                           self.detail_view.add_marking_span],

            self.model.sig_marking_removed: [
                self.outline_view.remove_marking_span,
                self.detail_view.remove_marking_span,
            ],

            self.model.sig_marking_label_updated: [
                self.outline_view.update_span_color,
                self.detail_view.update_span_color,
            ]
        }
        for source, target in sources_to_targets.items():
            targets = target if isinstance(target, list) \
                             else [target]
            for target_i in targets:
                if os.environ.get('PYDEBUG', None):
                    target_i = debug_decorator(target_i, str(target_i.__name__))
                source.connect(target_i)

        # Other connections
        self.canvas.mpl_connect('pick_event', self.detail_view.on_pick)
        self.canvas.mpl_connect('key_press_event', self.on_key_press)

    def setup_list_view(self, item_model):
        list_view = SeriesListView()
        list_view.setModel(item_model)
        list_view.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Expanding
        )
        list_view.setEditTriggers(list_view.NoEditTriggers)
        return list_view

    def setup_figure(self):
        # Figure
        fig = Figure((8.0, 6.0), dpi=90, facecolor=FIG_FACECOLOR)
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        canvas.setFocusPolicy( Qt.ClickFocus )
        canvas.setFocus() # put last?
        toolbar = NavigationToolbar(canvas, parent=self)
        # Since we have only one plot, we can use add_axes
        # instead of add_subplot, but then the subplot
        # configuration tool in the navigation toolbar wouldn't
        # work.
        #
#         self.axes = self.fig.add_subplot(111)
#         self.axes = self.fig.axes

        # Create the navigation toolbar, tied to the canvas
        #

        return fig, canvas, toolbar
#         self.request_canvas_redraw()

    def setup_views(self, fig, items):
        grid_spec = mpl.gridspec.GridSpec(
            2,1,
            height_ratios=[1,2]
        )
        outline_view = OutlineView(
            fig.add_subplot(grid_spec[0], axisbg=AXISBG),
            items
        )
        detail_view = DetailView(
            fig.add_subplot(grid_spec[1], axisbg=AXISBG),
            items
        )
        outline_view.sig_interval_selected.connect(
            detail_view.display_interval
        )
        return outline_view, detail_view

    def resizeEvent(self, resizeEvent):
        self.canvas_redraw()

    def request_canvas_redraw(self):
        self.draw_timer.stop()
        self.draw_timer.start(10)
        logger.debug('Redraw requested at {}'.format(time()))
        self.statusBar().showMessage('Redraw requested at {}'.format(time()))

    def canvas_redraw(self):
        logger.debug('Commencing redraw')
        draw_t0 = time()
        self.fig.subplots_adjust(
            left=0.04,
            right=0.99,
            top=0.96,
            bottom=0.04,
            hspace=0.12
        )
        self.fig.canvas.draw()
        t_diff = time() - draw_t0
        self.draw_timer.stop()
        fps = int(round(1/t_diff))
        status_msg = 'Ready, last draw: {} s ({} fps)'.format(round(t_diff, 2), fps)
        self.statusBar().showMessage(status_msg)
        logger.debug(status_msg)

    def toggle_plugin(self, plugin_class, state):
        if state:
            if plugin_class.name in self.plugins:
                raise Exception('expected {} to be disabled'.format(plugin_class))
            instance = plugin_class()
            if hasattr(instance, 'actions'):
                list(map(
                    self.plugin_menus[plugin_class.name].addAction,
                    instance.actions
                ))
            self.plugins[plugin_class.name] = instance

            # Connect any plugin slots to known signals by name.
            # Currently assumes they can be found in the self.model object.
            for sig, slot in instance.slot_bindings.items():
                if os.environ.get('PYDEBUG', None):
                    slot = debug_decorator(slot, slot.__name__)
                self.avail_signals[sig].connect(slot)
                # We could potentially add the slot here
                # to self.avail_slots_by_signal. If so, we'd also have to remove
                # it/them if we disabled the plugin.
                # This could be solved by not allowing plugin disabling.
                # Also, enablement of plugins would be order-dependant.

            # Connect any plugin signals with known slots by name
            for sig_name, sig in instance.signals.items():
                for slot in self.avail_slots_by_signal.get(sig_name, []):
                    if os.environ.get('PYDEBUG', None):
                        slot = debug_decorator(slot, slot.__name__)
                    sig.connect(slot)
            print_out('Enabled plugin: {}'.format(plugin_class.name))
        else:
            instance = self.plugins.pop(plugin_class.name)
            instance.destroy()
            # TODO disconnect any signals and slots?
            print_out('Disabled plugin: {}'.format(plugin_class.name))

    def load_seria(self, series_container, name=None):
        """

        :param series_container: Series | Dataframe | [float] | {str: Series}
            Also accepts a list of any of the above
            types (will looped over).
        :param name: str | None
        """
        # numpy.ndarray
        if isinstance(series_container, np.ndarray):
            if min(series_container.shape) == 1 or series_container.ndim == 1:
                try:
                    series = pd.Series(series_container)
                except Exception as e:
                    logger.error('Item {}: Could not make into Series: {}'
                                 ''.format(idx, e))
                    return
                self.model.add_dataitem(series, name)
            else:
                logger.error('Unsatisfactory array: %s' %series_container.shape)
                return

        # pandas.Series
        elif isinstance(series_container, pd.Series):
            self.model.add_dataitem(series_container, name)

        # pandas.DataFrame, dict (recursion)
        elif isinstance(series_container, (pd.DataFrame, dict)):
            if 'series' in series_container:
                self.model.add_dataitem(
                    series=series_container.get('series'),
                    name=series_container.get('name', None),
                    metadata=series_container.get('metadata', None)
                )
            else:
                # Check items/iteritems for py2/py3 compatibility
                if hasattr(series_container, 'items'):
                    items = series_container.items()
                else:
                    items =  series_container.iteritems()
                for name, subcontainer in items:
                    self.load_seria(subcontainer, name)

        # tuple or list (call recursively)
        elif isinstance(series_container, (tuple, list)):
            if not series_container:
                logger.debug('series_container empty')
            elif isinstance(series_container[0], Number):
                self.load_seria(np.array(series_container))
            else:
                for item in series_container:
                    self.load_seria(item)
        else:
            logger.error('Could not load object: %s' % str(series_container)[:500])

    def load_files(self, paths):
        for p in paths:
            try:
                self.load_file(p)
            except Exception as err:
                logger.error('Could not load file {}. Unsupported filetype?\n{}'
                             ''.format(p, err.message)
                )

    def load_file(self, path):
        if path.endswith('.gz'):
            open_ = gzip.open
        else:
            open_ = open
        with open_(path, 'r') as fh:
            contents = fh.read()
        self.load_bytes(contents, data_source=path)

    def load_bytes(self, bytestring, data_source=''):
        load_methods = [
             msgpack_lz4_to_series,
             pd.read_msgpack,
             pickle.loads,
        ]
        seria = None
        for loader in load_methods:
            try:
                loaded = loader(bytestring)
            except Exception as err:
                continue
            if isinstance(loaded, pd.Series):
                seria = [loaded]
            elif isinstance(loaded, pd.DataFrame):
                seria = list(map(
                    itemgetter(1),
                    loaded.iteritems()
                ))
            elif isinstance(loaded, list):
                seria = loaded
            else:
                logger.error('Unexpected object found: {:.30}... (using deserializer {}'
                          ''.format(seria, loader))
                return
        if seria is None:
            logger.error('Could not deserialize contents of {} with any of {}'
                      ''.format(data_source, load_methods))
            return

        for idx, series in enumerate(seria):
            if not series.name:
                if os.path.exists(data_source):
                    prefix = os.path.split(data_source)[1]
                else:
                    prefix=data_source
                series.name = '{}_{}'.join(map(str, [prefix, idx]))
            self.model.add_dataitem(series, name=series.name)
            logger.info('Loaded "{n}" ({v} values) from {src}'
                      ''.format(n=series.name, v=len(series), src=data_source))

    def move_interval(self, direction):
        xlim = self.detail_view.axes.get_xlim()
        diff = xlim[1] - xlim[0]
        if direction == 'left':
            new_lim = (xlim[0] - diff, xlim[0])
        elif direction == 'right':
            new_lim = (xlim[1], xlim[1] + diff)
        else:
            raise ValueError('urecognized move direction %s' %direction)
        self.outline_view.on_span_select(*new_lim)

    def selected_list_item_rows(self):
        rows = list(map(
            methodcaller('row'),
            self.list_view.selectionModel().selectedIndexes()
        ))
        # We can get duplicates when clicking the row or by using selectRow()
        return list(set(rows))

    def remove_selected_list_items(self):
        rows = self.selected_list_item_rows()
        self.model.remove_rows(rows)

    def delete_visible_markings_in_displayed_interval(self):
        self.model.delete_markings_in_interval(
            *self.detail_view.get_xlim(),
            only_visible=True
        )
        self.request_canvas_redraw()

    def marking_picked(self, item, marking, event):
        if event.mouseevent.button == 3:
            self.model.update_marking_label(marking)
            action = 'Changing'
            label_text = "'{}'".format(marking.label)
        else:
            if event.mouseevent.key == 'shift':
                self.model.remove_marking(item, marking)
                return
            elif event.mouseevent.key == 'control':
                raise NotImplementedError("changing note for marking not implemented")
            else:
                action = 'Clicked'
                label_text = "'{}'".format(marking.label)

        def fmt_if_datetime(d):
            if isinstance(d, datetime):
                return d.strftime('%Y-%m-%d %H:%M:%S')
            else:
                return d
        logger.info(
            "{action} '{name}' {start} <==> {end} ({td}) {label}  | note: {note}".format(
                action=action,
                name=item.name,
                label=label_text,
                start=fmt_if_datetime(marking.start),
                end=fmt_if_datetime (marking.end),
                td=marking.end - marking.start,
                note=marking.note,
            )
       )

    def add_list_item(self, model_item):
        # We have to resize the color patch column after some items were added
        self.list_view.horizontalHeader().resizeSection(0, 20)

    def on_key_press(self, event):
        logger.debug('you pressed %s' % event.key)
        # implement the default mpl key press events described at
        # http://matplotlib.sourceforge.net/users/navigation_toolbar.html#navigation-keyboard-shortcuts
        key_press_handler(event, self.canvas, self.mpl_toolbar)


class SeriesListView(QtWidgets.QTableView):
    """
    ListView widget configured for accepting drag-n-dropped files
    """
    sig_dropped = pyqtSignal(object)
    def __init__(self):
        super(SeriesListView, self).__init__(None)
        self.setAcceptDrops(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            links = []
            for url in event.mimeData().urls():
                links.append(str(url.toLocalFile()))
            self.sig_dropped.emit(links)
        else:
            event.ignore()

