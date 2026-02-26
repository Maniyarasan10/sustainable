# Sustainable Community API (CivicSense) — Backend
# Python 3.11 slim for smaller image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system deps if needed (e.g. for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Run with uvicorn (bind to 0.0.0.0 for Docker)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
