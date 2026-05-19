#!/bin/bash
set -e

# Change ownership of mounted volumes
chown -R botuser:botuser /app/database
chown -R botuser:botuser /app/downloads

# Drop privileges and execute the main command
exec gosu botuser "$@"
