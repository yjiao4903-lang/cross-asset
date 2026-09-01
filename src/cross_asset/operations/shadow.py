"""Shadow runner using the live service path with trading disabled."""
import json
from datetime import UTC, datetime
from pathlib import Path

from ..ingestion.live_run import run_live_pipeline


class ShadowRunner:
    def __init__(self, store, archive_root, output_root, fetcher, lock_path=None):
        self.store, self.archive_root, self.output_root, self.fetcher, self.lock_path = store, archive_root, output_root, fetcher, lock_path

    def run(self, as_of, *, run_key=None, retry=False):
        def health(rows): return not any(str(r.get('quality', r.get('metadata',{}).get('quality',''))).lower() in ('stale','failed') for r in rows)
        return run_live_pipeline(store=self.store, archive_root=self.archive_root, output_root=self.output_root, fetcher=self.fetcher, run_key=run_key or f'SHADOW_{as_of}', retry=retry, source_mode='SIMULATED', lock_path=self.lock_path, as_of=as_of, run_mode='SHADOW', quality_checker=health)

    def weekly_report(self, dates):
        rows=[]
        affected_dates=[]; affected_series=set()
        for d in dates:
            p=Path(self.output_root)/str(d)/'run_manifest.json'
            if p.exists():
                manifest=json.loads(p.read_text(encoding='utf-8')); base=p.parent
                scores=json.loads((base/'asset_scores.json').read_text(encoding='utf-8')) if (base/'asset_scores.json').exists() else {}
                alloc=json.loads((base/'allocation.json').read_text(encoding='utf-8')) if (base/'allocation.json').exists() else {}
                health=json.loads((base/'data_health.json').read_text(encoding='utf-8')) if (base/'data_health.json').exists() else {}
                events=health.get('quality_events', [])
                manifest.update({'score':scores.get('scores',{}).get('US_EQ'),'confidence':scores.get('confidence',{}).get('US_EQ') if isinstance(scores.get('confidence'),dict) else scores.get('confidence'),'allocation':alloc.get('weights')})
                manifest['provider_failure_count']=int(manifest.get('status')=='DEGRADED')
                manifest['fallback_count']=sum(bool(e.get('fallback')) for e in events if isinstance(e,dict))
                manifest['stale_count']=sum(str(e.get('status','')).upper() in {'STALE','FAILED'} or str(e.get('quality','')).lower()=='stale' for e in events if isinstance(e,dict))
                if manifest['provider_failure_count'] or manifest['fallback_count'] or manifest['stale_count'] or manifest.get('allocation_status')=='FROZEN':
                    affected_dates.append(str(d))
                    affected_series.update(str(e.get('series_id')) for e in events if isinstance(e,dict) and str(e.get('status','')).upper() in {'STALE','FAILED'})
                rows.append(manifest)
        report={'run_mode':'SHADOW','runs':rows,'run_count':len(rows),'provider_failure_count':sum(r.get('provider_failure_count',0) for r in rows),'fallback_count':sum(r.get('fallback_count',0) for r in rows),'stale_count':sum(r.get('stale_count',0) for r in rows),'degraded_count':sum(r.get('status')=='DEGRADED' for r in rows),'frozen_count':sum(r.get('allocation_status')=='FROZEN' for r in rows),'affected_dates':sorted(set(affected_dates)),'affected_series':sorted(affected_series),'date_start':str(min(dates)) if dates else None,'date_end':str(max(dates)) if dates else None,'score_changes':[r.get('score') for r in rows],'allocation_changes':[r.get('allocation') for r in rows],'confidence_changes':[r.get('confidence') for r in rows],'revision_count':sum(bool(r.get('revision')) for r in rows)}
        return report

    def write_weekly_report(self, dates):
        report=self.weekly_report(dates)
        path=Path(self.output_root)/'weekly_shadow_review.md'; path.parent.mkdir(parents=True,exist_ok=True)
        lines=['# Weekly Shadow Review', '', f"Date range: {report['date_start']} to {report['date_end']}", f"Runs: {report['run_count']}", '', '## Reliability', f"provider_failure_count: {report['provider_failure_count']}", f"fallback_count: {report['fallback_count']}", f"stale_count: {report['stale_count']}", f"degraded_count: {report['degraded_count']}", f"frozen_count: {report['frozen_count']}", f"revision_count: {report['revision_count']}", f"affected_dates: {', '.join(report['affected_dates']) or 'none'}", f"affected_series: {', '.join(report['affected_series']) or 'none'}", '', f"score_changes: {report['score_changes']}", f"allocation_changes: {report['allocation_changes']}", f"confidence_changes: {report['confidence_changes']}"]
        path.write_text('\n'.join(lines)+'\n',encoding='utf-8'); return path,report

def weekly_shadow_report(output_root='artifacts/shadow', dates=None):
    root=Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    selected=dates or sorted(p.name for p in root.iterdir() if p.is_dir() and (p/'run_manifest.json').exists())
    runner=ShadowRunner(None,None,root,lambda _: [])
    return runner.write_weekly_report(selected)

def load_schedule(path='config/schedule.yml'):
    import re

    import yaml
    data=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if not data.get('timezone') or not isinstance(data.get('jobs'), list): raise ValueError('schedule requires timezone and jobs')
    for job in data['jobs']:
        if not job.get('name') or not job.get('command') or not isinstance(job.get('enabled'), bool): raise ValueError('invalid schedule job')
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', str(job.get('local_time', ''))): raise ValueError('invalid local_time')
        if job.get('frequency') == 'weekly' and not job.get('day'): raise ValueError('weekly job requires day')
    return data


def shadow_run(**kwargs):
    runner=ShadowRunner(kwargs.pop('store'),kwargs.pop('archive_root','data/raw'),kwargs.pop('output_root','artifacts/shadow'),kwargs.pop('fetcher'),kwargs.pop('lock_path',None))
    return runner.run(kwargs.pop('as_of',datetime.now(UTC).date()),**kwargs)
