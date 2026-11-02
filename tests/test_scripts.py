from app.modeling_spec import ModelingSpec
from app.rhino_executor import build_creation_script
from app.validator import build_validation_script
from tests.test_modeling_spec import box_spec, enclosure_spec, flange_spec


def test_generated_scripts_have_expected_guards_and_checks():
    spec = ModelingSpec.model_validate(box_spec())
    creation = build_creation_script(spec)
    validation = build_validation_script(spec)
    assert "BeginUndoRecord" in creation and "__rhino_doc__" in creation
    assert "bbox_dimensions" in validation and "closed_solid" in validation and "valid_geometry" in validation


def test_precision_scripts_use_deterministic_booleans_and_feature_checks():
    flange = ModelingSpec.model_validate(flange_spec())
    enclosure = ModelingSpec.model_validate(enclosure_spec())
    flange_creation, flange_validation = build_creation_script(flange), build_validation_script(flange)
    enclosure_creation, enclosure_validation = build_creation_script(enclosure), build_validation_script(enclosure)
    assert "CreateBooleanDifference" in flange_creation and "bolt_hole_pattern" in flange_validation and "feature_volume" in flange_validation
    assert "CreateBooleanDifference" in enclosure_creation and "enclosure_cavity" in enclosure_validation and "enclosure_wall" in enclosure_validation
