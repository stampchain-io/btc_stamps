from dotenv import load_dotenv


def main():
    load_dotenv()

    import src.index_core.server as server

    db = server.initialize(log_file='indexer.log')

    if db is None:
        print('Failed to connect to database')
        exit(1)

    server.start_all(db)


if __name__ == "__main__":
    main()
