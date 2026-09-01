"""Dependency-injectable live-run orchestration used by CLI and offline E2E tests."""
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from ..backtest.replay import FullModelStrategy
from ..storage import ProvenanceStore
from .normalization import normalize_observation
from .raw_archive import ImmutableRawArchive

CANONICAL_LIVE_SERIES=("US_EQ","GOLD","COPPER","OIL","DXY","USDCNH","HK_EQ","US_GOV_10Y")

def _run_live_pipeline_unlocked(*, store, archive_root, output_root, fetcher, probe=None, run_key=None, retry=False, source_mode='SIMULATED', as_of=None, quality_checker=None):
    if source_mode not in ('SIMULATED','FIXTURE'): raise ValueError('live test mode must be SIMULATED or FIXTURE')
    today=((as_of.date() if hasattr(as_of,'date') else as_of) if as_of else datetime.now(UTC).date()); today=today.isoformat() if hasattr(today,'isoformat') else str(today); out=Path(output_root)/today; out.mkdir(parents=True,exist_ok=True)
    key=run_key or f'LIVE_DAILY_{today.replace("-","")}'
    marker=out/'run_manifest.json'
    if marker.exists() and not retry: return json.loads(marker.read_text(encoding='utf-8')) | {'reused':True}
    if retry: key=f'{key}_RETRY_{datetime.now(UTC).strftime("%H%M%S%f")}'; marker=out/f'run_manifest_{key.lower()}.json'
    now=datetime.now(UTC).replace(tzinfo=None); status='SIMULATED_SUCCESS'; rows=[]; error=None
    try:
        rows=list(fetcher(CANONICAL_LIVE_SERIES, as_of)) if len(inspect.signature(fetcher).parameters)>1 else list(fetcher(CANONICAL_LIVE_SERIES))
    except Exception as exc:  # noqa: BLE001 - injected provider failures are degraded
        status='DEGRADED'; error=str(exc)[:240]
    normalized=[]
    for item in rows:
        item=normalize_observation(item)
        item.metadata={**(item.metadata or {}), 'origin': source_mode}
        normalized.append(item.model_dump(mode='json'))
    raw=None
    if normalized:
        raw=ImmutableRawArchive(archive_root).write('simulated' if source_mode=='SIMULATED' else 'fixture','observations',normalized)
        for row in normalized: row['raw_file']=raw
        store.insert_observations(normalized,run_id=key)
    for sid in CANONICAL_LIVE_SERIES:
        store.record_provider_attempt({'attempt_id':str(uuid4()),'provider':source_mode.lower(),'series_id':sid,'started_at':now,'finished_at':datetime.now(UTC).replace(tzinfo=None),'status':'SUCCESS' if any(r['series_id']==sid for r in normalized) else 'FAILED','latency_ms':0.0,'schema_error':None,'fallback':False,'source_switch':False,'error_message':error})
        store.record_quality_event({'event_id':str(uuid4()),'detected_at':now,'series_id':sid,'severity':'INFO' if normalized else 'ERROR','event_type':'OK' if normalized else 'FETCH_ERROR','message':'simulated provider result' if normalized else (error or 'provider failed'),'provider':source_mode.lower(),'run_id':key})
    health = quality_checker(normalized) if quality_checker else not any(str(r.get('quality','')).lower() in ('stale','failed') for r in normalized)
    p=ProvenanceStore(store.conn); snap=p.create_snapshot(normalized,data_cutoff=now)
    rid=p.start_model_run('live_daily',now,'live_v0.1','simulated_config_hash','simulated_code_version',snap,now,[status])
    p.finish_model_run(rid,'success' if normalized else 'partial',[status])
    modes={sid:(source_mode if any(r['series_id']==sid for r in normalized) else 'UNAVAILABLE') for sid in CANONICAL_LIVE_SERIES}
    frame=pd.DataFrame(normalized)
    if not frame.empty:
        frame['_available']=pd.to_datetime(frame['available_at'],utc=True)
        cutoff=pd.Timestamp(as_of or now); cutoff=cutoff.tz_localize('UTC') if cutoff.tzinfo is None else cutoff.tz_convert('UTC')
        frame=frame[frame['_available']<=cutoff]
    assets=['US_EQ','GOLD','COPPER','OIL','DXY','USDCNH','HK_EQ','US_GOV_10Y']; strategic={a:1/len(assets) for a in assets}
    strategy=FullModelStrategy(assets,strategic_weights=strategic)
    decision_time=pd.Timestamp(as_of or now); decision_time=decision_time.tz_localize('UTC') if decision_time.tzinfo is None else decision_time.tz_convert('UTC')
    weights=strategy(frame, decision_time, health=health)
    decision=strategy.last_decision or {}; allocation=decision.get('allocation')
    def obj(x):
        if hasattr(x,'__dict__'): return {k:obj(v) for k,v in x.__dict__.items()}
        if isinstance(x,dict): return {k:obj(v) for k,v in x.items()}
        if isinstance(x,(list,tuple)): return [obj(v) for v in x]
        return x
    summaries={'market':obj(decision.get('market_state',{})),'macro':obj(decision.get('macro_state',{})),'style':obj(decision.get('style_state',{})),'asset_scores':obj(decision.get('asset_scores',{})),'confidence':{k:getattr(v,'confidence',None) for k,v in decision.get('asset_scores',{}).items()},'allocation':obj(allocation),'allocation_status':getattr(allocation,'status',None),'weights':weights,'attribution':obj(decision.get('attribution',{})),'model_versions':decision.get('model_versions',{})}
    payload={'run_key':key,'run_id':rid,'as_of':today,'source_mode':modes,'origin_summary':{'origin':source_mode,'counts':{source_mode:len(normalized)}},'status':status,'series_count':len({r['series_id'] for r in normalized}),'rows_written':len(normalized),'reused':False,'data_snapshot_id':snap,'model_version':'live_v0.1','config_hash':'simulated_config_hash','data_cutoff':now.isoformat(),'quality_health':health,**summaries}
    common={'run_id':rid,'as_of':today,'origin':source_mode,'model_versions':summaries['model_versions'],'data_cutoff':now.isoformat()}
    artifact_payloads={'capability':{**common,'probe':obj(probe or {}),'status':status,'source':modes},'data_health':{**common,'health':health,'quality_events':[{'series_id':sid,'source_mode':modes[sid],'status':'OK' if health else 'FAILED'} for sid in CANONICAL_LIVE_SERIES],'source_modes':modes},'market_state':{**common,'state':summaries['market']},'macro_state':{**common,'state':summaries['macro']},'style_state':{**common,'state':summaries['style']},'asset_scores':{**common,'scores':summaries['asset_scores'],'confidence':summaries['confidence']},'allocation':{**common,'allocation':summaries['allocation'],'weights':weights,'attribution':summaries['attribution'],'status':summaries['allocation_status']}}
    for name,content in artifact_payloads.items():
        (out/f'{name}.json').write_text(json.dumps(content,default=str,indent=2),encoding='utf-8')
    (out/'daily.md').write_text(f'# Live Daily Report\n\nStatus: {status}\n\nSource mode: {source_mode}\n',encoding='utf-8')
    marker.write_text(json.dumps(payload,default=str,indent=2),encoding='utf-8')
    return payload

def run_live_pipeline(*, store, archive_root, output_root, fetcher, probe=None, run_key=None, retry=False, source_mode='SIMULATED', lock_path=None, as_of=None, run_mode='LIVE', quality_checker=None):
    """Run once under an inter-process lock; marker idempotency remains separate."""
    from ..live.locks import RunLock
    key=run_key or 'LIVE_DAILY'
    with RunLock(lock_path or (Path(output_root).parent / '.run.lock'), key):
        result=_run_live_pipeline_unlocked(store=store, archive_root=archive_root, output_root=output_root, fetcher=fetcher, probe=probe, run_key=run_key, retry=retry, source_mode=source_mode, as_of=as_of, quality_checker=quality_checker)
        result.update({'run_mode':run_mode,'no_trade':run_mode=='SHADOW','parameters_frozen':run_mode=='SHADOW','strategic_weights_unchanged':True}); return result
