import inspect
import json
import logging
from pathlib import Path


class DBSimulator:
    def __init__(self, simulation_data_path):
        self.logger = logging.getLogger()
        self.simulation_data_path = simulation_data_path
        self.load_simulation_data()

    def cursor(self):
        return self

    def __enter__(self):
        return self.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def load_simulation_data(self):
        with open(self.simulation_data_path, "r") as file:
            print(file)
            self.simulation_data = json.load(file)
            print(self.simulation_data)

    def find_max_stamp(self):
        try:
            max_stamp = max((entry["stamp"] for entry in self.simulation_data["StampTableV4"]))
            return max_stamp
        except KeyError:
            return None

    def execute(self, query, params=None):
        if "SELECT" in query.upper():
            self.execute_results = self.simulate_select_query(query, params)
        elif "INSERT" in query.upper() or "UPDATE" in query.upper() or "DELETE" in query.upper():
            self.simulate_write_query(query, params)
        else:
            self.logger.info(f"Unsupported query type in simulation: {query}")

    def simulate_select_query(self, query, params):
        if "transactions" in query:
            return self.simulation_data.get("transactions", [])
        elif "blocks" in query:
            return self.simulation_data.get("blocks", [])
        elif "SRC101Valid" in query and "DEPLOY" in query:
            self.src101valid_results = self.simulation_data.get("SRC101Valid", [])
            self.src101valid_query = query
            self.src101valid_params = params
        elif "srcbackground" in query:
            return None
        elif "MAX(stamp)" in query:
            max_stamp = self.find_max_stamp()
            if max_stamp is None:
                return [(1000,)]
            else:
                return [(max_stamp,)]
        else:
            self.logger.info(f"Unsupported SELECT query in simulation: {query}")
            return None

    def simulate_write_query(self, query, params):
        self.logger.info(f"Simulating write operation: {query} with params {params}")

    def fetchone(self):
        current_frame = inspect.currentframe()
        if current_frame is not None:
            caller_frame = current_frame.f_back
            if caller_frame is not None:
                caller_name = caller_frame.f_code.co_name
                self.logger.info(f"The calling function is {caller_name}")

                self.logger.info(f"fetchone db results: {self.execute_results}")
                if caller_name == "get_src101_deploy_in_db":
                    if self.src101valid_params[0] is not None:
                        for result in self.src101valid_results:
                            if result["tick"].upper() == self.src101valid_params[0].upper():
                                return (result["lim"], result["pri"], result["mintstart"], result["mintend"], result["rec"])
                    return (
                        10,
                        "",
                        0,
                        18446744073709551615,
                        [
                            "mrkZu7YtBW3udp1a7vHtq9PeKQNgraTLzn",
                            "mjg7b3WktK67qh85t42NcMyXe2cMxNpQaM",
                            "mragE3E64YCyoFnfj3qJbJG15YFYgosCn4",
                        ],
                    )

                if self.execute_results:
                    result = self.execute_results.pop(0)
                    return (result,) if not isinstance(result, tuple) else result
        return None

    def fetchall(self):
        current_frame = inspect.currentframe()
        if current_frame is not None:
            caller_frame = current_frame.f_back
            if caller_frame is not None:
                caller_name = caller_frame.f_code.co_name
                self.logger.info(f"The calling function is {caller_name}")

                deploy_hash = caller_frame.f_locals.get("deploy_hash", None)
                tokenid_utf8 = caller_frame.f_locals.get("tokenid_utf8", None)
                addresses = caller_frame.f_locals.get("addresses", [])

                if caller_name == "get_total_src101_minted_from_db":
                    return [(1)]

                if caller_name == "get_next_stamp_number":
                    return [(1,)]

                if caller_name == "get_owner_expire_data_from_running":
                    filtered_owners = []
                    for o in self.simulation_data["owners"]:
                        if o["deploy_hash"] == deploy_hash and o["tokenid_utf8"] == tokenid_utf8:
                            filtered_owners.append(
                                (
                                    o["deploy_hash"],
                                    o["tokenid_utf8"],
                                    o["src101_preowner"],
                                    o["src101_owner"],
                                    o["expire_timestamp"],
                                    o["address_data"],
                                    o["txt_data"],
                                    o["prim"],
                                )
                            )
                    self.logger.info(f"query: owners, deploy_hash: {deploy_hash}, addresses: {addresses}")
                    self.logger.info(f"filtered_owners: {filtered_owners}")
                    return filtered_owners

        result = self.simulation_data
        self.simulation_data = []
        return result

    def fetchmany(self, size):
        result = self.simulation_data[:size]
        self.simulation_data = self.simulation_data[size:]
        return result

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass
