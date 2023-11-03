03/11/2023: [WIP] Docker compose (author: JA):
    - Add Dockerfile and docker-compose.yml
    - Add more dependencies to requirements.txt
    - Change BACKEND_URL to RPC_URL to work wih quicknode in backend.py
    - Change BLOCK schema in SQLite and MySQL for difficulty to FLOAT in blocks.py
  - Detected Errors:
    - raises ConsensusError in check.py line 145 because calculated_hash differs of expected_hash
      - seems that content used to generate calculated_hash has some None attributes, idk if this is the problem.