## 本番パス設定（EXE向け）

- EXE と同じフォルダ（`dist` 配下など）に `pm_settings.ini` を置くと、本番データの参照先や文字コードを外だし設定できます。
- もしくは環境変数を使用します。

### `pm_settings.ini` 例

[paths]
IF126_TEMPLATE=K:\\PW_Tableau\\IF126_納期日程管理\\NHSAPOTHIF126_{yyyymmdd}.txt
SHORT_TEMPLATE=K:\\PW_MM_FileShare\\05_短納期品一覧\\西神\\短納期品(西神)_{yyyymmdd}.csv
# SAMPLE_DIRS=C:\\data\\samples;D:\\another\\dir

[encoding]
file=cp932

[server]
HOST=0.0.0.0
PORT=5000

[logs]
# LOG_DIR=C:\\SCMLogs

### 環境変数（代替）
- `PM_IF126_TEMPLATE` / `PM_SHORT_TEMPLATE` / `PM_ENCODING` / `PM_SAMPLE_DIRS`（`;`区切り）

### 注意点
- ネットワークドライブの代わりに UNC パス（例: `\\\\server\\share\\...`）を推奨（サービス実行時のドライブ割当問題を回避）。
- 読み込み文字コードは `cp932` → `utf-8-sig` → `utf-8` の順で自動フォールバックします。
