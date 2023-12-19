import os
import pymysql as mysql
import csv
from dotenv import load_dotenv
import os

parent_dir = os.path.dirname(os.getcwd())
dotenv_path = os.path.join(parent_dir, '.env')
load_dotenv(dotenv_path)
            
rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')

mysql_conn = mysql.connect(
    host=rds_host,
    user=rds_user,
    password=rds_password,
    port=3306,
    database=rds_database
)


def main():
    bootstrap_dir = os.path.join(os.getcwd(), '..', 'bootstrap')

    cursor = mysql_conn.cursor()
    cursor.execute("SELECT * FROM srcbackground;")
    results = cursor.fetchall()
    with open(os.path.join(bootstrap_dir, 'srcbackground.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        for row in results:
            writer.writerow(row)

    cursor.execute("SELECT * FROM creator;")
    results = cursor.fetchall()
    with open(os.path.join(bootstrap_dir, 'creator.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        for row in results:
            writer.writerow(row)
    mysql_conn.close()


if __name__ == "__main__":
    main()