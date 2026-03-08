import gzip
import json

SOH = b'\x01'
STX = b'\x02'
ETX = b'\x03'

class ProtocolError(Exception):
    pass

def read_message(reader_func):
    """
    Reads a message using a reader function that returns bytes.
    reader_func(n) should return n bytes.
    Returns (header_dict, body_json).
    """
    # 1. Read SOH (1 byte)
    soh = reader_func(1)
    if not soh:
        return None, None # Connection closed
    if soh != SOH:
        raise ProtocolError(f"Expected SOH (0x01), got {soh}")

    # 2. Read Header until STX
    header_bytes = bytearray()
    while True:
        b = reader_func(1)
        if not b:
             raise ProtocolError("Connection closed while reading header")
        if b == STX:
            break
        header_bytes.extend(b)
    
    header_str = header_bytes.decode('ascii')
    header_dict = {}
    for part in header_str.split(','):
        if '=' in part:
            k, v = part.split('=', 1)
            header_dict[k.strip()] = v.strip()
    
    # 3. Read Body based on SIZE
    try:
        size = int(header_dict.get("SIZE", 0))
    except ValueError:
        raise ProtocolError("Invalid SIZE in header")
    
    body_data = reader_func(size)
    if body_data is None or len(body_data) != size:
         raise ProtocolError(f"Incomplete body. Expected {size}, got {len(body_data) if body_data else 0}")

    # 4. Read ETX
    etx = reader_func(1)
    if not etx or etx != ETX:
         raise ProtocolError(f"Expected ETX (0x03), got {etx}")

    # 5. Decompress and parse
    body_json = decode_body(body_data)
    
    return header_dict, body_json

def encode_response(api_code, body_dict, status="00"):
    """
    Encodes a response message.
    Returns bytes ready to send.
    """
    body_json = json.dumps(body_dict).encode('utf-8')
    compressed_body = gzip.compress(body_json)
    size = len(compressed_body)
    
    # Response header: STATUS=XX,SIZE=YY
    header_str = f"STATUS={status},SIZE={size}"
    header_bytes = header_str.encode('ascii')
    
    return SOH + header_bytes + STX + compressed_body + ETX

def decode_body(compressed_body):
    try:
        json_bytes = gzip.decompress(compressed_body)
        return json.loads(json_bytes)
    except Exception as e:
        raise ProtocolError(f"Failed to decompress or parse body: {e}")

def parse_header(header_bytes):
    header_str = header_bytes.decode('ascii')
    parts = header_str.split(',')
    header_dict = {}
    for part in parts:
        if '=' in part:
            k, v = part.split('=', 1)
            header_dict[k.strip()] = v.strip()
    return header_dict
