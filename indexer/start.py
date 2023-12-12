import os
import logging

logger = logging.getLogger(__name__)

if os.path.exists('.env'):
    logger.warning('Found .env file. Loading environment variables')
    with open('.env') as f:
        for line in f:
            key, value = line.strip().split('=')
            os.environ[key] = value

import server

log_file = 'log.file'
db = server.initialize( log_file=log_file, backend_password='rpc', backend_user='rpc' )

if db is None:
    print('Failed to connect to database')
    exit(1)
else:
    cursor = db.cursor()

server.start_all(db)