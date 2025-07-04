#!/usr/bin/env python3
"""
Debug script to check what fields are available in dispense events from Counterparty API.
"""
import json
import logging
from index_core.fetch_utils import fetch_xcp

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_dispense_fields():
    """Check what fields are available in dispense events."""
    # Test with a known stamp that has dispenses
    # Let's try a few different CPIDs to find one with dispenses
    test_cpids = [
        "A17170486731055620000",  # Known to have dispenses
        "A11577890719069954000",  # STAMP:0
        "A3766397144519081300",  # Another common stamp
        "A12900681189845834000",  # Another one
    ]

    for test_cpid in test_cpids:
        try:
            # Fetch dispenses
            endpoint = f"/assets/{test_cpid}/dispenses"
            params = {"limit": 5}  # Just get a few to see the structure

            logger.info(f"Fetching dispenses for {test_cpid}...")
            response = fetch_xcp(endpoint, params)

            if response and "result" in response:
                dispenses = response["result"]

                if dispenses:
                    logger.info(f"Found {len(dispenses)} dispenses for {test_cpid}")
                    logger.info("\nFirst dispense event structure:")

                    # Pretty print the first dispense
                    first_dispense = dispenses[0]
                    print(json.dumps(first_dispense, indent=2))

                    # List all available fields
                    logger.info("\nAll available fields:")
                    for field in sorted(first_dispense.keys()):
                        value = first_dispense[field]
                        logger.info(f"  - {field}: {type(value).__name__} = {value}")

                    # Found one with dispenses, we're done
                    return
                else:
                    logger.info(f"No dispenses found for {test_cpid}")
            else:
                logger.error(f"Failed to fetch dispenses for {test_cpid}")
        except Exception as e:
            logger.error(f"Error with {test_cpid}: {e}")
            continue

    logger.info("No stamps with dispenses found in test list")


if __name__ == "__main__":
    check_dispense_fields()
