"""Atomic project backup and isolated restore verification."""
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb


def _sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def create_backup(project_root='.', destination='artifacts/backups'):
    root=Path(project_root); dest=Path(destination); dest.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'); temp=Path(tempfile.mkdtemp(prefix='.backup-',dir=dest))
    try:
        targets=[root/'data/db/cross_asset.duckdb',root/'config',root/'data/manual_archive']
        for src in targets:
            if not src.exists(): continue
            rel=src.relative_to(root); out=temp/rel
            if src.is_dir(): shutil.copytree(src,out)
            else: out.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,out)
        raw_manifest=[]
        for src in (root/'data/raw').rglob('*') if (root/'data/raw').exists() else []:
            if src.is_file(): raw_manifest.append({'path':str(src.relative_to(root)).replace('\\','/'),'sha256':_sha(src),'size':src.stat().st_size})
        manifest={'version':'0.1','created_at':datetime.now(UTC).isoformat(),'source_root':str(root.resolve()),'files':[], 'raw_manifest':raw_manifest}
        for p in temp.rglob('*'):
            if p.is_file(): manifest['files'].append({'path':str(p.relative_to(temp)).replace('\\','/'),'sha256':_sha(p),'size':p.stat().st_size})
        (temp/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        final=dest/f'backup_{stamp}'; temp.rename(final); return str(final)
    except Exception:
        shutil.rmtree(temp,ignore_errors=True); raise

def verify_backup(backup_path):
    backup=Path(backup_path); manifest=json.loads((backup/'manifest.json').read_text(encoding='utf-8')); errors=[]
    for item in manifest['files']:
        p=backup/item['path']
        if not p.exists() or _sha(p)!=item['sha256']: errors.append(item['path'])
    db=backup/'data/db/cross_asset.duckdb'
    if db.exists():
        try:
            c=duckdb.connect(str(db),read_only=True); c.execute('SELECT 1'); c.close()
        except (OSError, duckdb.Error) as exc: errors.append(f'database:{type(exc).__name__}')
    return {'valid':not errors,'errors':errors,'manifest':manifest}
