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
            self.simulation_data = json.load(file)

    def find_max_stamp(self):
        try:
            max_stamp = max((entry["stamp"] for entry in self.simulation_data["StampTableV4"]))
            return max_stamp
        except KeyError:
            return None

    def get_simulated_balance(self, tick, address):
        try:
            for balance in self.simulation_data["balances"]:
                if balance["tick"] == tick and balance["address"] == address:
                    return balance
            return None
        except Exception as e:
            print(f"An error occurred: {e}")
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
        elif "SRC20Valid" in query and "DEPLOY" in query:
            self.src20valid_results = self.simulation_data.get("SRC20Valid", [])
            self.src20valid_query = query
            self.src20valid_params = params
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
                if caller_name == "get_src20_deploy_in_db":
                    if self.src20valid_params[0] is not None:
                        for result in self.src20valid_results:
                            if result["tick"].upper() == self.src20valid_params[0].upper():
                                return (result["lim"], result["max"], result["deci"])
                    return (0, 0, 18)

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

                tick = caller_frame.f_locals.get("tick", None)
                addresses = caller_frame.f_locals.get("addresses", [])

                if caller_name == "get_total_src20_minted_from_db":
                    return [(0,)]

                if caller_name == "get_next_stamp_number":
                    return [(1,)]

                if caller_name == "get_total_user_balance_from_balances_db":
                    filtered_balances = []
                    for balance in self.simulation_data["balances"]:
                        if balance["tick"] == tick and balance["address"] in addresses:
                            filtered_balances.append(
                                (
                                    balance["tick"],
                                    balance["address"],
                                    balance["total_balance"],
                                    balance["highest_block_index"],
                                    balance["block_time_unix"],
                                    balance["locked_amt"],
                                )
                            )
                    self.logger.info(f"query: balance, tick: {tick}, addresses: {addresses}")
                    self.logger.info(f"filtered_balances: {filtered_balances}")
                    return filtered_balances

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


if __name__ == "__main__":
    simulation_data_path = Path(__file__).parent / "dbSimulation.json"
    db_simulator = DBSimulator(simulation_data_path)
    print(json.dumps(db_simulator.simulation_data, indent=4))

    db_simulator.execute("SELECT * FROM transactions")
    print("Results: 'SELECT FROM transactions':", db_simulator.execute_results)

    db_simulator.execute("SELECT MAX(stamp) FROM StampTableV4")
    print("Results:'SELECT MAX(stamp) FROM StampTableV4':", db_simulator.execute_results)

    db_simulator.close()
