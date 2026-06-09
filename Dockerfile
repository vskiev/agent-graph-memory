FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir "mcp[cli]" surrealdb uvicorn watchdog

COPY . .

# Default: SSE mode so both Claude and Gemini can connect via HTTP
# Override with MCP_TRANSPORT=stdio for docker exec usage
ENV MCP_TRANSPORT=sse
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=3333
ENV SURREALDB_URL=ws://surrealdb:8000/rpc
ENV SURREALDB_USER=root
ENV SURREALDB_PASS=root_password
ENV SURREALDB_NS=project
ENV SURREALDB_DB=main

CMD ["python3", "mcp_server.py"]
