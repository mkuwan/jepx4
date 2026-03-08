import socket
import threading
import sys
import time
import logging
import ssl
import os
import subprocess
from protocol import read_message, encode_response, ProtocolError
from handlers import handle_request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

HOST = "0.0.0.0"
PORT = 8888

def recv_all(sock, n):
    """Helper to receive exactly n bytes."""
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)

def handle_client(conn, addr):
    logger.info(f"Connected by {addr}")
    try:
        while True:
            # Create a reader wrapper for protocol.read_message
            def reader_func(n):
                return recv_all(conn, n)

            header, body = read_message(reader_func)
            if header is None:
                logger.info(f"Connection closed by {addr}")
                break

            api_code = header.get("API")
            logger.info(f"Received API: {api_code} from {addr}")
            
            if not api_code:
                logger.error("Missing API code in header")
                continue

            if api_code == "ITN1001":
                logger.info(f"Starting ITN1001 stream for {addr} with 5 second interval.")
                # Send the initial response immediately, then loop
                is_first = True
                while True:
                    response_body = handle_request(api_code, body, is_initial=is_first)
                    response_bytes = encode_response(api_code, response_body)
                    conn.sendall(response_bytes)
                    logger.info(f"Sent ITN1001 stream notification to {addr} (initial={is_first})")
                    is_first = False
                    time.sleep(5)
            else:
                # Process request
                response_body = handle_request(api_code, body)
                
                # Encode response
                response_bytes = encode_response(api_code, response_body)
                conn.sendall(response_bytes)
                logger.info(f"Sent response for {api_code}")

    except ProtocolError as e:
        logger.error(f"Protocol Error: {e}")
    except ConnectionError as e:
        logger.info(f"Client {addr} disconnected (Connection closed: {e})")
    except Exception as e:
        logger.error(f"Error handling client {addr}: {type(e).__name__} - {e}")
    finally:
        conn.close()
        logger.info(f"Connection closed for {addr}")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, PORT))
        except OSError as e:
            logger.error(f"Failed to bind to port {PORT}: {e}")
            sys.exit(1)
            
        s.listen()
        logger.info(f"JEPX Mock Server listening on {HOST}:{PORT}")
        
        # Generate certs dynamically if not existing
        if not os.path.exists("cert.pem") or not os.path.exists("key.pem"):
            logger.info("Generating self-signed TLS certificates at runtime...")
            subprocess.run([
                "openssl", "req", "-new", "-newkey", "rsa:2048", "-days", "365", 
                "-nodes", "-x509", "-keyout", "key.pem", "-out", "cert.pem", 
                "-subj", "/CN=mockserver"
            ], check=True)
            
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        
        try:
            while True:
                conn, addr = s.accept()
                try:
                    ssl_conn = context.wrap_socket(conn, server_side=True)
                    thread = threading.Thread(target=handle_client, args=(ssl_conn, addr))
                    thread.daemon = True
                    thread.start()
                except ssl.SSLError as e:
                    logger.error(f"SSL Handshake Failed for {addr}: {e}")
                    conn.close()
        except KeyboardInterrupt:
            logger.info("Server stopping...")

if __name__ == "__main__":
    main()
