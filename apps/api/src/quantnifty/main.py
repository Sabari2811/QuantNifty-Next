from __future__ import annotations
import asyncio, math, os, time, json
from datetime import datetime, timezone
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

BASE='https://api.indstocks.com'
TOKEN=os.getenv('INDSTOCKS_TOKEN','').strip()
NIFTY_ID=os.getenv('NIFTY_SECURITY_ID','40000001')
EXPIRY=os.getenv('NIFTY_EXPIRY','')

app=FastAPI(title='QuantNifty Next', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['*'], allow_headers=['*'])
cache={'snapshot':None,'updated_at':None}

async def api_get(path:str, params:dict[str,Any]|None=None):
    if not TOKEN: raise RuntimeError('INDSTOCKS_TOKEN is not configured')
    headers={'Authorization':TOKEN,'Accept':'application/json'}
    last=None
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r=await c.get(BASE+path,params=params,headers=headers)
            if r.status_code==429 or r.status_code>=500:
                last=f'HTTP {r.status_code}'; await asyncio.sleep(0.5*(2**attempt)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            last=str(e); await asyncio.sleep(0.5*(2**attempt))
    raise RuntimeError(last or 'provider request failed')

def norm_leg(leg:dict, strike:float, side:str):
    g=leg.get('greeks') or {}
    return {'strike':float(strike),'side':side,'last_price':float(leg.get('last_price') or 0),'oi':float(leg.get('oi') or 0),'previous_oi':float(leg.get('previous_oi') or leg.get('prev_oi') or 0),'volume':float(leg.get('volume') or 0),'bid':float(leg.get('bid') or 0),'ask':float(leg.get('ask') or 0),'iv':float(leg.get('iv') or 0),'delta':float(g.get('delta') if g.get('delta') is not None else leg.get('delta') or 0),'gamma':float(g.get('gamma') if g.get('gamma') is not None else leg.get('gamma') or 0),'vega':float(g.get('vega') if g.get('vega') is not None else leg.get('vega') or 0)}

def flatten_chain(data):
    root=data.get('data',data); strikes=root.get('strikes') or root.get('option_chain') or []
    rows=[]
    if isinstance(strikes,dict):
        for k,v in strikes.items():
            s=float(k); ce=v.get('call') or v.get('CE') or v.get('call_option') or {}; pe=v.get('put') or v.get('PE') or v.get('put_option') or {}
            if ce: rows.append(norm_leg(ce,s,'CE'))
            if pe: rows.append(norm_leg(pe,s,'PE'))
    elif isinstance(strikes,list):
        for x in strikes:
            s=float(x.get('strike_price') or x.get('strike') or 0); ce=x.get('call') or x.get('CE') or x.get('call_option') or {}; pe=x.get('put') or x.get('PE') or x.get('put_option') or {}
            if ce: rows.append(norm_leg(ce,s,'CE'))
            if pe: rows.append(norm_leg(pe,s,'PE'))
    return float(root.get('underlying_ltp') or root.get('underlying_price') or 0), rows

def analytics(spot, rows):
    calls=[x for x in rows if x['side']=='CE']; puts=[x for x in rows if x['side']=='PE']
    coi=sum(x['oi'] for x in calls); poi=sum(x['oi'] for x in puts); pcr=(poi/coi) if coi else 0
    call_chg=sum(x['oi']-x['previous_oi'] for x in calls); put_chg=sum(x['oi']-x['previous_oi'] for x in puts)
    gex=sum(x['gamma']*x['oi']*(spot**2)*0.01*(1 if x['side']=='PE' else -1) for x in rows)
    dex=sum(x['delta']*x['oi']*(1 if x['side']=='CE' else -1) for x in rows)
    ivc=[x['iv'] for x in calls if x['iv']>0]; ivp=[x['iv'] for x in puts if x['iv']>0]
    skew=(sum(ivp)/len(ivp)-sum(ivc)/len(ivc)) if ivc and ivp else 0
    walls=[]
    for side in ('CE','PE'):
        z=[x for x in rows if x['side']==side]
        if z:
            w=max(z,key=lambda x: x['oi']*abs(x['gamma']))
            walls.append({'side':side,'strike':w['strike'],'exposure':w['oi']*abs(w['gamma'])})
    by={}
    for x in rows: by.setdefault(x['strike'],[]).append(x)
    pts=[]
    for s in sorted(by):
        e=sum(y['gamma']*y['oi']*(spot**2)*0.01*(1 if y['side']=='PE' else -1) for y in by[s]); pts.append((s,e))
    flip=None
    for (a,ea),(b,eb) in zip(pts,pts[1:]):
        if ea==0: flip=a; break
        if ea*eb<0: flip=a+(b-a)*(abs(ea)/(abs(ea)+abs(eb))); break
    score=50
    score += 15 if pcr>1.15 else (-15 if pcr<0.85 else 0)
    score += 10 if skew>2 else (-10 if skew<-2 else 0)
    score += 10 if put_chg>call_chg else (-10 if call_chg>put_chg else 0)
    score += 5 if (flip is not None and spot>flip) else (-5 if flip is not None else 0)
    score=max(0,min(100,score)); bias='BULLISH' if score>=60 else ('BEARISH' if score<=40 else 'NEUTRAL')
    conf=round(abs(score-50)*2+50 if bias!='NEUTRAL' else 50,1)
    return {'spot':spot,'pcr':round(pcr,3),'call_oi':coi,'put_oi':poi,'call_oi_change':call_chg,'put_oi_change':put_chg,'gex':gex,'dex':dex,'iv_skew':skew,'gamma_flip':flip,'gamma_walls':walls,'bullish_score':round(score,1),'bearish_score':round(100-score,1),'bias':bias,'confidence':conf,'structure':'ABOVE_GAMMA_FLIP' if flip and spot>flip else ('BELOW_GAMMA_FLIP' if flip else 'UNAVAILABLE'),'data_integrity':'LIVE_PROVIDER' if TOKEN else 'PROVIDER_TOKEN_MISSING','rows':len(rows),'timestamp':datetime.now(timezone.utc).isoformat()}

async def snapshot():
    expiry=EXPIRY
    if not expiry:
        e=await api_get('/market/instruments/expiries',{'exchange':'NSE','segment':'INDEX','underlying-scrip':NIFTY_ID})
        vals=(e.get('data') or e.get('expiries') or [])
        if isinstance(vals,list) and vals: expiry=str(vals[0].get('expiry') if isinstance(vals[0],dict) else vals[0])
    raw=await api_get('/market/option-chain',{'exchange':'NSE','segment':'INDEX','underlying-scrip':NIFTY_ID,'expiry':expiry,'strike_count':20})
    spot,rows=flatten_chain(raw)
    if spot<=0: raise RuntimeError('provider returned invalid NIFTY spot')
    out=analytics(spot,rows); out['expiry']=expiry
    cache['snapshot']=out; cache['updated_at']=time.time(); return out

@app.get('/')
def root():
    p=os.path.join(os.path.dirname(__file__),'web','index.html')
    return FileResponse(p) if os.path.exists(p) else {'service':'QuantNifty Next','status':'ok'}
@app.get('/health')
def health(): return {'status':'ok','provider_configured':bool(TOKEN),'timestamp':datetime.now(timezone.utc).isoformat()}
@app.get('/api/v1/status')
def status(): return {'status':'ok','provider':'INDstocks','provider_configured':bool(TOKEN),'cached':cache['snapshot'] is not None}
@app.get('/api/v1/market')
async def market():
    try: return await snapshot()
    except Exception as e: raise HTTPException(503,detail=str(e))
@app.get('/api/v1/analytics')
async def analytics_api(): return await market()

@app.websocket('/ws')
async def ws(websocket:WebSocket):
    await websocket.accept()
    try:
        while True:
            try: data=await snapshot(); await websocket.send_json(data)
            except Exception as e: await websocket.send_json({'data_integrity':'UNAVAILABLE','error':str(e)})
            await asyncio.sleep(float(os.getenv('POLL_SECONDS','15')))
    except WebSocketDisconnect: pass
