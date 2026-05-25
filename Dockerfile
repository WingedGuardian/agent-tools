FROM python:3.12-slim

WORKDIR /app

# Install system deps for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[all]"

# Run as non-root — port 8000 is unprivileged, no root needed inside container
RUN useradd --system --no-create-home app
USER app

EXPOSE 8000

CMD ["uvicorn", "agent_tools.app:app", "--host", "0.0.0.0", "--port", "8000"]
