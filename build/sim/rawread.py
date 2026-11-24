"""Minimal ngspice raw-file reader (binary or ascii, real transient data)."""
import numpy as np


def read_raw(fn):
    with open(fn, "rb") as f:
        data = f.read()
    hdr_end = data.find(b"Binary:\n")
    binary = hdr_end >= 0
    if not binary:
        hdr_end = data.find(b"Values:\n")
    hdr = data[:hdr_end].decode("latin1").splitlines()
    nvar = int([l for l in hdr if l.startswith("No. Variables:")][0].split(":")[1])
    npts = int([l for l in hdr if l.startswith("No. Points:")][0].split(":")[1])
    i = [k for k, l in enumerate(hdr) if l.startswith("Variables:")][0]
    names = [hdr[i + 1 + k].split()[1].lower() for k in range(nvar)]
    body = data[hdr_end + 8:]
    if binary:
        arr = np.frombuffer(body[:8 * nvar * npts], dtype="<f8").reshape(npts, nvar)
    else:
        vals = [float(x.split()[-1]) for x in body.decode().split("\n") if x.strip()]
        arr = np.array(vals).reshape(npts, nvar)
    return {n: arr[:, k] for k, n in enumerate(names)}
