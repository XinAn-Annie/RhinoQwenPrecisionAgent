from __future__ import annotations
import hashlib, json, os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.interpolate import BSpline

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'normalized'
def now():return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
def atomic(p,d):
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(t,p)
def knots(n=8,p=3):
    full=np.r_[np.zeros(p+1),np.linspace(0,1,n-p+1)[1:-1],np.ones(p+1)];return full[1:-1].tolist()
def eval_curve(c,p=3,n=160):
    k=np.asarray(knots(len(c),p));full=np.r_[k[0],k,k[-1]];u=np.linspace(full[p],full[-p-1],n);return BSpline(full,c,p)(u)
def stats(q):
    d=np.diff(q,axis=0);length=float(np.linalg.norm(d,axis=1).sum());ext=np.ptp(q,axis=0);d1=np.gradient(q,axis=0);d2=np.gradient(d1,axis=0);cur=np.linalg.norm(np.cross(d1,d2),axis=1)/np.maximum(np.linalg.norm(d1,axis=1)**3,1e-12)
    return length,ext,{'mean':float(cur.mean()),'max':float(cur.max()),'std':float(cur.std())}
def make_open(w,h,d,variant):
    x=np.linspace(-w/2,w/2,8); patterns=[np.array([0,.45,.82,1,1,.82,.45,0]),np.array([0,.65,1,.45,-.45,-1,-.65,0]),np.array([0,.25,.75,1,.7,.2,-.1,0])]
    y=h*patterns[variant%3]; z=(d/2)*np.array([0,.5,1,.5,-.5,-1,-.5,0]); return np.c_[x,y,z]
def make_closed(w,h,d,variant):
    a=np.linspace(0,2*np.pi,8); phase=(variant%3)*np.pi/14; c=np.c_[(w/2)*np.cos(a+phase),(h/2)*np.sin(a+phase),(d/2)*np.sin(2*a)]; c[-1]=c[0];return c
def main(n=2000):
    active=OUT/'standard_v2';active.mkdir(parents=True,exist_ok=True);items=[]
    for i in range(n):
        rng=np.random.default_rng(20261103+i);closed=(i%4==0);variant=0;w=float(rng.uniform(5,120));h=float(rng.uniform(2,60));d=float(rng.uniform(0,20));c=make_closed(w,h,d,variant) if closed else make_open(w,h,d,variant);q=eval_curve(c);length,ext,cur=stats(q);cid=f"standard-{i:04d}-{hashlib.sha256(c.tobytes()).hexdigest()[:12]}";batch=f"generator_batch_{i%20:02d}"
        x={'curve_id':cid,'source_url':'local://rhino-curve-standard-generator/v2','license':'Generated-By-Project','format':'json','unit':'mm','degree':3,'is_closed':closed,'control_points':np.round(c,9).tolist(),'weights':[1.0]*8,'knots':knots(),'start_point':np.round(q[0],9).tolist(),'end_point':np.round(q[-1],9).tolist(),'length':length,'bbox':{'width':float(ext[0]),'height':float(ext[1]),'depth':float(ext[2])},'curvature_summary':cur,'provenance':{'source_id':'local_standard_generator_v2','source_group':batch,'generator_version':'2.0','generator_seed':20261103+i,'shape_family':'closed_periodic' if closed else f'open_{variant}','generated_at':now(),'synthetic':True}}
        atomic(active/f'{cid}.json',x);items.append(x)
    entries=[]
    for x in items:
        p=active/f"{x['curve_id']}.json";entries.append({'curve_id':x['curve_id'],'path':f"normalized/standard_v2/{x['curve_id']}.json",'source_id':'local_standard_generator_v2','source_group':x['provenance']['source_group'],'license':x['license'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    man={'schema_version':'2.0','generated_at':now(),'total_curves':n,'trainable_curves':n,'observed_curves':0,'synthetic_standard_curves':n,'archived_observed_curves':35,'open_curves':sum(not x['is_closed'] for x in items),'closed_curves':sum(x['is_closed'] for x in items),'degree_distribution':{'3':n},'control_point_count_distribution':{'8':n},'unit_distribution':{'mm':n},'license_distribution':{'Generated-By-Project':n},'split_group':'provenance.source_group','curves':entries};atomic(ROOT/'dataset_manifest.json',man)
    (ROOT/'dataset_report.md').write_text(f"""# Rhino 曲线数据质量报告 v2\n\n- 活跃训练曲线：{n}\n- 类型：项目内确定性生成的课堂标准曲线\n- 开放 / 闭合：{man['open_curves']} / {man['closed_curves']}\n- 单位：mm\n- 控制点：统一 8×3\n- 阶数：3\n- 分组：20 个生成批次；拆分时整组隔离\n- 旧版真实抓取基础曲线：35 条，保留在归档中，不混入本轮受限域模型。\n\n本版本不是对真实抓取量的替代声明。模型适用域仅限本生成器定义的标准开放曲线和闭合曲线族。\n""",encoding='utf-8')
    print({'active':n,'groups':20})
if __name__=='__main__':main()
