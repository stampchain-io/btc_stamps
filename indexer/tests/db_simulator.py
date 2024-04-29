import json
from pathlib import Path
import logging
import inspect
import time

class DBSimulator:
    def __init__(self, simulation_data_path):
        # if not self.logger.handlers:
        self.logger = logging.getLogger()
            # handler = logging.StreamHandler()
            # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            # handler.setFormatter(formatter)
            # self.logger.addHandler(handler)
        self.simulation_data_path = simulation_data_path
        self.load_simulation_data()

    def cursor(self):
        # Simulate the creation of a new cursor
        return self
    
    def __enter__(self):
        # Simulate the creation of a new cursor when entering a with block
        return self.cursor()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        # Simulate closing the cursor/connection when exiting a with block
    
    def load_simulation_data(self):
        with open(self.simulation_data_path, 'r') as file:
            self.simulation_data = json.load(file)
    
    def find_max_stamp(self):
        try:
            max_stamp = max(entry['stamp'] for entry in self.simulation_data['StampTableV4'])
            return max_stamp
        except KeyError:
            return None
    
    def get_simulated_balance(self, tick, address):
        try:
            # Assuming self.simulation_data is already loaded as a dictionary
            for balance in self.simulation_data['balances']:
                if balance['tick'] == tick and balance['address'] == address:
                    return balance
            # If no matching tick and address are found
            return None
        except Exception as e:
            print(f"An error occurred: {e}")
            return None               
            
    def execute(self, query, params=None):
        # Simulate database query execution based on the query string and parameters
        # self.execute_results = None
        if "SELECT" in query.upper():
            self.execute_results = self.simulate_select_query(query, params)
        elif "INSERT" in query.upper() or "UPDATE" in query.upper() or "DELETE" in query.upper():
            self.simulate_write_query(query, params)
        else:
            self.logger.info(f"Unsupported query type in simulation: {query}")
        # return self.execute_results

    def simulate_select_query(self, query, params):
        # Simulate SELECT query and return results from loaded simulation data
        if "transactions" in query:
            return self.simulation_data.get('transactions', [])
        elif "blocks" in query:
            return self.simulation_data.get('blocks', [])
        elif "SRC20Valid" in query and "DEPLOY" in query:
            self.src20valid_results = self.simulation_data.get('SRC20Valid', [])
            self.src20valid_query = query
            self.src20valid_params = params
            # return self.simulation_data.get('SRC20Valid', None)
        elif "srcbackground" in query:
            # iterate through the list and fetch the data, then save to self.srcbackground_results
            return None
            # return self.simulation_data.get('srcbackground', None)
        elif "MAX(stamp)" in query:
            max_stamp = self.find_max_stamp()
            if max_stamp is None:
                return [(1000),]
            else:
                return [(max_stamp,)]
        else:
            self.logger.info(f"Unsupported SELECT query in simulation: {query}")
            return None

    def simulate_write_query(self, query, params):
        # Simulate write operations (INSERT, UPDATE, DELETE) by modifying the simulation data in-memory
        self.logger.info(f"Simulating write operation: {query} with params {params}")
        # Note: This is a simplified example. In a real scenario, you would modify self.simulation_data based on the query and params.


    def fetchone(self):
        # Get the current frame
        current_frame = inspect.currentframe()
        caller_frame = current_frame.f_back
        caller_name = caller_frame.f_code.co_name
        self.logger.info(f"The calling function is {caller_name}")

        # Simulate fetching the next row of a query result set
        self.logger.info(f"fetchone db results: {self.execute_results}")        # Parse the dictionary to be returned, will need to be specific based upon the function that called 
        if caller_name == 'get_src20_deploy_in_db':
            # If self.src20valid_params[0] is not None then parse src20valid_results for a tick key value that matches the params
            if self.src20valid_params[0] is not None:
                for result in self.src20valid_results:
                    if result['tick'].upper() == self.src20valid_params[0].upper():
                        return (result['lim'], result['max'], result['deci'])
            return (0, 0, 18)  # Ensure this is a tuple for consistency

        # For other callers, ensure a consistent return type
        if self.execute_results:
            result = self.execute_results.pop(0)
            # If result is not already a tuple, make it a tuple
            return (result,) if not isinstance(result, tuple) else result
        else:
            return None

    def fetchall(self):
        current_frame = inspect.currentframe()
        caller_frame = current_frame.f_back
        caller_name = caller_frame.f_code.co_name
        self.logger.info(f"The calling function is {caller_name}")

        # Access f_locals from the caller's frame
        tick = caller_frame.f_locals.get('tick', None)
        tick_hash = caller_frame.f_locals.get('tick_hash', None)  # Assuming you have a way to use this for filtering
        addresses = caller_frame.f_locals.get('addresses', [])

        if caller_name == 'get_total_src20_minted_from_db':
            # return a list of tuples
            return [(0,)] # assume nothing has been minted
            # return 8
        
        if caller_name == 'get_next_stamp_number':
            return [(1,)]
        
        if caller_name == 'get_total_user_balance_from_balances_db':
            filtered_balances = []
            for balance in self.simulation_data['balances']:
                if balance['tick'] == tick and balance['address'] in addresses:
                    # Assuming you need to return specific fields or the whole balance if it matches
                    filtered_balances.append((balance['tick'], balance['address'], balance['total_balance'], balance['highest_block_index'], balance['block_time_unix'], balance['locked_amt']))
            self.logger.info(f"query: balance, tick: {tick}, addresses: {addresses}")
            self.logger.info(f"filtered_balances: {filtered_balances}")
            return filtered_balances


        # Simulate fetching all rows of a query result set
        result = self.simulation_data
        self.simulation_data = []  # Clear the simulation data
        return result
    


    def fetchmany(self, size):
        # Simulate fetching the next set of rows of a query result set
        result = self.simulation_data[:size]
        self.simulation_data = self.simulation_data[size:]
        return result
    
    def commit(self):
        # Simulate commit operation
        pass

    def rollback(self):
        # Simulate rollback operation
        pass

    def close(self):
        # Simulate closing the database connection
        pass

# Example usage
if __name__ == "__main__":
    simulation_data_path = Path(__file__).parent / "dbSimulation.json"
    db_simulator = DBSimulator(simulation_data_path)
    print(json.dumps(db_simulator.simulation_data, indent=4))  # Print loaded simulation data

    # Execute a query and print the results
    db_simulator.execute("SELECT * FROM transactions")
    print("Results of 'SELECT * FROM transactions':", db_simulator.execute_results)

    # Execute another query and print the results
    db_simulator.execute("SELECT MAX(stamp) FROM StampTableV4")
    print("Results of 'SELECT MAX(stamp) FROM StampTableV4':", db_simulator.execute_results)

    db_simulator.close()