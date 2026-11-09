from mev_lab.detect import Tx,classify,evaluate
def test_sandwich_pattern():
 b=[Tx(1,0,"bot","p","swap","A","B",1,victim="v"),Tx(1,1,"v","p","swap","A","B",1,victim="v"),Tx(1,2,"bot","p","swap","B","A",1,victim="v")]
 assert [x["prediction"] for x in classify(b)]==["sandwich","sandwich","sandwich"]
def test_metrics():
 rows=classify([Tx(1,0,"x","p","liquidation","A","B",1)]); m=evaluate(rows,["liquidation"]); assert m["recall"]==1
