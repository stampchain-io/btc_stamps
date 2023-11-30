# API:

- [DONE] Review stamps/[id] and cursed/[id]
  - add into cursed and stamps query folders
  - join issuances to update supply and locked status
  - divisibility 🤯
  - Reissuance problem when querying by stamp number or tx_hash
- [DONE] Add retry in handleQuery and connectDb
- [WIP] Blocks endpoint:
  - [DONE] create blocks_api file to host the query logic that will use api and
    pages in the explorer
  - [WIP]related blocks to show previous and next block for a given one
  - [TODO]add to block queries to be able to search by hash
- [TODO] Other endpoints:
  - [TODO] Migrate all the logic from enpoints to its own file to be reused by
    pages and endpoint

# EXPLORER:

- [WIP] Retrieve images from the static/stamps folder

-[TOFIX] new images are not being updated.... need to restart the container to
be updated, asking for solutions to this...

- [TODO] Work on blocks page
- [TODO] Work on index page
- [TODO] Work on stamp page
- [TODO] tons of work...
