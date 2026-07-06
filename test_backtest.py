import sys, backtest, formatter
sym = sys.argv[1] if len(sys.argv)>1 else "BTC/USDT"
tf = sys.argv[2] if len(sys.argv)>2 else "4h"
res = backtest.run_backtest(sym, tf)
print("accuracy:", res["accuracy"], "dir:", res.get("directional_accuracy"), "n:", res["points_tested"])
with open("last_backtest.txt","w",encoding="utf-8") as f:
    f.write(formatter.format_backtest(res))
print("yazıldı")
