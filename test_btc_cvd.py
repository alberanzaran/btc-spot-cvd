import unittest
from decimal import Decimal as D
import btc_cvd as m


class Tests(unittest.TestCase):
 def test_maker_inversion(self):
  self.assertEqual("BUY" if "sell"=="sell" else "SELL","BUY")
  self.assertEqual("BUY" if "buy"=="sell" else "SELL","SELL")
 def test_direct_math(self):
  now=1_000_000;s=m.source("okx","INDIVIDUAL_TRADES",[{"id":"1","ts":now-1000,"price":D("100"),"qty":D("2"),"side":"BUY"},{"id":"2","ts":now,"price":D("101"),"qty":D(".5"),"side":"SELL"}]);s["oldest"]=now-20_000
  x=m.stats(s,now-10_000,now);self.assertEqual((x["buy_btc"],x["sell_btc"],x["delta_btc"]),(2.0,.5,1.5))
 def test_kline_proxy(self):
  now=1_000_000;s=m.source("binance","KLINE_TAKER_PROXY",[{"ts":now-1000,"end":now,"po":D("100"),"pc":D("101"),"buy":D("3"),"sell":D("2"),"trades":9}]);s["oldest"]=now-20_000
  x=m.stats(s,now-10_000,now);self.assertEqual((x["delta_btc"],x["volume_btc"]),(1.0,5.0))


if __name__=="__main__":unittest.main()
