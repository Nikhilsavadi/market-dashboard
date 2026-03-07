"""
Quick runner: execute EP backtest from command line.
Usage: python run_ep_backtest.py [lookback_days]
"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

lookback = int(sys.argv[1]) if len(sys.argv) > 1 else 90

print(f"=== EP Backtest — {lookback} days ===")
print(f"Polygon key set: {bool(os.environ.get('POLYGON_API_KEY'))}")

from ep_backtest import run_ep_backtest_from_scan

result = run_ep_backtest_from_scan(lookback_days=lookback)

# Save to cache so the dashboard can read it
cache_path = Path(__file__).parent / "cache.json"
if cache_path.exists():
    cache = json.loads(cache_path.read_text())
else:
    cache = {}
cache["ep_backtest"] = result
cache_path.write_text(json.dumps(cache, indent=2, default=str))

# Print summary
print(f"\n{'='*60}")
print(f"EP Events found : {result['total_events']}")
print(f"Trades simulated: {result['total_trades']}")

if result.get("overall"):
    o = result["overall"]
    print(f"\n--- OVERALL ---")
    print(f"Win Rate    : {o.get('win_rate', 0)}%")
    print(f"Avg Return  : {o.get('avg_return', 0)}%")
    print(f"Median Ret  : {o.get('median_return', 0)}%")
    print(f"Avg Win     : +{o.get('avg_win', 0)}%")
    print(f"Avg Loss    : {o.get('avg_loss', 0)}%")
    print(f"Profit Fact : {o.get('profit_factor', 0)}")
    print(f"Expectancy  : {o.get('expectancy', 0)}%")
    print(f"Best Trade  : +{o.get('best_trade', 0)}%")
    print(f"Worst Trade : {o.get('worst_trade', 0)}%")
    print(f"Avg Hold    : {o.get('avg_hold_days', 0)} days")
    print(f"\nMulti-period avg returns:")
    for d in [1, 3, 5, 10, 20]:
        v = o.get(f"avg_return_{d}d")
        if v is not None:
            print(f"  {d:>2}d : {'+' if v > 0 else ''}{v}%")
    print(f"\nExit breakdown: {o.get('exit_breakdown', {})}")

if result.get("by_type"):
    print(f"\n--- BY EP TYPE ---")
    for t, s in result["by_type"].items():
        print(f"  {t:12s}: {s['total_trades']:3d} trades, {s['win_rate']}% WR, avg {s['avg_return']}%, PF {s['profit_factor']}")

if result.get("by_gap_size"):
    print(f"\n--- BY GAP SIZE ---")
    for g, s in result["by_gap_size"].items():
        print(f"  {g:10s}: {s['total_trades']:3d} trades, {s['win_rate']}% WR, avg {s['avg_return']}%")

if result.get("by_volume_ratio"):
    print(f"\n--- BY VOLUME RATIO ---")
    for v, s in result["by_volume_ratio"].items():
        print(f"  {v:10s}: {s['total_trades']:3d} trades, {s['win_rate']}% WR, avg {s['avg_return']}%")

if result.get("by_neglect"):
    print(f"\n--- BY NEGLECT STATUS ---")
    for k, s in result["by_neglect"].items():
        print(f"  {k:15s}: {s['total_trades']:3d} trades, {s['win_rate']}% WR, avg {s['avg_return']}%")

if result.get("by_technical_position"):
    print(f"\n--- BY TECHNICAL POSITION ---")
    for k, s in result["by_technical_position"].items():
        print(f"  {k:17s}: {s['total_trades']:3d} trades, {s['win_rate']}% WR, avg {s['avg_return']}%")

if result.get("insights"):
    print(f"\n--- KEY INSIGHTS ---")
    for i in result["insights"]:
        print(f"  * {i}")

if result.get("sample_trades"):
    print(f"\n--- TOP 10 BEST TRADES ---")
    best = sorted(result["sample_trades"], key=lambda x: x["pnl_pct"], reverse=True)[:10]
    for t in best:
        print(f"  {t['ticker']:6s} {t['ep_date']} {t['ep_type']:8s} gap {t['gap_pct']:5.1f}% -> {t['pnl_pct']:+6.1f}% ({t['exit_reason']})")

    print(f"\n--- TOP 10 WORST TRADES ---")
    worst = sorted(result["sample_trades"], key=lambda x: x["pnl_pct"])[:10]
    for t in worst:
        print(f"  {t['ticker']:6s} {t['ep_date']} {t['ep_type']:8s} gap {t['gap_pct']:5.1f}% -> {t['pnl_pct']:+6.1f}% ({t['exit_reason']})")

print(f"\nResults saved to cache.json — viewable in EP Dashboard.")
