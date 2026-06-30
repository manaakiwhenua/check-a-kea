import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if isinstance(sys.modules.get("qgis.core"), MagicMock):
    pytest.skip("QGIS not available", allow_module_level=True)

from qgis.core import (  # noqa: E402
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

_PLUGIN_DIR = Path(__file__).parent.parent


def _ensure_package():
    """Register the plugin directory as the 'check_a_kea' package.

    check_a_kea.py uses relative imports (from .core.x import ...), so it must
    be loaded as check_a_kea.check_a_kea, not as a top-level module.
    """
    if "check_a_kea" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "check_a_kea",
            str(_PLUGIN_DIR / "__init__.py"),
            submodule_search_locations=[str(_PLUGIN_DIR)],
        )
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "check_a_kea"
        sys.modules["check_a_kea"] = mod
        spec.loader.exec_module(mod)


_ensure_package()


def _layer(*validation_values):
    """In-memory point layer with validation and comment fields."""
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=validation:string&field=comment:string",
        "test_layer",
        "memory",
    )
    provider = layer.dataProvider()
    for val in validation_values:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        if val is not None:
            f["validation"] = val
        provider.addFeature(f)
    layer.updateExtents()
    return layer


def _make_plugin(qgis_iface):
    from check_a_kea import classFactory

    plugin = classFactory(qgis_iface)
    plugin.initGui()
    plugin.show_dock()
    return plugin


@pytest.fixture
def plugin_with_layer(qgis_iface):
    """Plugin with dock shown and a 3-feature layer (2 unvalidated, 1 validated).

    Config is overridden with known values so tests are independent of config.json.
    """
    layer = _layer(None, None, "true")
    QgsProject.instance().addMapLayer(layer)
    plugin = _make_plugin(qgis_iface)
    plugin.config.update(
        {
            "unvalidated_filter": "validation IS NULL OR validation = ''",
            "shortcuts": {"1": "true", "2": "false", "3": "maybe"},
            "auto_advance": True,
            "auto_advance_delay_ms": 100,
        }
    )
    yield plugin, layer
    plugin.unload()
    QgsProject.instance().removeMapLayer(layer.id())


@pytest.fixture
def started_plugin(plugin_with_layer):
    """plugin_with_layer after start_validation() — session has 2 unvalidated features."""
    plugin, layer = plugin_with_layer
    plugin.start_validation()
    return plugin, layer


# ------------------------------------------------------------------ smoke


def test_initgui_and_unload_do_not_crash(qgis_iface):
    from check_a_kea import classFactory

    plugin = classFactory(qgis_iface)
    plugin.initGui()
    plugin.unload()


def test_show_dock_creates_dock(qgis_iface):
    plugin = _make_plugin(qgis_iface)
    assert plugin.dock is not None
    plugin.unload()


# ------------------------------------------------------------------ start_validation


def test_start_validation_no_layer_shows_error(qgis_iface):
    for lid in list(QgsProject.instance().mapLayers().keys()):
        QgsProject.instance().removeMapLayer(lid)
    plugin = _make_plugin(qgis_iface)
    plugin.start_validation()
    assert "No valid layer" in plugin.status_label.text()
    plugin.unload()


def test_start_validation_missing_field_shows_error(qgis_iface):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=other:string", "t", "memory")
    QgsProject.instance().addMapLayer(layer)
    plugin = _make_plugin(qgis_iface)
    plugin.start_validation()
    assert "does not exist" in plugin.status_label.text()
    plugin.unload()
    QgsProject.instance().removeMapLayer(layer.id())


def test_start_validation_creates_session(plugin_with_layer):
    plugin, _ = plugin_with_layer
    plugin.start_validation()
    assert plugin.session is not None


def test_start_validation_respects_unvalidated_filter(plugin_with_layer):
    plugin, _ = plugin_with_layer
    # 3 features: 2 NULL + 1 "true" — default filter excludes "true"
    plugin.start_validation()
    assert len(plugin.session) == 2


def test_start_validation_no_filter_includes_all(plugin_with_layer):
    plugin, _ = plugin_with_layer
    plugin.config["unvalidated_filter"] = ""
    plugin.start_validation()
    assert len(plugin.session) == 3


# ------------------------------------------------------------------ footer / navigation


def test_footer_shows_current_feature_number(started_plugin):
    plugin, _ = started_plugin
    assert "Feature 1 of 2" in plugin.footer_label.text()


def test_next_feature_advances_footer(started_plugin):
    plugin, _ = started_plugin
    plugin.next_feature()
    assert "Feature 2 of 2" in plugin.footer_label.text()


def test_previous_at_start_is_a_no_op(started_plugin):
    plugin, _ = started_plugin
    plugin.previous_feature()
    assert "Feature 1 of 2" in plugin.footer_label.text()


def test_next_past_end_finishes_queue(started_plugin):
    plugin, _ = started_plugin
    plugin.next_feature()
    plugin.next_feature()  # steps off the end
    assert plugin.session is None
    assert "Finished" in plugin.status_label.text()


# ------------------------------------------------------------------ apply_validation


def test_apply_validation_writes_value(started_plugin):
    plugin, layer = started_plugin
    fid = plugin.session.current_fid
    plugin.apply_validation("1")  # shortcut "1" → "true"
    feature = next(layer.getFeatures(QgsFeatureRequest(fid)))
    assert feature["validation"] == "true"


def test_apply_validation_unknown_key_is_ignored(started_plugin):
    plugin, _ = started_plugin
    original_index = plugin.session.index
    plugin.apply_validation("9")  # not a configured shortcut
    assert plugin.session.index == original_index


def test_apply_validation_sets_waiting_flag(started_plugin):
    plugin, _ = started_plugin
    plugin.apply_validation("1")
    assert plugin.session.waiting_to_advance is True


# ------------------------------------------------------------------ comment


def test_comment_save_writes_to_layer(started_plugin):
    plugin, layer = started_plugin
    fid = plugin.session.current_fid
    plugin.comment_box.setPlainText("test comment")
    plugin.save_comment_for_current_feature()
    feature = next(layer.getFeatures(QgsFeatureRequest(fid)))
    assert feature["comment"] == "test comment"


def test_comment_textchanged_starts_timer(started_plugin):
    plugin, _ = started_plugin
    plugin._comment_save_timer.stop()
    plugin.comment_box.setPlainText("debounced")
    assert plugin._comment_save_timer.isActive()
