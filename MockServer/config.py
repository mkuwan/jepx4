import os

# Server configuration
HOST = os.environ.get("MOCK_HOST", "0.0.0.0")
PORT = int(os.environ.get("MOCK_PORT", 8888))

# TLS Certificate paths
CERT_FILE = os.environ.get("MOCK_CERT_FILE", "certs/server.crt")
KEY_FILE = os.environ.get("MOCK_KEY_FILE", "certs/server.key")

# Idle timeout (seconds) before server closes the connection (JEPX spec: 3 minutes)
# Set shorter for testing if needed
IDLE_TIMEOUT_SEC = int(os.environ.get("MOCK_IDLE_TIMEOUT_SEC", 180))

# ITN Stream push interval (seconds)
ITN_PUSH_INTERVAL_SEC = int(os.environ.get("MOCK_ITN_PUSH_INTERVAL_SEC", 10))

# Allowed MEMBER IDs (for auth mock)
ALLOWED_MEMBERS = ["9999", "0841"]
