from dotenv import load_dotenv

load_dotenv()

import server

db = server.initialize( log_file='log.file', backend_password='rpc', backend_user='rpc' )

if db is None:
    print('Failed to connect to database')
    exit(1)
else:
    cursor = db.cursor()

server.start_all(db)