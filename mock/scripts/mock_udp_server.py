# The mock HTTP server has moved to mock/server/.
# Run it with Docker:
#
#   cd mock/server
#   docker compose up
#
# Or directly (requires: pip install fastapi uvicorn pillow):
#
#   uvicorn mock.server.server:app --host 0.0.0.0 --port 8080
#
# Then point udp_clients[].base_url in config_window1.json to http://localhost:8080
