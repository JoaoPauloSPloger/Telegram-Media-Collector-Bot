# Telegram Media Collector Bot
# Copyright (C) 2026 Vulpes Tech
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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

# Copy backup of database if it exists
RUN if [ -f database/bot_database.db ]; then cp database/bot_database.db /app/bot_database_backup.db; fi

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh

# Run the bot via entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "src.main"]
