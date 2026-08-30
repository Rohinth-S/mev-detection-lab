from mev_lab.detect import Tx,classify,evaluate,temporal_arbitrage,confidence
def test_sandwich_pattern():
 b=[Tx(1,0,"bot","p","swap","A","B",1,victim="v"),Tx(1,1,"v","p","swap","A","B",1,victim="v"),Tx(1,2,"bot","p","swap","B","A",1,victim="v")]
 assert [x["prediction"] for x in classify(b)]==["sandwich","sandwich","sandwich"]
def test_metrics():
 rows=classify([Tx(1,0,"x","p","liquidation","A","B",1)]); m=evaluate(rows,["liquidation"]); assert m["recall"]==1

def test_temporal_multi_hop_arbitrage():
 candidates=temporal_arbitrage([[Tx(10,0,"bot","p1","swap","USDC","ETH",100)], [Tx(11,0,"bot","p2","swap","ETH","USDC",101)]])
 assert candidates[0]["path"]==["USDC","ETH","USDC"]
 assert candidates[0]["price_ratio"]==1.01

def test_temporal_detector_chains_three_hops_and_enforces_gap():
 candidates=temporal_arbitrage([
     [Tx(10,0,"bot","p1","swap","USDC","ETH",100)],
     [Tx(11,0,"bot","p2","swap","ETH","DAI",101)],
     [Tx(12,0,"bot","p3","swap","DAI","USDC",102)],
 ])
 assert candidates[0]["hops"] == 3
 assert candidates[0]["path"] == ["USDC","ETH","DAI","USDC"]
 assert temporal_arbitrage([[Tx(10,0,"bot","p","swap","A","B",1)], [Tx(12,0,"bot","p","swap","B","A",1)]], max_gap_blocks=1) == []

def test_confidence_is_bounded():
 assert 0 <= confidence({"prediction":"other"}) <= 1
