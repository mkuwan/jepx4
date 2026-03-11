Attribute VB_Name = "JepxApiRequest"
' -------------------------------------------------------------------------
' JEPX API連携システム - Web API リクエストモジュール (VBA)
' -------------------------------------------------------------------------

Option Explicit

' 共通設定：Django Web APIのベースURL (環境に合わせて変更してください)
Private Const BASE_URL As String = "http://localhost:8000"

'
' HTTPリクエスト送信 共通関数
'
Private Function SendHttpRequest(ByVal method As String, ByVal endpoint As String, Optional ByVal payload As String = "") As String
    Dim xmlHttp As Object
    Dim url As String
    
    ' MSXML2.XMLHTTP を遅延バインディングで生成
    Set xmlHttp = CreateObject("MSXML2.XMLHTTP")
    url = BASE_URL & endpoint
    
    On Error GoTo ErrorHandler
    
    xmlHttp.Open method, url, False ' 同期通信
    xmlHttp.setRequestHeader "Content-Type", "application/json"
    
    ' JWTトークン等が必要になった場合はここに追加します
    ' xmlHttp.setRequestHeader "Authorization", "Bearer xxxxx"
    
    If payload <> "" Then
        xmlHttp.send payload
    Else
        xmlHttp.send
    End If
    
    ' 実行結果をイミディエイトウィンドウに出力
    Debug.Print "--- [" & method & "] " & endpoint & " ---"
    Debug.Print "Status: " & xmlHttp.Status & " " & xmlHttp.statusText
    Debug.Print "Body: " & xmlHttp.responseText
    
    SendHttpRequest = xmlHttp.responseText
    Set xmlHttp = Nothing
    Exit Function

ErrorHandler:
    Debug.Print "通信エラー発生: " & Err.Description
    SendHttpRequest = "{""error"": ""通信・システムエラー""}"
    Set xmlHttp = Nothing
End Function


' =========================================================================
' 1. ITD入札 (ITD1001) - POST
' シートからデータを取得したと仮定して、複数件の入札をループで1件ずつ送信するパターン
' =========================================================================
Public Sub Call_ItdBid()
    ' ダミーのシートデータ（本来は ActiveSheet.Range("A2:H10") 等を配列に読み込みます）
    ' ここでは二次元配列として3件の入札データを用意します。
    Dim bidData(1 To 3, 1 To 7) As String
    
    ' [1件目]
    bidData(1, 1) = "2026-03-12"  ' deliveryDate
    bidData(1, 2) = "15"          ' timeCd
    bidData(1, 3) = "03"          ' areaCd
    bidData(1, 4) = "BUY-LIMIT"   ' bidTypeCd (買い指値)
    bidData(1, 5) = "15.50"       ' price
    bidData(1, 6) = "100.0"       ' volume
    bidData(1, 7) = "01"          ' deliveryContractCd
    
    ' [2件目]
    bidData(2, 1) = "2026-03-12"
    bidData(2, 2) = "16"
    bidData(2, 3) = "03"
    bidData(2, 4) = "SELL-LIMIT"  ' 売り指値
    bidData(2, 5) = "16.80"
    bidData(2, 6) = "50.0"
    bidData(2, 7) = "01"
    
    ' [3件目] (備考のみ追加)
    bidData(3, 1) = "2026-03-13"
    bidData(3, 2) = "01"
    bidData(3, 3) = "01"
    bidData(3, 4) = "BUY-MARKET"  ' 買い成行
    bidData(3, 5) = "0"           ' 成行は価格0または不要
    bidData(3, 6) = "200.0"
    bidData(3, 7) = "01"

    Dim i As Integer
    Dim jsonPayload As String
    Dim deliveryDate As String, timeCd As String, areaCd As String
    Dim bidTypeCd As String, price As String, volume As String, contractCd As String
    
    ' 複数件データに対するループ処理
    For i = LBound(bidData, 1) To UBound(bidData, 1)
        deliveryDate = bidData(i, 1)
        timeCd = bidData(i, 2)
        areaCd = bidData(i, 3)
        bidTypeCd = bidData(i, 4)
        price = bidData(i, 5)
        volume = bidData(i, 6)
        contractCd = bidData(i, 7)
        
        ' JSON文字列の組み立て（1件ずつ送信仕様）
        ' 注意: 日本語(全角)を含める場合、MSXML2では文字化けする可能性があるため、本例ではASCIIのみを使用しています。
        jsonPayload = "{" & _
            """deliveryDate"": """ & deliveryDate & """, " & _
            """timeCd"": """ & timeCd & """, " & _
            """areaCd"": """ & areaCd & """, " & _
            """bidTypeCd"": """ & bidTypeCd & """, " & _
            """price"": " & price & ", " & _
            """volume"": " & volume & ", " & _
            """deliveryContractCd"": """ & contractCd & """, " & _
            """note"": ""Bid-" & i & """" & _
        "}"
        
        Debug.Print ">>> No." & i & " の入札を実行中..."
        Call SendHttpRequest("POST", "/api/v1/itd/bid", jsonPayload)
    Next i
    
    Debug.Print "<<< 複数件の入札処理が完了しました。"
End Sub


' =========================================================================
' 2. ITD入札削除 (ITD1002) - POST
' =========================================================================
Public Sub Call_ItdDelete()
    ' ダミーデータの取得
    Dim deliveryDate As String: deliveryDate = "2026-03-12"
    Dim timeCd As String: timeCd = "15"
    Dim targetBidNo As String: targetBidNo = "ITD_9999999"
    
    Dim jsonPayload As String
    jsonPayload = "{" & _
        """deliveryDate"": """ & deliveryDate & """, " & _
        """timeCd"": """ & timeCd & """, " & _
        """bidNo"": """ & targetBidNo & """" & _
    "}"
    
    Call SendHttpRequest("POST", "/api/v1/itd/delete", jsonPayload)
End Sub


' =========================================================================
' 3. ITD入札照会 (ITD1003) - GET
' GETリクエストはパラメータをURLクエリ文字列として付与するパターン
' =========================================================================
Public Sub Call_ItdInquiry()
    ' ダミーデータの取得
    Dim deliveryDate As String: deliveryDate = "2026-03-12"
    Dim timeCd As String: timeCd = "15"
    
    Dim endpoint As String
    endpoint = "/api/v1/itd/inquiry?deliveryDate=" & deliveryDate & "&timeCd=" & timeCd
    
    Call SendHttpRequest("GET", endpoint)
End Sub


' =========================================================================
' 4. ITD約定照会 (ITD1004) - GET
' =========================================================================
Public Sub Call_ItdContract()
    ' ダミーデータの取得
    Dim deliveryDate As String: deliveryDate = "2026-03-12"
    
    Dim endpoint As String
    endpoint = "/api/v1/itd/contract?deliveryDate=" & deliveryDate
    
    Call SendHttpRequest("GET", endpoint)
End Sub


' =========================================================================
' 5. ITD清算照会 (ITD9001) - GET
' 2つの検索条件日付を付与するパターン
' =========================================================================
Public Sub Call_ItdSettlement()
    ' ダミーデータの取得
    Dim fromDate As String: fromDate = "2026-03-01"
    Dim toDate As String: toDate = "2026-03-31"
    
    Dim endpoint As String
    endpoint = "/api/v1/itd/settlement?fromDate=" & fromDate & "&toDate=" & toDate
    
    Call SendHttpRequest("GET", endpoint)
End Sub


' =========================================================================
' API疎通 全件一括テスト用
' =========================================================================
Public Sub RunAllApiTests()
    Debug.Print "=== 1. 入札テスト (/api/v1/itd/bid) ==="
    Call_ItdBid
    
    Debug.Print "=== 2. 取消テスト (/api/v1/itd/delete) ==="
    Call_ItdDelete
    
    Debug.Print "=== 3. 照会テスト (/api/v1/itd/inquiry) ==="
    Call_ItdInquiry
    
    Debug.Print "=== 4. 約定照会テスト (/api/v1/itd/contract) ==="
    Call_ItdContract
    
    Debug.Print "=== 5. 清算照会テスト (/api/v1/itd/settlement) ==="
    Call_ItdSettlement
    
    MsgBox "API呼び出しテストが完了しました。VBEの「イミディエイト ウィンドウ(Ctrl+G)」で結果を確認してください。", vbInformation
End Sub
