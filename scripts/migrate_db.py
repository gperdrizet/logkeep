#!/usr/bin/env python3
"""
Migrate SQLite database to PostgreSQL
"""
import sqlite3
import psycopg2
import sys

def migrate_database(sqlite_db_path, pg_host, pg_port, pg_user, pg_password, pg_db):
    """Migrate data from SQLite to PostgreSQL"""
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()
    
    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(
        host=pg_host,
        port=pg_port,
        user=pg_user,
        password=pg_password,
        database=pg_db
    )
    pg_cur = pg_conn.cursor()
    
    # Order matters due to foreign keys
    tables = ['users', 'tags', 'invites', 'links', 'link_tags']
    
    for table in tables:
        print(f"Migrating {table}...")
        
        # Get all rows from SQLite
        sqlite_cur.execute(f"SELECT * FROM {table}")
        rows = sqlite_cur.fetchall()
        
        if not rows:
            print(f"  No data in {table}")
            continue
            
        # Get column names
        columns = [description[0] for description in sqlite_cur.description]
        
        # Prepare INSERT statement
        placeholders = ','.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
        
        # Insert rows
        inserted = 0
        for row in rows:
            try:
                pg_cur.execute(insert_sql, tuple(row))
                inserted += 1
            except Exception as e:
                print(f"  Error inserting row: {e}")
                print(f"  Row data: {dict(row)}")
        
        pg_conn.commit()
        print(f"  Inserted {inserted}/{len(rows)} rows")
    
    # Update sequences
    for table in ['users', 'tags', 'invites', 'links']:
        try:
            pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table};")
            pg_conn.commit()
            print(f"Updated sequence for {table}")
        except Exception as e:
            print(f"Could not update sequence for {table}: {e}")
    
    sqlite_conn.close()
    pg_conn.close()
    print("\nMigration complete!")

if __name__ == '__main__':
    if len(sys.argv) != 7:
        print("Usage: python migrate_db.py <sqlite_db> <pg_host> <pg_port> <pg_user> <pg_password> <pg_db>")
        sys.exit(1)
    
    migrate_database(*sys.argv[1:])
