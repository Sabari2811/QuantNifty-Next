from __future__ import annotations
from typing import Any

def _num(value: Any) -> float:
    try: return float(value or 0)
    except (TypeError, ValueError): return 0.0

def _sign(value: float) -> int: return 1 if value > 0 else -1 if value < 0 else 0

def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0): return None
    return (current - previous) / abs(previous) * 100.0

def classify_market_state(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous=previous or {}; spot=_num(data.get("spot")); flip=data.get("gamma_flip"); gex=_num(data.get("gex")); expected=(data.get("expected_move") or {}).get("move"); bias=str(data.get("bias") or "NEUTRAL"); confidence=_num(data.get("confidence")); liquidity=_num(data.get("liquidity_score")); pcr=data.get("pcr")
    volume=sum(_num(r.get("volume")) for r in data.get("option_chain",[])); prev_volume=sum(_num(r.get("volume")) for r in previous.get("option_chain",[])); gex_change=_pct_change(gex,_num(previous.get("gex"))) if previous else None; em_change=_pct_change(expected,(previous.get("expected_move") or {}).get("move")) if previous else None
    if liquidity<35: state="LIQUIDITY_RISK"
    elif flip is not None and abs(spot-_num(flip))<=max(25.0,_num(expected)*0.10): state="GAMMA_TRANSITION"
    elif gex<0 and (gex_change is None or gex_change<0): state="NEGATIVE_GAMMA_EXPANSION"
    elif gex>0 and bias=="NEUTRAL": state="POSITIVE_GAMMA_MEAN_REVERSION"
    elif bias=="BULLISH": state="TREND_UP"
    elif bias=="BEARISH": state="TREND_DOWN"
    else: state="COMPRESSION"
    consumed=None
    if expected and expected>0 and flip is not None: consumed=min(200.0,abs(spot-_num(flip))/expected*100.0)
    return {"state":state,"label":state.replace("_"," ").title(),"spot_vs_gamma_flip":None if flip is None else round(spot-_num(flip),2),"gamma_change_pct":None if gex_change is None else round(gex_change,2),"expected_move_change_pct":None if em_change is None else round(em_change,2),"volume":round(volume,2),"volume_change_pct":_pct_change(volume,prev_volume) if prev_volume else None,"expected_move_consumed_pct":None if consumed is None else round(consumed,1),"confidence":round(confidence,1),"liquidity":round(liquidity,1),"bias":bias,"pcr":pcr,"transition":previous.get("market_state",{}).get("state") not in (None,state)}

def detect_events(data: dict[str, Any], previous: dict[str, Any] | None, state: dict[str, Any]) -> list[dict[str, Any]]:
    previous=previous or {}; events=[]; spot=_num(data.get("spot")); old_spot=_num(previous.get("spot")); flip=data.get("gamma_flip"); old_flip=previous.get("gamma_flip"); gex=_num(data.get("gex")); old_gex=_num(previous.get("gex")); em=_num((data.get("expected_move") or {}).get("move")); old_em=_num((previous.get("expected_move") or {}).get("move"))
    def add(kind,severity,message,value=None): events.append({"type":kind,"severity":severity,"message":message,"value":value})
    if flip is not None and old_flip is not None and _sign(spot-_num(flip))!=_sign(old_spot-_num(old_flip)): add("GAMMA_FLIP_CROSS","HIGH","Spot crossed the gamma flip",flip)
    if old_gex and gex and _sign(gex)!=_sign(old_gex): add("GEX_REGIME_CHANGE","HIGH","Aggregate gamma exposure changed sign",gex)
    if old_gex and abs(gex)>abs(old_gex)*1.10: add("GAMMA_ACCELERATION","HIGH","Gamma exposure magnitude accelerated",round(gex/old_gex-1,3))
    if old_em and em>old_em*1.05: add("EXPECTED_MOVE_EXPANSION","MEDIUM","Expected move expanded",round(em-old_em,2))
    if state.get("expected_move_consumed_pct") is not None and state["expected_move_consumed_pct"]>=80: add("EXPECTED_MOVE_CONSUMED","MEDIUM","Most of the expected move has been consumed",state["expected_move_consumed_pct"])
    if state.get("liquidity",100)<50: add("LIQUIDITY_WARNING","HIGH","Liquidity score is below the execution safety threshold",state["liquidity"])
    if state.get("transition"): add("MARKET_STATE_CHANGE","HIGH",f"Market state changed to {state['label']}",state["state"])
    return events

def move_attribution(data: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    previous=previous or {}; spot_move=_num(data.get("spot"))-_num(previous.get("spot")); call_doi=_num(data.get("call_oi_change")); put_doi=_num(data.get("put_oi_change")); gex_now=_num(data.get("gex")); gex_old=_num(previous.get("gex")); iv_now=_num(data.get("atm_iv")); iv_old=_num(previous.get("atm_iv")); volume=sum(_num(r.get("volume")) for r in data.get("option_chain",[])); prev_volume=sum(_num(r.get("volume")) for r in previous.get("option_chain",[]))
    raw={"OI positioning":abs(put_doi-call_doi),"Dealer gamma":abs(gex_now-gex_old),"IV expansion":abs(iv_now-iv_old)*100.0,"Volume impulse":abs(volume-prev_volume)/max(1.0,prev_volume)*100.0,"Price momentum":abs(spot_move)}; total=sum(raw.values()); shares={k:round(v/total*100.0,1) for k,v in raw.items()} if total else {k:0.0 for k in raw}; primary=max(shares,key=shares.get) if shares else "Unavailable"; direction="UP" if spot_move>0 else "DOWN" if spot_move<0 else "FLAT"; quality="HIGH" if total and max(shares.values())>=40 else "MEDIUM" if total else "LOW"
    return {"direction":direction,"points":round(spot_move,2),"primary_driver":primary,"quality":quality,"contributors":shares}

def pressure_map(data: dict[str, Any]) -> list[dict[str, Any]]:
    spot=_num(data.get("spot")); grouped={}
    for row in data.get("option_chain",[]):
        strike=_num(row.get("strike"));
        if strike<=0: continue
        b=grouped.setdefault(strike,{"ce_oi":0.0,"pe_oi":0.0,"ce_doi":0.0,"pe_doi":0.0,"gamma":0.0,"volume":0.0}); side=str(row.get("side","")).upper(); prefix="ce" if side=="CE" else "pe"; b[f"{prefix}_oi"]+=_num(row.get("oi")); b[f"{prefix}_doi"]+=_num(row.get("oi"))-_num(row.get("previous_oi")); b["gamma"]+=_num(row.get("gamma"))*_num(row.get("oi")); b["volume"]+=_num(row.get("volume"))
    out=[]
    for strike,b in sorted(grouped.items(),key=lambda x:abs(x[0]-spot)):
        pressure=b["ce_oi"]+b["pe_oi"]+abs(b["ce_doi"])*2+abs(b["pe_doi"])*2+abs(b["gamma"])*1000+b["volume"]*0.01; side="CALL" if b["ce_oi"]>b["pe_oi"] else "PUT" if b["pe_oi"]>b["ce_oi"] else "BALANCED"; out.append({"strike":strike,"distance":round(strike-spot,2),"pressure":round(pressure,2),"dominant_side":side,**{k:round(v,2) for k,v in b.items()}})
    return out

def signal_dna(data: dict[str, Any], state: dict[str, Any], attribution: dict[str, Any]) -> list[dict[str, Any]]:
    bias=str(data.get("bias") or "NEUTRAL"); gamma=_num(data.get("gex")); iv=_num(data.get("atm_iv")); confidence=_num(data.get("confidence")); liquidity=_num(data.get("liquidity_score")); doi_diff=abs(_num(data.get("put_oi_change"))-_num(data.get("call_oi_change"))); doi_total=max(1.0,abs(_num(data.get("put_oi_change")))+abs(_num(data.get("call_oi_change"))))
    components=[("Direction",confidence,"bias is directional" if bias!="NEUTRAL" else "bias is neutral"),("Gamma",min(100.0,50.0+abs(gamma)/(abs(gamma)+1.0)*50.0),"gamma regime"),("OI Flow",min(100.0,50.0+doi_diff/doi_total*50.0),"OI imbalance"),("Volatility",min(100.0,50.0+abs(iv)*2.0),"ATM IV context"),("Liquidity",liquidity,"execution quality"),("Move Attribution",75.0 if attribution.get("quality")=="HIGH" else 55.0,attribution.get("primary_driver","unknown"))]
    return [{"name":name,"score":round(max(0.0,min(100.0,score)),1),"reason":reason} for name,score,reason in components]

def decision_intelligence(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    state=classify_market_state(data,previous); attribution=move_attribution(data,previous); events=detect_events(data,previous,state); dna=signal_dna(data,state,attribution); pressure=pressure_map(data); confidence=_num(data.get("confidence")); liquidity=_num(data.get("liquidity_score")); bias=str(data.get("bias") or "NEUTRAL")
    gates={"direction":bias in {"BULLISH","BEARISH"},"confidence":confidence>=60,"liquidity":liquidity>=50,"state":state["state"] not in {"LIQUIDITY_RISK","COMPRESSION"}}; trade_ready=all(gates.values())
    return {"market_state":state,"events":events,"move_attribution":attribution,"signal_dna":dna,"pressure_map":pressure,"decision":{"status":"TRADE_CANDIDATE" if trade_ready else "NO_TRADE","trade_ready":trade_ready,"reasons":[k for k,ok in gates.items() if not ok],"bias":bias,"confidence":confidence,"execution":"DISABLED"}}
