#!/bin/bash

# File to track running state
PIDFILE="/tmp/indexer.pid"

cleanup() {
    echo "Shutting down indexer..."
    if [ -f "$PIDFILE" ]; then
        kill $(cat "$PIDFILE") 2>/dev/null
        rm -f "$PIDFILE"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

while true; do
    # Start indexer and save PID
    poetry run indexer & echo $! > "$PIDFILE"
    
    # Wait for process
    wait $(cat "$PIDFILE")
    exit_code=$?
    
    # Check if exit was intentional
    if [ $exit_code -eq 130 ] || [ $exit_code -eq 143 ]; then
        echo "Received shutdown signal, exiting..."
        cleanup
        break
    fi
    
    echo "Indexer stopped with code $exit_code, restarting in 5 seconds..."
    sleep 5
done 