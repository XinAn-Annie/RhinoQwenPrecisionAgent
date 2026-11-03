import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np,rhino3dm

ROOT=Path(__file__).resolve().parent; DATA=ROOT.parent/'training'; tests=json.loads((ROOT/'test_predictions.json').read_text(encoding='utf-8')); valid=closure=0
for x in tests:
    pts=[rhino3dm.Point3d(*p) for p in x['predicted_control_points']]; c=rhino3dm.Curve.CreateControlPointCurve(pts,3); valid+=int(c is not None and c.IsValid); expected=np.linalg.norm(np.asarray(x['predicted_control_points'][0])-np.asarray(x['predicted_control_points'][-1]))<1e-8; closure+=int(c is not None and c.IsClosed==expected)
man=json.loads((DATA/'dataset_manifest.json').read_text(encoding='utf-8')); hashes_ok=sum(hashlib.sha256((DATA/e['path']).read_bytes()).hexdigest()==e['sha256'] for e in man['curves'])
files=['model.joblib','scaler.joblib','feature_schema.json','train_metrics.json','test_predictions.json']; audit={'generated_at':datetime.now(timezone.utc).astimezone().isoformat(),'dataset_records':len(man['curves']),'dataset_hashes_valid':hashes_ok,'test_predictions':len(tests),'openNURBS_valid_count':valid,'openNURBS_valid_rate':valid/max(len(tests),1),'closure_consistency_rate':closure/max(len(tests),1),'artifact_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'release_gate_passed':hashes_ok==len(man['curves']) and valid==len(tests) and closure==len(tests) and json.loads((ROOT/'train_metrics.json').read_text(encoding='utf-8'))['meets_qwen_minimum_standard']}
(ROOT/'release_validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(audit)
