from __future__ import annotations
import unittest
from datetime import datetime,timedelta
from .runner import LabConfig,run_single_leg_tournament
from .multi_leg import run_multi_leg_tournament

def snapshot(ts:str,spot:float,call:float,put:float)->dict:
    rows=[]
    for strike,cp in ((spot,"CE"),(spot+50,"CE"),(spot-50,"CE"),(spot+100,"CE"),(spot-100,"CE"),(spot,"PE"),(spot+50,"PE"),(spot-50,"PE"),(spot+100,"PE"),(spot-100,"PE")):
        premium=call if cp=="CE" and strike==spot else put if cp=="PE" and strike==spot else max(5.0,call/2)
        rows.append({"security_id":f"{cp}-{int(strike)}","trading_symbol":f"NIFTY{int(strike)}{cp}","strike":strike,"option_type":cp,"expiry":"2026-09-24","bid":premium-.5,"ask":premium+.5,"last_price":premium,"volume":10000,"delta":.5 if cp=="CE" else -.5})
    return {"timestamp":ts,"spot":spot,"technicals":{"vwap":spot-10,"ema9":spot+5,"ema21":spot,"ema50":spot-20,"rsi":60,"volume_ratio":2.0},"oi_bias":"BULLISH","gex":-1,"gamma_flip":spot-20,"atm_iv":20,"realized_vol":15,"bias":"BULLISH","structure":"TREND","option_chain":rows}

class PostMarketLabSmokeTest(unittest.TestCase):
    def setUp(self):
        base=datetime.fromisoformat("2026-09-15T09:20:00+05:30")
        self.snaps=[snapshot((base+timedelta(minutes=10*i)).isoformat(),25000+i*10,100-i*5,90-i*2) for i in range(5)]

    def test_single_leg_tournament_is_research_only(self):
        report=run_single_leg_tournament(self.snaps,LabConfig(max_hold_bars=2))
        self.assertTrue(report["research_only"]);self.assertEqual(report["orders_placed"],0);self.assertEqual(report["tests"],72);self.assertTrue(all(r["contract_policy"]=="FIXED_AT_ENTRY" for r in report["results"]))

    def test_multi_leg_tournament_is_separate(self):
        report=run_multi_leg_tournament(self.snaps,LabConfig(max_hold_bars=2))
        self.assertTrue(report["research_only"]);self.assertEqual(report["orders_placed"],0);self.assertEqual(report["tests"],8)

if __name__=="__main__":unittest.main()
