from datetime import date

import pandas as pd

from procurement_manager import data_processor as dp


def make_if126_dataframe(supplier_confirm_value: str, *, classification_source: str) -> pd.DataFrame:
    max_idx = dp.col_letter_to_index('AC')
    columns = []
    for idx in range(max_idx + 1):
        if idx == dp.col_letter_to_index('B'):
            columns.append('サプライヤコード')
        elif idx == dp.col_letter_to_index('C'):
            columns.append('名称')
        elif idx == dp.col_letter_to_index('D'):
            columns.append('分類元')
        elif idx == dp.col_letter_to_index('F'):
            columns.append('分類F')
        elif idx == dp.col_letter_to_index('I'):
            columns.append('I列キー')
        elif idx == dp.col_letter_to_index('P'):
            columns.append('納期')
        elif idx == dp.col_letter_to_index('Y'):
            columns.append('サプライヤ確認の納入日付')
        else:
            columns.append(f'COL{idx}')
    row = [''] * len(columns)
    row[dp.col_letter_to_index('B')] = 'NVAA000001'
    row[dp.col_letter_to_index('C')] = 'テスト名称'
    row[dp.col_letter_to_index('D')] = classification_source
    row[dp.col_letter_to_index('F')] = 'W-XXXX'
    row[dp.col_letter_to_index('I')] = 'KEY-1'
    row[dp.col_letter_to_index('P')] = '2024/01/09'
    row[dp.col_letter_to_index('Y')] = supplier_confirm_value
    return pd.DataFrame([row], columns=columns)


def test_houchozan_blanks_placeholder_supplier_confirmation_date():
    df = make_if126_dataframe('000000000', classification_source='H-XXXX')
    _, _, view_df, _ = dp.build_houchozan(df, date(2024, 1, 10))
    assert view_df.at[0, 'サプライヤ確認の納入日付'] == ''


def test_text_items_blanks_placeholder_supplier_confirmation_date():
    df = make_if126_dataframe('00000000', classification_source='')
    _, _, view_df, _ = dp.build_text_items(df, date(2024, 1, 10))
    assert view_df.at[0, 'サプライヤ確認の納入日付'] == ''
