from __future__ import annotations
import argparse, hashlib, json, os, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "sources.json"
STATE = ROOT / "state" / "downloads.json"
UA = "RhinoCurveDataset-classroom/1.0"

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()
def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    start = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": UA}
    if start: headers["Range"] = f"bytes={start}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as r:
        if start and getattr(r, "status", 200) != 206:
            part.unlink(missing_ok=True); start = 0
            return download(url, dest)
        with part.open("ab" if start else "wb") as f:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk: break
                f.write(chunk)
    os.replace(part, dest)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append")
    args = ap.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"schema_version":"1.0","files":{}}
    selected = [s for s in catalog["sources"] if s.get("crawl_enabled")]
    if args.source: selected = [s for s in selected if s["source_id"] in set(args.source)]
    for src in selected:
        if src.get("license_status") not in {"verified", "verified_via_zenodo_api", "verified_with_upstream_notice"}: continue
        acq = src["acquisition"]
        if acq["type"] != "github_files": continue
        owner_repo, rev = acq["repository"], acq["revision"]
        for rel in acq["files"]:
            url = f"https://raw.githubusercontent.com/{owner_repo}/{rev}/{rel}"
            dest = ROOT / "raw" / src["source_id"] / rel
            key = f"{src['source_id']}::{rel}"
            if dest.exists() and state["files"].get(key,{}).get("sha256") == sha256(dest): continue
            download(url, dest)
            record = {"source_id":src["source_id"],"source_url":url,"license":src["license"],"license_url":src.get("license_url"),"retrieved_at":now(),"relative_path":str(dest.relative_to(ROOT)),"size_bytes":dest.stat().st_size,"sha256":sha256(dest)}
            state["files"][key] = record
            save_json(dest.with_suffix(dest.suffix + ".provenance.json"), record)
            save_json(STATE, state)
            print(f"downloaded {rel} {record['size_bytes']} bytes")
    state["updated_at"] = now(); save_json(STATE, state)
if __name__ == "__main__": main()
