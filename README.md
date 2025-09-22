# 調達品データ管理システム

3タブ（発注残管理・短納期管理・テキスト品管理）のWebアプリ。Python(Flask)＋HTML/CSS/JS、PyInstallerでEXE化対応。

## セットアップ
1) Python 3.8+、Windowsを想定
2) 依存関係: `pip install -r requirements.txt`
3) 開発起動: `python procurement_manager\main.py` （ポートは `config.py`）

サンプルデータはリポジトリ直下の `NHSAPOTHIF126_*.txt` と CSV を自動検出（Shift-JIS）。

## 主要機能
- 発注残管理: 納期(P)が当日より前の行を抽出、表示列 B,C,D,E,I,J,O,P,R,Y,AC＋遅延日数/分類/自由入力
- テキスト品管理: D列が空白のみ、分類はF列先頭文字で判定
- 短納期管理: A〜M列＋備考（自由入力）、月曜は前週土曜分も結合
- フィルター: C/D/F/P/分類（テキスト品も同様）、短納期は A/I/K
- インライン編集: 自由入力/備考は自動保存（JSON 永続化）

## ビルド/配布
- EXE化: `build.bat`（PyInstaller、テンプレート/静的ファイル同梱）
- 日次実行: `run_daily.bat`（`--once` で加工済みJSONを `data/processed/` に出力）

## 設定
- `procurement_manager/config.py`: パス/ポート/ログ。実運用は `--no-sample` でKドライブのテンプレートパスを使用

## 注意
- 文字コードは Shift-JIS（cp932）で読込、JSON保存はUTF-8
- ネットワークドライブの権限/接続状態に留意
