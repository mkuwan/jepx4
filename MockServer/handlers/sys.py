def handle_sys1001(body: dict) -> dict:
    """
    SYS1001: ソケット接続時間延長 (Keep-Alive)
    """
    return {
        "status": "200",
        "statusInfo": "Socket Expiration Time Extension"
    }
