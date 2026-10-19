"""Frozen source facts and explicitly separate demonstration choices."""
import copy

SOURCES = {
    "sop": {"url": "https://www.genscript.com/gsfiles/techfiles/CFXpress_Ecoli_Cell-free_Kit_Instruction_Manual.pdf",
            "version": "v1.0, 2025-06; accessed 2026-10-15", "pages": [4, 6]},
    "fluent": {"url": "https://lifesciences.tecan.com/fluent-laboratory-automation-workstation",
               "section": "Fluent 1080; accessed 2026-10-15"},
    "tips": {"url": "https://www.tecan.com/fluent-automated-workstation",
             "section": "Fluent Liquid Handler Specifications; accessed 2026-10-15"},
    "id5": {"url": "https://www.moleculardevices.com/sites/default/files/en/assets/brochures/br/spectramax-id5-multi-mode-microplate-reader.pdf",
            "version": "12/20 2134B, original iD5", "pages": [7]},
    "plate": {"url": "https://www.corning.com/catalog/cls/documents/selection-guides/CLS-DD-081.pdf",
              "section": "96-well biochemical assay plates, Cat. 3915"},
    "plate_geometry": {"url": "https://raw.githubusercontent.com/Opentrons/opentrons/6c00265bace1798d5a50bf5baa5357ab77ae97eb/shared-data/labware/definitions/2/corning_96_wellplate_360ul_flat/2.json",
                       "license": "Apache-2.0 (Opentrons shared-data); geometric reference, not 3915-specific CAD"},
    "facility_fluent": {"url": "https://infrasynbio.siat.ac.cn/platform/instrumentation/19",
                        "status": "catalog model/location rechecked 2026-10-15; actual installed options unverified",
                        "evidence": "sources/siat-19.json"},
    "facility_id5": {"url": "https://infrasynbio.siat.ac.cn/platform/instrumentation/67",
                     "status": "catalog model/location rechecked 2026-10-15; actual method unverified",
                     "evidence": "sources/siat-67.json"},
    "asset_search": {"url": "https://github.com/mbzuai-nlp/ChemLab-Assets",
                     "status": "no exact Fluent 1080 / SpectraMax iD5 asset located; do not relabel other instruments",
                     "license": "code MIT; assets CC BY-NC 4.0; none of these instrument meshes redistributed"},
}

UNKNOWN = [
    "Fluent actual installed arm, DiTi adapter, 1.5 mL tube carrier, deck coordinates and cold-source compatibility",
    "Validated pipetting range, dead volumes, liquid class and precision for this installed configuration",
    "cellfreeMIX composition, lot, activity and DNA compatibility (operator-supplied; not reconstructed)",
    "Thermomixer model, tube fit, shaking rpm, evaporation control and transfer cold-chain duration",
    "Physical plate Cat.3915 availability, reader method, gain, focal height, bandwidths and calibration",
    "Actual fluorescence, GFP yield and biological performance; no hardware connected",
]


def cards():
    return {
        "sources": copy.deepcopy(SOURCES), "unknowns": list(UNKNOWN),
        "verified_public_facts": {
            "reaction": {"typical_ul": 50, "vessel": "sterile nuclease-free 1.5/2 mL tube", "source": "sop p4"},
            "incubation": {"temperature_c": 30, "duration_hours_range": [3, 6],
                           "shaking": "vigorous; numeric rpm unspecified", "assembly_and_stop": "on ice", "source": "sop p4"},
            "gfp_read": {"excitation_nm": 488, "emission_nm": 525, "source": "sop p6"},
            "fluent_1080": {"footprint_mm": [2150, 780], "height_mm": None,
                            "source": "Fluent manual 399706 V2.7 p41; overall D923, footprint D780", "configuration": "optional arms; site configuration unverified",
                            "facility_location": "E building / 1F / 0115", "location_source": "facility_fluent"},
            "id5": {"envelope_whd_mm": [532, 401, 598], "plate_wells": [6, 384],
                    "excitation_mono_nm": [250, 830], "emission_mono_nm": [270, 850], "source": "id5 p7",
                    "facility_location": "E building / 2F / 0202", "location_source": "facility_id5"},
            "read_plate": {"candidate": "Corning 3915, black PS, flat, 96 wells, 360 uL capacity", "source": "plate"},
            "tips": {"candidate": "Tecan 200 uL DiTi; installed adapter and tube carrier unknown", "source": "tips"},
        },
        "demo_configuration": {
            "label": "DEMONSTRATION ONLY; not a validated kit recipe or installed-device method",
            "replicates_per_group": 3, "groups": ["sfGFP", "no-template"],
            "reaction_ul": 50, "premixed_MIX_ul": 45, "DNA_or_water_ul": 5,
            "DNA_stock_ng_per_ul": 100, "positive_final_DNA_ng_per_ul": 10,
            "source_inventory_ul": {"MIX": 400, "DNA": 100, "WATER": 1000},
            "reserved_dead_volume_ul": {"MIX": 20, "DNA": 5, "WATER": 20},
            "pipetting_assumed_range_ul": [5, 200], "incubation_seconds": 10800,
            "read_aliquot_ul": 20, "read_diluent_ul": 80, "dilution_factor": 5,
            "reader": {"mode": "FI", "excitation_nm": 488, "emission_nm": 525,
                       "gain": None, "bandwidth_nm": None, "focal_height_mm": None,
                       "read_direction": "top (demo assumption)"},
            "geometry": "schematic layout; interfaces and Fluent height are demonstration coordinates",
            "MIX_liquid_model": "water-like volume bookkeeping; manual premix is opaque",
        },
        "validation_scope": {"software_ledger": True, "PlanIR_virtual_deck": True,
                             "vendor_motion_simulation": False, "geometry_collision_validation": False,
                             "installed_hardware_compatibility": False, "biological_validation": False,
                             "onsite_guidance_ready": False},
    }
