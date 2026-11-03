from __future__ import annotations
import json, math
from pathlib import Path
import joblib, numpy as np
from scipy.interpolate import BSpline

ROOT=Path(__file__).resolve().parent
MODEL=joblib.load(ROOT/"model.joblib"); SCALER=joblib.load(ROOT/"scaler.joblib")
SCHEMA=json.loads((ROOT/"feature_schema.json").read_text(encoding="utf-8")); METRICS=json.loads((ROOT/"train_metrics.json").read_text(encoding="utf-8"))
FEATURES=SCHEMA["features"]
def sample_controls(p,n=160):
    degree=3; count=len(p); full=np.r_[np.zeros(degree+1),np.linspace(0,1,count-degree+1)[1:-1],np.ones(degree+1)]; return BSpline(full,p,degree)(np.linspace(0,1,n))
def calibrate(p,desired):
    q=sample_controls(p); lo=q.min(0); hi=q.max(0); center=(lo+hi)/2; span=hi-lo
    for j in range(3):
        if desired[j]<=1e-10:p[:,j]=0.0
        elif span[j]>1e-10:p[:,j]=(p[:,j]-center[j])*(desired[j]/span[j])+center[j]
    return p
def predict_curve(payload:dict)->dict:
    v={**SCHEMA.get("defaults",{}),**payload}; v.setdefault("depth",0.0); v.setdefault("is_closed",False); v.setdefault("degree",3); v.setdefault("length",math.hypot(float(v.get("width",0)),float(v.get("height",0))))
    if not v["is_closed"]:
        if "start_x" not in payload: v["start_x"]=-float(v.get("width",0))/2
        if "end_x" not in payload: v["end_x"]=float(v.get("width",0))/2
        if "end_y" not in payload: v["end_y"]=0.0
        if "end_z" not in payload: v["end_z"]=0.0
    row=np.asarray([[float(bool(v[n])) if n=="is_closed" else float(v.get(n,0)) for n in FEATURES]])
    warnings=[]
    optional_zero={"depth","curvature_mean","curvature_max","curvature_std"}
    for i,n in enumerate(FEATURES):
        lo,hi=SCHEMA["input_ranges"][n]
        if n in optional_zero and abs(row[0,i])<1e-12: continue
        if row[0,i]<lo or row[0,i]>hi: warnings.append(f"{n} outside training range [{lo:.4g}, {hi:.4g}]")
    xs=SCALER.transform(row); pred=MODEL.predict(xs)[0].reshape(8,3)
    if v["is_closed"]: pred[-1]=(pred[0]+pred[-1])/2; pred[0]=pred[-1]
    requested=np.array([v.get("width",0),v.get("height",0),v.get("depth",0)],float); pred=calibrate(pred,requested); sampled=sample_controls(pred)
    if hasattr(MODEL,"estimators_"):
        allp=np.stack([e.predict(xs)[0] for e in MODEL.estimators_]); spread=float(np.mean(np.std(allp,axis=0))); confidence=float(np.exp(-spread/max(METRICS["test"]["control_point_rmse"],1e-6)))
    else: confidence=float(np.exp(-METRICS["test"]["control_point_rmse"]))
    extent=np.ptp(sampled,axis=0); size_error=np.abs(extent-requested)
    valid=bool(np.isfinite(pred).all() and len(pred)==8 and 1<=int(v["degree"])<8)
    if not valid:warnings.append("geometry invalid")
    if confidence<.55:warnings.append("low confidence")
    if np.max(size_error)>.1:warnings.append("size error budget exceeds 0.1 mm")
    accepted=valid and confidence>=.55 and np.max(size_error)<=.1 and not any("outside training range" in x for x in warnings)
    return {"status":"preview_only" if accepted else "rejected","control_points":pred.tolist(),"confidence":confidence,"metrics":{"predicted_bbox":{"width":float(extent[0]),"height":float(extent[1]),"depth":float(extent[2])},"bbox_abs_error_mm":size_error.tolist(),"model_test_rmse_mm":METRICS["test"]["control_point_rmse"],"rhino_common_validation_required":True},"warnings":warnings,"model_version":SCHEMA["model_version"],"may_write_to_rhino":False}
