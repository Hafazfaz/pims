
import mysql.connector

try:
    # Establish the connection
    cnx = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Hafazfaz@1",  # Replace with the password you set during installation
        database="dtmgt_db"  # You can create a database using MySQL Workbench or a SQL client
    )

    if cnx.is_connected():
        print("Successfully connected to MySQL database")

        # Create a cursor object to execute queries
        cursor = cnx.cursor()

        # Example: Create a database if it doesn't exist
        # You might want to create your database using MySQL Workbench first
        # cursor.execute("CREATE DATABASE IF NOT EXISTS your_database_name")
        # print("Database 'your_database_name' created or already exists.")

        # Example: Execute a simple query (e.g., show databases)
        cursor.execute("SHOW DATABASES")
        for db in cursor:
            print(db)

except mysql.connector.Error as err:
    if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
        print("Something is wrong with your user name or password")
    elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
        print("Database does not exist")
    else:
        print(err)
finally:
    if 'cnx' in locals() and cnx.is_connected():
        cursor.close()
        cnx.close()
        print("MySQL connection is closed")
