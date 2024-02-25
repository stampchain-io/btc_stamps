import pymysql as mysql
import os
import sys
import argparse

if os.getcwd().endswith('/indexer'):
    sys.path.append(os.getcwd())
    dotenv_path = os.path.join(os.getcwd(), '.env')
else:
    sys.path.append(os.path.join(os.getcwd(), 'indexer'))
    dotenv_path = os.path.join(os.getcwd(), 'indexer/.env')

from dotenv import load_dotenv
load_dotenv(dotenv_path=dotenv_path, override=True)

import config
from src.aws import get_s3_objects
from src.src20 import build_src20_svg_string 
from src.stamp import store_files

parser = argparse.ArgumentParser()
parser.add_argument('ticks_to_update', nargs='+', help=f'''
    Provide a list of tick values to update.
    Use double backslash for unicode chars.
    Example: `python {os.path.basename(__file__)} kevin stamp bear\\\\u0001f43b`''')
args = parser.parse_args()

ticks_to_update = args.ticks_to_update

# we are specifying specific vars here instead of using defaults in config.py 
# so we can update to production or dev db's specifically
rds_host = os.environ.get('ST3_HOSTNAME')
rds_user = os.environ.get('ST3_USER')
rds_password = os.environ.get('ST3_PASSWORD')
rds_database = os.environ.get('RDS_DATABASE')
rds_port = int(os.environ.get("RDS_PORT", 3306))

db = mysql.connect(
    host=rds_host,
    user=rds_user,
    password=rds_password,
    port=rds_port,
    database=rds_database
)


print('connecting to database', rds_host)
config.S3_OBJECTS = get_s3_objects(db, config.AWS_S3_BUCKETNAME, config.AWS_S3_CLIENT)


stamp_mimetype = 'image/svg+xml'
cursor = db.cursor()

for tick_to_update in ticks_to_update:
    print(f"Updating {tick_to_update}...")

    cursor.execute("SELECT tx_hash, p, op, tick, amt, lim, max FROM SRC20Valid WHERE tick = %s", (tick_to_update,))
    src_20_dict = cursor.fetchall()

    for row in src_20_dict:
        tx_hash, p, op, tick, amt, lim, max = row
        #convert the decimal value of amt to an int
        if amt:
            amt = int(amt)
        p = p.upper()
        tick = tick.upper()
        op = op.upper()
        svg_string = build_src20_svg_string(db, {'p': p, 'op': op, 'tick': tick, 'amt': amt, 'lim': lim, 'max': max})

        file_suffix = 'svg'
        if type(svg_string) is str:
            svg_string = svg_string.encode('utf-8')
        filename = f"{tx_hash}.{file_suffix}"
        file_obj_md5 = store_files(db, filename, svg_string, stamp_mimetype)

        cursor.execute("UPDATE StampTableV4 SET file_hash = %s WHERE tx_hash = %s", (file_obj_md5, tx_hash))

db.commit()
db.close()
