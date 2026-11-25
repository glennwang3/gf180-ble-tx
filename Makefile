# Shortcuts for the commands in digital/README.md and .github/workflows.
#
#   make test            model, RTL, edge, UART, debug-UART and full-chain tests (what CI runs)
#   make rtl-test SPS=8  run a single SPS (default: 2, 8 and 16)
#   make gl-test         synthesize, then simulate the gate-level netlist
#   make gl-test TOP=ble_tx_uart  the same with the UART front end (also synth, sta)
#   make sta             synthesize, then pre-layout timing
#
# synth, gl-test and sta need the IIC-OSIC-TOOLS container (Yosys, OpenSTA, PDK).

# Tests run every SPS unless SPS is given; synth and STA default to 8.
SYNTH_SPS = $(or $(SPS),8)
TOP ?= ble_tx
GL_TEST = $(if $(filter ble_tx_uart,$(TOP)),test_ble_tx_uart.py,test_ble_tx.py)

.PHONY: test model-test rtl-test edge-test uart-test dbg-test chain-test synth gl-test sta lut help

test: model-test rtl-test edge-test uart-test dbg-test chain-test

model-test:
	cd model && pytest -q

rtl-test:
	cd digital/test && python3 test_ble_tx.py

edge-test:
	cd digital/test && python3 test_ble_tx_edge.py

uart-test:
	cd digital/test && python3 test_ble_tx_uart.py

# debug UART (dbg_tx), SPS 8: all 80 sample offsets rebuild the waveform
dbg-test:
	cd digital/test && python3 test_ble_dbg_tx.py

chain-test:
	cd behavioral && python3 test_tx_chain.py

synth:
	cd digital/synth && TOP=$(TOP) SPS=$(SYNTH_SPS) yosys -c synth.tcl

gl-test: synth
	cd digital/test && GL=1 SPS=$(SYNTH_SPS) python3 $(GL_TEST)
	$(if $(filter ble_tx_uart,$(TOP)),cd digital/test && GL=1 DBG_KS="0 1 40 79" python3 test_ble_dbg_tx.py)

sta: synth
	cd digital/sta && TOP=$(TOP) SPS=$(SYNTH_SPS) sta -exit sta.tcl

# Only needed after changing the DAC step, SPS or code width.
lut:
	python3 digital/scripts/gen_gauss_lut.py

help:
	@sed -n '2,9p' Makefile
