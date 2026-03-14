import asyncio
import ssl
import time
from typing import Dict

from config import HOST, PORT, CERT_FILE, KEY_FILE, IDLE_TIMEOUT_SEC
from core.protocol import parse_request, build_response, ProtocolError
from core.router import Router
from core.itn_engine import itn_engine

# Shared state to track idle sockets
active_connections: Dict[asyncio.StreamWriter, float] = {}

# Streaming connections (ITN配信) — JEPX仕様§2.3: 配信通信は無通信でも切断しない
streaming_connections: set[asyncio.StreamWriter] = set()

async def connection_timeout_monitor():
    """Background task to drop connections idle for longer than IDLE_TIMEOUT_SEC"""
    while True:
        now = time.time()
        stale_writers = []
        
        for writer, last_active in list(active_connections.items()):
            # JEPX仕様§2.3: 配信通信(ITN)は無通信でも切断しない → タイムアウト対象外
            if writer in streaming_connections:
                continue
            if now - last_active > IDLE_TIMEOUT_SEC:
                stale_writers.append(writer)
                
        for writer in stale_writers:
            peer = writer.get_extra_info('peername')
            print(f"[Timeout Monitor] Connection idle timeout reached for {peer}. Closing.")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            finally:
                 if writer in active_connections:
                     del active_connections[writer]
                     
        await asyncio.sleep(10) # Check every 10 seconds

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peername = writer.get_extra_info('peername')
    print(f"\n[+] Accepted connection from {peername}")
    
    # Register connection for timeout monitoring
    active_connections[writer] = time.time()
    
    try:
        while True:
            # Sockets can receive arbitrarily chunked streams. In the JEPX protocol, ETX marks the end.
            # For this mock, we'll read larger chunks since the client should send atomic packets.
            data = await reader.read(65536)
            
            if not data:
                print(f"[-] Connection closed by peer {peername}")
                break
                
            # Update last active time for SYS1001 Keep-Alive checks
            active_connections[writer] = time.time()
            
            print(f"--> Received {len(data)} bytes from {peername}")
            
            try:
                # 1. Parsing
                header, body_dict = parse_request(data)
                api = header.get('API', 'Unknown')
                print(f"    Dispatching {api}...")
                
                # 2. Routing (Error injection points could be inserted here)
                keep_open, response_packet, is_streaming = await Router.dispatch(header, body_dict, writer)

                # JEPX仕様§2.3: 配信通信(ITN)はアイドルタイムアウトの対象外として登録する
                if is_streaming:
                    streaming_connections.add(writer)

                # 3. Respond
                if response_packet:
                    writer.write(response_packet)
                    await writer.drain()
                    print(f"<-- Sent {len(response_packet)} bytes response to {peername}")
                    
                if not keep_open:
                    break
                    
            except ProtocolError as pe:
                print(f"[X] Protocol Error: {pe}")
                error_packet = build_response(status=pe.status_code, body_dict={"error": str(pe)})
                writer.write(error_packet)
                await writer.drain()
                break # On severe protocol errors, JEPX drops connection
                
            except Exception as e:
                print(f"[X] Internal Server Error: {e}")
                err_packet = build_response(status="19", body_dict={"error": "Internal MockServer Error"})
                writer.write(err_packet)
                await writer.drain()
                break
                
    except asyncio.CancelledError:
        pass
    except ConnectionResetError:
        print(f"[-] Peer {peername} reset the connection")
    except Exception as e:
        print(f"[-] Unexpected error with {peername}: {e}")
    finally:
        print(f"[*] Cleaning up connection for {peername}")
        active_connections.pop(writer, None)
        streaming_connections.discard(writer)
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass

async def start_server():
    print("Initializing MockServer...")
    
    # Configure TLS Context
    # Note: JEPX requires TLS 1.3
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
    
    server = await asyncio.start_server(
        handle_client, 
        HOST, 
        PORT, 
        ssl=ssl_context
    )

    addresses = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f"Ready. Listening on {addresses} with TLS 1.3")
    
    # Start background tasks
    asyncio.create_task(connection_timeout_monitor())
    asyncio.create_task(itn_engine.run_engine())

    async with server:
        await server.serve_forever()

