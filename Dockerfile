FROM python:3.11-slim

# Install ffmpeg and gosu, then clean up
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gosu && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create a non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create directories
RUN mkdir -p downloads database

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh

# Run the bot via entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "src.main"]
