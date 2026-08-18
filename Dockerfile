FROM python:3.11-slim

WORKDIR /app

# System dependencies (ffmpeg for audio conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create runtime directories
RUN mkdir -p data downloads plugins

# Non-root user for security
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

# Run bot
CMD ["python", "bot.py"]
