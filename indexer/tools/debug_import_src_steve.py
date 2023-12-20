import os
import csv
import pymysql as mysql
from dotenv import load_dotenv

parent_dir = os.path.dirname(os.getcwd())
dotenv_path = os.path.join(parent_dir, '.env')
load_dotenv(dotenv_path)

# Connection parameters
rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')

# Connect to the database
mysql_conn = mysql.connect(
    host=rds_host,
    user=rds_user,
    password=rds_password,
    database=rds_database
)

print('rdshost:', rds_host)
print('drs_user:', rds_user)

# Read the CSV file
csv_file = 'steve_src20_balance_v4.csv'

# Modify the CREATE TABLE statement to change the data type of 'column5' to DECIMAL(39, 18)
create_table_query = '''
CREATE TABLE IF NOT EXISTS SRC_STEVE (
    column1 VARCHAR(255),
    column2 VARCHAR(255),
    column3 VARCHAR(32),
    column4 DATETIME,
    column5 DECIMAL(39, 18),
    column6 INT
)
'''
with open(csv_file, 'r') as file:
    csv_data = csv.reader(file)
    column_names = next(csv_data)  # Get the column names from the first row

    # Create a new table
    create_table_query = f'''
    CREATE TABLE IF NOT EXISTS SRC_STEVE (
        {column_names[0]} VARCHAR(255),
        {column_names[1]} VARCHAR(255),
        {column_names[2]} VARCHAR(32),
        {column_names[3]} DATETIME,
        {column_names[4]} DECIMAL(39, 18),
        {column_names[5]} INT
    )
    '''
    with mysql_conn.cursor() as cursor:
        cursor.execute(create_table_query)
        mysql_conn.commit()

    # Insert data into the table
    insert_query = f'''
    INSERT INTO SRC_STEVE ({', '.join(column_names)})
    VALUES (%s, %s, %s, %s, %s, %s)
    '''
    with mysql_conn.cursor() as cursor:
        for row in csv_data:
            try:
                cursor.execute(insert_query, row)
            except mysql.DataError as e:
                print('Error:', e)
                print('Row:', row)
            mysql_conn.commit()

# Close the database connection
mysql_conn.close()

# id, creator tick datetime amt block_index