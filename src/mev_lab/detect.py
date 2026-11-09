from dataclasses import dataclass
from typing import Iterable
@dataclass(frozen=True)
class Tx:
    block:int; index:int; sender:str; to:str; kind:str; token_in:str; token_out:str; amount:float; victim:str|None=None

def classify(block: list[Tx]) -> list[dict]:
    rows=[]
    sandwich_indices=set()
    for i in range(len(block)-2):
      a,m,z=block[i:i+3]
      if (a.kind==m.kind==z.kind=="swap" and a.sender==z.sender and m.victim and a.victim==m.victim==z.victim):
        sandwich_indices.update((i,i+1,i+2))
    for i,tx in enumerate(block):
      label="other"
      if i in sandwich_indices: label="sandwich"
      elif tx.kind=="liquidation": label="liquidation"
      elif i+1<len(block) and tx.kind=="swap" and block[i+1].kind=="swap" and tx.sender==block[i+1].sender: label="arbitrage"
      elif tx.kind=="swap" and i+1<len(block) and block[i+1].kind=="swap": label="backrun"
      rows.append({"tx":tx,"prediction":label})
    return rows

def synthetic_blocks() -> list[list[Tx]]:
    return [[Tx(1,0,"bot","pool","swap","USDC","ETH",100,victim="alice"),Tx(1,1,"alice","pool","swap","USDC","ETH",100,victim="alice"),Tx(1,2,"bot","pool","swap","ETH","USDC",100,victim="alice")],[Tx(2,0,"arb","p1","swap","USDC","ETH",50),Tx(2,1,"arb","p2","swap","ETH","USDC",50)],[Tx(3,0,"keeper","aave","liquidation","ETH","USDC",12)]]

def evaluate(rows, truth):
 tp=sum(r["prediction"]==t and t!="other" for r,t in zip(rows,truth)); pred=sum(r["prediction"]!="other" for r in rows); actual=sum(t!="other" for t in truth)
 return {"precision":tp/pred if pred else 0.0,"recall":tp/actual if actual else 0.0,"false_positives":sum(r["prediction"]!="other" and t=="other" for r,t in zip(rows,truth))}
