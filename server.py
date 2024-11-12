import socket
import argparse
import os
from datetime import datetime
import queue
import threading
import multiprocessing
import pyodbc
import configparser
import concurrent.futures

class HexStringConverter:
    @staticmethod
    def hex_to_string(hex_string):
        try:
            return bytes.fromhex(hex_string).decode('utf-8')
        except UnicodeDecodeError as e:
            print(f"Error converting hex to string: {e}")

    @staticmethod
    def string_to_hex(input_string):
        try:
            return input_string.encode('utf-8').hex()
        except Exception as e:
            print(f"Error converting string to hex: {e}")

class Config:
    def __init__(self, env):
        self.cf = configparser.ConfigParser()
        self.cf.read("settings1.config")
        self.env = env
        self.driver = self.cf.get(self.env, 'driver')
        self.server = str(self.cf.get(self.env, 'server'))
        self.database = str(self.cf.get(self.env, 'database'))
        self.ip_address = self.cf.get(self.env, 'ip_address')
        self.port_number = int(self.cf.get(self.env, 'port_number'))
        self.log_folder_path = self.cf.get(self.env, 'log_folder_path')

class LogCreation:
    def __init__(self, config, log_queue):
        self.config = config
        self.LOGS_FOLDER = self.config.log_folder_path
        self.log_queue = log_queue

    def log_data(self, log_type, data):
        try:
            current_date = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            log_folder_path = os.path.join(self.LOGS_FOLDER, current_date)

            if not os.path.exists(log_folder_path):
                os.makedirs(log_folder_path)

            log_file_name = f"{log_type}_data.log"
            log_file_path = os.path.join(log_folder_path, log_file_name)

            log_entry = f'currenttime: {current_time} - {log_type}: {data}\n'
            self.log_queue.put((log_file_path, log_entry))
            print(f"Logged {log_type} data")
        except Exception as e:
            print(f"Error logging {log_type} data: {e}")

class LogWriter:
    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.stop_event = threading.Event()

    def write_logs(self):
        while not self.stop_event.is_set():
            try:
                log_file_path, log_entry = self.log_queue.get(timeout=1)
                with open(log_file_path, "a") as log_file:
                    log_file.write(log_entry)
            except queue.Empty:
                pass

    def stop(self):
        self.stop_event.set()

class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.connection = None
        self.db_lock = threading.Lock()
        self.connect_to_database()
        self.batch_size = 100  # Adjust the batch size as needed
        self.raw_data_batch = []  # Store raw data in batches
        self.db_gps_queue = queue.Queue()  # Queue for GPS data

    def connect_to_database(self):
        try:
            connection_string = f"Driver={self.config.driver};Server={self.config.server};Database={self.config.database};Trusted_Connection=yes;"
            self.connection = pyodbc.connect(connection_string)
            self.cursor = self.connection.cursor()
            print("SQL Server connection successful")
        except pyodbc.Error as e:
            print(f"Error while connecting to the MS SQL server: {e}")

    def insert_data(self, logdatetime, raw_data):
        try:
            query = "INSERT INTO DATAS (logdatetime, raw_data) VALUES (?, ?)"
            with self.db_lock:
                self.raw_data_batch.append((logdatetime, raw_data))
                if len(self.raw_data_batch) >= self.batch_size:
                    self.cursor.executemany(query, self.raw_data_batch)
                    self.connection.commit()
                    self.raw_data_batch = []  # Clear the batch
            print("Data inserted successfully into DATAS.")
        except pyodbc.Error as e:
            print(f"Error while inserting into the DATAS: {e}")

    def insert_gps_data(self, clientname, latitude, longitude):
        try:
            query = "INSERT INTO GPSdata (clientname, latitude, longitude) VALUES (?, ?, ?)"
            with self.db_lock:
                self.db_gps_queue.put((clientname, latitude, longitude))  # Enqueue GPS data
                if self.db_gps_queue.qsize() >= self.batch_size:
                    gps_data_batch = []
                    while not self.db_gps_queue.empty():
                        gps_data_batch.append(self.db_gps_queue.get())
                    self.cursor.executemany(query, gps_data_batch)
                    self.connection.commit()
            print("Data inserted successfully into GPSdata.")
        except pyodbc.Error as e:
            print(f"Error while inserting into the GPSdata: {e}")

class SocketServer:
    def __init__(self, config):
        self.HOST = config.ip_address
        self.PORT = config.port_number
        self.converter = HexStringConverter()
        self.log_queue = queue.Queue()
        self.raw_log_queue = queue.Queue()  # New queue for raw data
        self.log_creation = LogCreation(config, self.log_queue)
        self.log_writer = LogWriter(self.log_queue)
        self.db_manager = DatabaseManager(config)

    def handle_client(self, client_socket):
        with client_socket:
            hex_data = client_socket.recv(1024).decode('utf-8')
            logdatetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            decoded_data = self.converter.hex_to_string(hex_data)

            if decoded_data:
                clientname, lat, lon = map(str.strip, decoded_data.split(','))
                self.log_creation.log_data("client", f'{clientname}, {lat}, {lon}')
                self.log_creation.log_data("raw", hex_data)
                self.db_manager.insert_data(logdatetime, hex_data)
                self.db_manager.insert_gps_data(clientname, lat, lon)

                # Enqueue raw data
                self.raw_log_queue.put(hex_data)  # Add raw data to the raw_log_queue
            else:
                self.log_creation.log_data("error", decoded_data)

    def start(self):
        self.log_writer_thread = threading.Thread(target=self.log_writer.write_logs)
        self.log_writer_thread.start()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((self.HOST, self.PORT))
            server_socket.listen(1000)
            print(f"Server started on {self.HOST}:{self.PORT}")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                while True:
                    client_socket, _ = server_socket.accept()
                    executor.submit(self.handle_client, client_socket)

    def stop(self):
        self.log_writer.stop()
        self.log_writer_thread.join()

# Function to retrieve and write raw log data
def write_raw_logs(raw_log_queue, log_folder_path):
    current_date = datetime.now().strftime("%Y-%m-%d")  # Calculate the current date once
    while True:
        try:
            hex_data = raw_log_queue.get(timeout=1)
            if hex_data:
                if not os.path.exists(log_folder_path):
                    os.makedirs(log_folder_path)
                # log_file_name = "raw_data.log"
                log_file_path = os.path.join(log_folder_path)
                log_entry = f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')} - {hex_data}\n"
                with open(log_file_path, "a") as log_file:
                    log_file.write(log_entry)
        except queue.Empty:
            pass

def start_server():
    parser = argparse.ArgumentParser(description="Socket server settings.")
    parser.add_argument('env', type=str, help='Environment ')
    args = parser.parse_args()
    config = Config(args.env)
    server = SocketServer(config)

    # Start the thread for writing raw logs
    raw_log_thread = threading.Thread(target=write_raw_logs, args=(server.raw_log_queue, config.log_folder_path))
    raw_log_thread.start()

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()

if __name__ == "__main__":
    # Create multiple processes to handle the server
    num_processes = 1  # Adjust the number of server processes as needed
    processes = []

    for _ in range(num_processes):
        process = multiprocessing.Process(target=start_server)
        process.daemon = True
        processes.append(process)
        process.start()

    for process in processes:
        process.join()
