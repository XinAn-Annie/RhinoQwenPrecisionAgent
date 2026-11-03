from __future__ import annotations
import base64, hashlib, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_IMAGE_BYTES=20*1024*1024
ALLOWED={"image/png":".png","image/jpeg":".jpg","image/webp":".webp","image/bmp":".bmp","image/gif":".gif"}

def _valid_signature(data:bytes,mime:str)->bool:
    return {
        "image/png":data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg":data.startswith(b"\xff\xd8\xff"),
        "image/webp":len(data)>12 and data[:4]==b"RIFF" and data[8:12]==b"WEBP",
        "image/bmp":data.startswith(b"BM"),
        "image/gif":data.startswith((b"GIF87a",b"GIF89a")),
    }.get(mime,False)

def store_reference(root:Path,filename:str,mime_type:str,data_base64:str)->dict[str,Any]:
    if mime_type not in ALLOWED: raise ValueError("unsupported image type")
    try:data=base64.b64decode(data_base64,validate=True)
    except Exception as exc:raise ValueError("invalid base64 image") from exc
    if not data or len(data)>MAX_IMAGE_BYTES:raise ValueError("image must be 1 byte to 20 MB")
    if not _valid_signature(data,mime_type):raise ValueError("image signature does not match MIME type")
    digest=hashlib.sha256(data).hexdigest();folder=root/"evaluation"/"references";folder.mkdir(parents=True,exist_ok=True);path=folder/f"{digest}{ALLOWED[mime_type]}"
    if not path.exists():path.write_bytes(data)
    meta={"asset_id":digest,"original_filename":Path(filename).name[:180],"mime_type":mime_type,"size_bytes":len(data),"sha256":digest,"stored_path":str(path),"stored_at":datetime.now(timezone.utc).astimezone().isoformat()}
    meta_path=folder/f"{digest}.json";tmp=meta_path.with_suffix(".json.tmp");tmp.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8");os.replace(tmp,meta_path)
    return {**meta,"path":path}
