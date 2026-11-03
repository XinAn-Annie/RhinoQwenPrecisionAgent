from app.curve_workflow import extract_payload, validation_script, write_script

POINTS=[[float(i),float(i%2),0.0] for i in range(8)]
PARAMS={"width":7.0,"height":1.0,"depth":0.0,"length":8.0,"degree":3,"is_closed":False}

def test_validation_is_memory_only():
    script=validation_script(POINTS,PARAMS)
    assert "CreateControlPointCurve" in script
    assert "Objects.AddCurve" not in script
    assert "bbox_error_exceeds_0.1mm" in script
    assert "CurvatureAt" in script

def test_write_revalidates_before_add():
    script=write_script(POINTS,PARAMS,"token","version")
    assert script.index("curve.IsValid") < script.index("Objects.AddCurve")
    assert "bbox error exceeds 0.1 mm" in script
    assert "confirmation_token" in script

def test_extract_payload_from_router_string():
    result={"parsed":[{"payload":"progress\n{\"passed\": true}\n"}]}
    assert extract_payload(result)=={"passed":True}
