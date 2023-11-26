import requests
import os

endpoint = "https://arweave.net/graphql"
stampchain_arweave_wallet = "T9SMEcU-q0eQY7RiePwP_oZO6D4b-6el5AhgAn9o218"


def download_arweave_file(transaction_id, local_file_path):
    url = f"https://arweave.net/{transaction_id}"
    response = requests.get(url, stream=True)

    if response.status_code == 200:
        with open(local_file_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"file downloaded and saved to: {local_file_path}")
    else:
        print(f"Error downloading file: {response.status_code}")


def get_arweave_transaction(wallet=stampchain_arweave_wallet, tags=[]):
    formatted_tags = [
        {
            "name": tag_name,
            "values": [str(tag_value)]  # Convertir todos los valores a strings
        } for tag_name, tag_value in tags
    ]
    query = {
        "query": """
        query($wallet: String!, $tags: [TagFilter!]) {
            transactions(owners: [$wallet], tags: $tags) {
                edges {
                    node {
                        id
                        tags {
                            name
                            value
                        }
                    }
                }
            }
        }
        """,
        "variables": {
            "wallet": wallet,
            "tags": formatted_tags
        }
    }
    response = requests.post(endpoint, json=query)
    if response.status_code == 200:
        print(response.json())
        return response.json()['data']['transactions']['edges']
    else:
        raise Exception(f"Error fetching Arweave: {response.status_code}")


def fetch_and_download_arweave_files(
    wallet=stampchain_arweave_wallet,
    tags=[],
    download_path="."
):
    try:
        transactions = get_arweave_transaction(wallet, tags)
    except Exception as e:
        print(f"Error retrieving transactions: {e}")
        return

    for edge in transactions:
        print(edge)
        transaction_id = edge['node']['id']
        tx_hash = next(
            (
                tag['value'] for tag in edge['node']['tags']
                if tag['name'] == 'tx_hash'
            ),
            None
        )
        content_type = next(
            (
                tag['value'] for tag in edge['node']['tags']
                if tag['name'] == 'Content-Type'
            ),
            'text/plain'
        )
        extension = content_type.split('/')[-1]
        local_file_path = os.path.join(
            download_path, f"{tx_hash}.{extension}"
        )
        download_arweave_file(transaction_id, local_file_path)


'''
 # USAGE
 tags = [
     (
         "tx_hash",
         "1a524c62c58538e2fe6f98d31f4e555ef1aa2a3bfa2536d227b09195fe95f912"
     ),
     ("stamp", "91")
 ]
 download_path = "./downloaded_files"
 os.makedirs(download_path, exist_ok=True)
 fetch_and_download_arweave_files(
     stampchain_arweave_wallet,
     tags,
     download_path
 )
'''
