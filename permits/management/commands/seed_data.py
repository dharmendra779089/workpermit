"""
Database seed command for Opmaint CMMS Permit to Work (PTW) module.
Populates:
- 4 Users (one per role: Requester, Area Owner, Safety Officer, Admin)
- 2 Industrial Plants
- 4 Process Areas
- 7 Equipment items
- 12 Realistic Permits across all lifecycle states (Draft, Pending, Approved, Active, Expiring Soon, Suspended, Expired, Closed, Closed & Verified, Rejected, Cancelled)
- Audit trails, approvals, and dynamic type data for all 5 permit types!
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from permits.models import User, Plant, Area, Equipment, Permit, PermitApproval, PermitAuditLog


class Command(BaseCommand):
    help = "Seeds database with Opmaint CMMS initial plant, equipment, user, and permit data."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting database seeding for Opmaint CMMS PTW..."))

        # 1. Create Users
        default_pwd = "SafetyFirst@2026"

        requester, _ = User.objects.get_or_create(
            username="requester",
            defaults={
                "email": "requester@opmaint.com",
                "first_name": "Rahul",
                "last_name": "Sharma",
                "role": User.Role.REQUESTER,
                "badge_number": "REQ-8821",
                "phone": "+91 98401 22341",
            }
        )
        requester.set_password(default_pwd)
        requester.save()

        area_owner, _ = User.objects.get_or_create(
            username="areaowner",
            defaults={
                "email": "areaowner@opmaint.com",
                "first_name": "Priya",
                "last_name": "Nair",
                "role": User.Role.AREA_OWNER,
                "badge_number": "AO-4412",
                "phone": "+91 98402 33452",
            }
        )
        area_owner.set_password(default_pwd)
        area_owner.save()

        safety_officer, _ = User.objects.get_or_create(
            username="safety",
            defaults={
                "email": "safety@opmaint.com",
                "first_name": "Vikram",
                "last_name": "Singh",
                "role": User.Role.SAFETY_OFFICER,
                "badge_number": "SO-1099",
                "phone": "+91 98403 44563",
            }
        )
        safety_officer.set_password(default_pwd)
        safety_officer.save()

        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@opmaint.com",
                "first_name": "Tanzeel",
                "last_name": "Admin",
                "role": User.Role.ADMIN,
                "badge_number": "ADM-0001",
                "phone": "+91 98400 11223",
                "is_staff": True,
                "is_superuser": True,
            }
        )
        admin_user.set_password(default_pwd)
        admin_user.save()

        self.stdout.write(self.style.SUCCESS("[OK] 4 Users created (Requester, Area Owner, Safety Officer, Admin)."))

        # 2. Create Plants
        plant1, _ = Plant.objects.get_or_create(
            code="PLANT-CHE-01",
            defaults={
                "name": "Chennai Petrochemical Complex",
                "location": "Manali Industrial Corridor, Chennai, TN",
                "description": "Continuous hydrocarbon refining, catalytic cracking, and steam generation units."
            }
        )

        plant2, _ = Plant.objects.get_or_create(
            code="PLANT-ENN-02",
            defaults={
                "name": "Ennore Power & Gas Terminal",
                "location": "Ennore Port Zone, Chennai, TN",
                "description": "Natural gas distribution, cogeneration turbines, and high-voltage grid switchyard."
            }
        )

        self.stdout.write(self.style.SUCCESS("[OK] 2 Industrial Plants created."))

        # 3. Create Areas
        area1, _ = Area.objects.get_or_create(
            plant=plant1,
            code="AREA-CDU-01",
            defaults={
                "name": "Crude Distillation Unit (CDU-1)",
                "owner": area_owner,
                "description": "Atmospheric and vacuum distillation columns, heat exchanger trains, and crude furnace."
            }
        )
        area_owner.assigned_area = area1
        area_owner.save()

        area2, _ = Area.objects.get_or_create(
            plant=plant1,
            code="AREA-BLR-02",
            defaults={
                "name": "Boiler House & High Pressure Steam",
                "owner": area_owner,
                "description": "Boilers, deaerator, feed pumps, and superheater manifolds operating at 65 bar."
            }
        )

        area3, _ = Area.objects.get_or_create(
            plant=plant2,
            code="AREA-SWG-03",
            defaults={
                "name": "High Voltage Switchyard & Substation",
                "owner": None,
                "description": "415V, 3.3kV, and 11kV busbars, transformers, and circuit breaker banks."
            }
        )

        area4, _ = Area.objects.get_or_create(
            plant=plant2,
            code="AREA-TNK-04",
            defaults={
                "name": "Hydrocarbon Storage & Tank Farm",
                "owner": None,
                "description": "Above-ground and underground bulk storage tanks, manifold valves, and bund areas."
            }
        )

        self.stdout.write(self.style.SUCCESS("[OK] 4 Plant Process Areas created."))

        # 4. Create Equipment
        eq1, _ = Equipment.objects.get_or_create(
            tag_number="EQ-COL-101",
            defaults={
                "area": area1,
                "name": "Crude Distillation Column C-101",
                "criticality": Equipment.Criticality.HIGH,
                "description": "45-metre tall multi-stage fractionation column with hydrocarbon vapor trays."
            }
        )

        eq2, _ = Equipment.objects.get_or_create(
            tag_number="EQ-RCT-201",
            defaults={
                "area": area1,
                "name": "Catalytic Cracker Reactor R-201",
                "criticality": Equipment.Criticality.HIGH,
                "description": "Fluidized bed reactor vessel operating under cyclic catalyst circulation."
            }
        )

        eq3, _ = Equipment.objects.get_or_create(
            tag_number="EQ-PMP-102A",
            defaults={
                "area": area2,
                "name": "Boiler Feed Water Pump P-102A",
                "criticality": Equipment.Criticality.HIGH,
                "description": "Multi-stage high pressure boiler feed centrifugal pump with 415V motor drive."
            }
        )

        eq4, _ = Equipment.objects.get_or_create(
            tag_number="EQ-HDR-04",
            defaults={
                "area": area2,
                "name": "Steam Superheater Header SH-04",
                "criticality": Equipment.Criticality.MEDIUM,
                "description": "Steam distribution manifold lines and relief bypass piping."
            }
        )

        eq5, _ = Equipment.objects.get_or_create(
            tag_number="EQ-SWG-415V",
            defaults={
                "area": area3,
                "name": "Substation Main Switchgear Panel SWG-415V",
                "criticality": Equipment.Criticality.HIGH,
                "description": "Industrial low-voltage switchboard panel with air circuit breakers and bus couplers."
            }
        )

        eq6, _ = Equipment.objects.get_or_create(
            tag_number="EQ-UST-04",
            defaults={
                "area": area4,
                "name": "Underground Hydrocarbon Tank UST-04",
                "criticality": Equipment.Criticality.HIGH,
                "description": "500 cu.m underground enclosed storage vessel with top manway access."
            }
        )

        eq7, _ = Equipment.objects.get_or_create(
            tag_number="EQ-FLG-12",
            defaults={
                "area": area4,
                "name": "Manifold Transfer Flange Rack FM-12",
                "criticality": Equipment.Criticality.MEDIUM,
                "description": "Piping manifold for tank transfer valves and bypass lines."
            }
        )

        self.stdout.write(self.style.SUCCESS("[OK] 7 Critical Plant Equipment items created."))

        # 5. Clear and Seed 12 Permits across all statuses
        Permit.objects.all().delete()
        now = timezone.now()

        # Dummy signature PNG data URI for realistic audit trail demo
        dummy_sig = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='40'><path d='M10 30 Q 50 10, 80 25 T 150 15' fill='none' stroke='%230284c7' stroke-width='2.5'/></svg>"

        # --- Permit 1: DRAFT (Hot Work) ---
        p1 = Permit.objects.create(
            permit_number="PTW-2026-0001",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Welding structural gusset bracket on Transfer Flange Rack",
            description="Fabrication and MMA welding of reinforced carbon steel gusset plates on rack support leg.",
            requester=requester,
            contractor_name="Larsen & Toubro Heavy Fabrication",
            team_size=3,
            equipment=eq7,
            planned_start=now + timedelta(hours=2),
            planned_end=now + timedelta(hours=10),
            status=Permit.Status.DRAFT,
            hazards=["Open flame / Sparks", "Flammable vapours or gases", "Combustible materials within 10m"],
            ppe_required=["Welding shield / Cutting goggles", "Leather welding apron & gloves", "Flame-resistant coveralls", "Steel-toe safety boots"],
            precautions=["All combustible materials cleared within 10 metres radius", "Fire watch person assigned and present", "Appropriate fire extinguisher present at immediate work area"],
            type_data={
                "hot_work_type": "Welding",
                "fire_watch_assigned": "Karthik Subramanian",
                "fire_extinguisher_type": "DCP (Dry Chemical Powder) 9kg",
                "combustibles_cleared_radius_m": 12,
                "gas_test_o2_pct": 20.9,
                "gas_test_lel_pct": 0.0,
                "gas_test_time": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitAuditLog.objects.create(
            permit=p1, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="CREATED",
            from_status="NONE", to_status=Permit.Status.DRAFT,
            comment="Permit draft initialized by supervisor."
        )

        # --- Permit 2: PENDING_APPROVAL (Confined Space Entry) ---
        p2 = Permit.objects.create(
            permit_number="PTW-2026-0002",
            permit_type=Permit.PermitType.CONFINED_SPACE,
            title="Internal sludge cleaning & ultrasonic thickness survey inside Tank UST-04",
            description="Entry via top manway MW-01 for sludge removal, wall cleaning, and NDT thickness inspection.",
            requester=requester,
            contractor_name="Apex Industrial Cleaning Services",
            team_size=4,
            equipment=eq6,
            planned_start=now + timedelta(hours=3),
            planned_end=now + timedelta(hours=11),
            status=Permit.Status.PENDING_APPROVAL,
            hazards=["Oxygen deficiency (< 19.5%) or enrichment (> 23.5%)", "Toxic gas accumulation (H2S, CO)", "Restricted entry and egress points"],
            ppe_required=["Multi-gas 4-channel personal monitor", "Full body rescue harness with retrieval lifeline", "Intrinsically safe headlamp (ATEX Zone 0)"],
            precautions=["Process and utility lines blanked/blinded and locked out", "Space purged, cleaned, and forced-air ventilated continuously", "Pre-entry 4-gas atmospheric testing logged and verified", "Stationed standby attendant with communication link and hoist"],
            type_data={
                "space_id": "UST-04-MAIN-VESSEL",
                "entry_point": "Top Manway MW-01 (600mm dia)",
                "standby_attendant_name": "M. Selvam (Safety Attendant)",
                "rescue_plan": "Tripod hoist mounted over MW-01 with auto-locking winch. 2x 30-min SCBA sets staged at ground level.",
                "ventilation_method": "Continuous Forced Mechanical Blower",
                "gas_test_o2_pct": 20.8,
                "gas_test_lel_pct": 0.0,
                "gas_test_h2s_ppm": 0.0,
                "gas_test_co_ppm": 2,
                "gas_test_time": now.strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitAuditLog.objects.create(
            permit=p2, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="SUBMITTED",
            from_status=Permit.Status.DRAFT, to_status=Permit.Status.PENDING_APPROVAL,
            comment="Submitted for Area Owner and Safety Officer sign-off."
        )
        PermitApproval.objects.create(
            permit=p2, approver=area_owner, role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.PENDING
        )
        PermitApproval.objects.create(
            permit=p2, approver=safety_officer, role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.PENDING
        )

        # --- Permit 3: PENDING_APPROVAL (Hot Work - One approval granted, waiting for Safety Officer) ---
        p3 = Permit.objects.create(
            permit_number="PTW-2026-0003",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Grinding weld seam on Crude Distillation Column C-101 nozzle flange",
            description="Preparation of 8-inch nozzle face using angle grinder prior to RT inspection.",
            requester=requester,
            contractor_name="Reliable Mechanical Works",
            team_size=2,
            equipment=eq1,
            planned_start=now + timedelta(hours=1),
            planned_end=now + timedelta(hours=7),
            status=Permit.Status.PENDING_APPROVAL,
            hazards=["Open flame / Sparks", "High radiant heat / Hot slag"],
            ppe_required=["Welding shield / Cutting goggles", "Leather welding apron & gloves", "Flame-resistant coveralls"],
            precautions=["All combustible materials cleared within 10 metres radius", "Combustible floors wetted or covered with fire-resistant blankets", "Fire watch person assigned and present"],
            type_data={
                "hot_work_type": "Grinding",
                "fire_watch_assigned": "S. Rajesh Kumar",
                "fire_extinguisher_type": "DCP (Dry Chemical Powder) 9kg",
                "combustibles_cleared_radius_m": 10,
                "gas_test_o2_pct": 20.9,
                "gas_test_lel_pct": 0.0,
                "gas_test_time": now.strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitAuditLog.objects.create(
            permit=p3, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="SUBMITTED",
            from_status=Permit.Status.DRAFT, to_status=Permit.Status.PENDING_APPROVAL,
            comment="Submitted for approvals."
        )
        # Area Owner approved!
        PermitApproval.objects.create(
            permit=p3, approver=area_owner, role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.APPROVED,
            comment="Isolation verified on crude column. Spark containment curtains must be tied securely.",
            signature_data=dummy_sig, acted_at=now - timedelta(minutes=20)
        )
        PermitAuditLog.objects.create(
            permit=p3, actor=area_owner, actor_name=area_owner.get_full_name(),
            actor_role=area_owner.get_role_display(), action="APPROVED",
            from_status=Permit.Status.PENDING_APPROVAL, to_status=Permit.Status.PENDING_APPROVAL,
            comment="Area Owner sign-off completed."
        )
        # Safety Officer pending
        PermitApproval.objects.create(
            permit=p3, approver=safety_officer, role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.PENDING
        )

        # --- Permit 4: APPROVED (Electrical LOTO - Awaiting start time to activate) ---
        p4 = Permit.objects.create(
            permit_number="PTW-2026-0004",
            permit_type=Permit.PermitType.ELECTRICAL_LOTO,
            title="Annual contactor overhaul & relay testing on 415V Switchgear Panel",
            description="De-energization of busbar B, rack out breaker CB-04, and service vacuum contactor.",
            requester=requester,
            contractor_name="Siemens Industrial Services",
            team_size=3,
            equipment=eq5,
            planned_start=now + timedelta(minutes=45),  # starts in 45 mins -> cannot activate yet!
            planned_end=now + timedelta(hours=6),
            status=Permit.Status.APPROVED,
            hazards=["Electric shock / Electrocution", "Arc flash / Arc blast explosion"],
            ppe_required=["Arc flash suit / face shield (cal/cm² rated to task)", "Dielectric insulated electrical gloves", "Insulated dielectric safety footwear (18kV rated)"],
            precautions=["Energy isolation plan formulated and verified with single line diagram", "All upstream isolators, circuit breakers, and switches racked out", "Personal red safety padlocks and danger tags attached", "Test Before Touch executed with calibrated voltage detector"],
            type_data={
                "equipment_tag": "EQ-SWG-415V-BKR4",
                "voltage_level": "415V AC (3-Phase Industrial Low Voltage)",
                "isolation_points_list": "Incomer Breaker ACB-01, Feeder Switch SW-12, Bus Tie Coupler BC-02",
                "lock_numbers": "LCK-RED-8801, LCK-RED-8802",
                "tag_numbers": "DANGER-TAG-4101",
                "earthing_applied": True,
                "tested_dead_by": "Venkatesh Rao (Certified Electrical Lead)"
            }
        )
        PermitApproval.objects.create(
            permit=p4, approver=area_owner, role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.APPROVED,
            comment="Feeder lockout scheduled with operations log.",
            signature_data=dummy_sig, acted_at=now - timedelta(hours=1)
        )
        PermitApproval.objects.create(
            permit=p4, approver=safety_officer, role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.APPROVED,
            comment="LOTO procedure and zero energy protocol verified.",
            signature_data=dummy_sig, acted_at=now - timedelta(minutes=30)
        )
        PermitAuditLog.objects.create(
            permit=p4, actor=safety_officer, actor_name=safety_officer.get_full_name(),
            actor_role="SYSTEM_EVALUATOR", action="FULLY_APPROVED",
            from_status=Permit.Status.PENDING_APPROVAL, to_status=Permit.Status.APPROVED,
            comment="All approvals in place. Activation unlocks at planned start time."
        )

        # --- Permit 5: ACTIVE (Hot Work - Active right now, countdown running) ---
        p5 = Permit.objects.create(
            permit_number="PTW-2026-0005",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Cutting damaged anchor bolts on Reactor R-201 skirt support",
            description="Oxy-acetylene torch cutting of sheared anchor studs on catalytic cracker pedestal.",
            requester=requester,
            contractor_name="Larsen & Toubro Heavy Fabrication",
            team_size=4,
            equipment=eq2,
            planned_start=now - timedelta(hours=2),
            planned_end=now + timedelta(hours=4),
            actual_start=now - timedelta(hours=1, minutes=45),
            status=Permit.Status.ACTIVE,
            hazards=["Open flame / Sparks", "Flammable vapours or gases", "High radiant heat / Hot slag"],
            ppe_required=["Welding shield / Cutting goggles", "Leather welding apron & gloves", "Flame-resistant coveralls"],
            precautions=["All combustible materials cleared within 10 metres radius", "Calibrated multi-gas detector deployed on site", "Fire watch person assigned and present", "Appropriate fire extinguisher present at immediate work area"],
            type_data={
                "hot_work_type": "Torch Cutting",
                "fire_watch_assigned": "D. Ananth (Qualified Fire Watch)",
                "fire_extinguisher_type": "CO2 4.5kg",
                "combustibles_cleared_radius_m": 15,
                "gas_test_o2_pct": 20.9,
                "gas_test_lel_pct": 0.0,
                "gas_test_time": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitApproval.objects.create(
            permit=p5, approver=area_owner, role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.APPROVED, signature_data=dummy_sig, acted_at=now - timedelta(hours=3)
        )
        PermitApproval.objects.create(
            permit=p5, approver=safety_officer, role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.APPROVED, signature_data=dummy_sig, acted_at=now - timedelta(hours=2, minutes=30)
        )
        PermitAuditLog.objects.create(
            permit=p5, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="ACTIVATED",
            from_status=Permit.Status.APPROVED, to_status=Permit.Status.ACTIVE,
            comment="Torch cutting started on site."
        )

        # --- Permit 6: ACTIVE & EXPIRING SOON (< 2 hours remaining! Amber Alert demonstration) ---
        p6 = Permit.objects.create(
            permit_number="PTW-2026-0006",
            permit_type=Permit.PermitType.HEIGHT,
            title="Inspection of overhead vapor line insulation at 18m elevation on Column C-101",
            description="Climbing certified scaffolding platform to inspect aluminum cladding and insulation integrity.",
            requester=requester,
            contractor_name="SkyAccess Scaffolding & NDT",
            team_size=2,
            equipment=eq1,
            planned_start=now - timedelta(hours=3),
            planned_end=now + timedelta(minutes=45),  # 45 minutes left -> EXPIRING SOON!
            actual_start=now - timedelta(hours=2, minutes=50),
            status=Permit.Status.ACTIVE,
            hazards=["Fall from elevation", "Falling tools or dropped objects striking ground personnel"],
            ppe_required=["Full body safety harness with double shock-absorbing lanyards", "Chin-strap safety helmet with impact resistance", "Tool lanyards / tethering pouches for all hand tools"],
            precautions=["Scaffolding inspected, certified, and tagged with green safety tag", "100% tie-off policy strictly enforced at all times", "Ground perimeter cordoned off with danger tape and signage"],
            type_data={
                "height_in_metres": 18.5,
                "access_method": "Certified Scaffolding (Green Tagged)",
                "fall_arrest_equipment": "Twin-leg elastomeric lanyard with energy absorber",
                "anchor_point_checked": True,
                "anchor_point_location": "Scaffold structural upright ledger rosette",
                "barricading_below": True
            }
        )
        PermitApproval.objects.create(
            permit=p6, approver=area_owner, role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.APPROVED, signature_data=dummy_sig, acted_at=now - timedelta(hours=4)
        )
        PermitApproval.objects.create(
            permit=p6, approver=safety_officer, role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.APPROVED, signature_data=dummy_sig, acted_at=now - timedelta(hours=3, minutes=30)
        )
        PermitAuditLog.objects.create(
            permit=p6, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="ACTIVATED",
            from_status=Permit.Status.APPROVED, to_status=Permit.Status.ACTIVE,
            comment="Scaffold ascent initiated."
        )

        # --- Permit 7: SUSPENDED (Confined Space - Gas alarm triggered!) ---
        p7 = Permit.objects.create(
            permit_number="PTW-2026-0007",
            permit_type=Permit.PermitType.CONFINED_SPACE,
            title="Internal vessel sandblasting in Chemical Storage Tank UST-04",
            description="Abrasive blast cleaning inside underground storage compartment.",
            requester=requester,
            contractor_name="Apex Industrial Cleaning Services",
            team_size=3,
            equipment=eq6,
            planned_start=now - timedelta(hours=4),
            planned_end=now + timedelta(hours=4),
            actual_start=now - timedelta(hours=3, minutes=30),
            status=Permit.Status.SUSPENDED,
            hazards=["Toxic gas accumulation (H2S, CO)", "Oxygen deficiency (< 19.5%) or enrichment (> 23.5%)"],
            ppe_required=["Multi-gas 4-channel personal monitor", "Full body rescue harness with retrieval lifeline", "Supplied air respirator / SCBA (if IDLH atmosphere)"],
            precautions=["Space purged, cleaned, and forced-air ventilated continuously", "Pre-entry 4-gas atmospheric testing logged and verified", "Stationed standby attendant with communication link and hoist"],
            type_data={
                "space_id": "UST-04-SECTION-B",
                "entry_point": "North Manhole MH-02",
                "standby_attendant_name": "R. Vignesh",
                "rescue_plan": "Harness extraction crane and standby air manifold.",
                "ventilation_method": "Continuous Forced Mechanical Blower",
                "gas_test_o2_pct": 20.8,
                "gas_test_lel_pct": 2.0,
                "gas_test_h2s_ppm": 1.0,
                "gas_test_co_ppm": 4,
                "gas_test_time": (now - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitAuditLog.objects.create(
            permit=p7, actor=safety_officer, actor_name=safety_officer.get_full_name(),
            actor_role=safety_officer.get_role_display(), action="SUSPENDED",
            from_status=Permit.Status.ACTIVE, to_status=Permit.Status.SUSPENDED,
            comment="EMERGENCY SUSPENSION: Fixed VOC gas monitor channel 3 tripped alarm at 14:15. Evacuated all workers immediately."
        )

        # --- Permit 8: EXPIRED (Hot Work - Past validity window, auto-expired) ---
        p8 = Permit.objects.create(
            permit_number="PTW-2026-0008",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Replace corroded bypass drain pipe on Steam Superheater SH-04",
            description="TIG welding of replacement 2-inch ASTM A335 P11 alloy steel steam tubing.",
            requester=requester,
            contractor_name="Reliable Mechanical Works",
            team_size=2,
            equipment=eq4,
            planned_start=now - timedelta(days=2),
            planned_end=now - timedelta(days=1),
            status=Permit.Status.EXPIRED,
            hazards=["Open flame / Sparks", "High radiant heat / Hot slag"],
            ppe_required=["Welding shield / Cutting goggles", "Leather welding apron & gloves"],
            precautions=["All combustible materials cleared within 10 metres radius", "Fire watch person assigned and present"],
            type_data={
                "hot_work_type": "Welding",
                "fire_watch_assigned": "S. Rajesh Kumar",
                "fire_extinguisher_type": "DCP (Dry Chemical Powder) 9kg",
                "combustibles_cleared_radius_m": 10,
                "gas_test_o2_pct": 20.9,
                "gas_test_lel_pct": 0.0,
                "gas_test_time": (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitAuditLog.objects.create(
            permit=p8, actor=None, actor_name="SYSTEM MONITOR",
            actor_role="SYSTEM", action="EXPIRED",
            from_status=Permit.Status.APPROVED, to_status=Permit.Status.EXPIRED,
            comment=f"Permit validity window expired at {(now - timedelta(days=1)).isoformat()}. Expired permits can never be reactivated."
        )

        # --- Permit 9: CLOSED (Awaiting Safety Officer verification) ---
        p9 = Permit.objects.create(
            permit_number="PTW-2026-0009",
            permit_type=Permit.PermitType.ELECTRICAL_LOTO,
            title="Replace mechanical seal & align drive motor on Feed Water Pump P-102A",
            description="Replaced cartridge seal, checked pump shaft runout, laser aligned 415V motor coupling.",
            requester=requester,
            contractor_name="Siemens Industrial Services",
            team_size=3,
            equipment=eq3,
            planned_start=now - timedelta(hours=6),
            planned_end=now - timedelta(hours=1),
            actual_start=now - timedelta(hours=5, minutes=30),
            actual_end=now - timedelta(hours=1, minutes=10),
            closed_at=now - timedelta(hours=1, minutes=10),
            status=Permit.Status.CLOSED,
            completion_notes="Seal replacement completed successfully. Coupling alignment within 0.03mm. LOTO padlocks removed and returned to lockbox.",
            hazards=["Electric shock / Electrocution"],
            ppe_required=["Dielectric insulated electrical gloves", "Non-conductive safety glasses"],
            precautions=["All upstream isolators, circuit breakers, and switches racked out", "Personal red safety padlocks and danger tags attached"],
            type_data={
                "equipment_tag": "EQ-PMP-102A-MTR",
                "voltage_level": "415V AC (3-Phase Industrial Low Voltage)",
                "isolation_points_list": "MCC-BLR-02 Feeder 4A",
                "lock_numbers": "LCK-RED-1092",
                "tag_numbers": "DANGER-TAG-1092",
                "earthing_applied": True,
                "tested_dead_by": "Venkatesh Rao"
            }
        )
        PermitAuditLog.objects.create(
            permit=p9, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="CLOSED",
            from_status=Permit.Status.ACTIVE, to_status=Permit.Status.CLOSED,
            comment="Work completed. Awaiting safety officer site inspection."
        )

        # --- Permit 10: CLOSED_VERIFIED (Archived & fully verified) ---
        p10 = Permit.objects.create(
            permit_number="PTW-2026-0010",
            permit_type=Permit.PermitType.HEIGHT,
            title="Install permanent safety cable lifeline on Boiler House Roof",
            description="Anchored 8mm stainless steel horizontal lifeline system to structural purlins.",
            requester=requester,
            contractor_name="SkyAccess Scaffolding & NDT",
            team_size=2,
            equipment=eq4,
            planned_start=now - timedelta(days=3),
            planned_end=now - timedelta(days=2),
            actual_start=now - timedelta(days=3),
            actual_end=now - timedelta(days=2, hours=2),
            closed_at=now - timedelta(days=2, hours=2),
            closure_verified_by=safety_officer,
            closure_verified_at=now - timedelta(days=2, hours=1),
            closure_verification_notes="Walk-around verified. Lifeline tensioned and tested. Scaffolding dismantled and ground cleared. All permits closed.",
            status=Permit.Status.CLOSED_VERIFIED,
            completion_notes="Lifeline pull-tested to 12 kN. Swaged end fittings stamped.",
            hazards=["Fall from elevation"],
            ppe_required=["Full body safety harness with double shock-absorbing lanyards"],
            precautions=["100% tie-off policy strictly enforced at all times"],
            type_data={
                "height_in_metres": 14.0,
                "access_method": "Fixed Permanent Platform / Catwalk",
                "fall_arrest_equipment": "Self-retracting lifeline (SRL)",
                "anchor_point_checked": True,
                "anchor_point_location": "Roof Main Trusses TR-1 to TR-5",
                "barricading_below": True
            }
        )
        PermitAuditLog.objects.create(
            permit=p10, actor=safety_officer, actor_name=safety_officer.get_full_name(),
            actor_role=safety_officer.get_role_display(), action="CLOSED_VERIFIED",
            from_status=Permit.Status.CLOSED, to_status=Permit.Status.CLOSED_VERIFIED,
            comment=p10.closure_verification_notes
        )

        # --- Permit 11: REJECTED (Safety violation caught before approval) ---
        p11 = Permit.objects.create(
            permit_number="PTW-2026-0011",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Open torch heating of frozen drain valve on Tank UST-04",
            description="Use propane torch to thaw frozen valve body.",
            requester=requester,
            contractor_name="QuickFix Maintenance",
            team_size=2,
            equipment=eq6,
            planned_start=now - timedelta(hours=10),
            planned_end=now - timedelta(hours=4),
            status=Permit.Status.REJECTED,
            hazards=["Open flame / Sparks", "Flammable vapours or gases"],
            ppe_required=["Welding shield / Cutting goggles"],
            precautions=["Fire watch person assigned and present"],
            type_data={
                "hot_work_type": "Welding",
                "fire_watch_assigned": "T. Murugan",
                "fire_extinguisher_type": "Water Mist / Wet Chemical",
                "combustibles_cleared_radius_m": 3,  # Violation: only 3m!
                "gas_test_o2_pct": 20.8,
                "gas_test_lel_pct": 8.5,
                "gas_test_time": (now - timedelta(hours=11)).strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitApproval.objects.create(
            permit=p11, approver=safety_officer, role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.REJECTED,
            comment="CRITICAL REJECTION: Open torch heating prohibited on hydrocarbon storage tank valve. Combustible clearance is only 3m (minimum 10m required) and LEL is at 8.5%. Use low-pressure steam tracing instead.",
            acted_at=now - timedelta(hours=9)
        )
        PermitAuditLog.objects.create(
            permit=p11, actor=safety_officer, actor_name=safety_officer.get_full_name(),
            actor_role=safety_officer.get_role_display(), action="REJECTED",
            from_status=Permit.Status.PENDING_APPROVAL, to_status=Permit.Status.REJECTED,
            comment="Rejected due to unacceptable explosion risk."
        )

        # --- Permit 12: CANCELLED (Cancelled by requester) ---
        p12 = Permit.objects.create(
            permit_number="PTW-2026-0012",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Weld support stiffeners on Steam Superheater Header SH-04",
            description="Reinforcement welding on piping hanger.",
            requester=requester,
            contractor_name="Reliable Mechanical Works",
            team_size=2,
            equipment=eq4,
            planned_start=now + timedelta(days=1),
            planned_end=now + timedelta(days=1, hours=8),
            status=Permit.Status.CANCELLED,
            hazards=["Open flame / Sparks"],
            ppe_required=["Welding shield / Cutting goggles"],
            precautions=["All combustible materials cleared within 10 metres radius"],
            type_data={
                "hot_work_type": "Welding",
                "fire_watch_assigned": "S. Rajesh Kumar",
                "fire_extinguisher_type": "DCP (Dry Chemical Powder) 9kg",
                "combustibles_cleared_radius_m": 10,
                "gas_test_o2_pct": 20.9,
                "gas_test_lel_pct": 0.0,
                "gas_test_time": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
            }
        )
        PermitAuditLog.objects.create(
            permit=p12, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="CANCELLED",
            from_status=Permit.Status.DRAFT, to_status=Permit.Status.CANCELLED,
            comment="Cancelled: Client rescheduled maintenance shutdown."
        )

        # --- Permit 13: EXCAVATION (Demonstrates 5th extensible permit type!) ---
        p13 = Permit.objects.create(
            permit_number="PTW-2026-0013",
            permit_type=Permit.PermitType.EXCAVATION,
            title="Trenching for underground fire hydrant pipeline replacement",
            description="1.8m deep trench excavation alongside Tank Farm access perimeter road.",
            requester=requester,
            contractor_name="Afcons Infrastructure Civils",
            team_size=5,
            equipment=eq6,
            planned_start=now + timedelta(hours=4),
            planned_end=now + timedelta(hours=14),
            status=Permit.Status.PENDING_APPROVAL,
            hazards=["Cave-in / trench wall collapse", "Striking underground high-voltage cables or gas pipelines"],
            ppe_required=["High-visibility vest (Class 2)", "Steel-toe puncture-resistant boots", "Safety helmet (Type 1 Class E)"],
            precautions=["Underground utility drawings consulted and CAT-scanner sweep conducted", "Soil classified and appropriate sloping/shoring/trench box installed", "Access/egress ladders placed within 7.5 metres of all workers in trench"],
            type_data={
                "excavation_depth_metres": 1.8,
                "soil_type": "Type B: Silt / Sandy Clay Loam (Medium Stability)",
                "underground_utilities_scanned": True,
                "shoring_sloping_method": "Steel Trench Box Shield",
                "ladder_distance_metres": 6.0
            }
        )
        PermitApproval.objects.create(
            permit=p13, approver=safety_officer, role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.PENDING
        )
        PermitApproval.objects.create(
            permit=p13, approver=area_owner, role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.PENDING
        )
        PermitAuditLog.objects.create(
            permit=p13, actor=requester, actor_name=requester.get_full_name(),
            actor_role=requester.get_role_display(), action="SUBMITTED",
            from_status=Permit.Status.DRAFT, to_status=Permit.Status.PENDING_APPROVAL,
            comment="Submitted for civil & safety clearance."
        )

        self.stdout.write(self.style.SUCCESS(f"[OK] 13 Real-world Permits seeded across all 10 state machine statuses and 5 permit types!"))
        self.stdout.write(self.style.NOTICE("=" * 60))
        self.stdout.write(self.style.NOTICE("Demo Credentials:"))
        self.stdout.write(self.style.NOTICE("  1. Requester:      requester@opmaint.com  /  SafetyFirst@2026"))
        self.stdout.write(self.style.NOTICE("  2. Area Owner:     areaowner@opmaint.com  /  SafetyFirst@2026"))
        self.stdout.write(self.style.NOTICE("  3. Safety Officer: safety@opmaint.com     /  SafetyFirst@2026"))
        self.stdout.write(self.style.NOTICE("  4. Admin:          admin@opmaint.com      /  SafetyFirst@2026"))
        self.stdout.write(self.style.NOTICE("=" * 60))
