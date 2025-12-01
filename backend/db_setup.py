
import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def create_tables():
    try:
        # Establish a connection to the MySQL server
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()

        # Create the database if it doesn't exist
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        print(f"Database '{DB_NAME}' created or already exists.")

        # Switch to the specified database
        cursor.execute(f"USE {DB_NAME}")

        # Read the schema.sql file
        with open('schema.sql', 'r') as f:
            sql_script = f.read()

        # Split the script into individual statements
        sql_statements = sql_script.split(';')

        # Execute each statement
        for statement in sql_statements:
            if statement.strip():
                cursor.execute(statement)
                print(f"Executed: {statement.strip()}")

        print("Tables created successfully!")

    except mysql.connector.Error as err:
        print(f"Error: {err}")

    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection is closed.")

if __name__ == "__main__":
    create_tables()
