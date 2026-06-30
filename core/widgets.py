from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtGui import QBrush, QColor, QStandardItem
from qgis.PyQt.QtCore import Qt, QDate, QEvent, QObject, QVariant

from qgis.core import QgsExpression, QgsField, QgsIconUtils, QgsLayerTree, QgsProject, QgsVectorDataProvider, QgsVectorLayer
from qgis.gui import QgsExpressionBuilderDialog

from .shortcuts import shortcut_conflicts
from .constants import (
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
)
from .utils import tr


class CommentFocusGuard(QObject):
    """Redirects focus to the canvas when the user clicks outside the comment box.

    Without this, the comment box keeps keyboard focus and swallows the
    validation shortcut keys.
    """

    def __init__(self, comment_box, canvas):
        super().__init__()
        self._box = comment_box
        self._canvas = canvas

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.MouseButtonPress
            and self._box.hasFocus()
            and isinstance(obj, QWidget)
            and obj is not self._box
            and not self._box.isAncestorOf(obj)
        ):
            self._canvas.setFocus()
        return False


class CheckableComboBox(QComboBox):
    """A combo box whose dropdown items each have a checkbox."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(tr("Select attributes..."))

    def showPopup(self):
        self.view().viewport().installEventFilter(self)
        super().showPopup()

    def hidePopup(self):
        self.view().viewport().removeEventFilter(self)
        super().hidePopup()

    def eventFilter(self, obj, event):
        if obj == self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            if index.isValid():
                item = self.model().itemFromIndex(index)
                if item and item.isCheckable():
                    item.setCheckState(
                        Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                    )
                    return True
        return super().eventFilter(obj, event)

    def add_check_item(self, text, checked=False):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.model().appendRow(item)

    def checked_items(self):
        model = self.model()
        return [
            model.item(i).text()
            for i in range(model.rowCount())
            if model.item(i) and model.item(i).checkState() == Qt.Checked
        ]

    def update_display(self):
        checked = self.checked_items()
        self.lineEdit().setText(", ".join(checked) if checked else "")

    def check_all(self):
        model = self.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if item and item.isCheckable():
                item.setCheckState(Qt.Checked)
        self.update_display()

    def uncheck_all(self):
        model = self.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if item and item.isCheckable():
                item.setCheckState(Qt.Unchecked)
        self.update_display()


_ADD_FIELD_SENTINEL = "__add_field__"


def _coerce_shortcut(value, field):
    """Convert a shortcut string to the validation field's native type."""
    if field is None:
        return value
    t = field.type()
    try:
        if t in (QVariant.Int, QVariant.LongLong, QVariant.UInt, QVariant.ULongLong):
            return int(value)
        if t == QVariant.Double:
            return float(value)
        if t == QVariant.Bool:
            lower = value.strip().lower()
            if lower in ("true", "1", "yes"):
                return True
            if lower in ("false", "0", "no"):
                return False
    except (ValueError, AttributeError):
        pass
    return value


class _NullableWidget(QWidget):
    """Value widget wrapper that adds a NULL (∅) toggle checkbox."""

    def __init__(self, inner_widget, is_null=False, parent=None):
        super().__init__(parent)
        self._inner = inner_widget
        self._null_cb = QCheckBox("∅")
        self._null_cb.setToolTip(tr("Write NULL — clears the field value"))
        self._null_cb.setChecked(is_null)
        self._null_cb.toggled.connect(
            lambda checked: self._inner.setEnabled(not checked)
        )
        self._inner.setEnabled(not is_null)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)
        layout.addWidget(self._inner, 1)
        layout.addWidget(self._null_cb)

    def is_null(self):
        return self._null_cb.isChecked()

    def inner_widget(self):
        return self._inner


class ConfigDialog(QDialog):
    """Session setup and settings dialog."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Check-a-Kea setup"))
        self.resize(500, 480)
        self.config = dict(config)
        self._save_button = None
        self._validation_combo_last = 0
        self._comment_combo_last = 0
        self._validation_warning = None
        self._comment_warning = None
        self._filter_warning = None
        self._shortcuts_ok = True

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_project_tab(), tr("Settings"))
        tabs.addTab(self._build_prefs_tab(), tr("Preferences"))
        layout.addWidget(tabs)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self._save_button = button_box.button(QDialogButtonBox.Save)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._update_save_button()

    # ------------------------------------------------------------------ layer

    def _build_layer_combo(self):
        combo = QComboBox()
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        self._populate_layer_combo(combo)
        combo.currentIndexChanged.connect(self._on_layer_changed)
        combo.currentIndexChanged.connect(lambda: self._update_layer_combo_display(combo))
        self._update_layer_combo_display(combo)
        return combo

    def _update_layer_combo_display(self, combo):
        idx = combo.currentIndex()
        if idx >= 0:
            name = combo.itemData(idx, Qt.UserRole + 1)
            if name:
                combo.lineEdit().setText(name)

    def _populate_layer_combo(self, combo):
        combo.blockSignals(True)
        combo.clear()
        model = combo.model()
        folder_icon = QApplication.style().standardIcon(QStyle.SP_DirIcon)

        def add_layers(node, prefix=""):
            valid = [
                c for c in node.children()
                if QgsLayerTree.isGroup(c)
                or (QgsLayerTree.isLayer(c) and c.layer() is not None)
            ]
            for i, child in enumerate(valid):
                is_last = i == len(valid) - 1
                if not prefix:
                    connector = ""
                    child_prefix = "  "
                else:
                    connector = "└─ " if is_last else "├─ "
                    child_prefix = prefix + ("   " if is_last else "│  ")

                if QgsLayerTree.isGroup(child):
                    combo.addItem(folder_icon, prefix + connector + child.name(), None)
                    item = model.item(combo.count() - 1)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setFlags(Qt.ItemIsEnabled)
                    add_layers(child, child_prefix)
                else:
                    layer = child.layer()
                    is_vector = isinstance(layer, QgsVectorLayer)
                    can_write = is_vector and bool(
                        layer.dataProvider().capabilities()
                        & QgsVectorDataProvider.ChangeAttributeValues
                    )
                    combo.addItem(
                        QgsIconUtils.iconForLayer(layer),
                        prefix + connector + layer.name(),
                        layer.id(),
                    )
                    item = model.item(combo.count() - 1)
                    item.setData(layer.name(), Qt.UserRole + 1)
                    if not can_write:
                        item.setFlags(Qt.NoItemFlags)

        add_layers(QgsProject.instance().layerTreeRoot())

        saved_id = self.config.get(KEY_LAYER_ID, DEFAULT_LAYER_ID)
        if saved_id:
            idx = combo.findData(saved_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                existing = QgsProject.instance().mapLayer(saved_id)
                if existing is not None:
                    label = tr("⚠ {} (not a vector layer)").format(existing.name())
                else:
                    label = tr("⚠ Saved layer not found")
                combo.insertItem(0, label, saved_id)
                combo.model().item(0).setData(label, Qt.UserRole + 1)
                combo.setCurrentIndex(0)

        combo.blockSignals(False)

    def _current_layer(self):
        layer_id = self._layer_combo.currentData()
        if not layer_id:
            return None
        layer = QgsProject.instance().mapLayer(layer_id)
        return layer if isinstance(layer, QgsVectorLayer) else None

    def _on_layer_changed(self):
        current_validation = self._validation_combo.currentData()
        if not current_validation or current_validation == _ADD_FIELD_SENTINEL:
            current_validation = self.config.get(
                KEY_VALIDATION_FIELD, DEFAULT_VALIDATION_FIELD
            )
        current_comment = self._comment_combo.currentData()
        if current_comment == _ADD_FIELD_SENTINEL:
            current_comment = self.config.get(KEY_COMMENT_FIELD, DEFAULT_COMMENT_FIELD)

        v_found = self._populate_field_combo(
            self._validation_combo, current_validation, "_validation_combo_last"
        )
        c_found = self._populate_field_combo(
            self._comment_combo, current_comment, "_comment_combo_last", allow_none=True
        )

        if self._validation_warning:
            self._validation_warning.setVisible(
                not v_found and bool(current_validation)
            )
        if self._comment_warning:
            self._comment_warning.setVisible(not c_found and bool(current_comment))

        self._populate_display_fields_combo(self._display_fields_combo.checked_items())
        self._update_layer_warning()
        self._rebuild_shortcut_value_widgets()
        self._update_save_button()

    def _update_layer_warning(self):
        layer_id = self._layer_combo.currentData()
        if layer_id and self._current_layer() is None:
            existing = QgsProject.instance().mapLayer(layer_id)
            if existing is not None:
                msg = tr("⚠ {} is not a vector layer.").format(existing.name())
            else:
                msg = tr("⚠ This layer no longer exists in the project.")
            self._layer_warning.setText(msg)
            self._layer_warning.setVisible(True)
        else:
            self._layer_warning.setVisible(False)

    # ------------------------------------------------------------------ fields

    def _make_field_row(self, current_value, last_attr, warning_attr, allow_none=False):
        """Returns (row_widget, combo). The row widget contains the combo and a ⚠ indicator."""
        combo = QComboBox()
        found = self._populate_field_combo(
            combo, current_value, last_attr, allow_none=allow_none
        )
        combo.activated.connect(
            lambda idx, c=combo, a=last_attr, w=warning_attr: self._on_field_combo_activated(
                c, idx, a, w
            )
        )
        combo.currentIndexChanged.connect(self._update_save_button)

        warning = QLabel("⚠")
        warning.setStyleSheet("color: #b36b00; font-size: 14px;")
        warning.setToolTip(
            tr("Saved field '{}' was not found in this layer.").format(current_value)
        )
        # No warning when value is explicitly "none" (empty string with allow_none)
        warning.setVisible(not found and bool(current_value))
        setattr(self, warning_attr, warning)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(combo, 1)
        row_layout.addWidget(warning)

        return row, combo

    def _populate_field_combo(self, combo, select_value, last_attr, allow_none=False):
        """Repopulate combo from the current layer. Returns True if select_value was found."""
        combo.blockSignals(True)
        combo.clear()

        if allow_none:
            combo.addItem(tr("— none —"), "")

        layer = self._current_layer()

        for field in layer.fields() if layer else []:
            combo.addItem(f"{field.name()}  ({field.typeName()})", field.name())

        if layer:
            combo.insertSeparator(combo.count())
            combo.addItem(tr("Add field…"), _ADD_FIELD_SENTINEL)

        found = False
        for i in range(combo.count()):
            if combo.itemData(i) == select_value:
                combo.setCurrentIndex(i)
                setattr(self, last_attr, i)
                found = True
                break

        if not found:
            combo.setCurrentIndex(-1)
            setattr(self, last_attr, -1)

        combo.blockSignals(False)
        return found

    def _on_field_combo_activated(self, combo, index, last_attr, warning_attr):
        if combo.itemData(index) == _ADD_FIELD_SENTINEL:
            self._do_add_field(combo, last_attr, warning_attr)
        else:
            setattr(self, last_attr, index)
            getattr(self, warning_attr).setVisible(False)
            if combo is self._validation_combo:
                self._rebuild_shortcut_value_widgets()

    def _do_add_field(self, combo, last_attr, warning_attr):
        layer = self._current_layer()
        if not layer:
            return
        name, ok = QInputDialog.getText(self, tr("Add field"), tr("Field name:"))
        name = name.strip()
        if not ok or not name:
            combo.blockSignals(True)
            combo.setCurrentIndex(getattr(self, last_attr))
            combo.blockSignals(False)
            return

        success = layer.dataProvider().addAttributes([QgsField(name, QVariant.String)])
        layer.updateFields()

        if success:
            self._populate_field_combo(combo, name, last_attr)
            getattr(self, warning_attr).setVisible(False)
            self._update_save_button()
        else:
            QMessageBox.warning(
                self, tr("Error"), tr("Could not add field '{}'.").format(name)
            )
            combo.blockSignals(True)
            combo.setCurrentIndex(getattr(self, last_attr))
            combo.blockSignals(False)

    # ------------------------------------------------------------------ display fields

    def _populate_display_fields_combo(self, selected_fields=()):
        """Repopulate display-fields combo from the current layer.

        Pass an empty sequence to reset (all unchecked = show nothing).
        """
        if not hasattr(self, "_display_fields_combo"):
            return
        try:
            self._display_fields_combo.model().itemChanged.disconnect(
                self._display_fields_combo.update_display
            )
        except TypeError:
            pass
        self._display_fields_combo.clear()
        layer = self._current_layer()
        if layer:
            selected = set(selected_fields)
            for field in layer.fields():
                self._display_fields_combo.add_check_item(
                    field.name(), checked=field.name() in selected
                )
            self._display_fields_combo.update_display()
        self._display_fields_combo.model().itemChanged.connect(
            self._display_fields_combo.update_display
        )

    # ------------------------------------------------------------------ shortcut value widgets

    def _validation_field(self):
        """Return the QgsField for the current validation field combo, or None."""
        layer = self._current_layer()
        field_name = self._validation_combo.currentData()
        if not layer or not field_name or field_name == _ADD_FIELD_SENTINEL:
            return None
        idx = layer.fields().indexOf(field_name)
        return layer.fields().field(idx) if idx >= 0 else None

    def _make_value_widget(self, value, field):
        """Create a nullable, type-appropriate editor for a shortcut value."""
        return _NullableWidget(
            self._make_inner_value_widget(value, field),
            is_null=value is None,
        )

    def _make_inner_value_widget(self, value, field):
        """Create the inner type-appropriate editor widget (without NULL wrapper)."""
        t = field.type() if field else QVariant.String

        if t in (QVariant.Int, QVariant.LongLong, QVariant.UInt, QVariant.ULongLong):
            widget = QSpinBox()
            widget.setRange(-2147483648, 2147483647)
            widget.setFrame(False)
            try:
                widget.setValue(int(value))
            except (ValueError, TypeError):
                pass
            return widget

        if t == QVariant.Double:
            widget = QDoubleSpinBox()
            widget.setRange(-1e15, 1e15)
            widget.setDecimals(6)
            widget.setFrame(False)
            try:
                widget.setValue(float(value))
            except (ValueError, TypeError):
                pass
            return widget

        if t == QVariant.Bool:
            widget = QComboBox()
            widget.addItem("true", True)
            widget.addItem("false", False)
            is_false = value is False or (
                isinstance(value, str) and value.strip().lower() in ("false", "0", "no")
            )
            widget.setCurrentIndex(1 if is_false else 0)
            return widget

        if t in (QVariant.Date, QVariant.DateTime):
            widget = QDateEdit()
            widget.setCalendarPopup(True)
            widget.setFrame(False)
            if isinstance(value, str) and value:
                date = QDate.fromString(value, Qt.ISODate)
                if date.isValid():
                    widget.setDate(date)
            return widget

        # String and all other types
        widget = QLineEdit()
        widget.setFrame(False)
        if value is True:
            display = "true"
        elif value is False:
            display = "false"
        else:
            display = str(value) if value is not None else ""
        widget.setText(display)
        return widget

    def _read_value_widget(self, widget):
        """Read the current typed value from a shortcut value widget."""
        if isinstance(widget, _NullableWidget):
            if widget.is_null():
                return None
            widget = widget.inner_widget()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QDateEdit):
            return widget.date().toString(Qt.ISODate)
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        return ""

    def _rebuild_shortcut_value_widgets(self):
        """Replace value-column widgets to match the current validation field type."""
        if not hasattr(self, "_shortcuts_table") or self._shortcuts_table is None:
            return
        field = self._validation_field()
        for row in range(self._shortcuts_table.rowCount()):
            old_widget = self._shortcuts_table.cellWidget(row, 1)
            current_val = self._read_value_widget(old_widget) if old_widget else ""
            self._shortcuts_table.setCellWidget(
                row, 1, self._make_value_widget(current_val, field)
            )

    # ------------------------------------------------------------------ tab builders

    def _build_project_tab(self):
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)

        self._layer_combo = self._build_layer_combo()
        self._layer_combo.setToolTip(
            tr("The vector layer whose features will be validated.")
        )
        self._layer_warning = QLabel()
        self._layer_warning.setStyleSheet("color: #b36b00;")
        self._layer_warning.setWordWrap(True)
        self._layer_warning.setVisible(False)

        v_row, self._validation_combo = self._make_field_row(
            self.config.get(KEY_VALIDATION_FIELD, DEFAULT_VALIDATION_FIELD),
            "_validation_combo_last",
            "_validation_warning",
        )
        self._validation_combo.setToolTip(
            tr("Field where the shortcut value is written when you validate a feature.")
        )
        c_row, self._comment_combo = self._make_field_row(
            self.config.get(KEY_COMMENT_FIELD, DEFAULT_COMMENT_FIELD),
            "_comment_combo_last",
            "_comment_warning",
            allow_none=True,
        )
        self._comment_combo.setToolTip(
            tr(
                "Optional field for free-text comments. Leave as '— none —' to hide the comment box."
            )
        )
        self._filter_edit, filter_row = self._make_filter_row(
            self.config.get(KEY_UNVALIDATED_FILTER, DEFAULT_UNVALIDATED_FILTER)
        )
        self._filter_edit.setToolTip(
            tr(
                "QGIS expression that selects features still needing validation. "
                "Applied on top of any filter already set on the layer source. "
                "Leave blank to include all features that also pass the current layer filter."
            )
        )

        self._display_fields_combo = CheckableComboBox()
        self._display_fields_combo.setToolTip(
            tr(
                "Attributes shown in the feature preview panel. Use 'Select all' to show everything; leave blank to hide the preview entirely."
            )
        )
        self._populate_display_fields_combo(
            self.config.get(KEY_DISPLAY_FIELDS, DEFAULT_DISPLAY_FIELDS)
        )

        _select_all_btn = QPushButton(tr("Select all"))
        _select_all_btn.setFlat(True)
        _select_all_btn.clicked.connect(self._display_fields_combo.check_all)
        _clear_all_btn = QPushButton(tr("Clear all"))
        _clear_all_btn.setFlat(True)
        _clear_all_btn.clicked.connect(self._display_fields_combo.uncheck_all)
        _df_btn_row = QHBoxLayout()
        _df_btn_row.setContentsMargins(0, 0, 0, 0)
        _df_btn_row.addWidget(_select_all_btn)
        _df_btn_row.addWidget(_clear_all_btn)
        _df_btn_row.addStretch()
        _display_fields_container = QWidget()
        _df_layout = QVBoxLayout(_display_fields_container)
        _df_layout.setContentsMargins(0, 0, 0, 0)
        _df_layout.setSpacing(2)
        _df_layout.addWidget(self._display_fields_combo)
        _df_layout.addLayout(_df_btn_row)

        layout.addRow(tr("Layer"), self._layer_combo)
        layout.addRow("", self._layer_warning)
        layout.addRow(tr("Validation field"), v_row)
        layout.addRow(tr("Comment field"), c_row)
        layout.addRow(tr("Unvalidated filter"), filter_row)
        layout.addRow(tr("Display fields"), _display_fields_container)
        layout.addRow(tr("Shortcuts"), self._build_shortcuts_widget())

        self._update_layer_warning()
        return widget

    def _make_filter_row(self, current_value):
        """Returns (line_edit, row_widget) for the expression filter field."""
        line_edit = QLineEdit(current_value)
        line_edit.setPlaceholderText('e.g. "validation" IS NULL OR "validation" = \'\'')

        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(28)
        browse_btn.setToolTip(tr("Open expression builder"))
        browse_btn.clicked.connect(lambda: self._open_expression_builder(line_edit))

        self._filter_warning = QLabel("⚠")
        self._filter_warning.setStyleSheet("color: #b36b00; font-size: 14px;")
        self._filter_warning.setVisible(False)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(line_edit, 1)
        row_layout.addWidget(browse_btn)
        row_layout.addWidget(self._filter_warning)

        line_edit.textChanged.connect(self._validate_filter)
        self._validate_filter(current_value)

        return line_edit, row

    def _validate_filter(self, text):
        if not self._filter_warning:
            return
        text = text.strip()
        if not text:
            self._filter_warning.setVisible(False)
        else:
            expr = QgsExpression(text)
            if expr.hasParserError():
                self._filter_warning.setToolTip(expr.parserErrorString())
                self._filter_warning.setVisible(True)
            else:
                self._filter_warning.setVisible(False)
        self._update_save_button()

    def _open_expression_builder(self, line_edit):
        layer = self._current_layer()
        dialog = QgsExpressionBuilderDialog(layer, line_edit.text(), self, "generic")
        dialog.setWindowTitle(tr("Unvalidated filter expression"))
        if dialog.exec_():
            line_edit.setText(dialog.expressionText().strip())

    def _build_shortcuts_widget(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self._shortcuts_table = QTableWidget(0, 2)
        self._shortcuts_table.setHorizontalHeaderLabels([tr("Key"), tr("Value")])
        self._shortcuts_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self._shortcuts_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self._shortcuts_table.verticalHeader().setVisible(False)
        self._shortcuts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._shortcuts_table.itemChanged.connect(self._validate_shortcuts)

        for key, value in self.config.get(KEY_SHORTCUTS, DEFAULT_SHORTCUTS).items():
            self._add_shortcut_row(key, value)
        self._validate_shortcuts()

        add_btn = QPushButton(tr("Add row"))
        add_btn.clicked.connect(lambda: self._add_shortcut_row("", ""))
        remove_btn = QPushButton(tr("Remove row"))
        remove_btn.clicked.connect(self._remove_shortcut_row)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()

        layout.addWidget(self._shortcuts_table)
        layout.addLayout(btn_layout)
        return container

    def _add_shortcut_row(self, key, value):
        row = self._shortcuts_table.rowCount()
        self._shortcuts_table.insertRow(row)
        self._shortcuts_table.setItem(row, 0, QTableWidgetItem(str(key)))
        self._shortcuts_table.setCellWidget(
            row, 1, self._make_value_widget(value, self._validation_field())
        )

    def _remove_shortcut_row(self):
        row = self._shortcuts_table.currentRow()
        if row >= 0:
            self._shortcuts_table.removeRow(row)

    def _validate_shortcuts(self, *_):
        keys = []
        for row in range(self._shortcuts_table.rowCount()):
            item = self._shortcuts_table.item(row, 0)
            key = item.text().strip() if item else ""
            keys.append(key)

        conflicting = shortcut_conflicts(keys)

        invalid = False
        for row, key in enumerate(keys):
            item = self._shortcuts_table.item(row, 0)
            if item:
                if key and key in conflicting:
                    item.setBackground(QColor("#ffcccc"))
                    item.setToolTip(
                        tr("Duplicate key.")
                        if keys.count(key) > 1
                        else tr(
                            "Conflicts with another shortcut (one is a prefix of the other)."
                        )
                    )
                    invalid = True
                else:
                    item.setBackground(QBrush())
                    item.setToolTip("")

        self._shortcuts_ok = not invalid
        self._update_save_button()

    def _read_shortcuts(self):
        shortcuts = {}
        for row in range(self._shortcuts_table.rowCount()):
            key_item = self._shortcuts_table.item(row, 0)
            key = key_item.text().strip() if key_item else ""
            value_widget = self._shortcuts_table.cellWidget(row, 1)
            val = self._read_value_widget(value_widget) if value_widget else ""
            if key:
                shortcuts[key] = val
        return shortcuts

    def _build_prefs_tab(self):
        widget = QWidget()
        layout = QFormLayout(widget)

        self._zoom_buffer = QSpinBox()
        self._zoom_buffer.setRange(0, 500)
        self._zoom_buffer.setSuffix(" %")
        self._zoom_buffer.setValue(
            self.config.get(KEY_ZOOM_BUFFER, DEFAULT_ZOOM_BUFFER)
        )
        self._zoom_buffer.setToolTip(
            tr("Extra space added around a feature's bounding box when zooming to it.")
        )

        self._auto_advance = QCheckBox()
        self._auto_advance.setChecked(
            self.config.get(KEY_AUTO_ADVANCE, DEFAULT_AUTO_ADVANCE)
        )
        self._auto_advance.setToolTip(
            tr(
                "Automatically move to the next unvalidated feature after applying a shortcut."
            )
        )

        self._advance_delay = QSpinBox()
        self._advance_delay.setRange(0, 10000)
        self._advance_delay.setSuffix(" ms")
        self._advance_delay.setValue(
            self.config.get(KEY_AUTO_ADVANCE_DELAY, DEFAULT_AUTO_ADVANCE_DELAY)
        )
        self._advance_delay.setToolTip(
            tr("How long to pause on the current feature before advancing to the next.")
        )

        self._auto_identify = QCheckBox()
        self._auto_identify.setChecked(
            self.config.get(KEY_AUTO_IDENTIFY, DEFAULT_AUTO_IDENTIFY)
        )
        self._auto_identify.setToolTip(
            tr("Open QGIS Identify Results for the current feature as you navigate.")
        )

        self._flash_changes = QCheckBox()
        self._flash_changes.setChecked(
            self.config.get(KEY_FLASH_CHANGES, DEFAULT_FLASH_CHANGES)
        )
        self._flash_changes.setToolTip(
            tr("Highlight attribute rows whose value differs from the previous feature.")
        )

        self._flash_changes_delay = QSpinBox()
        self._flash_changes_delay.setRange(0, 30000)
        self._flash_changes_delay.setSuffix(" ms")
        self._flash_changes_delay.setValue(
            self.config.get(KEY_FLASH_CHANGES_DELAY, DEFAULT_FLASH_CHANGES_DELAY)
        )
        self._flash_changes_delay.setToolTip(
            tr("How long the changed-value highlight remains visible.")
        )

        layout.addRow(tr("Zoom buffer"), self._zoom_buffer)
        layout.addRow(tr("Auto-advance"), self._auto_advance)
        layout.addRow(tr("Auto-advance delay"), self._advance_delay)
        layout.addRow(tr("Auto-identify"), self._auto_identify)
        layout.addRow(tr("Flash changes"), self._flash_changes)
        layout.addRow(tr("Flash duration"), self._flash_changes_delay)

        return widget

    # ------------------------------------------------------------------ validation / accept

    def _update_save_button(self):
        if self._save_button is None:
            return
        layer_ok = self._current_layer() is not None
        field_data = self._validation_combo.currentData()
        field_ok = bool(field_data) and field_data != _ADD_FIELD_SENTINEL
        filter_text = self._filter_edit.text().strip() if self._filter_edit else ""
        filter_ok = not filter_text or not QgsExpression(filter_text).hasParserError()
        self._save_button.setEnabled(
            layer_ok and field_ok and filter_ok and self._shortcuts_ok
        )

    def accept(self):
        self.config[KEY_LAYER_ID] = self._layer_combo.currentData() or ""
        self.config[KEY_VALIDATION_FIELD] = self._validation_combo.currentData()
        self.config[KEY_COMMENT_FIELD] = self._comment_combo.currentData() or ""
        self.config[KEY_UNVALIDATED_FILTER] = self._filter_edit.text().strip()
        self.config[KEY_DISPLAY_FIELDS] = self._display_fields_combo.checked_items()
        self.config[KEY_SHORTCUTS] = self._read_shortcuts()
        self.config[KEY_ZOOM_BUFFER] = self._zoom_buffer.value()
        self.config[KEY_AUTO_ADVANCE] = self._auto_advance.isChecked()
        self.config[KEY_AUTO_ADVANCE_DELAY] = self._advance_delay.value()
        self.config[KEY_AUTO_IDENTIFY] = self._auto_identify.isChecked()
        self.config[KEY_FLASH_CHANGES] = self._flash_changes.isChecked()
        self.config[KEY_FLASH_CHANGES_DELAY] = self._flash_changes_delay.value()
        super().accept()
