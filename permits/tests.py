"""
Unit and integration tests for Opmaint Permit to Work (PTW) CMMS module.
Focuses on the state machine safety invariants, permission rules, and data model validation.
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import ValidationError, PermissionDenied

from permits.models import User, Plant, Area, Equipment, Permit, PermitApproval, PermitAuditLog
from permits.services import PermitStateMachine, ConflictDetector
from permits.schemas import validate_type_data


class PermitSafetyRulesTestCase(TestCase):
    def setUp(self):
        # 1. Create Users
        self.requester = User.objects.create_user(
            username="tech_rahul", email="rahul@opmaint.com", password="password123",
            role=User.Role.REQUESTER, first_name="Rahul", last_name="Sharma"
        )
        self.area_owner_1 = User.objects.create_user(
            username="ao_priya", email="priya@opmaint.com", password="password123",
            role=User.Role.AREA_OWNER, first_name="Priya", last_name="Nair"
        )
        self.area_owner_2 = User.objects.create_user(
            username="ao_rajesh", email="rajesh@opmaint.com", password="password123",
            role=User.Role.AREA_OWNER, first_name="Rajesh", last_name="Kumar"
        )
        self.safety_officer = User.objects.create_user(
            username="so_vikram", email="vikram@opmaint.com", password="password123",
            role=User.Role.SAFETY_OFFICER, first_name="Vikram", last_name="Singh"
        )
        self.admin = User.objects.create_user(
            username="admin_tanzeel", email="tanzeel@opmaint.com", password="password123",
            role=User.Role.ADMIN, first_name="Tanzeel", last_name="Admin"
        )

        # 2. Dual-Role User to test "Cannot approve own permit even if role allows it"
        self.dual_role_user = User.objects.create_user(
            username="safety_lead", email="lead@opmaint.com", password="password123",
            role=User.Role.SAFETY_OFFICER, first_name="Lead", last_name="Officer"
        )

        # 3. Hierarchy
        self.plant = Plant.objects.create(name="Chennai Petrochemical Complex", code="PLANT-CHE-01", location="Chennai")
        self.area_1 = Area.objects.create(plant=self.plant, name="Area 1 - Refining", code="AREA-01", owner=self.area_owner_1)
        self.area_2 = Area.objects.create(plant=self.plant, name="Area 2 - Utilities", code="AREA-02", owner=self.area_owner_2)

        self.equipment_1 = Equipment.objects.create(area=self.area_1, name="Crude Column C-101", tag_number="EQ-C101")
        self.equipment_2 = Equipment.objects.create(area=self.area_2, name="Boiler Pump P-102A", tag_number="EQ-P102A")

        self.now = timezone.now()

    def test_requester_cannot_approve_any_permit(self):
        """Rule: Requester cannot approve anything."""
        permit = Permit.objects.create(
            permit_number="PTW-TEST-0001",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Welding test",
            requester=self.requester,
            contractor_name="Contractor A",
            equipment=self.equipment_1,
            planned_start=self.now + timedelta(hours=1),
            planned_end=self.now + timedelta(hours=8),
            status=Permit.Status.PENDING_APPROVAL,
            type_data={"hot_work_type": "Welding", "fire_watch_assigned": "Watchman", "fire_extinguisher_type": "CO2 4.5kg", "combustibles_cleared_radius_m": 10, "gas_test_o2_pct": 20.9, "gas_test_lel_pct": 0.0, "gas_test_time": "2026-09-25T10:00"}
        )
        can_approve, reason = PermitStateMachine.can_user_approve(permit, self.requester)
        self.assertFalse(can_approve)
        with self.assertRaises(PermissionDenied):
            PermitStateMachine.approve(permit, self.requester, comment="Trying to self-approve")

    def test_person_can_never_approve_their_own_permit(self):
        """
        Key non-negotiable rule: A person can never approve their own permit,
        even if their role would otherwise allow it.
        """
        # Safety Officer creates a permit as requester
        permit = Permit.objects.create(
            permit_number="PTW-TEST-0002",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Safety Officer's Own Hot Work",
            requester=self.dual_role_user,  # Requester is Safety Officer!
            contractor_name="Internal Maintenance",
            equipment=self.equipment_1,
            planned_start=self.now + timedelta(hours=1),
            planned_end=self.now + timedelta(hours=8),
            status=Permit.Status.PENDING_APPROVAL,
            type_data={"hot_work_type": "Welding", "fire_watch_assigned": "Watchman", "fire_extinguisher_type": "CO2 4.5kg", "combustibles_cleared_radius_m": 10, "gas_test_o2_pct": 20.9, "gas_test_lel_pct": 0.0, "gas_test_time": "2026-09-25T10:00"}
        )

        can_approve, reason = PermitStateMachine.can_user_approve(permit, self.dual_role_user)
        self.assertFalse(can_approve)
        self.assertIn("cannot approve your own permit", reason)

        with self.assertRaises(PermissionDenied):
            PermitStateMachine.approve(permit, self.dual_role_user, comment="Self-approval attempt")

    def test_area_owner_cannot_approve_other_areas(self):
        """Rule: Area Owner cannot approve equipment outside their assigned area."""
        permit_in_area_2 = Permit.objects.create(
            permit_number="PTW-TEST-0003",
            permit_type=Permit.PermitType.ELECTRICAL_LOTO,
            title="LOTO test",
            requester=self.requester,
            contractor_name="Contractor B",
            equipment=self.equipment_2,  # Belongs to area_2 (owned by area_owner_2)
            planned_start=self.now + timedelta(hours=1),
            planned_end=self.now + timedelta(hours=8),
            status=Permit.Status.PENDING_APPROVAL,
            type_data={"equipment_tag": "EQ-P102A", "voltage_level": "415V", "isolation_points_list": "Breaker 1", "lock_numbers": "L-1", "tag_numbers": "T-1", "earthing_applied": True, "tested_dead_by": "Eng"}
        )

        # area_owner_1 tries to approve permit in area_2
        can_approve, reason = PermitStateMachine.can_user_approve(permit_in_area_2, self.area_owner_1)
        self.assertFalse(can_approve)
        with self.assertRaises(PermissionDenied):
            PermitStateMachine.approve(permit_in_area_2, self.area_owner_1)

    def test_cannot_activate_unless_every_required_approver_approved(self):
        """Rule: A permit cannot go ACTIVE unless every required approver has approved."""
        permit = Permit.objects.create(
            permit_number="PTW-TEST-0004",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Activation check",
            requester=self.requester,
            contractor_name="Contractor A",
            equipment=self.equipment_1,
            planned_start=self.now - timedelta(minutes=10),
            planned_end=self.now + timedelta(hours=8),
            status=Permit.Status.DRAFT,
            type_data={"hot_work_type": "Welding", "fire_watch_assigned": "Watchman", "fire_extinguisher_type": "CO2 4.5kg", "combustibles_cleared_radius_m": 10, "gas_test_o2_pct": 20.9, "gas_test_lel_pct": 0.0, "gas_test_time": "2026-09-25T10:00"}
        )
        PermitStateMachine.submit(permit, self.requester)
        self.assertEqual(permit.status, Permit.Status.PENDING_APPROVAL)

        # Only Area Owner approves
        PermitStateMachine.approve(permit, self.area_owner_1, comment="Area owner OK")
        permit.refresh_from_db()
        self.assertEqual(permit.status, Permit.Status.PENDING_APPROVAL)

        # Attempting activation when Safety Officer hasn't approved must raise ValidationError
        with self.assertRaises(ValidationError):
            PermitStateMachine.activate(permit, self.requester)

        # Now Safety Officer also approves -> becomes APPROVED
        PermitStateMachine.approve(permit, self.safety_officer, comment="Safety OK")
        permit.refresh_from_db()
        self.assertEqual(permit.status, Permit.Status.APPROVED)

        # Now activation succeeds
        PermitStateMachine.activate(permit, self.requester)
        permit.refresh_from_db()
        self.assertEqual(permit.status, Permit.Status.ACTIVE)

    def test_cannot_activate_before_planned_start_time(self):
        """Rule: A permit cannot go ACTIVE before its planned start time."""
        future_start = self.now + timedelta(hours=2)
        permit = Permit.objects.create(
            permit_number="PTW-TEST-0005",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Future start",
            requester=self.requester,
            contractor_name="Contractor A",
            equipment=self.equipment_1,
            planned_start=future_start,
            planned_end=future_start + timedelta(hours=8),
            status=Permit.Status.DRAFT,
            type_data={"hot_work_type": "Welding", "fire_watch_assigned": "Watchman", "fire_extinguisher_type": "CO2 4.5kg", "combustibles_cleared_radius_m": 10, "gas_test_o2_pct": 20.9, "gas_test_lel_pct": 0.0, "gas_test_time": "2026-09-25T10:00"}
        )
        PermitStateMachine.submit(permit, self.requester)
        PermitStateMachine.approve(permit, self.area_owner_1)
        PermitStateMachine.approve(permit, self.safety_officer)
        permit.refresh_from_db()
        self.assertEqual(permit.status, Permit.Status.APPROVED)

        # Attempting activation before planned start time must be rejected
        with self.assertRaises(ValidationError) as ctx:
            PermitStateMachine.activate(permit, self.requester)
        self.assertIn("before its planned start time", str(ctx.exception))

    def test_auto_expiry_and_cannot_reactivate_expired(self):
        """Rule: A permit auto-expires when validity window passes. An expired permit can never be reactivated."""
        past_end = self.now - timedelta(minutes=10)
        permit = Permit.objects.create(
            permit_number="PTW-TEST-0006",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Expired permit",
            requester=self.requester,
            contractor_name="Contractor A",
            equipment=self.equipment_1,
            planned_start=self.now - timedelta(hours=4),
            planned_end=past_end,
            status=Permit.Status.ACTIVE,
            type_data={"hot_work_type": "Welding", "fire_watch_assigned": "Watchman", "fire_extinguisher_type": "CO2 4.5kg", "combustibles_cleared_radius_m": 10, "gas_test_o2_pct": 20.9, "gas_test_lel_pct": 0.0, "gas_test_time": "2026-09-25T10:00"}
        )
        expired = permit.check_and_update_expiry()
        self.assertTrue(expired)
        self.assertEqual(permit.status, Permit.Status.EXPIRED)

        # Attempting to activate or resume must fail
        with self.assertRaises(ValidationError):
            PermitStateMachine.activate(permit, self.requester)
        with self.assertRaises(ValidationError):
            PermitStateMachine.resume(permit, self.safety_officer)

    def test_safety_officer_can_suspend_and_resume(self):
        """Rule: Safety Officer can suspend any ACTIVE permit instantly, and resume when safe."""
        permit = Permit.objects.create(
            permit_number="PTW-TEST-0007",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Suspend test",
            requester=self.requester,
            contractor_name="Contractor A",
            equipment=self.equipment_1,
            planned_start=self.now - timedelta(hours=1),
            planned_end=self.now + timedelta(hours=4),
            status=Permit.Status.ACTIVE,
            type_data={"hot_work_type": "Welding", "fire_watch_assigned": "Watchman", "fire_extinguisher_type": "CO2 4.5kg", "combustibles_cleared_radius_m": 10, "gas_test_o2_pct": 20.9, "gas_test_lel_pct": 0.0, "gas_test_time": "2026-09-25T10:00"}
        )

        # Requester cannot suspend
        with self.assertRaises(PermissionDenied):
            PermitStateMachine.suspend(permit, self.requester, reason="Attempt")

        # Safety officer suspends
        PermitStateMachine.suspend(permit, self.safety_officer, reason="Heavy rain storm")
        permit.refresh_from_db()
        self.assertEqual(permit.status, Permit.Status.SUSPENDED)

        # Resume by safety officer
        PermitStateMachine.resume(permit, self.safety_officer, notes="Storm passed, site verified")
        permit.refresh_from_db()
        self.assertEqual(permit.status, Permit.Status.ACTIVE)

    def test_rejection_requires_mandatory_reason(self):
        """Rule: Rejection requires a mandatory reason."""
        permit = Permit.objects.create(
            permit_number="PTW-TEST-0008",
            permit_type=Permit.PermitType.HOT_WORK,
            title="Reject test",
            requester=self.requester,
            contractor_name="Contractor A",
            equipment=self.equipment_1,
            planned_start=self.now + timedelta(hours=1),
            planned_end=self.now + timedelta(hours=4),
            status=Permit.Status.PENDING_APPROVAL,
            type_data={"hot_work_type": "Welding", "fire_watch_assigned": "Watchman", "fire_extinguisher_type": "CO2 4.5kg", "combustibles_cleared_radius_m": 10, "gas_test_o2_pct": 20.9, "gas_test_lel_pct": 0.0, "gas_test_time": "2026-09-25T10:00"}
        )
        with self.assertRaises(ValidationError):
            PermitStateMachine.reject(permit, self.safety_officer, reason="")

        PermitStateMachine.reject(permit, self.safety_officer, reason="Combustible clearance is inadequate")
        permit.refresh_from_db()
        self.assertEqual(permit.status, Permit.Status.REJECTED)

    def test_hot_work_dangerous_lel_rejected_by_schema(self):
        """Rule: Dynamic schema validation catches dangerous gas levels (e.g. LEL >= 10%)."""
        dangerous_type_data = {
            "hot_work_type": "Welding",
            "fire_watch_assigned": "Watchman",
            "fire_extinguisher_type": "CO2 4.5kg",
            "combustibles_cleared_radius_m": 10,
            "gas_test_o2_pct": 20.9,
            "gas_test_lel_pct": 12.5,  # DANGEROUS! >= 10%
            "gas_test_time": "2026-09-25T10:00"
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_type_data("HOT_WORK", dangerous_type_data)
        self.assertIn("gas_test_lel_pct", str(ctx.exception))

    def test_conflict_detection_between_hot_work_and_confined_space(self):
        """Bonus Feature: Conflict detected if Hot Work overlaps Confined Space in same Area."""
        Permit.objects.create(
            permit_number="PTW-TEST-CS-01",
            permit_type=Permit.PermitType.CONFINED_SPACE,
            title="Tank Entry",
            requester=self.requester,
            contractor_name="Contractor A",
            equipment=self.equipment_1,
            planned_start=self.now,
            planned_end=self.now + timedelta(hours=6),
            status=Permit.Status.ACTIVE,
            type_data={"space_id": "V-101", "entry_point": "MW1", "standby_attendant_name": "John", "rescue_plan": "Tripod", "ventilation_method": "Blower", "gas_test_o2_pct": 20.8, "gas_test_lel_pct": 0.0, "gas_test_h2s_ppm": 0.0, "gas_test_co_ppm": 0, "gas_test_time": "2026-09-25T10:00"}
        )

        conflicts = ConflictDetector.check_conflicts(
            permit=None,
            equipment=self.equipment_1,
            start_time=self.now + timedelta(hours=1),
            end_time=self.now + timedelta(hours=5),
            permit_type=Permit.PermitType.HOT_WORK
        )
        self.assertTrue(len(conflicts) > 0)
        self.assertEqual(conflicts[0]['type'], 'HOT_WORK_CONFINED_SPACE_CLASH')
