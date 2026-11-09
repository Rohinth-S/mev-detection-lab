from .detect import synthetic_blocks,classify,evaluate
def main():
 rows=[]
 for b in synthetic_blocks(): rows.extend(classify(b))
 print({"detections":len(rows),"labels":[r["prediction"] for r in rows]})
if __name__=="__main__":main()
