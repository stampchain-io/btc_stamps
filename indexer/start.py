import os

if os.path.exists('.env'):
    print('Found .env file. Loading environment variables')
    with open('.env') as f:
        for line in f:
            key, value = line.strip().split('=')
            os.environ[key] = value
            print(f'Loaded {key}={value}')

import server

db = server.initialize( log_file='log.file', backend_password='rpc', backend_user='rpc' )

if db is None:
    print('Failed to connect to database')
    exit(1)
else:
    cursor = db.cursor()

server.start_all(db)