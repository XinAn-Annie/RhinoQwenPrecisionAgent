from __future__ import annotations
import csv, hashlib, json, math, os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.interpolate import BSpline

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"normalized"; MAN=ROOT/"dataset_manifest.json"
def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
def atomic(path,data):
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,path)
def evaluate(cps,w,knots,degree,n=128):
    t=np.asarray(knots,float); full=np.r_[t[0],t,t[-1]]
    lo,hi=full[degree],full[-degree-1]; u=np.linspace(lo,hi,n)
    num=BSpline(full,cps*w[:,None],degree,extrapolate=False)(u); den=BSpline(full,w,degree,extrapolate=False)(u)
    return num/np.maximum(den[:,None],1e-12)
def metrics(q):
    length=float(np.linalg.norm(np.diff(q,axis=0),axis=1).sum()); ext=np.ptp(q,axis=0)
    d1=np.gradient(q,axis=0); d2=np.gradient(d1,axis=0); k=np.linalg.norm(np.cross(d1,d2),axis=1)/np.maximum(np.linalg.norm(d1,axis=1)**3,1e-12); k=k[np.isfinite(k)]
    return length,ext,{"mean":float(k.mean()),"max":float(k.max()),"std":float(k.std())}
def main(target=2000):
    man=json.loads(MAN.read_text(encoding="utf-8")); bases=[json.loads((ROOT/e["path"]).read_text(encoding="utf-8")) for e in man["curves"]]
    if not bases: raise SystemExit("no base curves")
    items=list(bases); idx=0
    while len(items)<target:
        b=bases[idx%len(bases)]; gen=idx//len(bases)+1; idx+=1
        seed=int(hashlib.sha256(f"{b['curve_id']}:{gen}".encode()).hexdigest()[:16],16); rng=np.random.default_rng(seed)
        cps=np.asarray(b["control_points"],float); w=np.asarray(b["weights"],float); span=max(float(np.ptp(cps,axis=0).max()),1e-6)
        scales=rng.uniform(.72,1.28,3); c=cps*scales
        noise=rng.normal(0,span*.006,size=c.shape)
        if len(c)>2:
            noise=(np.roll(noise,1,axis=0)+2*noise+np.roll(noise,-1,axis=0))/4
        if b["is_closed"]:
            noise[-1]=noise[0]
        else:
            noise[0]=0; noise[-1]=0
        c=c+noise
        q=evaluate(c,w,np.asarray(b["knots"],float),int(b["degree"])); length,ext,curv=metrics(q)
        aid=f"{b['curve_id']}-aug{gen:03d}"; x=dict(b); x.update({"curve_id":aid,"control_points":np.round(c,9).tolist(),"start_point":np.round(q[0],9).tolist(),"end_point":np.round(q[-1],9).tolist(),"length":length,"bbox":{"width":float(ext[0]),"height":float(ext[1]),"depth":float(ext[2])},"curvature_summary":curv})
        x["provenance"]=dict(b["provenance"]); x["provenance"].update({"derivation":"deterministic_control_point_augmentation","base_curve_id":b["curve_id"],"source_group":b["curve_id"],"augmentation_index":gen,"augmentation_seed":seed,"axis_scales":scales.tolist(),"jitter_sigma_mm":span*.006,"processed_at":now()})
        atomic(OUT/f"{aid}.json",x); items.append(x)
    entries=[]
    for x in items[:target]:
        p=OUT/f"{x['curve_id']}.json"; entries.append({"curve_id":x["curve_id"],"path":f"normalized/{x['curve_id']}.json","source_id":x["provenance"]["source_id"],"source_group":x["provenance"].get("source_group",x["curve_id"]),"license":x["license"],"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
    man.update({"generated_at":now(),"total_curves":target,"trainable_curves":target,"observed_curves":len(bases),"derived_curves":target-len(bases),"open_curves":sum(not x["is_closed"] for x in items[:target]),"closed_curves":sum(x["is_closed"] for x in items[:target]),"degree_distribution":dict(Counter(str(x["degree"]) for x in items[:target])),"control_point_count_distribution":dict(Counter(str(len(x["control_points"])) for x in items[:target])),"unit_distribution":{"mm":target},"license_distribution":dict(Counter(x["license"] for x in items[:target])),"curves":entries}); atomic(MAN,man)
    with (OUT/"curves.csv").open("w",newline="",encoding="utf-8-sig") as f:
        fields=["curve_id","source_group","license","degree","is_closed","control_point_count","unit","length","width","height","depth","path"]; wri=csv.DictWriter(f,fieldnames=fields); wri.writeheader()
        for x in items[:target]: wri.writerow({"curve_id":x["curve_id"],"source_group":x["provenance"].get("source_group",x["curve_id"]),"license":x["license"],"degree":x["degree"],"is_closed":x["is_closed"],"control_point_count":len(x["control_points"]),"unit":"mm","length":x["length"],"width":x["bbox"]["width"],"height":x["bbox"]["height"],"depth":x["bbox"]["depth"],"path":f"normalized/{x['curve_id']}.json"})
    report=f"""# Rhino 曲线数据质量报告\n\n生成时间：{man['generated_at']}\n\n- 总曲线数：{target}\n- 可训练曲线数：{target}\n- 真实抓取并解析的基础曲线：{len(bases)}\n- 可追溯派生曲线：{target-len(bases)}\n- 开放 / 闭合：{man['open_curves']} / {man['closed_curves']}\n- 单位：mm\n- 许可证：{man['license_distribution']}\n- 阶数分布：{man['degree_distribution']}\n- 控制点数分布：{man['control_point_count_distribution']}\n\n## 真实性说明\n\n没有虚构抓取量。实际网络抓取为 7 个 McNeel rview 3DM 文件（约 26.8 MB），其中只有 RhinoLogo.3dm 含可提取 BRep 曲线，去重后得到 {len(bases)} 条基础曲线。其余 {target-len(bases)} 条是对基础 NURBS 控制点做确定性尺度与小扰动得到的派生训练样本，均保留 base_curve_id、种子和变换参数。\n\n## 处理规则\n\n只接受内嵌单位，统一为 mm；转换为 NURBS；按几何哈希去重；平移到质心并使用确定性 PCA 右手坐标系；不缩放基础曲线物理尺寸。训练拆分必须按 base_curve_id 分组，禁止派生同源泄漏。\n"""; (ROOT/"dataset_report.md").write_text(report,encoding="utf-8")
    print(json.dumps({"total":target,"observed":len(bases),"derived":target-len(bases)},ensure_ascii=False))
if __name__=="__main__": main()
