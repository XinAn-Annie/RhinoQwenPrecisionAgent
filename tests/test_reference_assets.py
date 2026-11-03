import base64
from app.reference_assets import store_reference
from app.modeling_spec import MaterialAppearance

PNG_1X1="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

def test_reference_asset_hash_and_metadata(tmp_path):
    result=store_reference(tmp_path,"reference.png","image/png",PNG_1X1)
    assert result["size_bytes"]>0
    assert result["path"].exists()
    assert len(result["sha256"])==64

def test_reference_rejects_mime_mismatch(tmp_path):
    try:store_reference(tmp_path,"wrong.jpg","image/jpeg",PNG_1X1)
    except ValueError as exc:assert "signature" in str(exc)
    else:raise AssertionError("MIME mismatch accepted")

def test_material_schema():
    material=MaterialAppearance(base_color="#AABBCC",metallic=.8,roughness=.2,finish="metallic")
    assert material.metallic==.8
