FROM python:3.12-slim

RUN pip install uv

# Install openapi-mcp-server
RUN uv pip install --system openapi-mcp-server

# Copy OpenAPI spec
COPY coverageapi.json /app/coverageapi.json

WORKDIR /app

# Run in HTTP mode (exposes FastAPI on port 8000)
CMD ["uv", "run", "openapi_mcp_server", "--spec-path", "/app/coverageapi.json", "--api-url", "https://api.cms.gov/mcd", "--http"]