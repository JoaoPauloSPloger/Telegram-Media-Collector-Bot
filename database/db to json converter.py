import sqlite3
import json

def export_db_to_json(db_file_path: str, output_json_path: str):
    """Extracts an entire SQLite database into a structured JSON file."""
    
    # Connect and set row_factory to access columns by name
    conn = sqlite3.connect(db_file_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query the master table to find all existing tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row['name'] for row in cursor.fetchall()]

    database_dump = {}

    # Iterate through each table and fetch all rows
    for table in tables:
        # Skip internal SQLite metadata tables
        if table.startswith('sqlite_'):
            continue
            
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        
        # Convert rows to dictionaries and assign to the table key
        database_dump[table] = [dict(row) for row in rows]

    # Write the complete dictionary to a JSON file
    with open(output_json_path, 'w', encoding='utf-8') as json_file:
        json.dump(database_dump, json_file, indent=4, ensure_ascii=False)

    conn.close()
    print(f"✅ Successfully exported '{db_file_path}' to '{output_json_path}'")

# Execution
export_db_to_json('bot_database.db', 'database_export.json')