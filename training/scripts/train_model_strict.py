from __future__ import annotations
import hashlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
import joblib,numpy as np
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error,mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures,StandardScaler
from sklearn.linear_model import Ridge
from scipy.interpolate import BSpline

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT.parent/'curve_predictor'; OUT.mkdir(exist_ok=True)
FEATURES=['width','height','depth','length','degree','is_closed','start_x','start_y','start_z','end_x','end_y','end_z','curvature_mean','curvature_max','curvature_std','control_point_count']
def atomic(p,d):
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(t,p)
def feat(x):
    b=x['bbox'];s=x['start_point'];e=x['end_point'];k=x['curvature_summary'];return [b['width'],b['height'],b['depth'],x['length'],x['degree'],int(x['is_closed']),*s,*e,k['mean'],k['max'],k['std'],len(x['control_points'])]
def sample(p,n=160):
    d=3;full=np.r_[np.zeros(d+1),np.linspace(0,1,len(p)-d+1)[1:-1],np.ones(d+1)];return BSpline(full,p,d)(np.linspace(0,1,n))
def calibrate(flat,bbox,is_closed=False):
    p=np.asarray(flat).reshape(8,3).copy()
    if is_closed: p[0]=p[-1]=(p[0]+p[-1])/2
    q=sample(p);lo=q.min(0);hi=q.max(0);center=(lo+hi)/2;span=hi-lo;b=np.asarray(bbox)
    for j in range(3):
        if b[j]<=1e-12:p[:,j]=0
        elif span[j]>1e-12:p[:,j]=(p[:,j]-center[j])*(b[j]/span[j])+center[j]
    return p.reshape(-1)
def metrics(y,p,x):
    raw_rmse=float(mean_squared_error(y,p)**.5);raw_mae=float(mean_absolute_error(y,p));pc=np.asarray([calibrate(v,row[:3],bool(row[5])) for v,row in zip(p,x)]);rmse=float(mean_squared_error(y,pc)**.5);mae=float(mean_absolute_error(y,pc));bbox=[];length=[];valid=[];closed=[]
    for a,b,row in zip(pc,y,x):
        qa=sample(a.reshape(8,3));qb=sample(b.reshape(8,3));bbox.append(float(np.max(np.abs(np.ptp(qa,axis=0)-np.ptp(qb,axis=0)))));length.append(float(abs(np.linalg.norm(np.diff(qa,axis=0),axis=1).sum()-np.linalg.norm(np.diff(qb,axis=0),axis=1).sum())));valid.append(np.isfinite(a).all());closed.append((np.linalg.norm(a.reshape(8,3)[0]-a.reshape(8,3)[-1])<1e-7)==bool(row[5]))
    return {'raw_control_point_mae':raw_mae,'raw_control_point_rmse':raw_rmse,'control_point_mae':mae,'control_point_rmse':rmse,'bbox_max_error_mean':float(np.mean(bbox)),'bbox_max_error_p95':float(np.quantile(bbox,.95)),'bbox_le_0_1mm_rate':float(np.mean(np.array(bbox)<=.1)),'length_abs_error_mean':float(np.mean(length)),'array_validity_rate':float(np.mean(valid)),'closure_consistency_rate':float(np.mean(closed))},pc
def main():
    start=time.time();man=json.loads((ROOT/'dataset_manifest.json').read_text(encoding='utf-8'));data=[json.loads((ROOT/e['path']).read_text(encoding='utf-8')) for e in man['curves']];X=np.asarray([feat(x) for x in data],float);Y=np.asarray([np.asarray(x['control_points']).reshape(-1) for x in data]);G=np.asarray([x['provenance']['source_group'] for x in data]);ids=np.asarray([x['curve_id'] for x in data])
    if len(data)!=2000 or len(set(ids))!=2000 or not np.isfinite(X).all() or not np.isfinite(Y).all():raise RuntimeError('dataset validation failed')
    groups=np.array(sorted(set(G)));rng=np.random.default_rng(20261103);rng.shuffle(groups);test_groups=set(groups[:4]);te=np.where(np.isin(G,list(test_groups)))[0];dev=np.where(~np.isin(G,list(test_groups)))[0]
    scaler=StandardScaler().fit(X[dev]);A=scaler.transform(X)
    candidates={
      'ExtraTreesRegressor':ExtraTreesRegressor(n_estimators=350,max_depth=18,min_samples_leaf=4,max_features=.9,n_jobs=-1,random_state=42),
      'MLPRegressor':TransformedTargetRegressor(regressor=MLPRegressor(hidden_layer_sizes=(48,24),early_stopping=True,validation_fraction=.15,max_iter=600,alpha=.003,n_iter_no_change=35,random_state=42),transformer=StandardScaler()),
      'PolynomialRidge':Pipeline([('poly',PolynomialFeatures(2,include_bias=False)),('ridge',Ridge(alpha=.01))])
    }
    cv=GroupKFold(n_splits=4);summary={}
    for name,base in candidates.items():
        folds=[]
        for fi,(tr0,va0) in enumerate(cv.split(A[dev],Y[dev],G[dev])):
            tr,va=dev[tr0],dev[va0];m=clone(base);m.fit(A[tr],Y[tr]);ptr=m.predict(A[tr]);pva=m.predict(A[va]);tm,_=metrics(Y[tr],ptr,X[tr]);vm,_=metrics(Y[va],pva,X[va]);folds.append({'fold':fi+1,'train_groups':len(set(G[tr])),'validation_groups':len(set(G[va])),'train_rmse':tm['raw_control_point_rmse'],'validation_rmse':vm['raw_control_point_rmse'],'validation_calibrated_rmse':vm['control_point_rmse']})
        trm=np.mean([f['train_rmse'] for f in folds]);vr=np.mean([f['validation_rmse'] for f in folds]);vrc=np.mean([f['validation_calibrated_rmse'] for f in folds]);summary[name]={'folds':folds,'train_rmse_mean':float(trm),'validation_rmse_mean':float(vr),'validation_rmse_std':float(np.std([f['validation_rmse'] for f in folds])),'validation_calibrated_rmse_mean':float(vrc),'generalization_gap':float(vr-trm)}
    eligible=[n for n,v in summary.items() if v['generalization_gap']<=.05];best=min(eligible or summary,key=lambda n:summary[n]['validation_rmse_mean']);model=clone(candidates[best]);model.fit(A[dev],Y[dev]);train_pred=model.predict(A[dev]);test_raw=model.predict(A[te]);train_m,_=metrics(Y[dev],train_pred,X[dev]);test_m,test_pred=metrics(Y[te],test_raw,X[te]);edge=(X[te,0]>=np.quantile(X[dev,0],.9))|(X[te,1]>=np.quantile(X[dev,1],.9));edge_m,_=metrics(Y[te][edge],test_raw[edge],X[te][edge])
    ready=bool(test_m['raw_control_point_rmse']<=.1 and test_m['control_point_rmse']<=.1 and test_m['bbox_le_0_1mm_rate']>=.95 and test_m['closure_consistency_rate']==1 and summary[best]['generalization_gap']<=.05 and edge_m['control_point_rmse']<=.1)
    version=hashlib.sha256((best+man['generated_at']+'strict-v3').encode()).hexdigest()[:12];report={'schema_version':'3.0','model_version':version,'training_protocol':'untouched 4-group test + 4-fold GroupKFold on 16 development groups; model selected only by CV raw RMSE','selected_model':best,'candidates':summary,'split':{'development':len(dev),'test':len(te),'development_groups':len(set(G[dev])),'test_groups':sorted(test_groups)},'development_fit_metrics':train_m,'test':test_m,'edge_range_test':edge_m,'training_seconds_total':time.time()-start,'meets_qwen_minimum_standard':ready};joblib.dump(model,OUT/'model.joblib');joblib.dump(scaler,OUT/'scaler.joblib');atomic(OUT/'train_metrics.json',report)
    schema={'model_version':version,'features':FEATURES,'output_shape':[8,3],'unit':'mm','domain':'classroom_standard_open_and_closed_curve_families_v2','defaults':{'depth':0,'start_x':0,'start_y':0,'start_z':0,'end_x':0,'end_y':0,'end_z':0,'curvature_mean':0,'curvature_max':0,'curvature_std':0,'control_point_count':8},'input_ranges':{FEATURES[i]:[float(X[dev,i].min()),float(X[dev,i].max())] for i in range(len(FEATURES))},'postprocessing':{'type':'sampled_curve_bbox_calibration','samples':160},'rejection':{'bbox_max_error_mm':.1,'confidence_min':.55,'require_rhinocommon_validation':True}};atomic(OUT/'feature_schema.json',schema)
    preds=[]
    for idx,praw,pcal in zip(te,test_raw,test_pred):preds.append({'curve_id':ids[idx],'source_group':G[idx],'raw_predicted_control_points':praw.reshape(8,3).tolist(),'predicted_control_points':pcal.reshape(8,3).tolist(),'true_control_points':Y[idx].reshape(8,3).tolist()})
    atomic(OUT/'test_predictions.json',preds)
    conclusion='达到' if ready else '未达到';(OUT/'training_report.md').write_text(f"""# 严格分组训练报告\n\n- 模型版本：{version}\n- 选择模型：{best}\n- 协议：16组开发数据进行4折 GroupKFold；4组最终测试全程隔离；测试集不参与选模。\n- 训练/测试：{len(dev)} / {len(te)}\n- 交叉验证原始 RMSE：{summary[best]['validation_rmse_mean']:.6f} ± {summary[best]['validation_rmse_std']:.6f} mm\n- 泛化差距：{summary[best]['generalization_gap']:.6f} mm\n- 最终测试原始 RMSE：{test_m['raw_control_point_rmse']:.6f} mm\n- 最终测试校准后 RMSE：{test_m['control_point_rmse']:.6f} mm\n- 边界尺寸测试 RMSE：{edge_m['control_point_rmse']:.6f} mm\n- BBox ≤0.1 mm：{test_m['bbox_le_0_1mm_rate']:.2%}\n- 闭合一致率：{test_m['closure_consistency_rate']:.2%}\n\n## 结论\n\n**{conclusion}受限课堂曲线域的 Qwen 接入标准。** 该结论不外推到任意 Rhino NURBS。\n""",encoding='utf-8')
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    names=list(summary);fig,ax=plt.subplots(1,3,figsize=(13,4));xx=np.arange(len(names));ax[0].bar(xx-.18,[summary[n]['train_rmse_mean'] for n in names],.36,label='train');ax[0].bar(xx+.18,[summary[n]['validation_rmse_mean'] for n in names],.36,label='group CV');ax[0].set_xticks(xx,names,rotation=20);ax[0].set_ylabel('Raw CP RMSE (mm)');ax[0].legend();res=(test_pred-Y[te]).ravel();ax[1].hist(res,bins=40,color='#2878b5');ax[1].set_title('Held-out residuals');ax[1].set_xlabel('mm');true=Y[te].ravel();pred=test_pred.ravel();ax[2].scatter(true,pred,s=3,alpha=.25);lo=min(true.min(),pred.min());hi=max(true.max(),pred.max());ax[2].plot([lo,hi],[lo,hi],'r--');ax[2].set_xlabel('True');ax[2].set_ylabel('Predicted');ax[2].set_title('Untouched test');fig.tight_layout();fig.savefig(OUT/'training_diagnostics.png',dpi=170);plt.close(fig)
    print(json.dumps({'selected_model':best,'cv_rmse':summary[best]['validation_rmse_mean'],'gap':summary[best]['generalization_gap'],'test_raw_rmse':test_m['raw_control_point_rmse'],'test_calibrated_rmse':test_m['control_point_rmse'],'edge_rmse':edge_m['control_point_rmse'],'ready':ready},ensure_ascii=False))
if __name__=='__main__':main()
