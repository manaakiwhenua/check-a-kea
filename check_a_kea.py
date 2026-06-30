import json
from html import escape
from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QShortcut,
    QAbstractItemView,
    QTableWidgetItem,
)
from qgis.PyQt.QtGui import QBrush, QColor, QFont, QFontDatabase, QIcon, QKeySequence, QMouseEvent
from qgis.PyQt.QtCore import Qt, QSettings, QTimer, QEvent, QPoint, QCoreApplication

import sip  # type: ignore  # QGIS runtime dependency, not resolvable by static analysers

from qgis.core import QgsProject, NULL as QGIS_NULL
from qgis.gui import QgsHighlight, QgsAttributeTableFilterModel, QgsAttributeTableModel

from .core.shortcuts import normalise_key as _normalise_key
from .core.constants import (
    DEFAULT_AUTO_ADVANCE,
    DEFAULT_AUTO_ADVANCE_DELAY,
    DEFAULT_AUTO_IDENTIFY,
    DEFAULT_COMMENT_FIELD,
    DEFAULT_FLASH_CHANGES,
    DEFAULT_FLASH_CHANGES_DELAY,
    DEFAULT_DISPLAY_FIELDS,
    DEFAULT_LAYER_ID,
    DEFAULT_SHORTCUTS,
    DEFAULT_UNVALIDATED_FILTER,
    DEFAULT_VALIDATION_FIELD,
    DEFAULT_ZOOM_BUFFER,
    KEY_AUTO_ADVANCE,
    KEY_AUTO_ADVANCE_DELAY,
    KEY_AUTO_IDENTIFY,
    KEY_COMMENT_FIELD,
    KEY_FLASH_CHANGES,
    KEY_FLASH_CHANGES_DELAY,
    KEY_DISPLAY_FIELDS,
    KEY_LAYER_ID,
    KEY_SHORTCUTS,
    KEY_UNVALIDATED_FILTER,
    KEY_VALIDATION_FIELD,
    KEY_ZOOM_BUFFER,
    QGSPROJECT_SCOPE,
    QSETTINGS_GROUP,
)
from .core.dock import DockMixin
from .core.layer_utils import get_feature_ids
from .core.rendering import kbd_table
from .core.session import ValidationSession
from .core.utils import tr
from .core.widgets import ConfigDialog


class CheckAKea(DockMixin):
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.action = None
        self.dock = None

        self.attribute_table = None
        self.status_label = None
        self.footer_label = None
        self.comment_section_widget = None

        self.validation_controls_widget = None
        self.comment_box = None
        self._comment_save_timer = None

        self.session = None
        self._programmatic_selection = False

        self.histogram_widget = None

        self.highlight = None
        self.shortcuts = []
        self._focus_guard = None
        self._last_feature_values = {}
        self._flash_generation = 0

        self.plugin_dir = Path(__file__).parent
        self.config = self.load_config()

        self._translator = None
        self._load_translator()

    # ------------------------------------------------------------------ config

    def load_config(self):
        project = QgsProject.instance()
        settings = QSettings()
        g = QGSPROJECT_SCOPE
        qs = QSETTINGS_GROUP

        shortcuts_json, _ = project.readEntry(g, KEY_SHORTCUTS, "")
        try:
            shortcuts = (
                json.loads(shortcuts_json) if shortcuts_json else DEFAULT_SHORTCUTS
            )
        except (json.JSONDecodeError, ValueError):
            shortcuts = DEFAULT_SHORTCUTS

        return {
            KEY_LAYER_ID: project.readEntry(g, KEY_LAYER_ID, DEFAULT_LAYER_ID)[0],
            KEY_VALIDATION_FIELD: project.readEntry(
                g, KEY_VALIDATION_FIELD, DEFAULT_VALIDATION_FIELD
            )[0],
            KEY_COMMENT_FIELD: project.readEntry(
                g, KEY_COMMENT_FIELD, DEFAULT_COMMENT_FIELD
            )[0],
            KEY_UNVALIDATED_FILTER: project.readEntry(
                g, KEY_UNVALIDATED_FILTER, DEFAULT_UNVALIDATED_FILTER
            )[0],
            KEY_SHORTCUTS: shortcuts,
            KEY_DISPLAY_FIELDS: json.loads(
                project.readEntry(g, KEY_DISPLAY_FIELDS, "[]")[0] or "[]"
            ),
            KEY_ZOOM_BUFFER: settings.value(
                f"{qs}/{KEY_ZOOM_BUFFER}", DEFAULT_ZOOM_BUFFER, type=int
            ),
            KEY_AUTO_ADVANCE: settings.value(
                f"{qs}/{KEY_AUTO_ADVANCE}", DEFAULT_AUTO_ADVANCE, type=bool
            ),
            KEY_AUTO_ADVANCE_DELAY: settings.value(
                f"{qs}/{KEY_AUTO_ADVANCE_DELAY}", DEFAULT_AUTO_ADVANCE_DELAY, type=int
            ),
            KEY_AUTO_IDENTIFY: settings.value(
                f"{qs}/{KEY_AUTO_IDENTIFY}", DEFAULT_AUTO_IDENTIFY, type=bool
            ),
            KEY_FLASH_CHANGES: settings.value(
                f"{qs}/{KEY_FLASH_CHANGES}", DEFAULT_FLASH_CHANGES, type=bool
            ),
            KEY_FLASH_CHANGES_DELAY: settings.value(
                f"{qs}/{KEY_FLASH_CHANGES_DELAY}", DEFAULT_FLASH_CHANGES_DELAY, type=int
            ),
        }

    def save_config(self):
        project = QgsProject.instance()
        settings = QSettings()
        g = QGSPROJECT_SCOPE
        qs = QSETTINGS_GROUP

        project.writeEntry(g, KEY_LAYER_ID, self.config[KEY_LAYER_ID])
        project.writeEntry(g, KEY_VALIDATION_FIELD, self.config[KEY_VALIDATION_FIELD])
        project.writeEntry(g, KEY_COMMENT_FIELD, self.config[KEY_COMMENT_FIELD])
        project.writeEntry(
            g, KEY_UNVALIDATED_FILTER, self.config[KEY_UNVALIDATED_FILTER]
        )
        project.writeEntry(g, KEY_SHORTCUTS, json.dumps(self.config[KEY_SHORTCUTS]))
        project.writeEntry(
            g,
            KEY_DISPLAY_FIELDS,
            json.dumps(self.config.get(KEY_DISPLAY_FIELDS, DEFAULT_DISPLAY_FIELDS)),
        )

        settings.setValue(f"{qs}/{KEY_ZOOM_BUFFER}", self.config[KEY_ZOOM_BUFFER])
        settings.setValue(f"{qs}/{KEY_AUTO_ADVANCE}", self.config[KEY_AUTO_ADVANCE])
        settings.setValue(
            f"{qs}/{KEY_AUTO_ADVANCE_DELAY}", self.config[KEY_AUTO_ADVANCE_DELAY]
        )
        settings.setValue(
            f"{qs}/{KEY_AUTO_IDENTIFY}",
            self.config.get(KEY_AUTO_IDENTIFY, DEFAULT_AUTO_IDENTIFY),
        )
        settings.setValue(
            f"{qs}/{KEY_FLASH_CHANGES}",
            self.config.get(KEY_FLASH_CHANGES, DEFAULT_FLASH_CHANGES),
        )
        settings.setValue(
            f"{qs}/{KEY_FLASH_CHANGES_DELAY}",
            self.config.get(KEY_FLASH_CHANGES_DELAY, DEFAULT_FLASH_CHANGES_DELAY),
        )

    def _load_translator(self):
        from qgis.PyQt.QtCore import QTranslator, QSettings

        locale = QSettings().value("locale/userLocale", "en")[0:2]
        qm_path = self.plugin_dir / "i18n" / f"check_a_kea_{locale}.qm"
        if qm_path.exists():
            self._translator = QTranslator()
            self._translator.load(str(qm_path))
            QCoreApplication.installTranslator(self._translator)

    # ------------------------------------------------------------------ plugin lifecycle

    def initGui(self):
        icon_path = self.plugin_dir / "icon.png"
        if icon_path.exists():
            self.action = QAction(
                QIcon(str(icon_path)), "Check-a-Kea", self.iface.mainWindow()
            )
        else:
            self.action = QAction("Check-a-Kea", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock)
        self.iface.addPluginToMenu("&Check-a-Kea", self.action)
        self.iface.addToolBarIcon(self.action)

        QgsProject.instance().readProject.connect(self._on_project_changed)
        QgsProject.instance().cleared.connect(self._on_project_changed)

    def unload(self):
        QgsProject.instance().readProject.disconnect(self._on_project_changed)
        QgsProject.instance().cleared.disconnect(self._on_project_changed)
        if self._comment_save_timer is not None:
            self._comment_save_timer.stop()
        if self._translator:
            QCoreApplication.removeTranslator(self._translator)
            self._translator = None
        if self._focus_guard:
            QApplication.instance().removeEventFilter(self._focus_guard)
            self._focus_guard = None
        if self.action:
            self.iface.removePluginMenu("&Check-a-Kea", self.action)
            self.iface.removeToolBarIcon(self.action)
        self.clear_shortcuts()
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock = None

    def show_dock(self):
        if self.dock is None:
            self.build_dock()
        self.dock.show()
        self.dock.raise_()

    # ------------------------------------------------------------------ UI state

    def set_validation_controls_visible(self, visible):
        if self.validation_controls_widget is not None:
            self.validation_controls_widget.setVisible(visible)
        if not visible and self.footer_label is not None:
            self.footer_label.setText("")

    # ------------------------------------------------------------------ config actions

    def open_config_dialog(self):
        dialog = ConfigDialog(self.config, parent=self.iface.mainWindow())
        if dialog.exec_() != QDialog.Accepted:
            return
        self.config = dialog.config
        self.save_config()
        self.register_shortcuts()
        self.start_validation()

    def _on_project_changed(self, *_):
        self.clear_active_queue()
        self.config = self.load_config()
        self.register_shortcuts()
        if self.status_label:
            self.status_label.setText(tr("Project changed. Open Setup to begin."))

    # ------------------------------------------------------------------ attribute table

    def refresh_attribute_table(self, feature=None):
        if self.attribute_table is None:
            return
        self.attribute_table.setRowCount(0)
        if not self.session:
            return
        if feature is None:
            feature = self.session.current_feature()
            if feature is None:
                return
        display_fields = set(
            self.config.get(KEY_DISPLAY_FIELDS, DEFAULT_DISPLAY_FIELDS)
        )
        fields_to_show = [
            f for f in self.session.layer.fields() if f.name() in display_fields
        ]
        self.attribute_table.setVisible(bool(fields_to_show))
        if not fields_to_show:
            return
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        flash_color = QColor("#fff9c4")

        self._flash_generation += 1
        gen = self._flash_generation
        changed_rows = []

        self.attribute_table.setRowCount(len(fields_to_show))
        new_values = {}
        for row, field in enumerate(fields_to_show):
            value = feature[field.name()]
            value_str = "" if (value is None or value == QGIS_NULL) else str(value)
            new_values[field.name()] = value_str

            name_item = QTableWidgetItem(field.name())
            value_item = QTableWidgetItem(value_str)
            value_item.setFont(mono)

            if (
                field.name() in self._last_feature_values
                and value_str != self._last_feature_values[field.name()]
            ):
                name_item.setBackground(flash_color)
                value_item.setBackground(flash_color)
                changed_rows.append(row)

            self.attribute_table.setItem(row, 0, name_item)
            self.attribute_table.setItem(row, 1, value_item)

        self._last_feature_values = new_values
        self.attribute_table.resizeRowsToContents()

        if changed_rows and self.config.get(KEY_FLASH_CHANGES, DEFAULT_FLASH_CHANGES):
            delay = self.config.get(KEY_FLASH_CHANGES_DELAY, DEFAULT_FLASH_CHANGES_DELAY)
            def clear_flash(g=gen):
                if self._flash_generation != g:
                    return
                for r in changed_rows:
                    for col in range(2):
                        item = self.attribute_table.item(r, col)
                        if item:
                            item.setBackground(QBrush())
            QTimer.singleShot(delay, clear_flash)

    # ------------------------------------------------------------------ shortcuts

    def register_shortcuts(self):
        self.clear_shortcuts()
        all_shortcuts = [
            (QKeySequence(_normalise_key(key)), lambda k=key: self.apply_validation(k))
            for key in self.config[KEY_SHORTCUTS]
        ] + [
            (QKeySequence(Qt.Key_Left), self.previous_feature),
            (QKeySequence(Qt.Key_Right), self.next_feature),
        ]
        for sequence, handler in all_shortcuts:
            shortcut = QShortcut(sequence, self.iface.mainWindow())
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

    def clear_shortcuts(self):
        for shortcut in self.shortcuts:
            shortcut.setParent(None)
            shortcut.deleteLater()
        self.shortcuts = []

    # ------------------------------------------------------------------ validation queue

    def _connect_selection_signal(self):
        self.session.layer.selectionChanged.connect(self._on_layer_selection_changed)

    def _disconnect_selection_signal(self):
        if self.session:
            try:
                self.session.layer.selectionChanged.disconnect(
                    self._on_layer_selection_changed
                )
            except TypeError:
                pass

    def _on_layer_selection_changed(self, selected_ids, *_):
        if self._programmatic_selection or not self.session:
            return
        if len(selected_ids) != 1:
            return
        fid = selected_ids[0]
        new_index = self.session.index_of(fid)
        if new_index is None:
            return
        self.session.index = new_index
        self.show_current_feature()

    def clear_active_queue(self):
        self._disconnect_selection_signal()
        self.session = None
        self._last_feature_values = {}
        self._flash_generation += 1
        self.clear_highlight()
        self.clear_comment_box()
        self.set_validation_controls_visible(False)

    def start_validation(self):
        layer_id = self.config.get(KEY_LAYER_ID, "")
        layer = QgsProject.instance().mapLayer(layer_id) if layer_id else None

        if not layer:
            if self.status_label:
                self.status_label.setText(
                    tr("No layer configured. Open Setup to begin.")
                )
            self.set_validation_controls_visible(False)
            return

        validation_field = self.config[KEY_VALIDATION_FIELD]
        if validation_field not in [f.name() for f in layer.fields()]:
            if self.status_label:
                self.status_label.setText(
                    tr(
                        "Field '{}' not found in layer. Open Setup to reconfigure."
                    ).format(escape(validation_field))
                )
            self.set_validation_controls_visible(False)
            return

        if not layer.isEditable():
            layer.startEditing()

        feature_ids = get_feature_ids(layer, self.config)
        if not feature_ids:
            if self.status_label:
                self.status_label.setText(tr("No features found for validation."))
            self.clear_highlight()
            self.clear_comment_box()
            self.set_validation_controls_visible(False)
            return

        self.session = ValidationSession(layer, feature_ids)
        self._connect_selection_signal()
        self.set_validation_controls_visible(True)
        self._update_comment_visibility()
        self.show_current_feature()

    def refresh_histogram(self):
        if not self.session or self.histogram_widget is None:
            return
        counts = self.session.validation_counts(self.config[KEY_VALIDATION_FIELD])
        self.histogram_widget.update_data(counts)

    # ------------------------------------------------------------------ feature display

    def show_current_feature(self):
        if not self.session:
            return
        self.session.clamp_index()
        feature = self.session.current_feature()
        if feature is None:
            self.status_label.setText(tr("Could not load feature."))
            return

        fid = self.session.current_fid
        self._programmatic_selection = True
        self.session.layer.selectByIds([fid])
        self._programmatic_selection = False
        QTimer.singleShot(0, self._scroll_attribute_table_to_selection)
        self.zoom_to_feature(feature)
        self.highlight_feature(feature)
        self.load_comment_for_feature(feature)
        if self.config.get(KEY_AUTO_IDENTIFY, DEFAULT_AUTO_IDENTIFY):
            self._auto_identify_feature(feature)
        self.refresh_attribute_table(feature)

        validation_field = self.config[KEY_VALIDATION_FIELD]
        current_value = feature[validation_field]
        field_is_null = current_value is None or current_value == QGIS_NULL
        active_value = None if field_is_null else str(current_value)

        attr_fids = self._get_ordered_fids_from_attr_table()
        if attr_fids is not None:
            session_set = set(self.session.feature_ids)
            ordered = [f for f in attr_fids if f in session_set]
            try:
                display_pos = ordered.index(fid) + 1
                display_total = len(ordered)
            except ValueError:
                display_pos = self.session.index + 1
                display_total = len(self.session)
        else:
            display_pos = self.session.index + 1
            display_total = len(self.session)

        self.footer_label.setText(
            f'<table width="100%"><tr>'
            f'<td>{tr("Feature {} of {}").format(display_pos, display_total)}</td>'
            f'<td align="right">FID: {fid}</td>'
            f"</tr></table>"
        )
        self.status_label.setText(
            f"<h4 style='margin: 4px 0;'>{tr('Keyboard shortcuts')}</h4>"
            f"{kbd_table(list(self.config[KEY_SHORTCUTS].items()), active_value=active_value, null_active=field_is_null)}"
        )

    def _scroll_attribute_table_to_selection(self):
        if not self.session:
            return
        fid = self.session.current_fid
        for widget in QApplication.instance().allWidgets():
            if not hasattr(widget, "model") or not hasattr(widget, "scrollTo"):
                continue
            try:
                raw = widget.model()
                if raw is None:
                    continue
                if raw.metaObject().className() != "QgsAttributeTableFilterModel":
                    continue
                model = sip.wrapinstance(
                    sip.unwrapinstance(raw), QgsAttributeTableFilterModel
                )
                if model.layer().id() != self.session.layer.id():
                    continue
                index = model.fidToIndex(fid)
                if index.isValid():
                    widget.scrollTo(index, QAbstractItemView.PositionAtCenter)
            except Exception:
                pass

    # ------------------------------------------------------------------ identify / comment visibility

    def _update_comment_visibility(self):
        if self.comment_section_widget is None:
            return
        self.comment_section_widget.setVisible(
            bool(self.config.get(KEY_COMMENT_FIELD, ""))
        )

    def _auto_identify_feature(self, feature):
        if not self.session or feature is None:
            return
        geom = feature.geometry()
        if geom is None or geom.isNull():
            return
        canvas = self.iface.mapCanvas()
        map_point = geom.pointOnSurface().asPoint()
        ct = canvas.getCoordinateTransform()
        canvas_pt = ct.transform(map_point.x(), map_point.y())
        qpoint = QPoint(int(canvas_pt.x()), int(canvas_pt.y()))
        self.iface.actionIdentify().trigger()
        viewport = canvas.viewport()
        QApplication.sendEvent(
            viewport,
            QMouseEvent(
                QEvent.MouseButtonPress,
                qpoint,
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        QApplication.sendEvent(
            viewport,
            QMouseEvent(
                QEvent.MouseButtonRelease,
                qpoint,
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )

    # ------------------------------------------------------------------ zoom / highlight

    def zoom_to_feature(self, feature):
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            return
        extent = geom.boundingBox()
        buffer_percent = self.config.get(KEY_ZOOM_BUFFER, 30)
        extent.scale(1 + buffer_percent / 100)
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def highlight_feature(self, feature):
        self.clear_highlight()
        self.highlight = QgsHighlight(
            self.canvas, feature.geometry(), self.session.layer
        )
        self.highlight.setWidth(3)
        self.highlight.show()

    def clear_highlight(self):
        if self.highlight:
            self.highlight.hide()
            self.highlight = None

    # ------------------------------------------------------------------ comment

    def load_comment_for_feature(self, feature):
        if self.comment_box is None:
            return
        comment_field = self.config.get(KEY_COMMENT_FIELD, "comment")
        field_index = self.session.layer.fields().indexOf(comment_field)
        self.comment_box.blockSignals(True)
        if field_index == -1:
            self.comment_box.setPlainText("")
            self.comment_box.setEnabled(False)
            self.comment_box.setPlaceholderText(
                tr("Comment field '{}' does not exist.").format(comment_field)
            )
        else:
            comment_value = feature[comment_field]
            self.comment_box.setPlainText(
                ""
                if (comment_value is None or comment_value == QGIS_NULL)
                else str(comment_value)
            )
            self.comment_box.setEnabled(True)
            self.comment_box.setPlaceholderText(
                tr("Write an optional comment for this feature...")
            )
        self.comment_box.blockSignals(False)

    def clear_comment_box(self):
        if self.comment_box is None:
            return
        self.comment_box.blockSignals(True)
        self.comment_box.setPlainText("")
        self.comment_box.blockSignals(False)

    def save_comment_for_current_feature(self):
        if not self.session or self.comment_box is None:
            return
        comment_field = self.config.get(KEY_COMMENT_FIELD, "comment")
        field_index = self.session.layer.fields().indexOf(comment_field)
        if field_index == -1:
            return
        fid = self.session.current_fid
        comment_text = self.comment_box.toPlainText()
        comment_value = comment_text if comment_text else None
        if not self.session.layer.isEditable():
            self.session.layer.startEditing()
        self.session.layer.changeAttributeValue(fid, field_index, comment_value)

    # ------------------------------------------------------------------ navigation

    def apply_validation(self, key):
        if not self.session or self.session.waiting_to_advance:
            return
        if key not in self.config[KEY_SHORTCUTS]:
            return

        validation_value = self.config[KEY_SHORTCUTS][key]
        validation_field = self.config[KEY_VALIDATION_FIELD]

        try:
            success = self.session.write_validation(validation_field, validation_value)
        except ValueError:
            self.status_label.setText(
                tr("Field '{}' does not exist.").format(escape(validation_field))
            )
            return
        if not success:
            self.status_label.setText(
                tr("Could not write '{}' to feature {}.").format(
                    escape(validation_value), self.session.current_fid
                )
            )
            return

        self.save_comment_for_current_feature()

        if self.config.get(KEY_AUTO_ADVANCE, True):
            delay_ms = self.config.get(KEY_AUTO_ADVANCE_DELAY, 100)
            self.session.waiting_to_advance = True
            QTimer.singleShot(delay_ms, self.advance_after_delay)
        else:
            self.show_current_feature()

    def advance_after_delay(self):
        if self.session:
            self.session.waiting_to_advance = False
        self.next_feature()

    def _get_ordered_fids_from_attr_table(self):
        """Return FIDs in the order currently shown in the open attribute table, or None."""
        if not self.session:
            return None
        for widget in QApplication.instance().allWidgets():
            if not hasattr(widget, "model") or not hasattr(widget, "scrollTo"):
                continue
            try:
                raw = widget.model()
                if raw is None:
                    continue
                if raw.metaObject().className() != "QgsAttributeTableFilterModel":
                    continue
                model = sip.wrapinstance(
                    sip.unwrapinstance(raw), QgsAttributeTableFilterModel
                )
                if model.layer().id() != self.session.layer.id():
                    continue
                master = sip.wrapinstance(
                    sip.unwrapinstance(model.masterModel()), QgsAttributeTableModel
                )
                return [
                    master.rowToId(model.mapToSource(model.index(row, 0)).row())
                    for row in range(model.rowCount())
                ]
            except Exception:
                pass
        return None

    def _navigate(self, delta):
        if not self.session or self.session.waiting_to_advance:
            return
        self.save_comment_for_current_feature()

        attr_fids = self._get_ordered_fids_from_attr_table()
        if attr_fids is not None:
            session_set = set(self.session.feature_ids)
            ordered = [f for f in attr_fids if f in session_set]
            try:
                pos = ordered.index(self.session.current_fid)
            except ValueError:
                pass
            else:
                new_pos = pos + delta
                if 0 <= new_pos < len(ordered):
                    self.session.index = self.session.index_of(ordered[new_pos])
                    self.show_current_feature()
                elif delta > 0:
                    self.clear_active_queue()
                    self.status_label.setText(tr("Finished validation queue."))
                return

        if self.session.navigate(delta):
            self.show_current_feature()
        elif delta > 0:
            self.clear_active_queue()
            self.status_label.setText(tr("Finished validation queue."))

    def next_feature(self):
        self._navigate(1)

    def previous_feature(self):
        self._navigate(-1)
