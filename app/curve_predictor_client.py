from __future__ import annotations
import os
from typing import Any
import httpx

class CurvePredictorClient:
    def __init__(self, base_url: str | None = None):
        self.base_url=(base_url or os.getenv("CURVE_PREDICTOR_URL","http://127.0.0.1:8777")).rstrip("/")
    async def predict(self, params:dict[str,Any])->dict[str,Any]:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            r=await client.post(self.base_url+"/predict_curve",json=params); r.raise_for_status(); result=r.json()
        result["integration_gate"]="blocked_before_rhino" if result.get("status")!="preview_only" else "awaiting_user_confirmation_and_rhinocommon_validation"
        result["rhino_write_performed"]=False
        return result
