# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeosysPluginDockWidget
                                 A QGIS plugin
 Discover, request and use aggregate imagery products based on landsat-8,
 Sentinel 2 and other sensors from within QGIS, using the GEOSYS API.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2019-03-11
        git sha              : $Format:%H$
        copyright            : (C) 2019 by Kartoza (Pty) Ltd
        email                : andre@kartoza.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QSettings

from qgis.core import QgsProject

from geosys.bridge_api.definitions import INSEASON_MAP_PRODUCTS, SENSORS
from geosys.utilities.gui_utilities import (
    add_ordered_combo_item, layer_icon, is_polygon_layer, layer_from_combo)
from geosys.utilities.resources import get_ui_class

FORM_CLASS = get_ui_class('geosys_dockwidget_base.ui')


class GeosysPluginDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(GeosysPluginDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://doc.qt.io/qt-5/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        # Save reference to the QGIS interface and parent
        self.iface = iface
        self.parent = parent
        self.settings = QSettings()
        self.max_stacked_widget_index = self.stacked_widget.count() - 1
        self.current_stacked_widget_index = 0

        # Input values
        self.layer = None
        self.map_product = None
        self.sensor = None
        self.start_date = None
        self.end_date = None

        # Flag used to prevent recursion and allow bulk loads of layers to
        # trigger a single event only
        self.get_layers_lock = False

        # Set button connectors
        self.setup_button_connectors()

        # Populate layer combo box
        self.connect_layer_listener()

        # Populate map product combo box
        self.populate_map_products()

        # Populate sensor combo box
        self.populate_sensors()

        # Set default behaviour
        self.help_push_button.setEnabled(False)
        self.back_push_button.setEnabled(False)
        self.next_push_button.setEnabled(True)
        self.stacked_widget.setCurrentIndex(self.current_stacked_widget_index)

    def populate_sensors(self):
        """Obtain a list of sensors from Bridge API definition."""
        for sensor in SENSORS:
            add_ordered_combo_item(
                self.sensor_combo_box, sensor['name'], sensor['key'])

    def populate_map_products(self):
        """Obtain a list of map products from Bridge API definition."""
        for map_product in INSEASON_MAP_PRODUCTS:
            add_ordered_combo_item(
                self.map_product_combo_box,
                map_product['name'],
                map_product['key'])

    def show_help(self):
        """Open the help dialog."""
        # noinspection PyTypeChecker
        pass  # not implemented yet

    def show_previous_page(self):
        """Open previous page of stacked widget."""
        if self.current_stacked_widget_index > 0:
            self.current_stacked_widget_index -= 1
            self.stacked_widget.setCurrentIndex(
                self.current_stacked_widget_index)
            self.next_push_button.setEnabled(True)
        if self.current_stacked_widget_index == 0:
            self.back_push_button.setEnabled(False)

    def show_next_page(self):
        """Open next page of stacked widget."""
        if self.current_stacked_widget_index < self.max_stacked_widget_index:
            self.current_stacked_widget_index += 1
            self.stacked_widget.setCurrentIndex(
                self.current_stacked_widget_index)
            self.back_push_button.setEnabled(True)
        if self.current_stacked_widget_index == self.max_stacked_widget_index:
            self.next_push_button.setEnabled(False)

    def get_layers(self, *args):
        """Obtain a list of layers currently loaded in QGIS.

        Only **polygon vector** layers will be added to the layers list.

        :param *args: Arguments that may have been passed to this slot.
            Typically a list of layers, but depends on which slot or function
            called this function.
        :type *args: list

        ..note:: \*args is only used for debugging purposes.
        """
        _ = args  # NOQA
        # Prevent recursion
        if self.get_layers_lock:
            return

        # Map registry may be invalid if QGIS is shutting down
        project = QgsProject.instance()
        canvas_layers = self.iface.mapCanvas().layers()
        # MapLayers returns a QMap<QString id, QgsMapLayer layer>
        layers = list(project.mapLayers().values())

        self.get_layers_lock = True

        # Make sure this comes after the checks above to prevent signal
        # disconnection without reconnection.
        self.block_signals()
        self.geometry_combo_box.clear()

        for layer in layers:
            # show only active layers
            if layer not in canvas_layers or not is_polygon_layer(layer):
                continue

            layer_id = layer.id()
            title = layer.title() or layer.name()
            icon = layer_icon(layer)

            add_ordered_combo_item(
                self.geometry_combo_box, title, layer_id, icon=icon)

        self.unblock_signals()
        # Note: Don't change the order of the next two lines otherwise there
        # will be a lot of unneeded looping around as the signal is handled
        self.connect_layer_listener()
        self.get_layers_lock = False

    def connect_layer_listener(self):
        """Establish a signal/slot to listen for layers loaded in QGIS.

        ..seealso:: disconnect_layer_listener
        """
        project = QgsProject.instance()
        project.layersWillBeRemoved.connect(self.get_layers)
        project.layersAdded.connect(self.get_layers)
        project.layersRemoved.connect(self.get_layers)

        self.iface.mapCanvas().layersChanged.connect(self.get_layers)

    # pylint: disable=W0702
    def disconnect_layer_listener(self):
        """Destroy the signal/slot to listen for layers loaded in QGIS.

        ..seealso:: connect_layer_listener
        """
        project = QgsProject.instance()
        project.layersWillBeRemoved.disconnect(self.get_layers)
        project.layersAdded.disconnect(self.get_layers)
        project.layersRemoved.disconnect(self.get_layers)

        self.iface.mapCanvas().layersChanged.disconnect(self.get_layers)

    def setup_button_connectors(self):
        """Setup signal/slot mechanisms for dock buttons."""
        self.help_push_button.clicked.connect(self.show_help)
        self.back_push_button.clicked.connect(self.show_previous_page)
        self.next_push_button.clicked.connect(self.show_next_page)

    def unblock_signals(self):
        """Let the combos listen for event changes again."""
        self.geometry_combo_box.blockSignals(False)

    def block_signals(self):
        """Prevent the combos and dock listening for event changes."""
        self.disconnect_layer_listener()
        self.geometry_combo_box.blockSignals(True)

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()
