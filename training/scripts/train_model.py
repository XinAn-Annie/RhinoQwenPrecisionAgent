from __future__ import annotations
import json, math, os, time, hashlib
from pathlib import Path
import joblib, numpy as np
from scipy.interpolate import BSpline, make_lsq_spline
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.compose import TransformedTargetRegressor

ROOT=Path(__file__).resolve().parents[1]; MODEL_DIR=ROOT.parent/"curve_predictor"; MODEL_DIR.mkdir(parents=True,exist_ok=True); (MODEL_DIR/"logs").mkdir(exist_ok=True)
FEATURES=["width","height","depth","length","degree","is_closed","start_x","start_y","start_z","end_x","end_y","end_z","curvature_mean","curvature_max","curvature_std","control_point_count"]
ALLOWED={"MIT","CC-BY-4.0","Apache-2.0","BSD-2-Clause","BSD-3-Clause","CC0-1.0","Generated-By-Project"}
def atomic(path,data):
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,path)
def eval_nurbs(x,n=128):
    c=np.asarray(x["control_points"],float); w=np.asarray(x["weights"],float); k=int(x["degree"]); t=np.asarray(x["knots"],float); full=np.r_[t[0],t,t[-1]]; u=np.linspace(full[k],full[-k-1],n)
    return BSpline(full,c*w[:,None],k)(u)/np.maximum(BSpline(full,w,k)(u)[:,None],1e-12)
def arclength_resample(q,n=8):
    d=np.r_[0,np.cumsum(np.linalg.norm(np.diff(q,axis=0),axis=1))]
    if d[-1]<1e-12:return np.repeat(q[:1],n,axis=0)
    z=np.linspace(0,d[-1],n); return np.column_stack([np.interp(z,d,q[:,j]) for j in range(3)])
def target8(x):
    c=np.asarray(x["control_points"],float)
    if len(c)==8:return c
    q=eval_nurbs(x,160)
    if len(c)<8:return arclength_resample(q,8)
    d=np.r_[0,np.cumsum(np.linalg.norm(np.diff(q,axis=0),axis=1))]; u=d/max(d[-1],1e-12); deg=min(3,int(x["degree"]),7); internal=np.linspace(0,1,8-deg+1)[1:-1]; knots=np.r_[np.zeros(deg+1),internal,np.ones(deg+1)]
    return np.column_stack([make_lsq_spline(u,q[:,j],knots,deg).c for j in range(3)])
def feat(x):
    b=x["bbox"]; s=x["start_point"]; e=x["end_point"]; k=x["curvature_summary"]
    return [b["width"],b["height"],b["depth"],x["length"],x["degree"],int(x["is_closed"]),*s,*e,k.get("mean",0),k.get("max",0),k.get("std",0),len(x["control_points"])]
def curve_metrics(y,true):
    p=y.reshape(-1,3); t=true.reshape(-1,3); pq=sample_controls(p); tq=sample_controls(t); pe=np.ptp(pq,axis=0); te=np.ptp(tq,axis=0); plen=np.linalg.norm(np.diff(pq,axis=0),axis=1).sum(); tlen=np.linalg.norm(np.diff(tq,axis=0),axis=1).sum()
    d1=np.gradient(p,axis=0); d2=np.gradient(d1,axis=0); pk=np.linalg.norm(np.cross(d1,d2),axis=1)/np.maximum(np.linalg.norm(d1,axis=1)**3,1e-12)
    td1=np.gradient(t,axis=0); td2=np.gradient(td1,axis=0); tk=np.linalg.norm(np.cross(td1,td2),axis=1)/np.maximum(np.linalg.norm(td1,axis=1)**3,1e-12)
    return {"length_abs_error":float(abs(plen-tlen)),"bbox_mae":float(np.abs(pe-te).mean()),"bbox_max_error":float(np.abs(pe-te).max()),"start_error":float(np.linalg.norm(p[0]-t[0])),"end_error":float(np.linalg.norm(p[-1]-t[-1])),"curvature_mean_error":float(abs(np.nanmean(pk)-np.nanmean(tk))),"valid":bool(np.isfinite(p).all() and len(p)==8)}

def sample_controls(p,n=160):
    degree=3; count=len(p); full=np.r_[np.zeros(degree+1),np.linspace(0,1,count-degree+1)[1:-1],np.ones(degree+1)]; return BSpline(full,p,degree)(np.linspace(0,1,n))

def calibrate_controls(flat, desired_bbox):
    p=np.asarray(flat,float).reshape(8,3); q=sample_controls(p); lo=q.min(0); hi=q.max(0); center=(lo+hi)/2; span=hi-lo; desired=np.asarray(desired_bbox,float)
    for j in range(3):
        if desired[j] <= 1e-10: p[:,j]=0.0
        elif span[j] > 1e-10: p[:,j]=(p[:,j]-center[j])*(desired[j]/span[j])+center[j]
    return p.reshape(-1)
def main():
    started=time.time(); man=json.loads((ROOT/"dataset_manifest.json").read_text(encoding="utf-8")); data=[]
    for e in man["curves"]:
        x=json.loads((ROOT/e["path"]).read_text(encoding="utf-8"))
        if x["license"].split(" (")[0] not in ALLOWED: continue
        data.append(x)
    X=np.asarray([feat(x) for x in data]); Y=np.asarray([target8(x).reshape(-1) for x in data]); groups=np.asarray([x["provenance"].get("source_group",x["provenance"].get("base_curve_id",x["curve_id"])) for x in data])
    good=np.isfinite(X).all(1)&np.isfinite(Y).all(1); X,Y,groups=np.asarray(X[good]),np.asarray(Y[good]),groups[good]
    g1=GroupShuffleSplit(1,test_size=.30,random_state=42); tr,tmp=next(g1.split(X,Y,groups)); g2=GroupShuffleSplit(1,test_size=.50,random_state=43); va0,te0=next(g2.split(X[tmp],Y[tmp],groups[tmp])); va,te=tmp[va0],tmp[te0]
    scaler=StandardScaler().fit(X[tr]); xs={"train":scaler.transform(X[tr]),"validation":scaler.transform(X[va]),"test":scaler.transform(X[te])}
    models={"ExtraTreesRegressor":ExtraTreesRegressor(n_estimators=400,min_samples_leaf=1,n_jobs=-1,random_state=42),"MLPRegressor":TransformedTargetRegressor(regressor=MLPRegressor(hidden_layer_sizes=(64,32),solver="lbfgs",max_iter=1200,random_state=42,tol=1e-8),transformer=StandardScaler())}
    results={}; fitted={}
    for name,m in models.items():
        t=time.time(); m.fit(xs["train"],Y[tr]); pred=m.predict(xs["validation"]); results[name]={"validation_mae":float(mean_absolute_error(Y[va],pred)),"validation_rmse":float(mean_squared_error(Y[va],pred)**.5),"train_seconds":time.time()-t}; fitted[name]=m
    best=min(results,key=lambda n:results[n]["validation_rmse"]); model=fitted[best]; pred_raw=model.predict(xs["test"]); pred=np.asarray([calibrate_controls(p,X[i,:3]) for p,i in zip(pred_raw,te)])
    cm=[curve_metrics(p,t) for p,t in zip(pred,Y[te])]; aggregate={"control_point_mae":float(mean_absolute_error(Y[te],pred)),"control_point_rmse":float(mean_squared_error(Y[te],pred)**.5)}
    for k in ["length_abs_error","bbox_mae","bbox_max_error","start_error","end_error","curvature_mean_error"]: aggregate[k+"_mean"]=float(np.mean([m[k] for m in cm]))
    aggregate["rhino_curve_validity_rate"]=float(np.mean([m["valid"] for m in cm])); aggregate["max_size_error_le_0_1mm_rate"]=float(np.mean([m["bbox_max_error"]<=.1 for m in cm]))
    ready=bool(aggregate["rhino_curve_validity_rate"]==1 and aggregate["max_size_error_le_0_1mm_rate"]>=.95 and aggregate["control_point_rmse"]<=.1)
    version=hashlib.sha256((best+man["generated_at"]).encode()).hexdigest()[:12]
    metrics={"model_version":version,"selected_model":best,"candidates":results,"split":{"strategy":"GroupShuffleSplit by base_curve_id","train":len(tr),"validation":len(va),"test":len(te),"train_groups":len(set(groups[tr])),"validation_groups":len(set(groups[va])),"test_groups":len(set(groups[te]))},"test":aggregate,"training_seconds_total":time.time()-started,"meets_qwen_minimum_standard":ready}
    joblib.dump(model,MODEL_DIR/"model.joblib"); joblib.dump(scaler,MODEL_DIR/"scaler.joblib"); atomic(MODEL_DIR/"train_metrics.json",metrics)
    schema={"model_version":version,"features":FEATURES,"output_shape":[8,3],"unit":"mm","domain":"classroom_standard_open_and_closed_curve_families_v2","defaults":{"depth":0,"start_x":0,"start_y":0,"start_z":0,"end_x":0,"end_y":0,"end_z":0,"curvature_mean":0,"curvature_max":0,"curvature_std":0,"control_point_count":8},"input_ranges":{FEATURES[i]:[float(np.min(X[:,i])),float(np.max(X[:,i]))] for i in range(len(FEATURES))},"license_allowlist":sorted(ALLOWED),"postprocessing":{"type":"sampled_curve_bbox_calibration","samples":160,"does_not_change_degree_or_point_count":True},"rejection":{"bbox_max_error_mm":0.1,"require_finite":True,"require_8_points":True}}; atomic(MODEL_DIR/"feature_schema.json",schema)
    tests=[]
    for i,(ix,p,t) in enumerate(zip(te,pred,Y[te])):
        tests.append({"curve_id":data[int(ix)]["curve_id"],"predicted_control_points":p.reshape(8,3).tolist(),"true_control_points":t.reshape(8,3).tolist(),"metrics":cm[i]})
    atomic(MODEL_DIR/"test_predictions.json",tests)
    conclusion="达到" if ready else "未达到"
    report=f"""# 曲线预测模型训练报告\n\n- 模型版本：{version}\n- 最优模型：{best}\n- 训练/验证/测试：{len(tr)} / {len(va)} / {len(te)}（按 base_curve_id 分组，无派生同源泄漏）\n- 控制点 MAE：{aggregate['control_point_mae']:.6f} mm\n- 控制点 RMSE：{aggregate['control_point_rmse']:.6f} mm\n- BBox 最大尺寸误差均值：{aggregate['bbox_max_error_mean']:.6f} mm\n- 长度误差均值：{aggregate['length_abs_error_mean']:.6f} mm\n- 起点/终点误差均值：{aggregate['start_error_mean']:.6f} / {aggregate['end_error_mean']:.6f} mm\n- Rhino 几何基础有效率：{aggregate['rhino_curve_validity_rate']:.2%}\n- 最大尺寸误差 ≤0.1 mm 比例：{aggregate['max_size_error_le_0_1mm_rate']:.2%}\n\n## 结论\n\n**{conclusion}可接入 Qwen 的最低标准。** 接口已设置拒绝门：低置信度、输入超训练范围、尺寸误差预算超限或几何无效时只返回拒绝，不写入 Rhino。当前数据只有 35 条真实基础曲线，其余为可追溯派生样本；即使数值指标通过，也仅适合课堂演示，不代表通用 CAD 能力。\n"""; (MODEL_DIR/"training_report.md").write_text(report,encoding="utf-8")
    print(json.dumps({"selected":best,"test":aggregate,"ready":ready,"dir":str(MODEL_DIR)},ensure_ascii=False))
if __name__=="__main__": main()
