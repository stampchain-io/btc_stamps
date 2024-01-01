import requests

# This script fetches the latest version of the packages listed below from PyPI
packages = [
    "appdirs", "bitcoinlib", "colorlog", "sha3", "pycoin", "python-bitcoinlib",
    "python-bitcoinrpc", "regex", "pycryptodome", "requests", "cachetools",
    "pymysql", "python-docx", "cryptography", "pybase64", "python-magic",
    "boto3", "msgpack", "tqdm", "python-dotenv", "arweave-python-client"
]

for package in packages:
    response = requests.get(f"https://pypi.org/pypi/{package}/json")
    if response.ok:
        data = response.json()
        print(f"{package}=={data['info']['version']}")
    else:
        print(f"Failed to get data for {package}")
