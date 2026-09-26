"""
Extensible Permit Type Schema Registry.

Allows defining any permit type (Hot Work, Confined Space, Working at Height,
Electrical/LOTO, Excavation, or future additions) declaratively with:
- metadata (name, description, badge color, icon)
- recommended hazards, PPE, and precautions
- dynamic field specifications (name, label, type, required, options, units, validation)
- backend validation rules executed server-side.
"""

from rest_framework.exceptions import ValidationError


PERMIT_TYPE_REGISTRY = {
    'HOT_WORK': {
        'code': 'HOT_WORK',
        'name': 'Hot Work Permit',
        'description': 'Authorizes activities involving open flames, sparks, welding, cutting, or grinding near potential flammables.',
        'color': '#ef4444',
        'bg_color': 'rgba(239, 68, 68, 0.15)',
        'icon': 'flame',
        'default_hazards': [
            'Open flame / Sparks',
            'Flammable vapours or gases',
            'Combustible materials within 10m',
            'High radiant heat / Hot slag',
            'Fumes and metal oxides',
        ],
        'default_ppe': [
            'Welding shield / Cutting goggles',
            'Leather welding apron & gloves',
            'Flame-resistant coveralls',
            'Steel-toe safety boots',
            'Earplugs / Ear defenders',
        ],
        'default_precautions': [
            'All combustible materials cleared within 10 metres radius',
            'Combustible floors wetted or covered with fire-resistant blankets',
            'Calibrated multi-gas detector deployed on site',
            'Fire watch person assigned and present during and 30m after work',
            'Appropriate fire extinguisher present at immediate work area',
            'Atmospheric gas test completed and signed off',
        ],
        'fields': [
            {
                'name': 'hot_work_type',
                'label': 'Type of Hot Work',
                'type': 'select',
                'required': True,
                'options': ['Welding', 'Grinding', 'Torch Cutting', 'Soldering', 'Thermal Spraying'],
                'help_text': 'Specific thermal or spark-generating process being executed.'
            },
            {
                'name': 'fire_watch_assigned',
                'label': 'Dedicated Fire Watch Personnel',
                'type': 'text',
                'required': True,
                'placeholder': 'Full name of assigned fire watch',
                'help_text': 'Designated individual with fire extinguisher stationed at site.'
            },
            {
                'name': 'fire_extinguisher_type',
                'label': 'Fire Extinguisher Present',
                'type': 'select',
                'required': True,
                'options': ['DCP (Dry Chemical Powder) 9kg', 'CO2 4.5kg', 'AFFF Foam 9L', 'Water Mist / Wet Chemical'],
                'help_text': 'Primary extinguishing medium deployed at the location.'
            },
            {
                'name': 'combustibles_cleared_radius_m',
                'label': 'Combustibles Cleared Radius',
                'type': 'number',
                'unit': 'metres',
                'required': True,
                'min': 5,
                'max': 50,
                'placeholder': '10',
                'help_text': 'Minimum 10 metres required by plant safety standards.'
            },
            {
                'name': 'gas_test_o2_pct',
                'label': 'Oxygen Level (O₂ %)',
                'type': 'number',
                'unit': '%',
                'required': True,
                'min': 0,
                'max': 30,
                'step': '0.1',
                'placeholder': '20.9',
                'help_text': 'Safe atmospheric range: 19.5% to 23.5%.'
            },
            {
                'name': 'gas_test_lel_pct',
                'label': 'Combustible Gas (LEL %)',
                'type': 'number',
                'unit': '% LEL',
                'required': True,
                'min': 0,
                'max': 100,
                'step': '0.1',
                'placeholder': '0.0',
                'help_text': 'Must be strictly below 10% LEL (Lower Explosive Limit) to authorize open flame.'
            },
            {
                'name': 'gas_test_time',
                'label': 'Gas Test Timestamp',
                'type': 'datetime-local',
                'required': True,
                'help_text': 'Time test was performed by certified safety tester (within 2 hours of planned start).'
            }
        ]
    },
    'CONFINED_SPACE': {
        'code': 'CONFINED_SPACE',
        'name': 'Confined Space Entry',
        'description': 'Authorizes entry into vessels, tanks, pits, silos, or pipelines with restricted entry/exit or hazardous atmospheres.',
        'color': '#8b5cf6',
        'bg_color': 'rgba(139, 92, 246, 0.15)',
        'icon': 'box',
        'default_hazards': [
            'Oxygen deficiency (< 19.5%) or enrichment (> 23.5%)',
            'Toxic gas accumulation (H2S, CO)',
            'Engulfment by bulk solids or liquids',
            'Restricted entry and egress points',
            'Mechanical agitation hazard',
        ],
        'default_ppe': [
            'Multi-gas 4-channel personal monitor',
            'Full body rescue harness with retrieval lifeline',
            'Supplied air respirator / SCBA (if IDLH atmosphere)',
            'Intrinsically safe headlamp (ATEX Zone 0)',
            'Continuous radio communication headset',
        ],
        'default_precautions': [
            'Process and utility lines blanked/blinded and locked out',
            'Mechanical and electrical drives de-energized and padlocked (LOTO)',
            'Space purged, cleaned, and forced-air ventilated continuously',
            'Pre-entry 4-gas atmospheric testing logged and verified',
            'Stationed standby attendant with communication link and hoist',
            'Emergency rescue plan briefed to all entrants and emergency team',
        ],
        'fields': [
            {
                'name': 'space_id',
                'label': 'Confined Space Identifier',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., Vessel V-102 or Digester Tank Pit 4',
                'help_text': 'Exact vessel, column, tank, or sump asset identifier.'
            },
            {
                'name': 'entry_point',
                'label': 'Designated Entry Point',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., Top Manway MW-01 (600mm dia)',
                'help_text': 'Designated access port equipped with ladder or tripod.'
            },
            {
                'name': 'standby_attendant_name',
                'label': 'Standby Attendant Name',
                'type': 'text',
                'required': True,
                'placeholder': 'Full name of stationed attendant',
                'help_text': 'Person stationed outside entry point. NEVER enters space.'
            },
            {
                'name': 'rescue_plan',
                'label': 'Rescue Plan & Equipment Available',
                'type': 'textarea',
                'required': True,
                'placeholder': 'Describe tripod hoist, retrieval winch, SCBA sets ready on standby, and emergency call protocol.',
                'help_text': 'Pre-staged rescue equipment and emergency response details.'
            },
            {
                'name': 'ventilation_method',
                'label': 'Ventilation Method',
                'type': 'select',
                'required': True,
                'options': ['Continuous Forced Mechanical Blower', 'Exhaust Extraction Fan', 'Natural Ventilation (Draft)'],
                'help_text': 'Active atmospheric turnover system.'
            },
            {
                'name': 'gas_test_o2_pct',
                'label': 'O₂ Level',
                'type': 'number',
                'unit': '%',
                'required': True,
                'step': '0.1',
                'placeholder': '20.9',
                'help_text': 'Must be 19.5% - 23.5%.'
            },
            {
                'name': 'gas_test_lel_pct',
                'label': 'LEL Level',
                'type': 'number',
                'unit': '% LEL',
                'required': True,
                'step': '0.1',
                'placeholder': '0.0',
                'help_text': 'Must be 0% or strictly < 10% LEL.'
            },
            {
                'name': 'gas_test_h2s_ppm',
                'label': 'H₂S Level',
                'type': 'number',
                'unit': 'ppm',
                'required': True,
                'step': '0.1',
                'placeholder': '0.0',
                'help_text': 'Must be strictly < 10 ppm (OSHA PEL).'
            },
            {
                'name': 'gas_test_co_ppm',
                'label': 'CO Level',
                'type': 'number',
                'unit': 'ppm',
                'required': True,
                'step': '1',
                'placeholder': '0',
                'help_text': 'Must be strictly < 25 ppm (OSHA/ACGIH TLV).'
            },
            {
                'name': 'gas_test_time',
                'label': 'Atmospheric Test Timestamp',
                'type': 'datetime-local',
                'required': True,
                'help_text': 'Time test performed prior to initial entry.'
            },
            {
                'name': 'entry_exit_log',
                'label': 'Entry & Egress Personnel Log',
                'type': 'textarea',
                'required': True,
                'placeholder': 'Log authorized entrants, entry timestamps, exit timestamps, and continuous attendant check-ins (e.g. Entrant 1: Amit Verma - In: 10:05, Out: 11:30 | Entrant 2: Suresh Pillai - In: 10:05, Out: 11:25).',
                'help_text': 'Stationed standby attendant mandatory record of all entrants inside the space.'
            }
        ]
    },
    'HEIGHT': {
        'code': 'HEIGHT',
        'name': 'Working at Height',
        'description': 'Authorizes work at elevations above 1.8 metres (6 feet) where fall risk is present.',
        'color': '#0ea5e9',
        'bg_color': 'rgba(14, 165, 233, 0.15)',
        'icon': 'arrow-up-right',
        'default_hazards': [
            'Fall from elevation',
            'Falling tools or dropped objects striking ground personnel',
            'Unstable working surface or slippery grating',
            'Strong wind / adverse weather conditions',
            'Overhead power lines in proximity',
        ],
        'default_ppe': [
            'Full body safety harness with double shock-absorbing lanyards',
            'Chin-strap safety helmet with impact resistance',
            'Tool lanyards / tethering pouches for all hand tools',
            'High-traction slip-resistant safety boots',
            'Hi-vis reflective vest',
        ],
        'default_precautions': [
            'Scaffolding inspected, certified, and tagged with green safety tag',
            '100% tie-off policy strictly enforced at all times',
            'Ground perimeter cordoned off with danger tape and signage',
            'Toe boards and intermediate guardrails verified in position',
            'Certified anchor points rated to 22.2 kN (5,000 lbs) verified',
            'Weather and wind speed (< 35 km/h) checked before ascent',
        ],
        'fields': [
            {
                'name': 'height_in_metres',
                'label': 'Work Height',
                'type': 'number',
                'unit': 'metres',
                'required': True,
                'min': 1.8,
                'max': 150,
                'step': '0.5',
                'placeholder': '6.5',
                'help_text': 'Height above finished floor or ground level.'
            },
            {
                'name': 'access_method',
                'label': 'Access Method',
                'type': 'select',
                'required': True,
                'options': [
                    'Certified Scaffolding (Green Tagged)',
                    'Mobile Elevated Work Platform (Boom Lift / Scissor Lift)',
                    'Secured Industrial Extension Ladder',
                    'Fixed Permanent Platform / Catwalk',
                    'Rope Access System'
                ],
                'help_text': 'Approved temporary or permanent elevated access mechanism.'
            },
            {
                'name': 'fall_arrest_equipment',
                'label': 'Fall Arrest System Specified',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., 2m Twin-leg elasticated lanyard with shock absorber',
                'help_text': 'Specific harness and lanyard configuration.'
            },
            {
                'name': 'anchor_point_checked',
                'label': 'Anchor Point Load Inspected & Certified',
                'type': 'boolean',
                'required': True,
                'help_text': 'Check to confirm anchor point withstands 22 kN certified test.'
            },
            {
                'name': 'anchor_point_location',
                'label': 'Anchor Point Location',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., Overhead I-Beam Web Stiffener Column D-4',
                'help_text': 'Identified structural anchor point for tie-off.'
            },
            {
                'name': 'barricading_below',
                'label': 'Drop-Zone Barricaded Below',
                'type': 'boolean',
                'required': True,
                'help_text': 'Physical red barricading tape and dropped-object warnings erected below.'
            }
        ]
    },
    'ELECTRICAL_LOTO': {
        'code': 'ELECTRICAL_LOTO',
        'name': 'Electrical / Isolation (LOTO)',
        'description': 'Authorizes work on de-energized electrical panels, motors, switchgear, and hazardous kinetic energy circuits.',
        'color': '#f59e0b',
        'bg_color': 'rgba(245, 158, 11, 0.15)',
        'icon': 'zap',
        'default_hazards': [
            'Electric shock / Electrocution',
            'Arc flash / Arc blast explosion',
            'Stored electrical charge in capacitor banks',
            'Inadvertent re-energization by third party',
            'Residual hydraulic or pneumatic stored energy',
        ],
        'default_ppe': [
            'Arc flash suit / face shield (cal/cm² rated to task)',
            'Dielectric insulated electrical gloves (Class 0/1 with leather protectors)',
            'Insulated dielectric safety footwear (18kV rated)',
            'Non-conductive safety glasses',
            'Cotton / natural fiber undergarments',
        ],
        'default_precautions': [
            'Energy isolation plan formulated and verified with single line diagram (SLD)',
            'All upstream isolators, circuit breakers, and switches racked out / open',
            'Personal red safety padlocks and danger tags attached to lockout hasps',
            'Stored electrical/capacitive/residual pressure dissipated',
            'Test Before Touch (proved-dead-test) executed with calibrated voltage detector',
            'Portable safety grounding / earthing applied to all phases',
        ],
        'fields': [
            {
                'name': 'equipment_tag',
                'label': 'Equipment Tag Number',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., MCC-04-BKR-12',
                'help_text': 'Asset tag for electrical distribution equipment or breaker.'
            },
            {
                'name': 'voltage_level',
                'label': 'Operating Voltage Level',
                'type': 'select',
                'required': True,
                'options': [
                    '415V AC (3-Phase Industrial Low Voltage)',
                    '3.3kV AC (Medium Voltage Drive)',
                    '6.6kV AC (Substation Feeder)',
                    '11kV AC (High Voltage Primary)',
                    '230V AC (Single Phase Control Circuit)',
                    '110V / 220V DC (Battery Bank / UPS System)'
                ],
                'help_text': 'System voltage present prior to isolation.'
            },
            {
                'name': 'isolation_points_list',
                'label': 'Isolation Points (Switches / Breakers / Valves)',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., Main Breaker CB-102, Control Fuse F-01, Suction Valve V-08',
                'help_text': 'Detailed list of physical points locked and tagged out.'
            },
            {
                'name': 'lock_numbers',
                'label': 'Lock Numbers Applied',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., LCK-9011, LCK-9012, LCK-9013',
                'help_text': 'Padlock IDs attached to isolation hasp or lockbox.'
            },
            {
                'name': 'tag_numbers',
                'label': 'Danger Tag Numbers',
                'type': 'text',
                'required': True,
                'placeholder': 'e.g., TAG-RED-4401, TAG-RED-4402',
                'help_text': 'Standard danger / do not operate tag serial numbers.'
            },
            {
                'name': 'earthing_applied',
                'label': 'Portable Safety Earthing / Grounding Clamps Applied',
                'type': 'boolean',
                'required': True,
                'help_text': 'Temporary earthing leads clamped onto phase conductors.'
            },
            {
                'name': 'tested_dead_by',
                'label': 'Tested Dead By (Authorized Electrical Engineer)',
                'type': 'text',
                'required': True,
                'placeholder': 'Full name of certified electrical engineer',
                'help_text': 'Competent person who performed calibrated live-dead-live meter test.'
            }
        ]
    },
    'EXCAVATION': {
        'code': 'EXCAVATION',
        'name': 'Excavation & Trenching',
        'description': 'Authorizes mechanical or manual earth cutting, trenching, or digging exceeding 0.3 metres depth.',
        'color': '#10b981',
        'bg_color': 'rgba(16, 185, 129, 0.15)',
        'icon': 'shovel',
        'default_hazards': [
            'Cave-in / trench wall collapse',
            'Striking underground high-voltage cables or gas pipelines',
            'Hazardous atmosphere accumulation in deep trench',
            'Water ingress / flooding',
            'Adjacent heavy vehicle vibration causing destabilization',
        ],
        'default_ppe': [
            'High-visibility vest (Class 2)',
            'Steel-toe puncture-resistant boots',
            'Safety helmet (Type 1 Class E)',
            'Heavy-duty leather work gloves',
            'Safety glasses with side shields',
        ],
        'default_precautions': [
            'Underground utility drawings consulted and CAT-scanner sweep conducted',
            'Soil classified and appropriate sloping/shoring/trench box installed',
            'Excavated soil placed at least 1.5 metres away from trench edge',
            'Access/egress ladders placed within 7.5 metres of all workers in trench',
            'Heavy machinery and trucks restricted within 3 metres of trench lip',
            'Atmospheric testing conducted if depth exceeds 1.2 metres',
        ],
        'fields': [
            {
                'name': 'excavation_depth_metres',
                'label': 'Excavation Depth',
                'type': 'number',
                'unit': 'metres',
                'required': True,
                'min': 0.3,
                'max': 20,
                'step': '0.1',
                'placeholder': '1.8',
                'help_text': 'Maximum depth of trench or pit.'
            },
            {
                'name': 'soil_type',
                'label': 'Soil Classification',
                'type': 'select',
                'required': True,
                'options': [
                    'Type A: Stable Clay / Hardpan (Cohesive)',
                    'Type B: Silt / Sandy Clay Loam (Medium Stability)',
                    'Type C: Gravel / Sand / Submerged Soil (Unstable)',
                    'Solid Bedrock'
                ],
                'help_text': 'Geotechnical soil profile to calculate collapse risk.'
            },
            {
                'name': 'underground_utilities_scanned',
                'label': 'Cable/Pipe Avoidance Scan (CAT/Genny) Completed',
                'type': 'boolean',
                'required': True,
                'help_text': 'Electronic locator sweep verified with plant underground drawings.'
            },
            {
                'name': 'shoring_sloping_method',
                'label': 'Protective System / Shoring Method',
                'type': 'select',
                'required': True,
                'options': [
                    'Hydraulic Aluminum Shoring Cylinders',
                    'Steel Trench Box Shield',
                    'Sloping / Benching (1:1.5 angle ratio)',
                    'Timber Shoring Sheet Piles',
                    'None (< 1.2m and non-hazardous)'
                ],
                'help_text': 'Engineering control preventing sidewall collapse.'
            },
            {
                'name': 'ladder_distance_metres',
                'label': 'Distance to Nearest Egress Ladder',
                'type': 'number',
                'unit': 'metres',
                'required': True,
                'min': 1,
                'max': 15,
                'placeholder': '5',
                'help_text': 'Must be maximum 7.5 metres away from any worker in the trench.'
            }
        ]
    }
}


def validate_type_data(permit_type, type_data):
    """
    Validates dynamic type_data dictionary against the schema definition for permit_type.
    Raises rest_framework.exceptions.ValidationError with informative field errors.
    """
    if permit_type not in PERMIT_TYPE_REGISTRY:
        raise ValidationError({'permit_type': f"Unknown permit type '{permit_type}'"})

    schema = PERMIT_TYPE_REGISTRY[permit_type]
    field_defs = {f['name']: f for f in schema['fields']}
    errors = {}

    for field_name, f_def in field_defs.items():
        val = type_data.get(field_name)

        if f_def.get('required') and (val is None or val == ''):
            errors[field_name] = f"{f_def['label']} is required for {schema['name']}."
            continue

        if val is None or val == '':
            continue

        # Type checking and constraints
        if f_def['type'] == 'number':
            try:
                num = float(val)
                if 'min' in f_def and num < f_def['min']:
                    errors[field_name] = f"{f_def['label']} must be at least {f_def['min']} {f_def.get('unit', '')}."
                if 'max' in f_def and num > f_def['max']:
                    errors[field_name] = f"{f_def['label']} cannot exceed {f_def['max']} {f_def.get('unit', '')}."
            except (ValueError, TypeError):
                errors[field_name] = f"{f_def['label']} must be a valid number."

        elif f_def['type'] == 'boolean':
            if not isinstance(val, bool) and str(val).lower() not in ['true', 'false', '1', '0']:
                errors[field_name] = f"{f_def['label']} must be true or false."

        elif f_def['type'] == 'select':
            if val not in f_def.get('options', []):
                errors[field_name] = f"Invalid option '{val}'. Allowed options: {', '.join(f_def['options'])}."

    # Specific safety rule validations:
    # 1. Hot work combustible gas LEL check
    if permit_type == 'HOT_WORK':
        lel = type_data.get('gas_test_lel_pct')
        if lel is not None:
            try:
                if float(lel) >= 10.0:
                    errors['gas_test_lel_pct'] = "SAFETY VIOLATION: Combustible gas LEL is >= 10%. Hot work strictly prohibited!"
            except (ValueError, TypeError):
                pass

        o2 = type_data.get('gas_test_o2_pct')
        if o2 is not None:
            try:
                o2_val = float(o2)
                if o2_val < 19.5 or o2_val > 23.5:
                    errors['gas_test_o2_pct'] = f"SAFETY ALERT: Oxygen level ({o2_val}%) outside safe window (19.5% - 23.5%)."
            except (ValueError, TypeError):
                pass

    # 2. Confined space gas checks
    if permit_type == 'CONFINED_SPACE':
        h2s = type_data.get('gas_test_h2s_ppm')
        if h2s is not None:
            try:
                if float(h2s) > 10.0:
                    errors['gas_test_h2s_ppm'] = "SAFETY VIOLATION: H₂S concentration exceeds OSHA limit (10 ppm). Entry prohibited!"
            except (ValueError, TypeError):
                pass

    if errors:
        raise ValidationError({'type_data': errors})

    return True
