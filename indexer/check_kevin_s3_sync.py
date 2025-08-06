#!/usr/bin/env python3
"""Check KEVIN token S3 sync issue"""

import hashlib

# The problematic file
filename = "23765f9bc6b87e078b1f93ed213f90b9004998336575f726e46f34ddbea5e5f3.svg"

# Download current S3 file for comparison
import requests

s3_url = f"https://s3.us-east-1.amazonaws.com/stampchain.io/stamps/{filename}"
response = requests.get(s3_url)

if response.status_code == 200:
    print(f"Downloaded S3 file, size: {len(response.content)} bytes")
    print(f"S3 file MD5: {hashlib.md5(response.content).hexdigest()}")
    print(f"\nS3 file content preview:")
    print(response.text[:500])

    # Save for inspection
    with open("/home/ubuntu/stampsdev/btc_stamps/indexer/kevin_s3_current.svg", "wb") as f:
        f.write(response.content)
    print("\nSaved S3 file to: kevin_s3_current.svg")
else:
    print(f"Failed to download S3 file: {response.status_code}")

# Let's check what the S3 file looks like
print("\n" + "=" * 50)
print("Analysis:")
print("=" * 50)

# Check if it has background
if "background-image" in response.text:
    print("✓ File contains background-image style")
else:
    print("✗ File does NOT contain background-image style")

if "linear-gradient" in response.text:
    print("✓ File contains linear-gradient (default background)")
else:
    print("✗ File does NOT contain linear-gradient")

# Check the JSON content
import re

json_match = re.search(r"<pre>({.*?})</pre>", response.text, re.DOTALL)
if json_match:
    print(f"\nJSON content in SVG:")
    print(json_match.group(1))
