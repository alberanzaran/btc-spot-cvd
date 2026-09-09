#!/usr/bin/env python3
"""CVD spot BTC on-demand mediante REST públicas oficiales."""
import argparse,json,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from decimal import Decimal as D
from urllib.parse import urlencode
from urllib.request import Request,urlopen

W={"15m":900,"1h":3600,"4h":14400,"24h":86400}; EX=("binance","coinbase","okx","bybit")
SYM={"binance":"BTCUSDT","coinbase":"BTC-USD","okx":"BTC-USDT","bybit":"BTCUSDT"}
def get(url,p=None):
 if p:url+=("&" if "?" in url else "?")+urlencode(p)
 with urlopen(Request(url,headers={"User-Agent":"btc-cvd/2.0","Accept":"application/json","Cache-Control":"no-cache"}),timeout=15) as r:return json.load(r)
def ims(s):return int(datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()*1000)
def iso(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")

def binance(now,limit):
 rows=[]; cur=now-86460_000
 while cur<now and time.monotonic()<limit:
  p=get("https://data-api.binance.vision/api/v3/klines",{"symbol":"BTCUSDT","interval":"1m","startTime":cur,"endTime":now,"limit":1000})
  if not p:break
  rows+=p;cur=int(p[-1][0])+60000
  if len(p)<1000:break
 s=[]
 for r in rows:
  v,b=D(r[5]),D(r[9]);s.append(dict(ts=int(r[0]),end=int(r[6]),po=D(r[1]),pc=D(r[4]),buy=b,sell=v-b,trades=int(r[8])))
 return source("binance","KLINE_TAKER_PROXY",s)
def coinbase(now,limit):
 rows=[];after=None;target=now-86400000
 while time.monotonic()<limit:
  q={"limit":1000}
  if after:q["after"]=after
  page=get("https://api.exchange.coinbase.com/products/BTC-USD/trades",q)
  if not page:break
  for r in page: rows.append(dict(id=str(r["trade_id"]),ts=ims(r["time"]),price=D(r["price"]),qty=D(r["size"]),side="BUY" if r["side"]=="sell" else "SELL"))
  if min(x["ts"] for x in rows)<=target or len(page)<1000:break
  nxt=str(min(int(r["trade_id"]) for r in page))
  if nxt==after:break
  after=nxt;time.sleep(.105)
 rows=sorted({x["id"]:x for x in rows}.values(),key=lambda x:x["ts"])
 return source("coinbase","INDIVIDUAL_TRADES",rows)
def okx(now,limit):
 rows=[];after=None;target=now-86400000
 while time.monotonic()<limit:
  q={"instId":"BTC-USDT","type":"1","limit":100}
  if after:q["after"]=after
  o=get("https://www.okx.com/api/v5/market/history-trades",q)
  if o.get("code")!="0":raise RuntimeError(o.get("msg") or o.get("code"))
  page=o["data"]
  if not page:break
  for r in page:rows.append(dict(id=r["tradeId"],ts=int(r["ts"]),price=D(r["px"]),qty=D(r["sz"]),side=r["side"].upper()))
  if min(x["ts"] for x in rows)<=target or len(page)<100:break
  nxt=str(min(int(r["tradeId"]) for r in page))
  if nxt==after:break
  after=nxt;time.sleep(.105)
 rows=sorted({x["id"]:x for x in rows}.values(),key=lambda x:x["ts"])
 return source("okx","INDIVIDUAL_TRADES",rows)
def bybit(now,limit):
 o=get("https://api.bybit.com/v5/market/recent-trade",{"category":"spot","symbol":"BTCUSDT","limit":60})
 if o.get("retCode")!=0:raise RuntimeError(o.get("retMsg"))
 rows=[dict(id=r["execId"],ts=int(r["time"]),price=D(r["price"]),qty=D(r["size"]),side=r["side"].upper()) for r in o["result"]["list"]]
 return source("bybit","RECENT_TRADES_LIMITED",sorted(rows,key=lambda x:x["ts"]))
def source(ex,method,s):return dict(exchange=ex,symbol=SYM[ex],method=method,samples=s,oldest=min((x["ts"] for x in s),default=None),newest=max((x.get("end",x["ts"]) for x in s),default=None),error=None)
F={"binance":binance,"coinbase":coinbase,"okx":okx,"bybit":bybit}
def fetch(seconds):
 now=int(time.time()*1000);st=time.monotonic();src={}
 with ThreadPoolExecutor(max_workers=4) as p:
  jobs={p.submit(F[e],now,st+seconds):e for e in EX}
  for f in as_completed(jobs):
   e=jobs[f]
   try:src[e]=f.result()
   except Exception as x:src[e]=dict(exchange=e,symbol=SYM[e],method="UNAVAILABLE",samples=[],oldest=None,newest=None,error=str(x))
 return now,src,time.monotonic()-st
def stats(s,start,now):
 data=[x for x in s["samples"] if start<=x["ts"]<=now]
 if s["method"]=="KLINE_TAKER_PROXY":
  buy=sum((x["buy"] for x in data),D(0));sell=sum((x["sell"] for x in data),D(0));n=sum(x["trades"] for x in data);p0=data[0]["po"] if data else None;p1=data[-1]["pc"] if data else None
 else:
  buy=sum((x["qty"] for x in data if x["side"]=="BUY"),D(0));sell=sum((x["qty"] for x in data if x["side"]=="SELL"),D(0));n=len(data);p0=data[0]["price"] if data else None;p1=data[-1]["price"] if data else None
 ready=bool(data and s["oldest"] is not None and s["oldest"]<=start)
 return dict(symbol=s["symbol"],method=s["method"],status="READY" if ready else "INCOMPLETE",included_in_aggregate=ready,coverage_start=iso(s["oldest"]) if s["oldest"] else None,coverage_seconds=max(0,(now-s["oldest"])//1000) if s["oldest"] else 0,buy_btc=float(buy),sell_btc=float(sell),delta_btc=float(buy-sell),cvd_btc=float(buy-sell),volume_btc=float(buy+sell),trades=n,price_change_pct=float((p1/p0-1)*100) if p0 and p1 else None,error=s["error"])
def report(now,src,elapsed,pnoise=5,cnoise=1):
 out={"generated_at":iso(now),"mode":"ON_DEMAND_REST","elapsed_seconds":round(elapsed,3),"windows":{}}
 for label,secs in W.items():
  es={e:stats(src[e],now-secs*1000,now) for e in EX};inc=[e for e in EX if es[e]["included_in_aggregate"]]
  buy=sum((D(str(es[e]["buy_btc"])) for e in inc),D(0));sell=sum((D(str(es[e]["sell_btc"])) for e in inc),D(0));vol=buy+sell
  for e,v in es.items():v["volume_share_pct"]=float(D(str(v["volume_btc"]))*100/vol) if e in inc and vol else 0
  signs=[]
  for e in inc:
   v=es[e];t=cnoise/100*v["volume_btc"];signs.append(1 if v["delta_btc"]>t else -1 if v["delta_btc"]<-t else 0)
  b,s,n=signs.count(1),signs.count(-1),len(signs);cls="CONFIRMACIÓN FUERTE" if n>=3 and b==n else "CONFIRMACIÓN MODERADA" if b>n/2 else "VENTA FUERTE" if n>=3 and s==n else "VENTA MODERADA" if s>n/2 else "MIXTO"
  pcs=[es[e]["price_change_pct"] for e in inc if es[e]["price_change_pct"] is not None];pc=sum(pcs)/len(pcs) if pcs else None;delta=buy-sell
  pd=0 if pc is None or abs(pc)<pnoise/100 else (1 if pc>0 else -1);cd=0 if not vol or abs(delta)<D(str(cnoise/100))*vol else (1 if delta>0 else -1)
  rel={(1,1):"confirmación compradora",(1,-1):"divergencia bajista",(-1,-1):"confirmación vendedora",(-1,1):"divergencia alcista"}.get((pd,cd),"sin señal (ruido/insuficiente)");ds=[es[e]["delta_btc"] for e in inc]
  out["windows"][label]=dict(data_quality="GOOD" if len(inc)==4 else "PARTIAL" if len(inc)>=2 else "POOR",included_exchanges=inc,excluded_exchanges=[e for e in EX if e not in inc],exchanges=es,aggregate=dict(buy_btc=float(buy),sell_btc=float(sell),delta_btc=float(delta),cvd_btc=float(delta),volume_btc=float(vol),trades=sum(es[e]["trades"] for e in inc)),consensus=dict(buyers=b,sellers=s,neutral=n-b-s,available=n,classification=cls),exchange_divergence=bool(ds and min(ds)<0<max(ds)),aggregate_price_change_pct=pc,price_cvd=rel)
 return out
def human(r):
 print("BTC SPOT CVD — ON DEMAND\n"+"="*60)
 for k,w in r["windows"].items():
  d=w["aggregate"]["delta_btc"];print(f"{k:>3} {'🟢' if d>0 else '🔴' if d<0 else '🟡'} {d:+.4f} BTC  {w['data_quality']:<7} incluye: {','.join(w['included_exchanges']) or 'ninguno'}")
 print(f"\nConsulta completada en {r['elapsed_seconds']:.2f}s\n\n4H por exchange:")
 w=r["windows"]["4h"]
 for e,v in w["exchanges"].items():print(f"{e.capitalize():<11}{v['delta_btc']:+10.4f} BTC  {v['status']:<10} {v['method']}")
 c=w["consensus"];print(f"AGGREGATE  {w['aggregate']['delta_btc']:+10.4f} BTC\nConsensus: {c['buyers']}/{c['available']} BUY — {c['classification']}\nPrice/CVD: {w['price_cvd']}")
 if w["exchange_divergence"]:print("⚠ DIVERGENCIA ENTRE EXCHANGES")
def main():
 p=argparse.ArgumentParser();p.add_argument("--json",action="store_true");p.add_argument("--max-seconds",type=float,default=45);p.add_argument("--price-noise-bps",type=float,default=5);p.add_argument("--cvd-noise-pct",type=float,default=1);a=p.parse_args()
 now,s,e=fetch(max(5,a.max_seconds));r=report(now,s,e,a.price_noise_bps,a.cvd_noise_pct);print(json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True) if a.json else "",end="" if a.json else "")
 if not a.json:human(r)
if __name__=="__main__":main()
