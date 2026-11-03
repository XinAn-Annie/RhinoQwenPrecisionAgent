from __future__ import annotations
import argparse, csv, hashlib, json, math, os, shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import rhino3dm

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT, REJ = ROOT/"raw", ROOT/"normalized", ROOT/"rejected"
UNIT_TO_MM={"microns":.001,"millimeters":1.,"centimeters":10.,"meters":1000.,"kilometers":1e6,"microinches":.0000254,"mils":.0254,"inches":25.4,"feet":304.8,"yards":914.4,"miles":1609344.}
def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
def atomic(path,data):
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,path)
def norm_unit(u):
    s=str(u).split(".")[-1].lower().replace(" ","")
    return s, UNIT_TO_MM.get(s)
def p3(p): return np.array([float(p.X),float(p.Y),float(p.Z)],dtype=float)
def sample_curve(c,n=128):
    d=c.Domain; ts=np.linspace(float(d.T0),float(d.T1),n); return np.array([p3(c.PointAt(float(t))) for t in ts])
def canonical(points):
    center=points.mean(axis=0); q=points-center
    if len(points)<3 or np.linalg.norm(q)<1e-12: return q,center,np.eye(3)
    _,_,v=np.linalg.svd(q,full_matrices=False); axes=v.T
    ref=points[-1]-points[0]
    for j in range(3):
        if np.dot(ref,axes[:,j]) < 0: axes[:,j]*=-1
    if np.linalg.det(axes)<0: axes[:,2]*=-1
    return q@axes,center,axes
def curvature_summary(q):
    if len(q)<5: return {"mean":0.,"max":0.,"std":0.}
    d1=np.gradient(q,axis=0); d2=np.gradient(d1,axis=0)
    den=np.linalg.norm(d1,axis=1)**3; k=np.linalg.norm(np.cross(d1,d2),axis=1)/np.maximum(den,1e-12); k=k[np.isfinite(k)]
    return {"mean":float(k.mean()) if len(k) else 0.,"max":float(k.max()) if len(k) else 0.,"std":float(k.std()) if len(k) else 0.}
def iter_curves(g):
    if isinstance(g,rhino3dm.Curve): yield g,"object_curve"
    elif isinstance(g,rhino3dm.Brep):
        for i,e in enumerate(g.Edges): yield e,f"brep_edge:{i}"
    elif isinstance(g,rhino3dm.Extrusion):
        b=g.ToBrep(True)
        if b:
            for i,e in enumerate(b.Edges): yield e,f"extrusion_edge:{i}"
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=2000); a=ap.parse_args()
    OUT.mkdir(exist_ok=True); REJ.mkdir(exist_ok=True)
    catalog=json.loads((ROOT/"sources.json").read_text(encoding="utf-8")); smap={s["source_id"]:s for s in catalog["sources"]}
    dstate=json.loads((ROOT/"state"/"downloads.json").read_text(encoding="utf-8")) if (ROOT/"state"/"downloads.json").exists() else {"files":{}}
    seen=set(); rows=[]; rejects=[]
    for path in sorted(RAW.rglob("*.3dm")):
        if len(rows)>=a.limit: break
        source_id=path.relative_to(RAW).parts[0]; src=smap.get(source_id,{})
        try: model=rhino3dm.File3dm.Read(str(path))
        except Exception as e: rejects.append({"file":str(path),"reason":"read_error","detail":str(e)}); continue
        uname,scale=norm_unit(model.Settings.ModelUnitSystem)
        if scale is None:
            rejects.append({"file":str(path),"reason":"missing_or_unsupported_unit","value":str(model.Settings.ModelUnitSystem)}); continue
        file_sha=hashlib.sha256(path.read_bytes()).hexdigest()
        for oi,obj in enumerate(model.Objects):
            for ci,(curve,role) in enumerate(iter_curves(obj.Geometry)):
                if len(rows)>=a.limit: break
                try:
                    n=curve.ToNurbsCurve()
                    if n is None or len(n.Points)<2: raise ValueError("no control points")
                    cps=np.array([[p.X,p.Y,p.Z] for p in n.Points],dtype=float)*scale
                    weights=[float(p.W) for p in n.Points]; knots=[float(x) for x in n.Knots.ToList()]
                    sampled=sample_curve(curve)*scale
                    if not np.isfinite(cps).all() or not np.isfinite(sampled).all(): raise ValueError("non-finite coordinates")
                    sampled_n,center,axes=canonical(sampled); cps_n=(cps-center)@axes
                    start,end=sampled_n[0],sampled_n[-1]; dif=np.diff(sampled_n,axis=0); length=float(np.linalg.norm(dif,axis=1).sum())
                    extent=np.ptp(sampled_n,axis=0); curv=curvature_summary(sampled_n)
                    geom_key=json.dumps({"d":int(n.Degree),"c":np.round(cps_n,6).tolist(),"w":np.round(weights,8).tolist(),"k":np.round(knots,8).tolist()},sort_keys=True,separators=(",",":"))
                    gh=hashlib.sha256(geom_key.encode()).hexdigest()
                    if gh in seen: continue
                    seen.add(gh); cid=f"{source_id}-{gh[:20]}"
                    item={"curve_id":cid,"source_url":src.get("source_url"),"license":src.get("license"),"format":"3dm","unit":"mm","degree":int(n.Degree),"is_closed":bool(curve.IsClosed),"control_points":np.round(cps_n,9).tolist(),"weights":weights,"knots":knots,"start_point":np.round(start,9).tolist(),"end_point":np.round(end,9).tolist(),"length":length,"bbox":{"width":float(extent[0]),"height":float(extent[1]),"depth":float(extent[2])},"curvature_summary":curv,"provenance":{"source_id":source_id,"raw_file":str(path.relative_to(ROOT)),"raw_sha256":file_sha,"object_index":oi,"curve_index":ci,"geometry_role":role,"original_unit":uname,"unit_scale_to_mm":scale,"normalization":{"translation":center.tolist(),"rotation_columns":axes.tolist(),"scale":1.0},"processed_at":now()}}
                    atomic(OUT/f"{cid}.json",item); rows.append(item)
                except Exception as e: rejects.append({"file":str(path.relative_to(ROOT)),"object_index":oi,"curve_index":ci,"reason":"curve_parse_error","detail":str(e)})
    atomic(REJ/"rejections.json",rejects)
    fields=["curve_id","source_id","license","degree","is_closed","control_point_count","unit","length","width","height","depth","path"]
    with (OUT/"curves.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for x in rows:w.writerow({"curve_id":x["curve_id"],"source_id":x["provenance"]["source_id"],"license":x["license"],"degree":x["degree"],"is_closed":x["is_closed"],"control_point_count":len(x["control_points"]),"unit":x["unit"],"length":x["length"],"width":x["bbox"]["width"],"height":x["bbox"]["height"],"depth":x["bbox"]["depth"],"path":f"normalized/{x['curve_id']}.json"})
    cdeg=Counter(str(x["degree"]) for x in rows); ccp=Counter(str(len(x["control_points"])) for x in rows); clic=Counter(x["license"] for x in rows); cunit=Counter(x["unit"] for x in rows)
    manifest={"schema_version":"1.0","generated_at":now(),"limit":a.limit,"total_curves":len(rows),"trainable_curves":len(rows),"rejected_curves":len(rejects),"open_curves":sum(not x["is_closed"] for x in rows),"closed_curves":sum(x["is_closed"] for x in rows),"degree_distribution":dict(cdeg),"control_point_count_distribution":dict(ccp),"unit_distribution":dict(cunit),"license_distribution":dict(clic),"curves":[{"curve_id":x["curve_id"],"path":f"normalized/{x['curve_id']}.json","source_id":x["provenance"]["source_id"],"license":x["license"],"sha256":hashlib.sha256((OUT/f"{x['curve_id']}.json").read_bytes()).hexdigest()} for x in rows]}
    atomic(ROOT/"dataset_manifest.json",manifest)
    report=f"""# Rhino 曲线数据质量报告\n\n生成时间：{manifest['generated_at']}\n\n- 总曲线数：{len(rows)}\n- 可训练曲线数：{len(rows)}\n- 拒绝记录：{len(rejects)}\n- 开放 / 闭合：{manifest['open_curves']} / {manifest['closed_curves']}\n- 单位：{dict(cunit)}\n- 阶数分布：{dict(cdeg)}\n- 控制点数分布：{dict(ccp)}\n- 许可证分布：{dict(clic)}\n\n## 处理规则\n\n仅接受许可证已核验且 3DM 内嵌单位可转换为 mm 的曲线；从独立曲线、BRep 边和挤出边提取 NURBS；按控制点、权重、节点和阶数去重；平移到质心并使用确定性 PCA 右手坐标系旋转，不缩放物理尺寸。\n\n## 限制\n\n当前为 2000 条课堂演示上限的 McNeel 小样本试运行。统计只反映实际成功解析的曲线，不代表完整 CAD 市场分布。\n"""
    (ROOT/"dataset_report.md").write_text(report,encoding="utf-8")
    print(json.dumps({k:manifest[k] for k in ["total_curves","trainable_curves","rejected_curves","open_curves","closed_curves"]},ensure_ascii=False))
if __name__=="__main__": main()
