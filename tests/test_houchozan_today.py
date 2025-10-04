from datetime import date, timedelta

import pandas as pd

from procurement_manager import data_processor as dp


def make_df_with_due_dates(dates):
    # Build a DataFrame with at least 16 columns so that P列(index 15) exists
    rows = []
    for d in dates:
        row = [""] * 16
        # D列(index 3) for classification source
        row[3] = "H-XXXX"
        # I列(index 8) as key
        row[8] = f"KEY-{d}"
        # P列(index 15) as due date string YYYY/MM/DD
        row[15] = d.strftime("%Y/%m/%d")
        rows.append(row)
    cols = list(range(16))
    return pd.DataFrame(rows, columns=cols)


def test_houchozan_today_includes_today_and_past_only():
    today = date.today()
    df = make_df_with_due_dates([today - timedelta(days=1), today, today + timedelta(days=1)])

    # 発注残: strictly before today
    h_cols, h_letters, h_df, _ = dp.build_houchozan(df.copy(), today)
    assert len(h_df) == 1
    assert any(str(today - timedelta(days=1)) in str(v) for v in h_df.values.flatten())

    # 当日検収確認: up to and including today
    t_cols, t_letters, t_df, _ = dp.build_houchozan_today(df.copy(), today)
    assert len(t_df) == 2
    # should include yesterday and today, but not tomorrow
    flat = [str(v) for v in t_df.values.flatten()]
    assert str(today) in " ".join(flat)
    assert str(today + timedelta(days=1)) not in " ".join(flat)

