#!/bin/bash
# Start the agent search detached (container). Log: digital/agent/runs/s3v3.console.log
cd /foss/designs/gf180-ble-tx-power/digital/agent
export PD_NO_FIX_BUFFER=1 LLM_PD_NO_CACHE=1
nohup ./venv/bin/python -m agents.graph --design designs/ble_tx_uart_3v3 --runs 40 --usd 4 \
  --weights 0,0.35,0.5,0.15 --work runs/s3v3 > runs/s3v3.console.log 2>&1 < /dev/null &
echo "started pid $!"
