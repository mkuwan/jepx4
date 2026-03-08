"""ITN受信バックグラウンドタスク (§5.4 / §5.5)

ASGI起動時に開始され、JEPX ITN1001ストリームを受信し続ける。
配信データは ItnMemoryStore に反映する。
"""
import asyncio
import logging

from django.conf import settings

from apps.jepx_client.client import JepxApiClient
from .store import ItnMemoryStore

logger = logging.getLogger('jepx.api')
audit_logger = logging.getLogger('jepx.audit')


async def itn_receiver_loop(store: ItnMemoryStore) -> None:
    """ITN1001ストリームを受信し続けるメインループ。

    接続切断時は5秒後に再接続する。
    """
    client = JepxApiClient()

    while True:
        try:
            store.set_connection_status(connected=False, error=None)
            audit_logger.info("[ITN] ITN1001 ストリーム接続開始...")

            is_first = True
            async for header, body in client.start_stream('ITN1001', {}):
                notices = body.get('notices', [])

                if is_first:
                    # 全量配信
                    store.set_full_state(notices)
                    store.set_connection_status(connected=True)
                    audit_logger.info(
                        "[ITN] 全量配信受信: %d件", len(notices)
                    )
                    is_first = False
                else:
                    # 差分配信
                    store.update_notices(notices)
                    logger.debug(
                        "[ITN] 差分配信受信: %d件, version=%d",
                        len(notices), store.get_version(),
                    )

        except Exception as e:
            error_msg = str(e)
            store.set_connection_status(connected=False, error=error_msg)
            logger.warning("[ITN] ストリーム切断: %s (5秒後に再接続)", error_msg)
            await asyncio.sleep(5)
