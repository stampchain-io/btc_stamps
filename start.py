import server

log_file = 'log.file'
db = server.initialise( log_file=log_file, backend_password='rpc', backend_user='rpc' )

if db is None:
    print('Failed to connect to database')
    exit(1)
else:
    cursor = db.cursor()

server.start_all(db)