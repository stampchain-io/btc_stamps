import time

import zmq

context = zmq.Context()
socket = context.socket(zmq.SUB)

# For mainnet
socket.connect("tcp://127.0.0.1:9333")

# For testnet, use:
# socket.connect("tcp://127.0.0.1:19333")

# Set socket options
socket.setsockopt(zmq.SUBSCRIBE, b"rawblock")

print("Listening for ZMQ notifications...")
while True:
    try:
        topic, body, seq = socket.recv_multipart()
        topic_str = topic.decode("utf-8")
        seq_str = seq.decode("utf-8")
        print(f"Received: {topic_str}, Sequence: {seq_str}")
        if topic == b"rawblock":
            print(f"Raw block received, size: {len(body)} bytes")
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(1)

print("Shutting down...")
socket.close()
context.term()
