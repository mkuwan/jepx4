# MockServer テスト仕様書

**文書バージョン**: 1.0  
**対象システム**: MockServer (JEPX API シミュレーター)  
**テストコード**: `tests/test_server.py`  
**テスト総数**: 20件（正常系13件 + 異常系4件 + 構造検証3件）

---

## 1. テスト実行環境と前提条件

| 項目 | 内容 |
|------|------|
| テストフレームワーク | `unittest.IsolatedAsyncioTestCase` (Python 3.11+) |
| テスト対象 | MockServer (Docker コンテナ or ネイティブ起動) |
| 接続先 | `127.0.0.1:8888` (TLS 1.3) |
| 接続方式 | `asyncio.open_connection` + SSL (証明書検証なし) |
| 前提条件 | MockServerが起動済みであること（未起動時はスキップ） |

### 実行コマンド
```bash
# PowerShellの場合
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python -m unittest tests/test_server.py -v
```

### 注意事項
- MockServerのインメモリ状態は**テスト間で蓄積される**（サーバー再起動まで永続）。各テストは蓄積を前提に設計。
- DockerコンテナはUTC、テスト実行環境はJSTのため、日時関連テストは±1日の許容範囲を持つ。

---

## 2. テストケース一覧

| # | テストID | 分類 | 対象API | テスト要約 |
|---|---------|------|---------|-----------|
| 01 | test_01_sys1001_keep_alive | 正常系 | SYS1001 | Keep-Alive正常レスポンス |
| 02 | test_02_dah1001_bid_and_dah1002_inquiry | 正常系 | DAH1001→DAH1002 | 入札→照会の状態保持 |
| 03 | test_03_invalid_member | 異常系 | SYS1001 | 不正MEMBER認証エラー |
| 04 | test_04_itn1001_stream | 正常系 | ITN1001 | 全量配信→差分配信ストリーム |
| 05 | test_05_dah1003_delete_and_dah1004_contract | 正常系 | DAH1001→1003→1002→1004 | 入札削除＋約定照会 |
| 06 | test_06_itd_market_suite | 正常系 | ITD1001→1003→1002→1004 | 時間前市場CRUD統合 |
| 07 | test_07_data_format_error | 異常系 | DAH1001 | SIZE不一致の電文異常 |
| 08 | test_08_tls13_connection | 構造検証 | — | TLS 1.3バージョン確認 |
| 09 | test_09_unknown_api_code | 異常系 | ZZZ9999 | 未知APIコードのエラー |
| 10 | test_10_sys1001_keep_alive_extends_socket | 正常系 | SYS1001→DAH1002 | Socket維持の証明 |
| 11 | test_11_dah1030_alias | 正常系 | DAH1030 | DAH1004エイリアス確認 |
| 12 | test_12_itn_full_state_structure | 構造検証 | ITN1001 | JEPX仕様フィールド検証 |
| 13 | test_13_dah1001_multi_bid | 正常系 | DAH1001→DAH1002 | 複数入札の一括送信 |
| 14 | test_14_response_header_size_validation | 構造検証 | SYS1001 | レスポンスSIZE整合性 |
| 15 | test_15_itn_full_state_date_range | 正常系 | ITN1001 | 全量配信の日付範囲 |
| 16 | test_16_itn_diff_delivery_date_valid | 正常系 | ITN1001 | 差分配信の日付有効性 |
| 17 | test_17_dah1003_delete_nonexistent_bid | 異常系 | DAH1003 | 存在しないbidNoの削除 |
| 18 | test_18_empty_body_request | 正常系 | DAH1002 | 空ボディリクエスト処理 |
| 19 | test_19_dah9001_settlement | 正常系 | DAH9001 | 翌日市場 清算照会 |
| 20 | test_20_itd9001_settlement | 正常系 | ITD9001 | 時間前市場 清算照会 |

---

## 3. テストケース詳細

---

### テスト01: SYS1001 Keep-Alive 正常系

| 項目 | 内容 |
|------|------|
| テストID | `test_01_sys1001_keep_alive` |
| 対象API | SYS1001 |
| 分類 | 正常系 |
| JEPX仕様 | 接続技術書 SYS1001 |
| 目的 | 切断防止用の共通APIを送信し、正常レスポンスが返るか検証する |

**リクエスト:**

| ヘッダ項目 | 値 |
|-----------|---|
| MEMBER | `9999` |
| API | `SYS1001` |
| Body | `{}` (空) |

**期待値:**

| 検証項目 | 期待値 | 検証メソッド |
|---------|-------|------------|
| レスポンスヘッダ STATUS | `"00"` | `assertEqual` |
| ボディ `status` | `"200"` | `assertEqual` |
| ボディ `statusInfo` | `"Socket Expiration Time Extension"` を含む | `assertIn` |

---

### テスト02: DAH1001入札 → DAH1002照会 状態保持

| 項目 | 内容 |
|------|------|
| テストID | `test_02_dah1001_bid_and_dah1002_inquiry` |
| 対象API | DAH1001 → DAH1002 |
| 分類 | 正常系 |
| JEPX仕様 | 902 §2.1, §2.2 |
| 目的 | 入札データがメモリに保存され、照会でJEPX仕様の `bids[]` 配列として返るか検証する |

**ステップ1: DAH1001 入札リクエスト:**

```json
{
  "bidOffers": [{
    "deliveryDate": "2026-04-01", "areaCd": "1", "timeCd": "48",
    "bidTypeCd": "SELL-LIMIT", "price": 120, "volume": 4320.5,
    "deliveryContractCd": "ABCD8"
  }]
}
```

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `status` | `"200"` |
| ボディ `statusInfo` | `"1"` (1件入札) |

**ステップ2: DAH1002 照会リクエスト:**

```json
{ "deliveryDate": "2026-04-01" }
```

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `bids[]` | 1件以上 |
| `bids[0].bidNo` | 存在すること（10桁数字文字列） |
| `bids[0].price` | `120` |

---

### テスト03: 無効MEMBER認証エラー

| 項目 | 内容 |
|------|------|
| テストID | `test_03_invalid_member` |
| 対象API | SYS1001 |
| 分類 | 異常系 |
| JEPX仕様 | 接続技術書 権限チェック |
| 目的 | 許可リストにないMEMBER IDで `STATUS=11`（権限なし）が返るか検証する |

**リクエスト:**

| ヘッダ項目 | 値 |
|-----------|---|
| MEMBER | `INVALID` (不正値) |
| API | `SYS1001` |

**期待値:**

| 検証項目 | 期待値 | 備考 |
|---------|-------|------|
| ヘッダ STATUS | `"11"` | レスポンスが返る場合 |
| TCP切断 | 許容 | `ConnectionResetError` の場合も合格 |

---

### テスト04: ITN1001 ストリーミング（全量→差分配信）

| 項目 | 内容 |
|------|------|
| テストID | `test_04_itn1001_stream` |
| 対象API | ITN1001 |
| 分類 | 正常系 |
| JEPX仕様 | 903 §4.1 |
| 目的 | 全量配信後、10秒間隔で差分データがPushされることを検証する |

**リクエスト:** MEMBER=`0841`, API=`ITN1001`, Body=`{}`

**ステップ1: 全量配信（接続直後、5秒以内）**

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `notices[]` | 1件以上（当日＋翌日の板情報） |
| ボディ `memo` | `"Mock: Current Full Market State"` |

**ステップ2: 差分配信（リクエストなしで最大15秒待機）**

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| `notices[0].noticeTypeCd` | `"CONTRACT"` または `"BID-BOARD"` |
| ボディ `memo` | `"from Engine"` を含む |

---

### テスト05: DAH1003入札削除 + DAH1004約定照会

| 項目 | 内容 |
|------|------|
| テストID | `test_05_dah1003_delete_and_dah1004_contract` |
| 対象API | DAH1001 → DAH1002 → DAH1003 → DAH1002 → DAH1004 |
| 分類 | 正常系 |
| JEPX仕様 | 902 §2.1, §2.2, §2.3, §2.4 |
| 目的 | 入札削除がStateに反映され、約定照会が仕様準拠のフォーマットで返ることを検証する |

**処理フロー:**

| ステップ | API | 操作 | 検証項目 | 期待値 |
|---------|-----|------|---------|-------|
| 1 | DAH1001 | 入札 (`deliveryDate: 2026-04-02`) | `statusInfo` | `"1"` |
| 2 | DAH1002 | 照会 → bidNo取得 | `bids[]` | 1件以上 |
| 3 | DAH1003 | 削除 (`bidDels[].bidNo`) | `status` | `"200"` |
| | | | `statusInfo` | `"1"` (1件削除) |
| 4 | DAH1002 | 削除後の照会 | `bids[]` | 0件 |
| 5 | DAH1004 | 約定照会 | `bidResults[]` | 1件以上 |
| | | | `bidResults[0].contractPrice` | 存在すること |
| | | | `bidResults[0].contractVolume` | 存在すること |

---

### テスト06: ITD系 統合テスト

| 項目 | 内容 |
|------|------|
| テストID | `test_06_itd_market_suite` |
| 対象API | ITD1001 → ITD1003 → ITD1002 → ITD1004 |
| 分類 | 正常系 |
| JEPX仕様 | 903 §2.1, §2.2, §2.3, §2.4 |
| 目的 | 時間前市場の全CRUD操作がJEPX仕様903準拠で動作するか検証する |

**処理フロー:**

| ステップ | API | 操作 | 検証項目 | 期待値 |
|---------|-----|------|---------|-------|
| 1 | ITD1001 | 入札 (`deliveryDate: 2026-04-03`) | ヘッダ STATUS | `"00"` |
| | | | ボディ `bidNo` | null以外（10桁数字） |
| 2 | ITD1003 | 照会 | `bids[]` | 1.で取得した `bidNo` が含まれる |
| 3 | ITD1002 | 削除 (`targetBidNo`指定) | `status` | `"200"` |
| 4 | ITD1004 | 約定照会 | `bidResults[]` | 1件以上 |
| | | | `bidResults[0].contractPrice` | 存在すること |

---

### テスト07: 電文フォーマット異常 (SIZE不一致)

| 項目 | 内容 |
|------|------|
| テストID | `test_07_data_format_error` |
| 対象API | DAH1001 |
| 分類 | 異常系 |
| JEPX仕様 | 接続技術書 SIZE検証 |
| 目的 | ヘッダSIZE値と実Body長が異なる場合、`STATUS=10` を返すか検証する |

**リクエスト:** ヘッダSIZEを `999999` に偽装し、実際のBody長と不一致にする。

| 検証項目 | 期待値 | 備考 |
|---------|-------|------|
| ヘッダ STATUS | `"10"` | レスポンスが返る場合 |
| TCP切断 | 許容 | `ConnectionResetError` も合格 |

---

### テスト08: TLS 1.3 プロトコル検証

| 項目 | 内容 |
|------|------|
| テストID | `test_08_tls13_connection` |
| 対象API | — (プロトコル層) |
| 分類 | 構造検証 |
| JEPX仕様 | 接続技術書 TLS 1.3 |
| 目的 | MockServerがTLS 1.3で通信していることをプロトコルバージョンで検証する |

| 検証項目 | 期待値 |
|---------|-------|
| `ssl_object` | null以外 |
| `ssl_object.version()` | `"TLSv1.3"` |

---

### テスト09: 未知APIコードのエラー

| 項目 | 内容 |
|------|------|
| テストID | `test_09_unknown_api_code` |
| 対象API | `ZZZ9999` (存在しない) |
| 分類 | 異常系 |
| 目的 | ルーターが認識しないAPIコードに対して `STATUS=10` を返すか検証する |

**リクエスト:** MEMBER=`9999`, API=`ZZZ9999`

| 検証項目 | 期待値 | 備考 |
|---------|-------|------|
| ヘッダ STATUS | `"10"` | レスポンスが返る場合 |
| TCP切断 | 許容 | `ConnectionResetError` も合格 |

---

### テスト10: Keep-Alive後のSocket維持確認

| 項目 | 内容 |
|------|------|
| テストID | `test_10_sys1001_keep_alive_extends_socket` |
| 対象API | SYS1001 → DAH1002 |
| 分類 | 正常系 |
| 目的 | Keep-Alive後に同一Socket上で別APIが処理されることを証明する |

| ステップ | API | 検証項目 | 期待値 |
|---------|-----|---------|-------|
| 1 | SYS1001 | ヘッダ STATUS | `"00"` |
| 2 | DAH1002 | ヘッダ STATUS | `"00"` |
| | | ボディ `bids` キー | 存在すること |

---

### テスト11: DAH1030エイリアス

| 項目 | 内容 |
|------|------|
| テストID | `test_11_dah1030_alias` |
| 対象API | DAH1030 |
| 分類 | 正常系 |
| JEPX仕様 | 902 §2.9 |
| 目的 | DAH1030がDAH1004と同一ハンドラで処理され、約定情報が返ることを検証する |

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `bidResults[]` | 1件以上 |

---

### テスト12: ITN全量配信のJEPX仕様フィールド検証

| 項目 | 内容 |
|------|------|
| テストID | `test_12_itn_full_state_structure` |
| 対象API | ITN1001 |
| 分類 | 構造検証 |
| JEPX仕様 | 903 §4.1 板情報フィールド |
| 目的 | 全量配信の各要素がJEPX仕様に定義された必須フィールドを含むか検証する |

| 検証項目 | 期待値 |
|---------|-------|
| `notices[]` | 1件以上 |
| `notices[0].noticeTypeCd` | 存在すること |
| `notices[0].deliveryDate` | 存在すること |
| `notices[0].timeCd` | 存在すること |
| `notices[0].price` | 存在すること |
| `notices[0].volume` | 存在すること |

---

### テスト13: DAH1001 複数入札の一括送信

| 項目 | 内容 |
|------|------|
| テストID | `test_13_dah1001_multi_bid` |
| 対象API | DAH1001 → DAH1002 |
| 分類 | 正常系 |
| JEPX仕様 | 902 §2.1 (bidOffers配列) |
| 目的 | 1リクエストに3件の入札を含め、全件が登録されユニークなbidNoが採番されるか検証する |

**リクエスト:** 3件の入札（`deliveryDate: 2026-05-01`, `areaCd: 2`, `timeCd: 01/02/03`）

| 検証項目 | 期待値 | 備考 |
|---------|-------|------|
| ヘッダ STATUS | `"00"` | |
| ボディ `statusInfo` | `"3"` | 3件入札完了 |
| DAH1002照会の `bids[]` | ≧ 3件 | サーバー状態蓄積を許容 |
| ユニーク `bidNo` 数 | ≧ 3 | 重複なし |

---

### テスト14: レスポンスヘッダSIZE整合性

| 項目 | 内容 |
|------|------|
| テストID | `test_14_response_header_size_validation` |
| 対象API | SYS1001 |
| 分類 | 構造検証 |
| JEPX仕様 | 接続技術書 SIZE仕様 |
| 目的 | レスポンスパケットのヘッダSIZEと、STX〜ETX間の実Body長が一致することを検証する |

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダの `SIZE` 値 | STX〜ETX間のバイト数と完全一致 |

---

### テスト15: ITN全量配信の日付範囲検証

| 項目 | 内容 |
|------|------|
| テストID | `test_15_itn_full_state_date_range` |
| 対象API | ITN1001 |
| 分類 | 正常系 |
| JEPX仕様 | 903 §4.1（当日＋翌日） |
| 目的 | 全量配信のnoticesに含まれるdeliveryDateが有効範囲内であるか検証する |

| 検証項目 | 期待値 | 備考 |
|---------|-------|------|
| 全 `notices[].deliveryDate` | 昨日〜明後日の範囲内 | UTC/JST差を許容 |

---

### テスト16: ITN差分配信の日付有効性

| 項目 | 内容 |
|------|------|
| テストID | `test_16_itn_diff_delivery_date_valid` |
| 対象API | ITN1001 |
| 分類 | 正常系 |
| JEPX仕様 | 903 §4.1 |
| 目的 | エンジンからPushされる差分のdeliveryDateが有効範囲内であるか検証する |

| 検証項目 | 期待値 | 備考 |
|---------|-------|------|
| 全 `notices[].deliveryDate` | 昨日〜明後日の範囲内 | UTC/JST差を許容 |

---

### テスト17: DAH1003 存在しないbidNoの削除

| 項目 | 内容 |
|------|------|
| テストID | `test_17_dah1003_delete_nonexistent_bid` |
| 対象API | DAH1003 |
| 分類 | 異常系（ビジネスエラー） |
| JEPX仕様 | 902 §2.3 |
| 目的 | 実在しないbidNoの削除で、クラッシュせず0件削除として応答するか検証する |

**リクエスト:**

```json
{ "deliveryDate": "2026-01-01", "bidDels": [{ "bidNo": "0000000000" }] }
```

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `statusInfo` | `"0"` (0件削除) |

---

### テスト18: 空ボディリクエスト処理

| 項目 | 内容 |
|------|------|
| テストID | `test_18_empty_body_request` |
| 対象API | DAH1002 |
| 分類 | 正常系（境界値） |
| 目的 | 空JSON `{}` で照会してもサーバーがクラッシュせず、空の `bids[]` で応答するか検証する |

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `bids` | `list` 型であること |

---

### テスト19: DAH9001 翌日市場 清算照会

| 項目 | 内容 |
|------|------|
| テストID | `test_19_dah9001_settlement` |
| 対象API | DAH9001 |
| 分類 | 正常系 |
| JEPX仕様 | 902 §3.1 |
| 目的 | 清算照会がJEPX仕様準拠の `settlements[]` 配列を返すか検証する |

**リクエスト:**

```json
{ "fromDate": "2026-04-01" }
```

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `status` | `"200"` |
| `settlements[]` | 1件以上 |
| `settlements[0].settlementNo` | 存在すること |
| `settlements[0].settlementDate` | 存在すること |
| `settlements[0].title` | 存在すること |
| `settlements[0].totalAmount` | 存在すること |
| `settlements[0].items` | 存在すること（配列） |
| `settlements[0].pdf` | 存在すること（Base64文字列） |

---

### テスト20: ITD9001 時間前市場 清算照会

| 項目 | 内容 |
|------|------|
| テストID | `test_20_itd9001_settlement` |
| 対象API | ITD9001 |
| 分類 | 正常系 |
| JEPX仕様 | 903 §3.1 |
| 目的 | 清算照会がJEPX仕様準拠の `settlements[]` 配列を返すか検証する |

**リクエスト:**

```json
{ "fromDate": "2026-04-01" }
```

| 検証項目 | 期待値 |
|---------|-------|
| ヘッダ STATUS | `"00"` |
| ボディ `status` | `"200"` |
| `settlements[]` | 1件以上 |
| `settlements[0]` 必須キー | `settlementNo`, `settlementDate`, `title`, `totalAmount`, `items`, `pdf` がすべて存在 |

---

## 4. API別カバレッジマトリクス

| API | 正常系 | 異常系 | フォーマット検証 | テスト番号 |
|-----|-------|-------|---------------|----------|
| SYS1001 | ✅ | — | — | 01, 10 |
| DAH1001 | ✅ | — | — | 02, 05, 13 |
| DAH1002 | ✅ | — | — | 02, 05, 10, 13, 18 |
| DAH1003 | ✅ | ✅ | — | 05, 17 |
| DAH1004 | ✅ | — | — | 05 |
| DAH1030 | ✅ | — | — | 11 |
| DAH9001 | ✅ | — | — | 19 |
| ITD1001 | ✅ | — | — | 06 |
| ITD1002 | ✅ | — | — | 06 |
| ITD1003 | ✅ | — | — | 06 |
| ITD1004 | ✅ | — | — | 06 |
| ITD9001 | ✅ | — | — | 20 |
| ITN1001 | ✅ | — | ✅ | 04, 12, 15, 16 |
| MEMBER認証 | — | ✅ | — | 03 |
| SIZE検証 | — | ✅ | ✅ | 07, 14 |
| TLS 1.3 | — | — | ✅ | 08 |
| 未知API | — | ✅ | — | 09 |

---

## 5. テスト結果の読み方

```
test_01_sys1001_keep_alive (...) ... ok     ← 合格
test_03_invalid_member (...) ... FAIL       ← 不合格（アサーション失敗）
test_04_itn1001_stream (...) ... ERROR      ← エラー（例外発生）
----------------------------------------------------------------------
Ran 20 tests in 16.696s
OK                                          ← 全テスト合格
```

- **ok**: 全アサーションが合格
- **FAIL**: アサーション検証の失敗（期待値と実際値の不一致）
- **ERROR**: テスト中に予期しない例外が発生
- **skipped**: 前提条件を満たさずスキップ（MockServer未起動時）
