#!/bin/bash
# Convert SQLite dump to PostgreSQL-compatible SQL

set -e

INPUT_FILE="$1"
OUTPUT_FILE="$2"

if [ -z "$INPUT_FILE" ] || [ -z "$OUTPUT_FILE" ]; then
    echo "Usage: $0 <input_sqlite_dump.sql> <output_postgres.sql>"
    exit 1
fi

echo "Converting SQLite dump to PostgreSQL format..."

# Create output file with PostgreSQL compatibility fixes
cat "$INPUT_FILE" | \
    # Remove SQLite-specific pragmas
    grep -v "^PRAGMA" | \
    # Remove SQLite-specific commands
    grep -v "^BEGIN TRANSACTION;" | \
    grep -v "^COMMIT;" | \
    # Convert AUTOINCREMENT to SERIAL (handle both upper and lower case)
    sed 's/INTEGER PRIMARY KEY AUTOINCREMENT/SERIAL PRIMARY KEY/gi' | \
    sed 's/INTEGER PRIMARY KEY/SERIAL PRIMARY KEY/gi' | \
    # Remove SQLite CREATE TABLE syntax that's not compatible
    sed 's/IF NOT EXISTS//g' | \
    # Convert SQLite's strftime to PostgreSQL's NOW()
    sed "s/datetime('now')/NOW()/g" | \
    sed "s/DATETIME('now')/NOW()/g" | \
    # Convert REAL to DOUBLE PRECISION
    sed 's/\bREAL\b/DOUBLE PRECISION/g' | \
    # Convert single quotes to double quotes for identifiers if needed
    sed 's/`/"/g' \
    > "$OUTPUT_FILE"

echo "Conversion complete: $OUTPUT_FILE"
echo "Lines: $(wc -l < "$OUTPUT_FILE")"
