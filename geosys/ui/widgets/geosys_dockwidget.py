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
import os

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QSettings, QMutex, QDate
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QLabel, QListWidgetItem, QMessageBox, QApplication

from qgis.core import (
    QgsProject,
    QgsFeatureRequest,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem)
from qgis.PyQt.QtCore import Qt

from geosys.bridge_api.default import (
    SHP_EXT, TIFF_EXT, VECTOR_FORMAT, PNG, ZIPPED_TIFF, ZIPPED_SHP, KMZ,
    VALID_QGIS_FORMAT, YIELD_AVERAGE, YIELD_MINIMUM, YIELD_MAXIMUM,
    ORGANIC_AVERAGE, SAMZ_ZONE, MAX_FEATURE_NUMBERS, DEFAULT_ZONE_COUNT)
from geosys.bridge_api.definitions import (
    ARCHIVE_MAP_PRODUCTS, ALL_SENSORS, SENSORS, DIFFERENCE_MAPS, INSEASON_NDVI,
    INSEASON_EVI)
from geosys.bridge_api.utilities import get_definition
from geosys.ui.widgets.geosys_coverage_downloader import (
    CoverageSearchThread, create_map, create_difference_map)
from geosys.ui.widgets.geosys_itemwidget import CoverageSearchResultItemWidget
from geosys.utilities.gui_utilities import (
    add_ordered_combo_item, layer_icon, is_polygon_layer, layer_from_combo,
    add_layer_to_canvas, reproject, item_data_from_combo)
from geosys.utilities.resources import get_ui_class
from geosys.utilities.settings import setting

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
        self.one_process_work = QMutex()
        self.search_threads = None
        self.max_stacked_widget_index = self.stacked_widget.count() - 1
        self.current_stacked_widget_index = 0

        # Coverage parameters from input values
        self.geometry_wkt = None
        self.map_product = None
        self.sensor_type = None
        self.start_date = None
        self.end_date = None

        # Map creation parameters from input values
        self.yield_average = None
        self.yield_minimum = None
        self.yield_maximum = None
        self.organic_average = None
        self.samz_zone = None
        self.output_map_format = None

        self.selected_coverage_results = []

        # Coverage parameters from settings
        self.crop_type = setting(
            'crop_type', expected_type=str, qsettings=self.settings)
        self.sowing_date = setting(
            'sowing_date', expected_type=str, qsettings=self.settings)
        self.output_directory = setting(
            'output_directory', expected_type=str, qsettings=self.settings)

        # Flag used to prevent recursion and allow bulk loads of layers to
        # trigger a single event only
        self.get_layers_lock = False

        # Set connectors
        self.setup_connectors()

        # Populate layer combo box
        self.connect_layer_listener()

        # Set checkbox label based on MAX_FEATURE_NUMBERS constant
        if MAX_FEATURE_NUMBERS:
            label_format = self.tr('Selected features only (max {} features)')
            self.selected_features_checkbox.setText(
                label_format.format(MAX_FEATURE_NUMBERS))

        # Populate map product combo box
        self.populate_map_products()

        # Populate sensor combo box
        self.populate_sensors()

        # Set default date value
        self.populate_date()

        # Set default behaviour
        self.help_push_button.setEnabled(False)
        self.back_push_button.setEnabled(False)
        self.next_push_button.setEnabled(True)
        self.difference_map_push_button.setVisible(False)
        self.samz_zone_form.setValue(DEFAULT_ZONE_COUNT)
        self.stacked_widget.setCurrentIndex(self.current_stacked_widget_index)
        self.set_next_button_text(self.current_stacked_widget_index)

    def populate_sensors(self):
        """Obtain a list of sensors from Bridge API definition."""
        for sensor in [ALL_SENSORS]+SENSORS:
            add_ordered_combo_item(
                self.sensor_combo_box, sensor['name'], sensor['key'])

    def populate_map_products(self):
        """Obtain a list of map products from Bridge API definition."""
        for map_product in ARCHIVE_MAP_PRODUCTS:
            add_ordered_combo_item(
                self.map_product_combo_box,
                map_product['name'],
                map_product['key'])

    def populate_date(self):
        """Set default value of start and end date to last week."""
        current_date = QDate.currentDate()
        last_week_date = current_date.addDays(-7)
        self.start_date_edit.setDate(last_week_date)
        self.end_date_edit.setDate(current_date)

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

        self.handle_difference_map_button()

    def show_next_page(self):
        """Open next page of stacked widget."""
        # If current page is map creation parameters page, create map without
        # increasing index.
        if self.current_stacked_widget_index == 2:
            self.start_map_creation()
            return

        if self.current_stacked_widget_index < self.max_stacked_widget_index:
            self.current_stacked_widget_index += 1
            self.stacked_widget.setCurrentIndex(
                self.current_stacked_widget_index)
            self.back_push_button.setEnabled(True)

        # If previous page is coverage parameters page and current page is
        # coverage results page, run coverage searcher.
        if self.current_stacked_widget_index == 1:
            self.next_push_button.setEnabled(False)
            self.start_coverage_search()

        self.handle_difference_map_button()

    def set_next_button_text(self, index):
        """Programmatically changed next button text based on current page."""
        text_rule = {
            0: 'Search Map',
            1: 'Next',
            2: 'Create Map'
        }
        self.next_push_button.setText(text_rule[index])

    def handle_difference_map_button(self):
        """Handle difference map button behavior."""
        if self.current_stacked_widget_index == 2:
            # show difference map button only if 2 items are being selected
            if len(self.selected_coverage_results) == 2 and (
                    self.map_product in [
                        INSEASON_NDVI['key'], INSEASON_EVI['key']]):
                self.difference_map_push_button.setVisible(True)
            else:
                self.difference_map_push_button.setVisible(False)
        else:
            self.difference_map_push_button.setVisible(False)

    def update_selection_data(self):
        """Update current selection data."""
        # update data based on selected coverage results
        self.selected_coverage_results = []
        for item in self.coverage_result_list.selectedItems():
            self.selected_coverage_results.append(item.data(Qt.UserRole))

        self.handle_difference_map_button()

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

    def get_map_format(self):
        """Get selected map format from the radio button."""
        widget_data = [
            {
                'widget': self.png_radio_button,
                'data': PNG
            },
            {
                'widget': self.tiff_radio_button,
                'data': ZIPPED_TIFF
            },
            {
                'widget': self.shp_radio_button,
                'data': ZIPPED_SHP
            },
            {
                'widget': self.kmz_radio_button,
                'data': KMZ
            },
        ]
        for wd in widget_data:
            if wd['widget'].isChecked():
                return wd['data']

    def load_layer(self, base_path):
        """Load layer tp QGIS map canvas.

        :param base_path: Base path of the layer.
        :type base_path: str
        """
        if self.output_map_format in VALID_QGIS_FORMAT:
            filename = os.path.basename(base_path)
            if self.output_map_format in VECTOR_FORMAT:
                map_layer = QgsVectorLayer(
                    base_path + SHP_EXT,
                    filename)
            else:
                map_layer = QgsRasterLayer(
                    base_path + TIFF_EXT,
                    filename)
            add_layer_to_canvas(map_layer, filename)

    def validate_map_creation_parameters(self):
        """Check current state of map creation parameters."""
        self.yield_average = self.yield_average_form.value()
        self.yield_minimum = self.yield_minimum_form.value()
        self.yield_maximum = self.yield_maximum_form.value()
        self.organic_average = self.organic_average_form.value()
        self.samz_zone = self.samz_zone_form.value()
        self.output_map_format = self.get_map_format()

        if len(self.selected_coverage_results) == 0:
            return False, 'Please select at least one coverage result.'

        return True, ''

    def validate_coverage_parameters(self):
        """Check current state of coverage parameters."""
        # Get geometry in WKT format
        layer = layer_from_combo(self.geometry_combo_box)
        if not layer:
            # layer is not selected
            return False, 'Layer is not selected.'
        use_selected_features = (
            self.selected_features_checkbox.isChecked() and (
                layer.selectedFeatureCount() > 0))

        # Reproject layer to EPSG:4326
        if layer.crs().authid() != 'EPSG:4326':
            layer = reproject(
                layer, QgsCoordinateReferenceSystem('EPSG:4326'))

        feature_iterator = layer.getFeatures()
        if use_selected_features:
            request = QgsFeatureRequest()
            request.setFilterFids(layer.selectedFeatureIds())
            feature_iterator = layer.getFeatures(request)

        # Handle multi features
        # Merge features into multi-part polygon
        # TODO use Collect Geometries processing algorithm
        geom = None
        for index, feature in enumerate(feature_iterator):
            if index >= MAX_FEATURE_NUMBERS:
                break
            if not feature.hasGeometry():
                continue
            if not geom:
                geom = feature.geometry()
            else:
                geom = geom.combine(feature.geometry())

        if geom:
            self.geometry_wkt = geom.asWkt()
        else:
            # geometry is not valid
            return False, 'Geometry is not valid.'

        # Get map product
        self.map_product = item_data_from_combo(self.map_product_combo_box)
        if not self.map_product:
            # map product is not valid
            return False, 'Map product data is not valid.'

        # Get the sensor type
        self.sensor_type = item_data_from_combo(self.sensor_combo_box)
        if not self.sensor_type:
            # sensor type is not valid
            return False, 'Sensor data is not valid.'
        if self.sensor_type == ALL_SENSORS['key']:
            self.sensor_type = None

        # Get the start and end date
        self.start_date = self.start_date_edit.date().toString('yyyy-MM-dd')
        self.end_date = self.end_date_edit.date().toString('yyyy-MM-dd')

        return True, ''

    def _start_map_creation(self, map_specification):
        """Actual method to run the map creation task.

        :param map_specification: Map specification.
        :type map_specification: dict
        """
        # Place the requested map specification on the top level of
        # coverage result dict. coverage_result['maps'][0] is the requested
        # map specification.
        # example:
        #   before = {
        #       'seasonField': {...},
        #       'image': {...},
        #       'maps': [
        #           {
        #               'type': 'INSEASON_NDVI',
        #               '_links': {...}
        #           }
        #       ],
        #       'coverageType': 'CLEAR'
        #   }
        #
        #   after = {
        #       'seasonField': {...},
        #       'image': {...},
        #       'type': 'INSEASON_NDVI',
        #       '_links': {...},
        #       'coverageType': 'CLEAR',
        #       'maps': [
        #           {
        #               'type': 'INSEASON_NDVI',
        #               '_links': {...}
        #           }
        #       ]
        #   }
        map_specification.update(map_specification['maps'][0])

        if map_specification:
            filename = '{}_{}_{}'.format(
                map_specification['type'],
                map_specification['seasonField']['id'],
                map_specification['image']['date']
            )
            data = {
                YIELD_AVERAGE: self.yield_average,
                YIELD_MINIMUM: self.yield_minimum,
                YIELD_MAXIMUM: self.yield_maximum,
                ORGANIC_AVERAGE: self.organic_average,
                SAMZ_ZONE: self.samz_zone
            }
            is_success, message = create_map(
                map_specification, self.output_directory, filename,
                data=data, output_map_format=self.output_map_format)
            if not is_success:
                QMessageBox.critical(
                    self,
                    'Map Creation Status',
                    'Error creating map. {}'.format(message))
                return

            # Add map to qgis canvas
            self.load_layer(os.path.join(self.output_directory, filename))

    def start_map_creation(self):
        """Map creation starts here."""
        # validate map creation parameters before creating the map
        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            is_success, message = self.validate_map_creation_parameters()
            if not is_success:
                QMessageBox.critical(
                    self,
                    'Map Creation Status',
                    'Error validating map creation parameters. {}'.format(
                        message))
                return

            # start map creation job
            map_product_definition = get_definition(self.map_product)
            if map_product_definition in DIFFERENCE_MAPS:
                # start difference map creation
                pass
            else:
                # start single map creation for each selected
                for coverage_result in self.selected_coverage_results:
                    self._start_map_creation(coverage_result)
        except:
            raise
        finally:
            QApplication.restoreOverrideCursor()

    def start_difference_map_creation(self):
        """Difference Map creation starts here."""
        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

            # Validate map creation parameters
            self.validate_map_creation_parameters()

            # Construct filename
            map_specifications = self.selected_coverage_results
            for map_specification in map_specifications:
                map_specification.update(map_specification['maps'][0])
            map_type_definition = get_definition(map_specifications[0]['type'])
            difference_map_definition = map_type_definition['difference_map']
            filename = '{}_{}_{}_{}'.format(
                difference_map_definition['key'],
                map_specifications[0]['seasonField']['id'],
                map_specifications[0]['image']['date'],
                map_specifications[1]['image']['date']
            )

            # Run difference map creation
            is_success, message = create_difference_map(
                map_specifications, self.output_directory,
                filename, output_map_format=self.output_map_format)

            if not is_success:
                QMessageBox.critical(
                    self,
                    'Map Creation Status',
                    'Error creating map. {}'.format(message))
                return

            # Add map to qgis canvas
            self.load_layer(os.path.join(self.output_directory, filename))
        except:
            raise
        finally:
            QApplication.restoreOverrideCursor()

    def start_coverage_search(self):
        """Coverage search starts here."""
        # validate coverage parameters before run the coverage searcher
        is_success, message = self.validate_coverage_parameters()
        if not is_success:
            self.show_error(
                'Error validating coverage parameters. {}'.format(message))
            return

        if self.search_threads:
            self.search_threads.data_downloaded.disconnect()
            self.search_threads.search_finished.disconnect()
            self.search_threads.stop()
            self.search_threads.wait()
            self.coverage_result_list.clear()

        # start search thread
        searcher = CoverageSearchThread(
            geometry=self.geometry_wkt,
            crop_type=self.crop_type,
            sowing_date=self.sowing_date,
            map_product=self.map_product,
            sensor_type=self.sensor_type,
            end_date=self.end_date,
            start_date=self.start_date,
            mutex=self.one_process_work,
            parent=self.iface.mainWindow())
        searcher.data_downloaded.connect(self.show_coverage_result)
        searcher.error_occurred.connect(self.show_error)
        searcher.search_started.connect(self.coverage_search_started)
        searcher.search_finished.connect(self.coverage_search_finished)
        self.search_threads = searcher
        searcher.start()

    def coverage_search_started(self):
        """Action after search thread started."""
        self.coverage_result_list.clear()
        self.coverage_result_list.insertItem(0, self.tr('Searching...'))

    def coverage_search_finished(self):
        """Action after search thread finished."""
        self.coverage_result_list.takeItem(0)
        coverage_result_empty = self.coverage_result_list.count() == 0
        self.next_push_button.setEnabled(not coverage_result_empty)
        if coverage_result_empty:
            new_widget = QLabel()
            new_widget.setTextFormat(Qt.RichText)
            new_widget.setOpenExternalLinks(True)
            new_widget.setWordWrap(True)
            new_widget.setText(
                u"<div align='center'> <strong>{}</strong> </div>"
                u"<div align='center' style='margin-top: 3px'> {} "
                u"</div>".format(
                    self.tr(u"No results."),
                    self.tr(
                        u"No coverage results available based on given "
                        u"parameters.")))
            new_item = QListWidgetItem(self.coverage_result_list)
            new_item.setSizeHint(new_widget.sizeHint())
            self.coverage_result_list.addItem(new_item)
            self.coverage_result_list.setItemWidget(
                new_item,
                new_widget
            )
        else:
            self.coverage_result_list.setCurrentRow(0)

    def show_coverage_result(self, coverage_map_json, thumbnail_ba):
        """Translate coverage map result into widget item.

        :param coverage_map_json: Result of single map coverage.
            example: {
                "seasonField": {
                    "id": "zgzmbrm",
                    "customerExternalId": "..."
                },
                "image": {
                    "date": "2018-10-18",
                    "sensor": "SENTINEL_2",
                    "weather": "HOT",
                    "soilMaterial": "BARE"
                },
                "maps": [
                    {
                        "type": "INSEASON_NDVI",
                        "_links": {
                            "self": "the_url",
                            "worldFile": "the_url",
                            "thumbnail": "the_url",
                            "legend": "the_url",
                            "image:image/png": "the_url",
                            "image:image/tiff+zip": "the_url",
                            "image:application/shp+zip": "the_url",
                            "image:application/vnd.google-earth.kmz": "the_url"
                        }
                    }
                ],
                "coverageType": "CLEAR"
            }
        :type coverage_map_json: dict

        :param thumbnail_ba: Thumbnail image data in byte array format.
        :type thumbnail_ba: QByteArray
        """
        if coverage_map_json:
            custom_widget = CoverageSearchResultItemWidget(
                coverage_map_json, thumbnail_ba)
            new_item = QListWidgetItem(self.coverage_result_list)
            new_item.setSizeHint(custom_widget.sizeHint())
            new_item.setData(Qt.UserRole, coverage_map_json)
            self.coverage_result_list.addItem(new_item)
            self.coverage_result_list.setItemWidget(new_item, custom_widget)

        else:
            new_item = QListWidgetItem()
            new_item.setText(self.tr('No results!'))
            new_item.setData(Qt.UserRole, None)
            self.coverage_result_list.addItem(new_item)
        self.coverage_result_list.update()

    def show_error(self, error_message):
        """Show error message as widget item.

        :param error_message: Error message.
        :type error_message: str
        """
        self.coverage_result_list.clear()
        new_widget = QLabel()
        new_widget.setTextFormat(Qt.RichText)
        new_widget.setOpenExternalLinks(True)
        new_widget.setWordWrap(True)
        new_widget.setText(
            u"<div align='center'> <strong>{}</strong> </div>"
            u"<div align='center' style='margin-top: 3px'> {} </div>".format(
                self.tr('Error'), error_message))
        new_item = QListWidgetItem(self.coverage_result_list)
        new_item.setSizeHint(new_widget.sizeHint())
        self.coverage_result_list.addItem(new_item)
        self.coverage_result_list.setItemWidget(new_item, new_widget)

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

    def setup_connectors(self):
        """Setup signal/slot mechanisms for dock elements."""
        # Button connector
        self.help_push_button.clicked.connect(self.show_help)
        self.back_push_button.clicked.connect(self.show_previous_page)
        self.next_push_button.clicked.connect(self.show_next_page)
        self.difference_map_push_button.clicked.connect(
            self.start_difference_map_creation)

        # Stacked widget connector
        self.stacked_widget.currentChanged.connect(self.set_next_button_text)

        # List widget item connector
        self.coverage_result_list.itemSelectionChanged.connect(
            self.update_selection_data)

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
