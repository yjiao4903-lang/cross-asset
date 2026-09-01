"""Deterministic model and data provenance helpers."""
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def _sha(data): return hashlib.sha256(data).hexdigest()


def _json_default(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)

def source_tree_hash(root='.'):
    root=Path(root); h=hashlib.sha256()
    # Fingerprint executable project sources only.  Scanning the entire worktree
    # makes identity depend on reports, editor files, and concurrent test output.
    candidates=[]
    for directory in ('src', 'scripts'):
        base=root/directory
        if base.exists(): candidates.extend(p for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for name in ('pyproject.toml', 'uv.lock'):
        path=root/name
        if path.is_file(): candidates.append(path)
    files=sorted(candidates,key=lambda p:p.relative_to(root).as_posix())
    for p in files: h.update(p.relative_to(root).as_posix().encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def code_version(root='.'):
    root=str(root)
    try:
        commit=subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        dirty=bool(subprocess.check_output(['git','-C',root,'status','--porcelain'],text=True,stderr=subprocess.DEVNULL).strip())
        return f'{commit}+source_tree:{source_tree_hash(root)}' if dirty else commit
    except (OSError, subprocess.CalledProcessError): return f'no_commit+source_tree:{source_tree_hash(root)}'

def config_hash(paths):
    paths=[paths] if isinstance(paths,(str,Path)) else list(paths); h=hashlib.sha256()
    for p in sorted((Path(x) for x in paths),key=lambda x:str(x)):
        h.update(str(p).replace('\\','/').encode()); h.update(b'\0'); h.update(p.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def data_snapshot_id(rows):
    # Only information-set identity participates; ordering and dict insertion order do not.
    keys=(
        'series_id','source','source_series_id','observation_date','value',
        'available_at','latest_available_at','vintage_date','raw_hash'
    )
    out=[]
    for row in rows:
        if isinstance(row, dict):
            get = row.get
        else:
            get = lambda k, item=row: getattr(item, k, None)
        out.append({k:(str(get(k)) if get(k) is not None else None) for k in keys})
    out.sort(key=lambda x:tuple(x[k] or '' for k in keys)); manifest=json.dumps(out,sort_keys=True,separators=(',',':')).encode()
    return _sha(manifest)

class ProvenanceStore:
    def __init__(self,connection): self.connection=connection

    def close(self):
        """Close the owned connection when used as a context manager."""
        close = getattr(self.connection, "close", None)
        if close:
            close()

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.close(); return False

    def create_snapshot(self,rows,data_cutoff=None,config_hash_value=None):
        rows=list(rows); sid=data_snapshot_id(rows); now=datetime.now(UTC).replace(tzinfo=None)
        if config_hash_value is not None and (not isinstance(config_hash_value,str) or not config_hash_value.strip()):
            raise ValueError('config_hash must be a non-empty string')
        manifest=json.dumps(rows,default=_json_default,sort_keys=True,separators=(",", ":"))
        available=[r.get("available_at", r.get("latest_available_at")) if isinstance(r,dict) else getattr(r,"available_at",None) for r in rows]
        max_available=max((x for x in available if x is not None), default=None)
        self.connection.execute('''INSERT INTO data_snapshots
            (snapshot_id,created_at,series_count,observation_count,max_available_at,data_cutoff,manifest_hash,manifest_json,config_hash)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING''',
            [sid,now,len({(r.get("series_id") if isinstance(r,dict) else getattr(r,"series_id",None)) for r in rows}),len(rows),max_available,data_cutoff,sid,manifest,config_hash_value])
        return sid
    def start_model_run(self,run_type,decision_time,model_version,config_hash_value,code_version_value,data_snapshot_id_value,data_cutoff=None,warnings=None,run_id=None):
        if not isinstance(config_hash_value,str) or not config_hash_value.strip(): raise ValueError('config_hash must be a non-empty string')
        rid=str(run_id or uuid4()); now=datetime.now(UTC).replace(tzinfo=None)
        self.connection.execute('''INSERT INTO model_runs
            (run_id,run_type,decision_time,model_version,config_hash,code_version,data_snapshot_id,data_cutoff,status,warnings,started_at,finished_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',[rid,run_type,decision_time,model_version,config_hash_value,code_version_value,data_snapshot_id_value,data_cutoff,'running',json.dumps(warnings or []),now,None]); return rid
    def finish_model_run(self,run_id,status='success',warnings=None):
        if status not in ('success','failed','partial'): raise ValueError('invalid model run status')
        self.connection.execute('UPDATE model_runs SET status=?,warnings=?,finished_at=? WHERE run_id=?',[status,json.dumps(warnings or []),datetime.now(UTC).replace(tzinfo=None),run_id])
    def fail_model_run(self,run_id,warnings=None): self.finish_model_run(run_id,'failed',warnings)
