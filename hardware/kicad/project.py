"""The KiCad project file and the library tables that point at the project library."""
import json
from pathlib import Path

import ids

RULES = dict(clearance=0.25, track=0.3, via=0.8, drill=0.4, edge=0.5, min_track=0.25)
TRACK_WIDTHS = [0.3, 0.5, 1.5, 2.0]

LIB_TABLE = '({kind}_lib_table\n\t(version 7)\n\t(lib (name "fan_controller") (type "KiCad") (uri "${{KIPRJMOD}}/{uri}") (options "") (descr "{descr}"))\n)\n'


def project_json(name):
    r = RULES
    return {
        "board": {
            "3dviewports": [],
            "design_settings": {
                "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "copper_text_size_h": 1.5, "copper_text_size_v": 1.5,
                             "copper_text_thickness": 0.3, "other_line_width": 0.15, "silk_line_width": 0.15, "silk_text_size_h": 1.0,
                             "silk_text_size_v": 1.0, "silk_text_thickness": 0.15},
                "rules": {"min_clearance": r["clearance"], "min_connection": 0.0, "min_copper_edge_clearance": r["edge"],
                          "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25, "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1,
                          "min_resolved_spokes": 2, "min_silk_clearance": 0.0, "min_text_height": 0.8, "min_text_thickness": 0.08,
                          "min_through_hole_diameter": r["drill"], "min_track_width": r["min_track"], "min_via_annular_width": 0.15,
                          "min_via_diameter": r["via"], "solder_mask_to_copper_clearance": 0.0, "use_height_for_length_calcs": True},
                "track_widths": [0.0] + TRACK_WIDTHS,
                "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": r["via"], "drill": r["drill"]}],
            },
            "ipc2581": {"dist": "", "distpn": "", "internal_id": "", "mfg": "", "mpn": ""},
            "layer_presets": [],
            "viewports": [],
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{name}.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [{"name": "Default", "bus_width": 12, "clearance": r["clearance"], "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                         "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                         "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647, "schematic_color": "rgba(0, 0, 0, 0.000)",
                         "track_width": r["track"], "via_diameter": r["via"], "via_drill": r["drill"], "wire_width": 6}],
            "meta": {"version": 4},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [],
        },
        "pcbnew": {"last_paths": {"gencad": "", "idf": "", "netlist": "", "plot": "", "pos_files": "", "specctra_dsn": "", "step": "", "svg": "", "vrml": ""},
                   "page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[str(ids.ROOT), "Root"]],
        "text_variables": {},
    }


def write_project(dir, name="fan_controller"):
    dir = Path(dir)
    dir.mkdir(parents=True, exist_ok=True)
    (dir / f"{name}.kicad_pro").write_text(json.dumps(project_json(name), indent=2) + "\n", encoding="utf-8")
    (dir / "sym-lib-table").write_text(LIB_TABLE.format(kind="sym", uri="fan_controller.kicad_sym", descr="Mini-360 buck module symbol"), encoding="utf-8")
    (dir / "fp-lib-table").write_text(LIB_TABLE.format(kind="fp", uri="fan_controller.pretty", descr="Mini-360 and radial polyfuse footprints"), encoding="utf-8")
