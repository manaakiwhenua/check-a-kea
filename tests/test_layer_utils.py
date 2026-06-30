import sys
from unittest.mock import MagicMock

import pytest

if isinstance(sys.modules.get("qgis.core"), MagicMock):
    pytest.skip("QGIS not available", allow_module_level=True)

from qgis.PyQt.QtCore import Qt  # noqa: E402
from qgis.core import (  # noqa: E402
    QgsAttributeTableConfig,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)

from core.constants import KEY_UNVALIDATED_FILTER  # noqa: E402
from core.layer_utils import get_feature_ids  # noqa: E402
from core.session import ValidationSession  # noqa: E402


def _layer(*validation_values):
    """In-memory point layer with one feature per value (None = NULL)."""
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=validation:string&field=rank:integer",
        "test",
        "memory",
    )
    provider = layer.dataProvider()
    for rank, val in enumerate(validation_values, start=1):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        if val is not None:
            f["validation"] = val
        f["rank"] = rank
        provider.addFeature(f)
    layer.updateExtents()
    return layer


# ------------------------------------------------------------------ filtering


def test_no_filter_returns_all_features():
    layer = _layer("true", "false", None)
    ids = get_feature_ids(layer, {KEY_UNVALIDATED_FILTER: ""})
    assert len(ids) == 3


def test_filter_excludes_validated_features():
    layer = _layer("true", None, None)
    ids = get_feature_ids(
        layer,
        {KEY_UNVALIDATED_FILTER: "validation IS NULL OR validation = ''"},
    )
    assert len(ids) == 2


def test_filter_empty_returns_all():
    layer = _layer("true", "false")
    ids = get_feature_ids(layer, {KEY_UNVALIDATED_FILTER: ""})
    assert len(ids) == 2


def test_all_validated_filter_returns_none():
    layer = _layer("true", "true")
    ids = get_feature_ids(
        layer,
        {KEY_UNVALIDATED_FILTER: "validation IS NULL OR validation = ''"},
    )
    assert ids == []


# ------------------------------------------------------------------ sort order


def _set_sort(layer, expression, ascending=True):
    config = QgsAttributeTableConfig()
    config.setSortExpression(expression)
    config.setSortOrder(Qt.AscendingOrder if ascending else Qt.DescendingOrder)
    layer.setAttributeTableConfig(config)


def _ranks(layer, ids):
    features = {f.id(): f for f in layer.getFeatures()}
    return [features[fid]["rank"] for fid in ids]


def test_sort_ascending():
    layer = _layer("a", "b", "c")  # ranks 1, 2, 3 in insertion order
    _set_sort(layer, "rank", ascending=True)
    ids = get_feature_ids(layer, {KEY_UNVALIDATED_FILTER: ""})
    assert _ranks(layer, ids) == [1, 2, 3]


def test_sort_descending():
    layer = _layer("a", "b", "c")
    _set_sort(layer, "rank", ascending=False)
    ids = get_feature_ids(layer, {KEY_UNVALIDATED_FILTER: ""})
    assert _ranks(layer, ids) == [3, 2, 1]


# ------------------------------------------------------------------ write_validation


def test_write_validation_sets_field_value():
    layer = _layer(None)
    fids = [f.id() for f in layer.getFeatures()]
    session = ValidationSession(layer, fids)
    assert session.write_validation("validation", "accepted") is True
    feature = next(layer.getFeatures())
    assert feature["validation"] == "accepted"


def test_write_validation_auto_starts_editing():
    layer = _layer(None)
    assert not layer.isEditable()
    fids = [f.id() for f in layer.getFeatures()]
    session = ValidationSession(layer, fids)
    session.write_validation("validation", "accepted")
    assert layer.isEditable()


def test_write_validation_advances_correctly_with_navigate():
    layer = _layer(None, None)
    fids = [f.id() for f in layer.getFeatures()]
    session = ValidationSession(layer, fids)

    session.write_validation("validation", "first")
    session.navigate(1)
    session.write_validation("validation", "second")
    values = {f.id(): f["validation"] for f in layer.getFeatures()}
    assert values[fids[0]] == "first"
    assert values[fids[1]] == "second"


def test_write_validation_unknown_field_raises():
    layer = _layer(None)
    fids = [f.id() for f in layer.getFeatures()]
    session = ValidationSession(layer, fids)
    with pytest.raises(ValueError):
        session.write_validation("nonexistent", "value")


# ------------------------------------------------------------------ current_feature


def test_current_feature_returns_first_feature():
    layer = _layer("a", "b", "c")
    fids = [f.id() for f in layer.getFeatures()]
    session = ValidationSession(layer, fids)
    assert session.current_feature().id() == fids[0]


def test_current_feature_updates_after_navigate():
    layer = _layer("a", "b", "c")
    fids = [f.id() for f in layer.getFeatures()]
    session = ValidationSession(layer, fids)
    session.navigate(1)
    assert session.current_feature().id() == fids[1]


# ------------------------------------------------------------------ validation_counts


def test_validation_counts_all_null():
    layer = _layer(None, None, None)
    session = ValidationSession(layer, [f.id() for f in layer.getFeatures()])
    assert session.validation_counts("validation") == {None: 3}


def test_validation_counts_mixed():
    layer = _layer("true", "false", "true", None)
    session = ValidationSession(layer, [f.id() for f in layer.getFeatures()])
    assert session.validation_counts("validation") == {"true": 2, "false": 1, None: 1}


def test_validation_counts_all_validated():
    layer = _layer("true", "true")
    session = ValidationSession(layer, [f.id() for f in layer.getFeatures()])
    assert session.validation_counts("validation") == {"true": 2}
