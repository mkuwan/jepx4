import asyncio
from core.protocol import build_response
from core.itn_engine import itn_engine

async def stream_itn1001(writer: asyncio.StreamWriter):
    """
    ITN1001: 時間前市場 市場情報通知
    JEPX仕様に基づき、接続直後に中央エンジンから「全量配信」を行い、
    その後、中央エンジンからPushされる「差分配信」を継続して送信します。
    """
    peername = writer.get_extra_info('peername')
    queue = None
    
    try:
        print(f"[ITN Stream] {peername} - 接続確立: 「全量配信」を開始します...")
        
        # 1. 接続直後: 中央エンジンから現在の全体状態(Full State)を取得して送信
        full_data = itn_engine.get_full_state()
        
        packet = build_response(status="00", body_dict=full_data)
        writer.write(packet)
        await writer.drain()
        print(f"[ITN Stream] {peername} - 「全量配信」完了。")
        
        # 2. 中央エンジンに購読(Subscribe)登録し、Queueを取得
        queue = itn_engine.subscribe()
        print(f"[ITN Stream] {peername} - 中央エンジンの「差分配信」を購読開始します。")
        
        # 3. キューからPushされる差分データを待ち受ける無限ループ
        while True:
            # エンジン側からデータがPushされるまで待機
            diff_data = await queue.get()
            
            # クライアントへ送信
            packet = build_response(status="00", body_dict=diff_data)
            writer.write(packet)
            await writer.drain()
            
            queue.task_done()
            print(f"[ITN Stream] {peername} - 「差分配信」送信完了。")
            
    except ConnectionResetError:
        print(f"[ITN Stream] {peername} - クライアントが切断しました (Connection Reset)")
    except Exception as e:
        print(f"[ITN Stream Error] {peername} - {e}")
    finally:
        # 4. 切断時は購読解除(Unsubscribe)する
        if queue:
            itn_engine.unsubscribe(queue)
