import pytest
from pydantic import ValidationError

from app.modeling_spec import ModelingSpec


def box_spec():
    return {
        "task_id": "box-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
        "objects": [{"name": "box", "primitive": "box", "dimensions": {"width": 100, "depth": 60, "height": 30}, "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "AI_Demo", "color": "blue", "value_sources": {"width": "user"}}],
        "constraints": [{"type": "closed_solid", "targets": ["box"]}],
        "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 1, "require_valid_geometry": True}, "assumptions": []
    }


def flange_spec():
    return {
        "task_id": "flange-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
        "objects": [{
            "name": "precision_flange", "primitive": "flange",
            "dimensions": {"outer_diameter": 160, "thickness": 20, "bore_diameter": 40, "bolt_circle_diameter": 110, "bolt_hole_diameter": 12, "bolt_hole_count": 6},
            "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "精密零件", "color": "blue",
            "value_sources": {"outer_diameter": "user", "bolt_hole_count": "user"}
        }],
        "constraints": [{"type": "closed_solid", "targets": ["precision_flange"]}],
        "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 1, "require_valid_geometry": True}, "assumptions": []
    }


def enclosure_spec():
    return {
        "task_id": "enclosure-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
        "objects": [{
            "name": "product_shell", "primitive": "enclosure",
            "dimensions": {"width": 180, "depth": 120, "height": 60, "wall_thickness": 3},
            "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "产品外壳", "color": "gray", "value_sources": {}
        }],
        "constraints": [{"type": "closed_solid", "targets": ["product_shell"]}],
        "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 1, "require_valid_geometry": True}, "assumptions": []
    }


def test_valid_box():
    assert ModelingSpec.model_validate(box_spec()).objects[0].dimensions["width"] == 100


def test_missing_dimension_rejected():
    value = box_spec(); del value["objects"][0]["dimensions"]["height"]
    with pytest.raises(ValidationError): ModelingSpec.model_validate(value)


def test_unknown_constraint_target_rejected():
    value = box_spec(); value["constraints"][0]["targets"] = ["missing"]
    with pytest.raises(ValidationError): ModelingSpec.model_validate(value)


def test_valid_precision_templates():
    assert ModelingSpec.model_validate(flange_spec()).objects[0].dimensions["bolt_hole_count"] == 6
    assert ModelingSpec.model_validate(enclosure_spec()).objects[0].dimensions["wall_thickness"] == 3


def test_flange_rejects_holes_outside_body():
    value = flange_spec(); value["objects"][0]["dimensions"]["bolt_circle_diameter"] = 158
    with pytest.raises(ValidationError): ModelingSpec.model_validate(value)


def test_enclosure_rejects_impossible_wall():
    value = enclosure_spec(); value["objects"][0]["dimensions"]["wall_thickness"] = 70
    with pytest.raises(ValidationError): ModelingSpec.model_validate(value)
