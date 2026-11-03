from __future__ import annotations
import json, math, re
from typing import Any
from .mcp_rhino_client import RhinoMCPClient

def _safe(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("'''", "")

def validation_script(points: list[list[float]], params: dict[str, Any]) -> str:
    payload=_safe({"points":points,"params":params})
    return f'''import json, math
import Rhino
data=json.loads(r"""{payload}""")
p=data["params"]
pts=[Rhino.Geometry.Point3d(float(v[0]),float(v[1]),float(v[2])) for v in data["points"]]
degree=int(p.get("degree",3))
curve=Rhino.Geometry.Curve.CreateControlPointCurve(pts,degree)
result={{"passed":False,"is_valid":False,"checks":{{}},"errors":[],"preview_points":[]}}
if curve is None:
    result["errors"].append("curve_creation_failed")
else:
    result["is_valid"]=bool(curve.IsValid)
    box=curve.GetBoundingBox(True)
    size=[abs(float(box.Diagonal.X)),abs(float(box.Diagonal.Y)),abs(float(box.Diagonal.Z))]
    expected=[float(p.get("width",0)),float(p.get("height",0)),float(p.get("depth",0))]
    bbox_error=[abs(size[i]-expected[i]) for i in range(3)]
    length=float(curve.GetLength())
    expected_length=float(p.get("length",length))
    length_error=abs(length-expected_length)
    start_error=float(curve.PointAtStart.DistanceTo(pts[0]))
    end_error=float(curve.PointAtEnd.DistanceTo(pts[-1]))
    curvatures=[]
    for i in range(33):
        t=curve.Domain.ParameterAt(i/32.0)
        k=curve.CurvatureAt(t)
        value=float(k.Length)
        if math.isnan(value) or math.isinf(value):
            result["errors"].append("non_finite_curvature")
        else: curvatures.append(value)
    for i in range(65):
        pt=curve.PointAt(curve.Domain.ParameterAt(i/64.0)); result["preview_points"].append([float(pt.X),float(pt.Y),float(pt.Z)])
    closed_ok=bool(curve.IsClosed)==bool(p.get("is_closed",False))
    result["checks"]={{"length_mm":length,"expected_length_mm":expected_length,"length_error_mm":length_error,"bbox_mm":size,"bbox_error_mm":bbox_error,"start_error_mm":start_error,"end_error_mm":end_error,"curvature_mean":sum(curvatures)/len(curvatures) if curvatures else None,"curvature_max":max(curvatures) if curvatures else None,"is_closed":bool(curve.IsClosed),"closed_matches":closed_ok}}
    length_tolerance=max(0.1,expected_length*0.05)
    result["passed"]=bool(curve.IsValid and max(bbox_error)<=0.1 and length_error<=length_tolerance and start_error<=1e-6 and end_error<=1e-6 and closed_ok and not result["errors"])
    if not curve.IsValid: result["errors"].append("rhino_curve_invalid")
    if max(bbox_error)>0.1: result["errors"].append("bbox_error_exceeds_0.1mm")
    if length_error>length_tolerance: result["errors"].append("length_error_exceeds_5_percent")
    if not closed_ok: result["errors"].append("closed_state_mismatch")
print(json.dumps(result))'''

def write_script(points: list[list[float]], params: dict[str, Any], token: str, model_version: str) -> str:
    payload=_safe({"points":points,"params":params,"token":token,"model_version":model_version})
    return f'''import json, math
import Rhino, System
data=json.loads(r"""{payload}"""); p=data["params"]
pts=[Rhino.Geometry.Point3d(float(v[0]),float(v[1]),float(v[2])) for v in data["points"]]
curve=Rhino.Geometry.Curve.CreateControlPointCurve(pts,int(p.get("degree",3)))
if curve is None or not curve.IsValid: raise RuntimeError("curve failed final RhinoCommon validation")
box=curve.GetBoundingBox(True); size=[abs(float(box.Diagonal.X)),abs(float(box.Diagonal.Y)),abs(float(box.Diagonal.Z))]; expected=[float(p.get("width",0)),float(p.get("height",0)),float(p.get("depth",0))]
if max(abs(size[i]-expected[i]) for i in range(3))>0.1: raise RuntimeError("bbox error exceeds 0.1 mm")
if bool(curve.IsClosed)!=bool(p.get("is_closed",False)): raise RuntimeError("closed state mismatch")
attrs=Rhino.DocObjects.ObjectAttributes(); attrs.Name="Qwen_Predicted_Curve"; attrs.SetUserString("curve_predictor_model",data["model_version"]); attrs.SetUserString("confirmation_token",data["token"])
undo_id=__rhino_doc__.BeginUndoRecord("Qwen confirmed curve")
try:
    object_id=__rhino_doc__.Objects.AddCurve(curve,attrs)
    if object_id==System.Guid.Empty: raise RuntimeError("failed to add curve")
    __rhino_doc__.Views.Redraw()
finally: __rhino_doc__.EndUndoRecord(undo_id)
print(json.dumps({{"written":True,"object_id":str(object_id),"undo_record":undo_id}}))'''

def extract_payload(result: dict[str, Any]) -> dict[str, Any]:
    for envelope in result.get("parsed",[]):
        payload=envelope.get("payload")
        if isinstance(payload,dict): return payload
        if isinstance(payload,str):
            for line in reversed(payload.splitlines()):
                line=line.strip()
                if line.startswith("{"):
                    try:return json.loads(line)
                    except json.JSONDecodeError:pass
    return {"passed":False,"errors":["unparseable_rhino_mcp_response"],"mcp_is_error":result.get("is_error",False)}

async def validate_in_rhino(mcp: RhinoMCPClient, points: list[list[float]], params: dict[str,Any], slot: str|None):
    args={"script":validation_script(points,params)}
    if slot:args["slot"]=slot
    return extract_payload(await mcp.call("run_python",args))

async def write_confirmed_curve(mcp: RhinoMCPClient, points:list[list[float]],params:dict[str,Any],token:str,model_version:str,slot:str|None):
    args={"script":write_script(points,params,token,model_version)}
    if slot:args["slot"]=slot
    return extract_payload(await mcp.call("run_python",args))
