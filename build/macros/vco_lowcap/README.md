# Lower-capacitance A01 differential VCO

`Differential_VCO_low_cap.gds` contains the revised stand-alone `Differential_VCO` cell. `A01_VCO_low_cap.gds` contains the matching integrated `A01_topcell_short_clk` copy. The source is the A01 short-clock Schottky-doubler design used for the preceding BLE and coarse-tuning sweeps. The revised VCO stays in the same coordinate frame and retains the same circuit, device sizes, native MOSCAPs, and PLL interfaces.

The selected reroute changes the O2P and O3P paths on Metal2 through Metal4. Candidate selection considered extracted capacitance, worst P/N mismatch, design rules, and whether the extracted RF doubler produced both pulses. Wider changes reduced capacitance further in some trials and limited the useful high-frequency RF range. The selected version also fixes inherited Metal1 grid, via enclosure and tap-area markers.

## Physical checks

- The GF180 six-metal variant E main DRC deck reported zero markers for the stand-alone VCO and integrated A01 layout.
- The extracted RF partition matched the existing A01 device reference uniquely in Netgen, with zero device property errors.
- The sum of explicit extracted node capacitances, including coupling incident on each node, fell from 88.659 to 86.280 fF. This sum counts each mutual phase-to-phase capacitor at both of its endpoints. The worst P/N difference fell from 1.929 to 1.028 fF. The O1P change is +0.010 fF. See `node_capacitance.csv` for each node.

## Post-extraction tests at 3.30 V, SS and 125 °C

| VTUNE | Added ideal capacitance per node | RF output | Prescaler |
| --- | ---: | ---: | --- |
| 1.100 V | 0 | 2.49356 GHz | ÷33 |
| 1.180 V | 0 | 2.48371–2.48373 GHz | ÷32 and ÷33 |
| 1.700 V | 0 | 2.40278 GHz | ÷33 |
| 1.020 V | 0.25 fF | 2.48072 GHz | ÷33 |

All four conditions produced two threshold crossings per core cycle in the measurement window. The added capacitors model a symmetric extra load. The physical coarse bank, closed-loop acquisition and statistical yield remain to be evaluated. These RF tests used fixed control and a 2.05 V buffer tail bias.
