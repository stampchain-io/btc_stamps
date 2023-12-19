import base64
import pymysql as mysql
import os
import mimetypes
import argparse
import sys
from PIL import Image
from dotenv import load_dotenv

parent_dir = os.path.dirname(os.getcwd())
dotenv_path = os.path.join(parent_dir, '.env')
load_dotenv(dotenv_path)

parser = argparse.ArgumentParser(description='Import SRC BG to MySQL')
parser.add_argument('file_names', nargs='+', help='Names of the files to import in tick-color.ext format')
args = parser.parse_args()

file_names = args.file_names

rds_host = os.environ.get('RDS_HOSTNAME')
rds_user = os.environ.get('RDS_USER')
rds_password = os.environ.get('RDS_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')

mysql_conn = mysql.connect(
    host=rds_host,
    user=rds_user,
    password=rds_password,
    database=rds_database
)


def main(file_names=file_names, mysql_conn=mysql_conn):

    for file_name in file_names:
        if not os.path.isfile(file_name):
            print(f"The file '{file_name}' does not exist.")
            continue
        
        file_prefix = os.path.splitext(file_name)[0].upper()

        if len(file_prefix.split("-")) != 2:
            print(f"The file '{file_name}' must be named tick-color.ext.")
            continue

        tick, text_color = file_prefix.split("-")
        text_color = text_color.lower()

        mysql_cursor = mysql_conn.cursor()
        mysql_cursor.execute('''
                             SELECT * FROM SRC20 WHERE tick = %s AND op = 'DEPLOY'
                                ''', (tick))
        if mysql_cursor.rowcount == 0:
            print(f"Tick '{tick}' deploy does not exist in the database.")
            continue

        with open(file_name, 'rb') as f:
            background_bytestring = f.read()
        
        mimetype, _ = mimetypes.guess_type(file_name)
        background_base64 = base64.b64encode(background_bytestring).decode('utf-8')
        bald_background_base64_prefixed = mimetype + ';base64,' + background_base64

        image = Image.open(file_name)
        width, height = image.size
        if width != 420 or height != 420:
            print(f"The image dimensions of '{file_name}' must be 420x420 pixels.")
            continue

        mysql_cursor.execute('''
            REPLACE INTO srcbackground (base64, tick, P, text_color)
            VALUES (%s, %s, %s, %s)
        ''', (bald_background_base64_prefixed, tick, 'SRC-20', text_color))
        mysql_conn.commit()

        mysql_cursor.close()
        mysql_conn.close()

        print("Tick:", tick)
        print("Mimetype:", mimetype)

        delete_file = input(f"Success: Delete '{file_name}'? (y/n): ")
        if delete_file.lower() == "y":
            os.remove(file_name)
            print(f"The file '{file_name}' has been deleted.")
        else:
            print(f"The file '{file_name}' has not been deleted.")


if __name__ == "__main__":
    main()