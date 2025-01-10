import logging
import os

from dotenv import load_dotenv

import index_core.log as log


def main():
    load_dotenv()

    root_logger = logging.getLogger()
    verbose = os.environ.get("DEBUG", "false").lower() == "true"
    log.set_up(root_logger, verbose=verbose)

    import index_core.server as server

    db = server.initialize(log_file="indexer.log")

    if db is None:
        print("Failed to connect to database")
        exit(1)

    server.start_all(db)


if __name__ == "__main__":
    main()
