# JEPX Mock Server

This is a mock implementation of the JEPX (Japan Electric Power Exchange) API server for testing purposes.
It simulates the JEPX dedicated line connection protocol (TCP/IP socket with custom framing).

## Features

- Implements the JEPX communication protocol: `SOH + Header + STX + Body(Gzipped JSON) + ETX`.
- Supports key APIs for Day Ahead (Spot) and Intraday markets.
- Runs in a Docker container.
- Includes a standard `unittest` suite for validation.

## Project Structure

- `src/main.py`: The TCP server entry point.
- `src/protocol.py`: Handles the low-level protocol parsing (SOH/STX/ETX framer, gzip compression).
- `src/handlers.py`: Contains the mock logic for various API endpoints (e.g., `DAH1001`, `ITD1001`).
- `Dockerfile`: Docker image definition.
- `docker-compose.yml`: Docker Compose configuration.
- `tests/test_server.py`: Unit tests for the server.

## How to Run

1.  **Start the server:**
    ```bash
    docker-compose up --build
    ```
    The server will listen on port **8888**.

2.  **Run Tests:**
    You can run the provided unit tests to verify the server is working correctly.
    Make sure the server is running first.

    ```bash
    # Run from the project root or MockServer directory
    python -m unittest tests/test_server.py
    ```

## Supported APIs

| API Code | Description | Mock Behavior |
| :--- | :--- | :--- |
| **DAH1001** | Day Ahead Bid Submission | Returns success with bid count. |
| **DAH1002** | Day Ahead Bid Inquiry | Returns dummy bid data. |
| **DAH1003** | Day Ahead Bid Deletion | Returns success. |
| **DAH1004** | Day Ahead Contract Inquiry | Returns dummy contract results. |
| **ITD1001** | Intraday Bid Submission | Returns success. |
| **ITD1003** | Intraday Bid Inquiry | Returns dummy intraday bids. |
| **SYS1001** | Keep Alive | Returns success. |

## Modifying Data

To change the mock data, edit `src/handlers.py`.
