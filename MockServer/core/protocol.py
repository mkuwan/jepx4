import zlib
import json

SOH = b'\x01'
STX = b'\x02'
ETX = b'\x03'

class ProtocolError(Exception):
    def __init__(self, message, status_code="10"):
        super().__init__(message)
        self.status_code = status_code

def parse_request(data: bytes):
    """
    Parses a raw JEPX TCP packet.
    Format: SOH + Header(MEMBER=...,API=...,SIZE=...) + STX + Body(gzip JSON) + ETX
    
    Returns:
        tuple: (header_dict, body_dict)
    """
    if not data:
        raise ProtocolError("Empty data received")

    # Find delimiters
    soh_idx = data.find(SOH)
    stx_idx = data.find(STX)
    etx_idx = data.rfind(ETX)

    if soh_idx == -1 or stx_idx == -1 or etx_idx == -1:
        raise ProtocolError("Missing framing characters (SOH/STX/ETX)")
        
    if not (soh_idx < stx_idx < etx_idx):
        raise ProtocolError("Invalid framing characters order")

    # 1. Parse Header
    header_bytes = data[soh_idx + 1:stx_idx]
    try:
        header_str = header_bytes.decode('ascii')
    except UnicodeDecodeError:
        raise ProtocolError("Header is not valid ASCII")

    header_dict = {}
    for pair in header_str.split(','):
        if '=' in pair:
            k, v = pair.split('=', 1)
            header_dict[k.strip()] = v.strip()
            
    if 'API' not in header_dict or 'SIZE' not in header_dict or 'MEMBER' not in header_dict:
        raise ProtocolError("Missing required header fields (API, SIZE, MEMBER)")

    # 2. Check SIZE
    try:
        expected_size = int(header_dict['SIZE'])
    except ValueError:
        raise ProtocolError("SIZE header is not an integer")

    body_bytes = data[stx_idx + 1:etx_idx]
    if len(body_bytes) != expected_size:
        raise ProtocolError(f"Body size mismatch. Expected {expected_size}, got {len(body_bytes)}")

    # 3. Decompress and parse JSON Body
    try:
        decompressed = zlib.decompress(body_bytes)
        body_dict = json.loads(decompressed.decode('utf-8')) if decompressed else {}
    except zlib.error:
        raise ProtocolError("Failed to decompress body (zlib error)")
    except json.JSONDecodeError:
        raise ProtocolError("Failed to parse JSON body")

    return header_dict, body_dict


def build_response(status: str, body_dict: dict = None) -> bytes:
    """
    Builds a JEPX TCP response packet.
    Format: SOH + Header(STATUS=...,SIZE=...) + STX + Body(gzip JSON) + ETX
    """
    if body_dict is None:
        body_dict = {}
        
    # Compress body
    json_bytes = json.dumps(body_dict).encode('utf-8')
    compressed_body = zlib.compress(json_bytes)
    
    body_size = len(compressed_body)
    
    # Build header
    header_str = f"STATUS={status},SIZE={body_size}"
    header_bytes = header_str.encode('ascii')
    
    # Assemble packet
    packet = SOH + header_bytes + STX + compressed_body + ETX
    return packet
