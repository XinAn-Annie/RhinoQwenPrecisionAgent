import pytest
from pydantic import ValidationError

from app.modeling_spec import ModelingSpec
from app.rhino_executor import build_creation_script
from app.validator import build_validation_script


def stepped_shaft_spec():
    return {
        "task_id": "advanced-shaft-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
        "objects": [{"name": "stepped_shaft", "primitive": "stepped_shaft", "dimensions": {},
            "steps": [{"diameter": 60, "length": 30}, {"diameter": 40, "length": 50}, {"diameter": 25, "length": 35}],
            "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "轴类零件", "color": "blue", "value_sources": {}}],
        "constraints": [{"type": "closed_solid", "targets": ["stepped_shaft"]}],
        "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 1, "require_valid_geometry": True}, "assumptions": []}


def sketch_spec(treatment="fillet"):
    return {
        "task_id": f"advanced-sketch-{treatment}", "intent": "create", "units": "mm", "document_tolerance": 0.01,
        "objects": [{"name": f"sketch_{treatment}", "primitive": "sketch_extrusion", "dimensions": {"height": 20},
            "sketch": [{"x": -50, "y": -30}, {"x": 50, "y": -30}, {"x": 50, "y": 30}, {"x": -50, "y": 30}],
            "edge_treatment": {"type": treatment, "size": 5 if treatment == "fillet" else 4, "selector": "vertical"},
            "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "草图特征", "color": "green", "value_sources": {}}],
        "constraints": [{"type": "closed_solid", "targets": [f"sketch_{treatment}"]}],
        "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 1, "require_valid_geometry": True}, "assumptions": []}


def loft_spec():
    return {
        "task_id": "advanced-loft-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
        "objects": [{"name": "freeform_loft", "primitive": "loft_surface", "dimensions": {},
            "sections": [
                {"z": 0, "width": 80, "depth": 50, "center_x": 0, "center_y": 0, "rotation_deg": 0},
                {"z": 40, "width": 105, "depth": 60, "center_x": 10, "center_y": 0, "rotation_deg": 15},
                {"z": 80, "width": 65, "depth": 90, "center_x": -5, "center_y": 10, "rotation_deg": -10}],
            "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "自由曲面", "color": "yellow", "value_sources": {}}],
        "constraints": [{"type": "valid_geometry", "targets": ["freeform_loft"]}],
        "acceptance": {"dimension_tolerance_mm": 0.5, "expected_object_count": 1, "require_valid_geometry": True}, "assumptions": []}


def assembly_spec():
    return {
        "task_id": "advanced-assembly-001", "intent": "create", "units": "mm", "document_tolerance": 0.01,
        "objects": [
            {"name": "base_disc", "primitive": "cylinder", "dimensions": {"diameter": 120, "height": 15}, "position": {"center_x": 0, "center_y": 0, "base_z": 0}, "layer": "装配_底座", "color": "gray", "value_sources": {}},
            {"name": "center_shaft", "primitive": "cylinder", "dimensions": {"diameter": 30, "height": 80}, "position": {"center_x": 0, "center_y": 0, "base_z": 15}, "layer": "装配_轴", "color": "blue", "value_sources": {}},
            {"name": "top_disc", "primitive": "cylinder", "dimensions": {"diameter": 90, "height": 12}, "position": {"center_x": 0, "center_y": 0, "base_z": 95}, "layer": "装配_顶盖", "color": "green", "value_sources": {}}],
        "constraints": [
            {"type": "center_aligned_xy", "targets": ["base_disc", "center_shaft", "top_disc"], "tolerance": 0.1},
            {"type": "z_contact", "targets": ["base_disc", "center_shaft"], "tolerance": 0.1},
            {"type": "z_contact", "targets": ["center_shaft", "top_disc"], "tolerance": 0.1},
            {"type": "interference_free", "targets": ["base_disc", "center_shaft", "top_disc"], "tolerance": 0.1}],
        "acceptance": {"dimension_tolerance_mm": 0.1, "expected_object_count": 3, "require_valid_geometry": True}, "assumptions": []}


def test_advanced_specs_and_scripts():
    for raw in (stepped_shaft_spec(), sketch_spec("fillet"), sketch_spec("chamfer"), loft_spec(), assembly_spec()):
        spec = ModelingSpec.model_validate(raw)
        creation, validation = build_creation_script(spec), build_validation_script(spec)
        assert "BeginUndoRecord" in creation and "bbox_dimensions" in validation
    assert "CreateFilletEdges" in build_creation_script(ModelingSpec.model_validate(sketch_spec("fillet")))
    assert "CreateFromLoft" in build_creation_script(ModelingSpec.model_validate(loft_spec()))
    assert "interference_free" in build_validation_script(ModelingSpec.model_validate(assembly_spec()))


def test_invalid_advanced_specs_rejected():
    bad = stepped_shaft_spec(); bad["objects"][0]["steps"] = [{"diameter": 20, "length": 10}]
    with pytest.raises(ValidationError): ModelingSpec.model_validate(bad)
    bad = loft_spec(); bad["objects"][0]["sections"][1]["z"] = -1
    with pytest.raises(ValidationError): ModelingSpec.model_validate(bad)
