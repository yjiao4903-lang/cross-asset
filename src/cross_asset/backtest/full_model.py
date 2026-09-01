"""Deterministic offline full-model strategy; consumes only replay PIT rows."""
from cross_asset.engines.allocation import allocate
from cross_asset.engines.asset_score import score_asset

ASSET_SERIES={"CN_EQ":"CN_EQ_LARGE","HK_EQ":"HK_EQ","US_EQ":"US_EQ","CN_BOND":"CN_BOND_10Y","GOLD":"GOLD","COMMODITY":"COPPER","CASH":None}
STRATEGIC={"CN_EQ":.25,"HK_EQ":.10,"US_EQ":.25,"CN_BOND":.20,"GOLD":.10,"COMMODITY":.05,"CASH":.05}
class FullModelStrategy:
    model_version="full_model_v0.1"
    def __init__(self, strategic_weights=None): self.strategic_weights=strategic_weights or STRATEGIC.copy(); self.last_scores={}; self.last_decision=None
    def __call__(self, info, decision):
        scores={}; cutoff=info["_available"].max() if len(info) else decision
        for asset,sid in ASSET_SERIES.items():
            if sid is None: scores[asset]=score_asset(asset,{"trend":0.0,"risk":0.0},confidence=.5,data_cutoff=cutoff); continue
            rows=info[info["series_id"]==sid].sort_values("observation_date")
            if len(rows)<2: scores[asset]=score_asset(asset,{},confidence=0,data_cutoff=cutoff); continue
            p=rows["value"].astype(float); trend=float(p.iloc[-1]/p.iloc[max(0,len(p)-22)]-1); scores[asset]=score_asset(asset,{"trend":max(-2,min(2,trend*10))},confidence=min(1,len(p)/22),data_cutoff=cutoff)
        health=not any(s.score is None for s in scores.values())
        result=allocate(scores,self.strategic_weights,health=health,as_of=decision,data_cutoff=cutoff,model_version="allocation_v0.1")
        self.last_scores=scores; self.last_decision={"decision":decision,"scores":scores,"allocation":result,"data_cutoff":cutoff,"model_version":self.model_version}
        return result.weights
    def next_return(self, info, weights, decision):
        # No forward rows are consumed: fixture baseline records a neutral return.
        return 0.0
