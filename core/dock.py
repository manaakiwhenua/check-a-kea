from qgis.PyQt.QtWidgets import (
    QApplication,
    QDockWidget,
    QScrollArea,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QSplitter,
)
from qgis.PyQt.QtCore import Qt, QTimer

from .histogram import HistogramWidget
from .utils import tr
from .widgets import CommentFocusGuard


class DockMixin:
    """Dock construction methods for CheckAKea."""

    def build_dock(self):
        self.dock = QDockWidget("Check-a-Kea", self.iface.mainWindow())
        self.dock.setObjectName("CheckAKeaDock")

        tabs = QTabWidget()

        # Tab 1: validation
        validate_widget = QWidget()
        validate_layout = QVBoxLayout(validate_widget)
        self._build_top_section(validate_layout)
        self.validation_controls_widget = self._build_validation_controls()
        self.status_label = QLabel(tr("Open Setup to configure and begin."))
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)
        self.footer_label = QLabel("")
        self.footer_label.setWordWrap(True)
        self.footer_label.setTextFormat(Qt.RichText)
        self.footer_label.setStyleSheet("color: gray; font-size: 10px;")
        validate_layout.addWidget(self.validation_controls_widget)
        validate_layout.addWidget(self.status_label)
        validate_layout.addWidget(self.footer_label)
        tabs.addTab(validate_widget, tr("Validate"))

        # Tab 2: summary
        self.histogram_widget = HistogramWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.histogram_widget)
        tabs.addTab(scroll, tr("Summary"))
        tabs.currentChanged.connect(
            lambda i: self.refresh_histogram() if i == 1 else None
        )

        self.dock.setWidget(tabs)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self._focus_guard = CommentFocusGuard(self.comment_box, self.canvas)
        QApplication.instance().installEventFilter(self._focus_guard)

        self.set_validation_controls_visible(False)
        self.register_shortcuts()

    def _build_top_section(self, layout):
        setup_button = QPushButton(tr("Settings / preferences"))
        setup_button.clicked.connect(self.open_config_dialog)
        layout.addWidget(setup_button)

    def _build_attribute_table(self):
        self.attribute_table = QTableWidget(0, 2)
        self.attribute_table.horizontalHeader().setVisible(False)
        self.attribute_table.verticalHeader().setVisible(False)
        self.attribute_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attribute_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.attribute_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.attribute_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        return self.attribute_table

    def _build_comment_section(self):
        self.comment_box = QTextEdit()
        self.comment_box.setPlaceholderText(
            tr("Write an optional comment for this feature...")
        )

        self._comment_save_timer = QTimer()
        self._comment_save_timer.setSingleShot(True)
        self._comment_save_timer.setInterval(500)
        self._comment_save_timer.timeout.connect(
            lambda: self.save_comment_for_current_feature()
        )
        self.comment_box.textChanged.connect(self._comment_save_timer.start)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(tr("Comment")))
        layout.addWidget(self.comment_box)
        return widget

    def _build_nav_section(self):
        prev_button = QPushButton(tr("◀ Previous"))
        prev_button.clicked.connect(self.previous_feature)
        prev_button.setToolTip(tr("Go to previous feature, Left Arrow"))

        next_button = QPushButton(tr("Next ▶"))
        next_button.clicked.connect(self.next_feature)
        next_button.setToolTip(tr("Go to next feature, Right Arrow"))

        layout = QHBoxLayout()
        layout.addWidget(prev_button)
        layout.addWidget(next_button)
        return layout

    def _build_validation_controls(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.comment_section_widget = self._build_comment_section()

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_attribute_table())
        splitter.addWidget(self.comment_section_widget)
        splitter.setSizes([80, 80])

        layout.addWidget(splitter)
        layout.addLayout(self._build_nav_section())

        return widget
