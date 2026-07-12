"""generate_d1_event_windows.py
==============================
从 D1 v11_state.pkl 的 events_v11 提取标准化事件表，
写入 D1 artifacts/data/D1_event_windows.xlsx，
供 D2 P1-C 链接逻辑（extract_freeze_events）使用。

列规范（D2 P1-C 期望）：
  event_id       str   "D1E_0001"
  sensor_id      str   "DO_1_1"
  start_ts       datetime
  end_ts         datetime
  duration_h     int
  fault_type     str   dominant Q sub-score during event window
  min_d1         float
  mean_d1        float
  severity_tag   str   "severe" / "moderate" (基于 min_d1)

运行方式：
  cd <D2 project root>
  python generate_d1_event_windows.py
"""
from __future__ import annotations
import pickle
import pandas as pd
from pathlib import Path

# ── 路径 ────────────────────────────────────────────────────────────────────
_ROOT   = Path(__file__).parent
_D1_DIR = _ROOT.parent / "D1 Sensor health"
_PKL    = _D1_DIR / "v11_state.pkl"
_OUT    = _D1_DIR / "artifacts" / "data" / "D1_event_windows.xlsx"

def main():
    print(f"[A-1] Loading D1 state: {_PKL}")
    if not _PKL.exists():
        raise FileNotFoundError(f"D1 pkl not found: {_PKL}")

    with open(_PKL, "rb") as f:
        S = pickle.load(f)

    events_raw  = S["events_v11"].copy()          # sensor_id / start / end / duration_h / min_d1 / mean_d1
    dominant    = S["dominant_v11"]               # DataFrame (6138 h × 14 ch), values = Q_xxx label

    print(f"    events_v11:    {len(events_raw)} rows, channels: {events_raw['sensor_id'].nunique()}")
    print(f"    dominant_v11:  {dominant.shape}")

    # ── Step 1: 为每条事件推导 fault_type（事件窗口内 dominant 众数）──────────
    fault_types = []
    for _, row in events_raw.iterrows():
        ch        = row["sensor_id"]
        ev_start  = pd.Timestamp(row["start"])
        ev_end    = pd.Timestamp(row["end"])

        if ch in dominant.columns:
            window = dominant[ch].loc[
                (dominant.index >= ev_start) & (dominant.index <= ev_end)
            ]
            if len(window) > 0:
                mode_val = window.mode()
                fault_types.append(str(mode_val.iloc[0]) if len(mode_val) > 0 else "unknown")
            else:
                fault_types.append("unknown")
        else:
            fault_types.append("unknown")

    # ── Step 2: 构建标准化事件表 ─────────────────────────────────────────────
    df = events_raw.rename(columns={"start": "start_ts", "end": "end_ts"}).copy()
    df.insert(0, "event_id", [f"D1E_{i+1:04d}" for i in range(len(df))])
    df["fault_type"]    = fault_types
    df["severity_tag"]  = df["min_d1"].apply(
        lambda v: "severe" if v < 2.0 else "moderate"
    )

    # 列排序
    col_order = ["event_id", "sensor_id", "start_ts", "end_ts",
                 "duration_h", "fault_type", "min_d1", "mean_d1", "severity_tag"]
    df = df[col_order]

    # ── Step 3: 输出 ──────────────────────────────────────────────────────────
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(_OUT, index=False)
    print(f"\n    [OK] Written: {_OUT}")
    print(f"    Events: {len(df)} rows | fault_type breakdown:")
    print(df["fault_type"].value_counts().to_string(indent=6))
    print(f"\n    severity_tag:")
    print(df["severity_tag"].value_counts().to_string(indent=6))
    print(f"\n    Per-channel count (top 5):")
    print(df["sensor_id"].value_counts().head(5).to_string(indent=6))
    print("\n[A-1] Done.")

if __name__ == "__main__":
    main()
