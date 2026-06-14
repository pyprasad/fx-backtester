import csv
import json
from pathlib import Path

from .models import InternalTick


FIELDS = [
    "timestamp", "bid", "ask", "mid", "bid_vol", "ask_vol",
    "spread_pips", "source", "epic", "delayed", "price_scale_divisor",
]


class IGDemoTickStore:
    def __init__(self, root: str | Path, jsonl: bool = False):
        self.root, self.jsonl = Path(root), jsonl

    def append(self, tick: InternalTick) -> Path:
        day = tick.timestamp_utc.strftime("%Y-%m-%d")
        folder = self.root / day
        folder.mkdir(parents=True, exist_ok=True)
        csv_path = folder / f"usdjpy_demo_ticks_{tick.timestamp_utc:%Y%m%d}.csv"
        if csv_path.exists():
            with csv_path.open(newline="") as handle:
                if next(csv.reader(handle), []) != FIELDS:
                    csv_path = csv_path.with_name(f"{csv_path.stem}_v2.csv")
        row = tick.row()
        row["timestamp"] = row.pop("timestamp_utc")
        row["price_scale_divisor"] = tick.raw.get("normalization_price_scale_divisor")
        exists = csv_path.exists() and csv_path.stat().st_size > 0
        with csv_path.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow(row)
            handle.flush()
        if self.jsonl:
            with (folder / f"usdjpy_demo_ticks_{tick.timestamp_utc:%Y%m%d}.jsonl").open("a") as handle:
                handle.write(json.dumps(row, default=str) + "\n")
                handle.flush()
        return csv_path


def latest_tick(root: str | Path) -> InternalTick | None:
    files = sorted(Path(root).glob("*/*.csv"))
    if not files:
        return None
    with files[-1].open() as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    row = rows[-1]
    from datetime import datetime
    return InternalTick(
        datetime.fromisoformat(row["timestamp"]), float(row["bid"]), float(row["ask"]),
        float(row["mid"]), float(row["spread_pips"]), row["source"], row["epic"],
        row["delayed"].lower() == "true",
        float(row["bid_vol"]) if row.get("bid_vol") else None,
        float(row["ask_vol"]) if row.get("ask_vol") else None,
        raw={
            "normalization_price_scale_divisor": float(row["price_scale_divisor"])
        } if row.get("price_scale_divisor") else {},
    )
