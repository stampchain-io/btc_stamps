



import server

database_file = 'server.db'
log_file = 'log.file'
db = server.initialise(database_file=database_file, log_file=log_file, backend_password='rpc', backend_user='rpc' )

if db is None:
    print('Failed to connect to database')
    exit(1)
else:
    cursor = db.cursor()

server.start_all(db)