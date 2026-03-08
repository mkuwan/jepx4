import asyncio
from typing import Tuple, Dict, Any, Optional

from config import ALLOWED_MEMBERS
from core.protocol import ProtocolError, build_response
import handlers.dah as dah
import handlers.itd as itd
import handlers.sys as sys
from handlers.itn import stream_itn1001

class Router:
    @staticmethod
    async def dispatch(header: Dict[str, str], body: Dict[str, Any], writer: asyncio.StreamWriter) -> Tuple[bool, Optional[bytes]]:
        """
        Dispatches the API request to the appropriate handler based on the header.
        
        Returns:
            Tuple[bool, Optional[bytes]]: (Keep Socket Open?, Response Packet if any)
        """
        # 1. Authority Check
        member = header.get("MEMBER", "")
        if member not in ALLOWED_MEMBERS:
            raise ProtocolError(f"Unauthorized MEMBER: {member}", status_code="11")
        
        # 2. API Routing
        api_code = header.get("API", "")
        response_dict = {}
        keep_open = True
        
        # DAH Handlers (Spot Market)
        if api_code == "DAH1001":
            response_dict = dah.handle_dah1001(body)
        elif api_code == "DAH1002":
            response_dict = dah.handle_dah1002(body)
        elif api_code == "DAH1003":
            response_dict = dah.handle_dah1003(body)
        elif api_code == "DAH1004" or api_code == "DAH1030":
            response_dict = dah.handle_dah1004(body)
        elif api_code == "DAH9001":
            response_dict = dah.handle_dah9001(body)
            
        # ITD Handlers (Intraday Market)
        elif api_code == "ITD1001":
            response_dict = itd.handle_itd1001(body)
        elif api_code == "ITD1002":
            response_dict = itd.handle_itd1002(body)
        elif api_code == "ITD1003":
            response_dict = itd.handle_itd1003(body)
        elif api_code == "ITD1004":
            response_dict = itd.handle_itd1004(body)
        elif api_code == "ITD9001":
            response_dict = itd.handle_itd9001(body)
            
        # ITN Handler (Intraday Streaming)
        elif api_code == "ITN1001":
            # Start background streaming task on this socket
            asyncio.create_task(stream_itn1001(writer))
            # Tell server NOT to close this, and we don't return an immediate single packet here
            return True, None
            
        # SYS Handlers (Keep-Alive)
        elif api_code == "SYS1001":
            response_dict = sys.handle_sys1001(body)
            
        else:
            print(f"Unknown API code requested: {api_code}")
            # Unknown API defaults to Format Error as a catch-all in this mock
            raise ProtocolError(f"Unknown API: {api_code}", status_code="10")
        
        # Build standard success response packet
        packet = build_response(status="00", body_dict=response_dict)
        return keep_open, packet
