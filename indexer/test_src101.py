import logging
import sys
import unittest
from pathlib import Path

import colorlog
from colour_runner.runner import ColourTextTestRunner

from index_core.blocks import BlockProcessor
from index_core.models import StampData
from index_core.src101 import parse_src101
from index_core.stamp import parse_stamp
from tests.db_simulator_src101 import DBSimulator
from tests.src101_variations_data import src101_variations_data

handler = colorlog.StreamHandler()
handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(asctime)s - %(log_color)s%(levelname)s:%(name)s:%(message)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
)

logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


class TestSrc101Variations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Add the project root directory to the sys.path for module importing
        project_root = Path(__file__).resolve().parent.parent
        sys.path.append(str(project_root))

        # Initialize DB Simulator with the path to dbSimulation.json
        db_simulation_path = project_root / "indexer" / "tests" / "dbSimulation_src101.json"
        try:
            cls.db_simulator = DBSimulator(db_simulation_path)
        except Exception as e:
            print(e)

    def test_src101_variations(self):
        block_processor = BlockProcessor(self.db_simulator)
        for test_case in src101_variations_data:
            stamp_result, src101_result, src101_result = None, None, None
            with self.subTest(msg=test_case["description"]):
                logger.info(f"Running test case: {test_case['description']}")
                stamp_data_instance = StampData(
                    tx_hash=test_case["tx_hash"],
                    source=test_case["source"],
                    destination=test_case["destination"],
                    destination_nvalue=test_case["destination_nvalue"],
                    btc_amount=test_case["btc_amount"],
                    fee=test_case["fee"],
                    data=test_case["src101JsonString"],
                    decoded_tx=test_case["decoded_tx"],
                    keyburn=test_case["keyburn"],
                    tx_index=test_case["tx_index"],
                    block_index=test_case["block_index"],
                    block_time=test_case["block_time"],
                    block_timestamp=test_case["block_timestamp"],
                    is_op_return=test_case["is_op_return"],
                    p2wsh_data=test_case["p2wsh_data"],
                )
                try:
                    stamp_result, parsed_stamp, valid_stamp, prevalidated_src = parse_stamp(
                        stamp_data=stamp_data_instance,
                        db=self.db_simulator,
                        valid_stamps_in_block=test_case["valid_stamps_in_block"],
                    )
                except:
                    stamp_result, parsed_stamp, valid_stamp, prevalidated_src = None, None, None, None
                stamp_result = False if stamp_result is None else stamp_result
                if stamp_result != test_case["expectedOutcome"]["stamp_success"]:
                    logger.error(f"FAIL: {test_case['description']}")
                    logger.error(f"FAIL: {test_case['sr101JsonString']}")
                    logger.error(
                        f"FAIL: in stamp_result test: {test_case['expectedOutcome']['message']} - Expected: {test_case['expectedOutcome']['stamp_success']}, Got: {stamp_result}"
                    )
                else:
                    logger.info(
                        f"Success in stamp_result {test_case['description']} test: {test_case['expectedOutcome']['message']}"
                    )

                if parsed_stamp:
                    block_processor.parsed_stamps.append(parsed_stamp)  # includes cursed and prevalidated src101 on CP
                if valid_stamp:
                    block_processor.valid_stamps_in_block.append(valid_stamp)
                if prevalidated_src:
                    src101_result, src101_dict = parse_src101(
                        self.db_simulator, prevalidated_src, block_processor.processed_src101_in_block
                    )
                    block_processor.processed_src101_in_block.append(src101_dict)

                src101_result = False if src101_result is None else src101_result

                if src101_result != test_case["expectedOutcome"]["src101_success"]:
                    logger.error(f"FAIL: {test_case['description']}")
                    logger.error(f"FAIL: {test_case['src101JsonString']}")
                    logger.error(
                        f"FAIL: in src101_result test: {test_case['expectedOutcome']['message']} - Expected: {test_case['expectedOutcome']['src101_success']}, Got: {src101_result}"
                    )
                else:
                    logger.info(f"Success in src101_result test: {test_case['expectedOutcome']['message']}")

                self.assertEqual(
                    stamp_result,
                    test_case["expectedOutcome"]["stamp_success"],
                    msg=f"Failure in stamp_result test: {test_case['expectedOutcome']['message']} - Expected: {test_case['expectedOutcome']['stamp_success']}, Got: {stamp_result}",
                )

                self.assertEqual(
                    src101_result,
                    test_case["expectedOutcome"]["src101_success"],
                    msg=f"Failure in src101_result test: {test_case['expectedOutcome']['message']} - Expected: {test_case['expectedOutcome']['src101_success']}, Got: {src101_result}",
                )


if __name__ == "__main__":
    unittest.main(testRunner=ColourTextTestRunner, exit=False, verbosity=3)
