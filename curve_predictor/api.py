from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel, Field
from predictor import predict_curve

ROOT=Path(__file__).resolve().parent; LOG=ROOT/"logs"/"predictions.jsonl"
class CurveRequest(BaseModel):
    width: float=Field(gt=0); height: float=Field(ge=0); depth: float=Field(default=0,ge=0); length: float|None=None; degree:int=Field(default=3,ge=1,le=7); is_closed:bool=False
    start_x:float=0; start_y:float=0; start_z:float=0; end_x:float|None=None; end_y:float|None=None; end_z:float|None=None
    curvature_mean:float=0; curvature_max:float=0; curvature_std:float=0; control_point_count:int=8
app=FastAPI(title="Rhino Curve Predictor",version="1.0")
@app.get("/health")
def health(): return {"ok":True,"write_to_rhino":False}
@app.post("/predict_curve")
def predict(req:CurveRequest):
    raw={k:v for k,v in req.model_dump().items() if v is not None}; result=predict_curve(raw)
    LOG.parent.mkdir(exist_ok=True); record={"timestamp":datetime.now(timezone.utc).astimezone().isoformat(),"input":raw,"output":result};
    with LOG.open("a",encoding="utf-8") as f:f.write(json.dumps(record,ensure_ascii=False)+"\n")
    return result
if __name__=="__main__":
    import uvicorn; uvicorn.run("api:app",host="127.0.0.1",port=8777,reload=False)
