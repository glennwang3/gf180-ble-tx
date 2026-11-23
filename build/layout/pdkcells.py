"""Wrap the GF180MCU PDK pcell generators (gdsfactory) into plain klayout.db cells."""
import os, sys, tempfile, hashlib
import klayout.db as db
PDK = os.environ.get("PDK_ROOT", "/foss/pdks") + "/gf180mcuD"
sys.path.insert(0, PDK + "/libs.tech/klayout/tech/pymacros")
os.environ.pop("PDK", None)
import gdsfactory as gf
try:
    from gdsfactory.gpdk import PDK as _GP
    _GP.activate()
except Exception:
    from gdsfactory.generic_tech import get_generic_pdk
    get_generic_pdk().activate()
import pya  # noqa: F401  (PDK cells import pya)
from cells._patches import patch_legacy_classes
patch_legacy_classes()
from cells.draw_fet import draw_nfet, draw_pfet
from cells.draw_cap_mim import draw_cap_mim
from cells.draw_res import draw_ppolyf_u_high_Rs_res, draw_ppolyf_res

_cache = {}


def _import(layout, builder, name):
    """run a PDK draw_* function in a scratch layout (it writes a temp GDS to the cwd), then copy
    the produced cell, flattened, into `layout` as `name`"""
    if name in _cache:
        return _cache[name]
    cwd = os.getcwd()
    tmp = tempfile.mkdtemp()
    os.chdir(tmp)
    try:
        src = db.Layout(); src.dbu = layout.dbu
        top = builder(src)
    finally:
        os.chdir(cwd)
    cell = layout.create_cell(name)
    for li in src.layer_indexes():
        info = src.get_info(li)
        r = db.Region(top.begin_shapes_rec(li))
        t = db.Texts(top.begin_shapes_rec(li))
        tl = layout.layer(info.layer, info.datatype)
        cell.shapes(tl).insert(r.merged().snapped(5, 5))   # PDK pcells emit some off-grid pads
        cell.shapes(tl).insert(t)
    _cache[name] = cell
    return cell


def nfet(layout, w, l=0.28, nf=1, gate="top", name=None):
    name = name or f"NFET_W{w:g}_L{l:g}_NF{nf}_{gate}".replace(".", "p")
    if name in _cache: return _cache[name]
    c = lambda L: draw_nfet(L, l_gate=l, w_gate=w, nf=nf, gate_con_pos=gate, sd_con_col=1, inter_sd_l=0.52,
                  grw=0.22, volt="3.3V", bulk="None")
    return _import(layout, c, name)


def pfet(layout, w, l=0.28, nf=1, gate="top", name=None):
    name = name or f"PFET_W{w:g}_L{l:g}_NF{nf}_{gate}".replace(".", "p")
    if name in _cache: return _cache[name]
    c = lambda L: draw_pfet(L, l_gate=l, w_gate=w, nf=nf, gate_con_pos=gate, sd_con_col=1, inter_sd_l=0.52,
                  grw=0.22, volt="3.3V", bulk="None")
    return _import(layout, c, name)


def mim(layout, w, l, name=None):
    name = name or f"MIM_{w:g}x{l:g}".replace(".", "p")
    if name in _cache: return _cache[name]
    return _import(layout, lambda L: draw_cap_mim(L, mim_option="MIM-B", metal_level="M6", lc=l, wc=w), name)


def ppoly_hr(layout, w, l, name=None):
    """ppolyf_u_1k (high-Rs) resistor"""
    name = name or f"RHR_W{w:g}_L{l:g}".replace(".", "p")
    if name in _cache: return _cache[name]
    return _import(layout, lambda L: draw_ppolyf_u_high_Rs_res(L, l_res=l, w_res=w, volt="3.3V"), name)


from cells.draw_cap_mos import draw_cap_mos


def moscap(layout, lc, wc, name=None):
    """cap_nmos_03v3 (inversion NMOS capacitor): gate = poly, S/D shorted (M1 U) = substrate side"""
    name = name or f"MOSCAP_L{lc:g}_W{wc:g}".replace(".", "p")
    if name in _cache: return _cache[name]
    return _import(layout, lambda L: draw_cap_mos(L, type="cap_nmos", lc=lc, wc=wc, volt="3.3V"), name)
