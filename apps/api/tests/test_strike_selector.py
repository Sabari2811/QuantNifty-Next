from quantnifty.strike_selector import select_strikes

def row(strike, side, premium=100, delta=0.5, gamma=0.01, theta=-2, volume=200000):
    return {'strike': strike, 'side': side, 'last_price': premium, 'delta': delta, 'gamma': gamma, 'theta': theta, 'iv': 10, 'volume': volume, 'bid': premium-1, 'ask': premium+1, 'security_id': str(strike)+side}

def test_normal_bullish_excludes_otm():
    r = select_strikes(24000, [row(23800,'CE',300,.75),row(24000,'CE',150,.52),row(24200,'CE',70,.28)], 'BULLISH')
    assert r['allowed_classifications'] == ['ATM','ITM']
    assert {x['classification'] for x in r['candidates']} <= {'ATM','ITM'}

def test_normal_bearish_excludes_otm():
    r = select_strikes(24000, [row(24200,'PE',300,-.75),row(24000,'PE',150,-.52),row(23800,'PE',70,-.28)], 'BEARISH')
    assert {x['classification'] for x in r['candidates']} <= {'ATM','ITM'}

def test_gamma_blast_allows_controlled_otm():
    r = select_strikes(24000, [row(23800,'CE',300,.75),row(24000,'CE',150,.52),row(24100,'CE',80,.35),row(24200,'CE',45,.22),row(24500,'CE',10,.08)], 'BULLISH', gamma_blast=True, expected_move=220)
    assert r['allowed_classifications'] == ['ATM','ITM','OTM']
    assert {x['classification'] for x in r['candidates']} == {'ATM','ITM','OTM'}
    assert all(x['strike'] <= 24200 for x in r['candidates'] if x['classification']=='OTM')

def test_neutral_no_strike():
    r = select_strikes(24000, [], 'NEUTRAL')
    assert not r['eligible'] and r['selected'] is None
