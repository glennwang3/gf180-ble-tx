"""Fail if any cocotb results file has a failing test, or if one is missing.

cocotb's runner exits 0 when run as a script even if tests fail, so CI runs
the test scripts and then checks their JUnit XML with this.

Usage: python scripts/check_cocotb_results.py RESULTS.xml [...]
"""

import sys
import xml.etree.ElementTree as ET

bad = 0
for path in sys.argv[1:]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        print(f"{path}: missing or unreadable ({e})")
        bad += 1
        continue
    cases = root.findall(".//testcase")
    failed = [c.get("name") for c in cases if c.find("failure") is not None or c.find("error") is not None]
    print(f"{path}: {len(cases) - len(failed)}/{len(cases)} passed" + (f", failed: {failed}" if failed else ""))
    bad += len(failed) + (len(cases) == 0)
sys.exit(1 if bad else 0)
