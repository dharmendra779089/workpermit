"""
Permit State Machine, Transition Enforcement, Conflict Detection, and Audit Service.

Every transition rule is enforced server-side.
Bypassing the UI to call the API directly will be caught and rejected with HTTP 400.
"""

from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import ValidationError, PermissionDenied
from .models import Permit, PermitApproval, PermitAuditLog, PermitWorkLog, User
from .schemas import validate_type_data
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Notification stub service logging outbound safety alerts.
    Demonstrates alert notification architecture for plant safety officers & area owners.
    """
    @staticmethod
    def notify(event_type, permit, recipient, message):
        logger.info(
            f"[NOTIFICATION DISPATCH] Event: {event_type} | Permit: {permit.permit_number} | "
            f"Recipient: {recipient.username} ({recipient.role}) | Message: {message}"
        )


class ConflictDetector:
    """
    Detects spatial and temporal safety conflicts between permits.
    Specifically checks:
    1. Hot Work overlapping with Confined Space in the same Area or Equipment.
    2. Multiple Hot Works in the exact same Area simultaneously.
    """
    @staticmethod
    def check_conflicts(permit, equipment=None, start_time=None, end_time=None, permit_type=None):
        eq = equipment or permit.equipment
        start = start_time or permit.planned_start
        end = end_time or permit.planned_end
        p_type = permit_type or permit.permit_type
        permit_id = permit.id if permit and hasattr(permit, 'id') else None

        active_statuses = [
            Permit.Status.PENDING_APPROVAL,
            Permit.Status.APPROVED,
            Permit.Status.ACTIVE,
            Permit.Status.SUSPENDED,
        ]

        # Overlapping permits query
        overlap_qs = Permit.objects.filter(
            status__in=active_statuses,
            equipment__area=eq.area,
            planned_start__lt=end,
            planned_end__gt=start,
        )
        if permit_id:
            overlap_qs = overlap_qs.exclude(id=permit_id)

        conflicts = []

        for other in overlap_qs:
            # Rule 1: Hot Work + Confined Space in same Area
            if (p_type == Permit.PermitType.HOT_WORK and other.permit_type == Permit.PermitType.CONFINED_SPACE) or \
               (p_type == Permit.PermitType.CONFINED_SPACE and other.permit_type == Permit.PermitType.HOT_WORK):
                conflicts.append({
                    'severity': 'CRITICAL',
                    'type': 'HOT_WORK_CONFINED_SPACE_CLASH',
                    'conflicting_permit_id': other.id,
                    'conflicting_permit_number': other.permit_number,
                    'conflicting_permit_title': other.title,
                    'area': eq.area.name,
                    'equipment': other.equipment.name,
                    'message': (
                        f"CRITICAL SAFETY CONFLICT: Hot Work ({p_type}) overlaps in time and area with "
                        f"Confined Space Entry permit {other.permit_number} on {other.equipment.name}. "
                        "Open flames near potential confined space venting creates severe explosion risk!"
                    )
                })

            # Rule 2: Multiple Hot Works on same equipment
            elif p_type == Permit.PermitType.HOT_WORK and other.permit_type == Permit.PermitType.HOT_WORK and other.equipment == eq:
                conflicts.append({
                    'severity': 'HIGH',
                    'type': 'CONCURRENT_HOT_WORK_SAME_EQUIPMENT',
                    'conflicting_permit_id': other.id,
                    'conflicting_permit_number': other.permit_number,
                    'conflicting_permit_title': other.title,
                    'area': eq.area.name,
                    'equipment': eq.name,
                    'message': (
                        f"CONCURRENT WORK WARNING: Another Hot Work permit {other.permit_number} is already "
                        f"active or pending on {eq.name}."
                    )
                })

        return conflicts


class PermitStateMachine:
    """
    Strict State Machine Engine enforcing all safety rules server-side.
    """

    @classmethod
    def can_user_approve(cls, permit, user):
        """
        Check if user can approve this permit.
        Key Rule: A person can NEVER approve their own permit, even if role allows it!
        """
        if user == permit.requester:
            return False, "You cannot approve your own permit."

        if user.is_admin_user():
            return True, "Admin override approval authorized."

        if user.is_safety_officer():
            return True, "Safety Officer approval authorized."

        if user.is_area_owner():
            # Check if this user owns the area
            if permit.equipment.area.owner == user or user.owned_areas.filter(id=permit.equipment.area_id).exists():
                return True, "Area Owner approval authorized for this area."
            return False, f"You are not the designated Area Owner for {permit.equipment.area.name}."

        return False, "Your role does not have approval authority."

    @classmethod
    def submit(cls, permit, user):
        """
        Transitions DRAFT -> PENDING_APPROVAL.
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.DRAFT:
            raise ValidationError(f"Only DRAFT permits can be submitted. Current status: {permit.status}")

        if user != permit.requester and not user.is_admin_user():
            raise PermissionDenied("Only the permit requester or an admin can submit this permit.")

        # Validate planned window
        now = timezone.now()
        if permit.planned_end <= permit.planned_start:
            raise ValidationError("Planned end time must be strictly after planned start time.")

        if permit.planned_end <= now:
            raise ValidationError("Cannot submit a permit whose validity window has already passed.")

        # Validate type_data
        validate_type_data(permit.permit_type, permit.type_data)

        # Setup required approvals
        permit.status = Permit.Status.PENDING_APPROVAL
        permit.save(update_fields=['status', 'updated_at'])

        # Reset or create approvals: Area Owner and Safety Officer
        PermitApproval.objects.filter(permit=permit).delete()

        # 1. Area Owner Approval
        area_owner = permit.equipment.area.owner
        if not area_owner:
            # Fallback to any area owner or admin if area has no assigned owner yet
            area_owner = User.objects.filter(role=User.Role.AREA_OWNER).exclude(id=permit.requester.id).first()

        # 2. Safety Officer Approval
        safety_officer = User.objects.filter(role=User.Role.SAFETY_OFFICER).exclude(id=permit.requester.id).first()

        if area_owner and area_owner != permit.requester:
            PermitApproval.objects.create(
                permit=permit,
                approver=area_owner,
                role_type=PermitApproval.RoleType.AREA_OWNER,
                status=PermitApproval.ApprovalStatus.PENDING
            )
            NotificationService.notify(
                'APPROVAL_REQUESTED', permit, area_owner,
                f"New PTW {permit.permit_number} submitted for your area {permit.equipment.area.name}."
            )

        if safety_officer and safety_officer != permit.requester:
            PermitApproval.objects.create(
                permit=permit,
                approver=safety_officer,
                role_type=PermitApproval.RoleType.SAFETY_OFFICER,
                status=PermitApproval.ApprovalStatus.PENDING
            )
            NotificationService.notify(
                'APPROVAL_REQUESTED', permit, safety_officer,
                f"New PTW {permit.permit_number} submitted requiring Safety Officer review."
            )

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="SUBMITTED",
            from_status=Permit.Status.DRAFT,
            to_status=Permit.Status.PENDING_APPROVAL,
            comment="Permit submitted for multi-party safety approvals.",
            details={"type": permit.permit_type, "equipment": permit.equipment.name}
        )

        return permit

    @classmethod
    def approve(cls, permit, user, comment="", signature_data=""):
        """
        Approves permit by Area Owner or Safety Officer.
        Transitions PENDING_APPROVAL -> APPROVED once ALL required approvers have approved.
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.PENDING_APPROVAL:
            raise ValidationError(f"Permit is not pending approval. Current status: {permit.status}")

        # KEY RULE: A person can NEVER approve their own permit!
        if user == permit.requester:
            raise PermissionDenied("SECURITY VIOLATION: A person can never approve their own permit.")

        can_approve, reason = cls.can_user_approve(permit, user)
        if not can_approve:
            raise PermissionDenied(reason)

        now = timezone.now()
        role_type = PermitApproval.RoleType.SAFETY_OFFICER if user.is_safety_officer() else PermitApproval.RoleType.AREA_OWNER

        # Check or create approval record for this role
        approval, created = PermitApproval.objects.get_or_create(
            permit=permit,
            role_type=role_type,
            defaults={'approver': user}
        )

        approval.approver = user
        approval.status = PermitApproval.ApprovalStatus.APPROVED
        approval.comment = comment or "Approved with all site safety precautions verified."
        approval.signature_data = signature_data
        approval.acted_at = now
        approval.save()

        # Audit log for individual approval
        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="APPROVED",
            from_status=permit.status,
            to_status=permit.status,
            comment=approval.comment,
            details={
                "role_type": role_type,
                "has_digital_signature": bool(signature_data)
            }
        )

        # Check if ALL required approvals are satisfied (Both Area Owner & Safety Officer)
        approvals = permit.approvals.all()
        has_area_owner_approval = approvals.filter(
            role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.APPROVED
        ).exists()
        has_safety_officer_approval = approvals.filter(
            role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.APPROVED
        ).exists()

        # If both are satisfied (or in case admin signs as sole required authority)
        if has_area_owner_approval and has_safety_officer_approval:
            old_status = permit.status
            permit.status = Permit.Status.APPROVED
            permit.save(update_fields=['status', 'updated_at'])

            PermitAuditLog.objects.create(
                permit=permit,
                actor=user,
                actor_name=user.get_full_name() or user.username,
                actor_role="SYSTEM_EVALUATOR",
                action="FULLY_APPROVED",
                from_status=old_status,
                to_status=Permit.Status.APPROVED,
                comment="All mandatory safety approvals completed. Permit is ready for site activation.",
                details={"area_owner_approved": True, "safety_officer_approved": True}
            )
            NotificationService.notify(
                'PERMIT_APPROVED', permit, permit.requester,
                f"Your permit {permit.permit_number} has been FULLY APPROVED."
            )

        return permit

    @classmethod
    def reject(cls, permit, user, reason):
        """
        Rejects permit. Transitions PENDING_APPROVAL -> REJECTED.
        Reason is strictly mandatory!
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.PENDING_APPROVAL:
            raise ValidationError(f"Only permits pending approval can be rejected. Current status: {permit.status}")

        if not reason or not reason.strip():
            raise ValidationError({'reason': "A mandatory rejection reason must be provided."})

        # Check permission
        can_approve, auth_reason = cls.can_user_approve(permit, user)
        if not can_approve:
            raise PermissionDenied(auth_reason)

        role_type = PermitApproval.RoleType.SAFETY_OFFICER if user.is_safety_officer() else PermitApproval.RoleType.AREA_OWNER

        approval, created = PermitApproval.objects.get_or_create(
            permit=permit,
            role_type=role_type,
            defaults={'approver': user}
        )
        approval.approver = user
        approval.status = PermitApproval.ApprovalStatus.REJECTED
        approval.comment = reason.strip()
        approval.acted_at = timezone.now()
        approval.save()

        old_status = permit.status
        permit.status = Permit.Status.REJECTED
        permit.save(update_fields=['status', 'updated_at'])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="REJECTED",
            from_status=old_status,
            to_status=Permit.Status.REJECTED,
            comment=f"Rejected: {reason.strip()}",
            details={"rejected_by_role": role_type}
        )

        NotificationService.notify(
            'PERMIT_REJECTED', permit, permit.requester,
            f"Permit {permit.permit_number} was REJECTED: {reason.strip()}"
        )

        return permit

    @classmethod
    def activate(cls, permit, user):
        """
        Transitions APPROVED -> ACTIVE.
        Enforces:
        - A permit cannot go ACTIVE unless **every** required approver has approved.
        - A permit cannot go ACTIVE before its planned start time.
        - Allowed by: Requester or Safety Officer or Admin.
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.APPROVED:
            raise ValidationError(
                f"Permit cannot be activated from status '{permit.status}'. "
                "Permit must be in APPROVED status with all approvals satisfied."
            )

        # Enforce Rule 1: Every required approver has approved
        approvals = permit.approvals.all()
        has_area_owner = approvals.filter(
            role_type=PermitApproval.RoleType.AREA_OWNER,
            status=PermitApproval.ApprovalStatus.APPROVED
        ).exists()
        has_safety_officer = approvals.filter(
            role_type=PermitApproval.RoleType.SAFETY_OFFICER,
            status=PermitApproval.ApprovalStatus.APPROVED
        ).exists()

        if not (has_area_owner and has_safety_officer):
            raise ValidationError("ILLEGAL ACTIVATION: Every required approver (Area Owner and Safety Officer) must approve before permit can go ACTIVE.")

        # Enforce Rule 2: Cannot go active before planned start time
        now = timezone.now()
        if now < permit.planned_start:
            raise ValidationError(
                f"ILLEGAL ACTIVATION: Permit cannot go ACTIVE before its planned start time "
                f"({permit.planned_start.strftime('%Y-%m-%d %H:%M UTC')}). Current time is {now.strftime('%Y-%m-%d %H:%M UTC')}."
            )

        # Enforce Rule 3: Cannot go active if already expired
        if now > permit.planned_end:
            permit.check_and_update_expiry()
            raise ValidationError("Permit validity window has expired. Cannot activate an expired permit.")

        # Check permissions
        if user != permit.requester and not user.is_safety_officer() and not user.is_admin_user():
            raise PermissionDenied("Only the requester, a safety officer, or an admin can activate this permit.")

        old_status = permit.status
        permit.status = Permit.Status.ACTIVE
        permit.actual_start = now
        permit.save(update_fields=['status', 'actual_start', 'updated_at'])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="ACTIVATED",
            from_status=old_status,
            to_status=Permit.Status.ACTIVE,
            comment="Permit officially activated on site. Hot/Hazardous work authorized inside window.",
            details={"actual_start": now.isoformat()}
        )

        return permit

    @classmethod
    def suspend(cls, permit, user, reason):
        """
        Transitions ACTIVE -> SUSPENDED.
        Enforces:
        - Safety Officer (or Admin) can suspend any ACTIVE permit instantly.
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.ACTIVE:
            raise ValidationError(f"Only ACTIVE permits can be suspended. Current status: {permit.status}")

        if not user.is_safety_officer() and not user.is_admin_user():
            raise PermissionDenied("Only a Safety Officer or System Admin has authority to suspend active work permits.")

        if not reason or not reason.strip():
            raise ValidationError({'reason': "Mandatory suspension reason required (e.g. gas alarm, weather, emergency)."})

        old_status = permit.status
        permit.status = Permit.Status.SUSPENDED
        permit.save(update_fields=['status', 'updated_at'])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="SUSPENDED",
            from_status=old_status,
            to_status=Permit.Status.SUSPENDED,
            comment=f"EMERGENCY SUSPENSION: {reason.strip()}",
            details={"reason": reason.strip()}
        )

        NotificationService.notify(
            'PERMIT_SUSPENDED', permit, permit.requester,
            f"URGENT: Permit {permit.permit_number} has been SUSPENDED by Safety Officer: {reason.strip()}"
        )

        return permit

    @classmethod
    def resume(cls, permit, user, notes=""):
        """
        Transitions SUSPENDED -> ACTIVE.
        Safety Officer (or Admin) verifies conditions are safe again and resumes work.
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.SUSPENDED:
            raise ValidationError(f"Only SUSPENDED permits can be resumed. Current status: {permit.status}")

        if not user.is_safety_officer() and not user.is_admin_user():
            raise PermissionDenied("Only a Safety Officer or System Admin can authorize resumption of suspended work.")

        now = timezone.now()
        if now > permit.planned_end:
            permit.check_and_update_expiry()
            raise ValidationError("Permit validity expired during suspension. Work cannot resume under this permit.")

        old_status = permit.status
        permit.status = Permit.Status.ACTIVE
        permit.save(update_fields=['status', 'updated_at'])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="RESUMED",
            from_status=old_status,
            to_status=Permit.Status.ACTIVE,
            comment=notes.strip() or "Site conditions reinspected and verified safe. Work authorized to resume.",
            details={"resumed_at": now.isoformat()}
        )

        return permit

    @classmethod
    def close(cls, permit, user, completion_notes):
        """
        Transitions ACTIVE -> CLOSED.
        Enforces:
        - Requester marks work complete with completion notes.
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.ACTIVE:
            raise ValidationError(f"Only ACTIVE permits can be closed. Current status: {permit.status}")

        if user != permit.requester and not user.is_admin_user():
            raise PermissionDenied("Only the permit requester or an admin can mark work as completed.")

        if not completion_notes or not completion_notes.strip():
            raise ValidationError({'completion_notes': "Mandatory completion notes required detailing work completed and housekeeping."})

        now = timezone.now()
        old_status = permit.status
        permit.status = Permit.Status.CLOSED
        permit.completion_notes = completion_notes.strip()
        permit.actual_end = now
        permit.closed_at = now
        permit.save(update_fields=['status', 'completion_notes', 'actual_end', 'closed_at', 'updated_at'])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="CLOSED",
            from_status=old_status,
            to_status=Permit.Status.CLOSED,
            comment=f"Work completed. Notes: {completion_notes.strip()}",
            details={"actual_end": now.isoformat()}
        )

        return permit

    @classmethod
    def verify_closure(cls, permit, user, notes=""):
        """
        Transitions CLOSED -> CLOSED_VERIFIED.
        Enforces:
        - Safety Officer inspects site, verifies area is clean, tools removed, isolation normalized, and closes it out.
        """
        if permit.status != Permit.Status.CLOSED:
            raise ValidationError(f"Only CLOSED permits can undergo closure verification. Current status: {permit.status}")

        if not user.is_safety_officer() and not user.is_admin_user():
            raise PermissionDenied("Only a Safety Officer or System Admin can perform final closure verification.")

        now = timezone.now()
        old_status = permit.status
        permit.status = Permit.Status.CLOSED_VERIFIED
        permit.closure_verified_by = user
        permit.closure_verified_at = now
        permit.closure_verification_notes = notes.strip() or "Physical site walk-around completed. Housekeeping verified, grounds clean, isolations normalized."
        permit.save(update_fields=[
            'status', 'closure_verified_by', 'closure_verified_at',
            'closure_verification_notes', 'updated_at'
        ])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="CLOSED_VERIFIED",
            from_status=old_status,
            to_status=Permit.Status.CLOSED_VERIFIED,
            comment=permit.closure_verification_notes,
            details={"verified_by": user.username, "verified_at": now.isoformat()}
        )

        return permit

    @classmethod
    def cancel(cls, permit, user, reason=""):
        """
        Transitions any non-terminal state -> CANCELLED.
        Terminal states: REJECTED, EXPIRED, CLOSED_VERIFIED, CANCELLED.
        """
        terminal_statuses = [
            Permit.Status.REJECTED,
            Permit.Status.EXPIRED,
            Permit.Status.CLOSED_VERIFIED,
            Permit.Status.CANCELLED,
        ]
        if permit.status in terminal_statuses:
            raise ValidationError(f"Permit is in terminal state '{permit.status}' and cannot be cancelled.")

        if user != permit.requester and not user.is_safety_officer() and not user.is_admin_user():
            raise PermissionDenied("Only the requester, safety officer, or admin can cancel this permit.")

        old_status = permit.status
        permit.status = Permit.Status.CANCELLED
        permit.save(update_fields=['status', 'updated_at'])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="CANCELLED",
            from_status=old_status,
            to_status=Permit.Status.CANCELLED,
            comment=reason.strip() or "Permit cancelled before completion.",
            details={"cancelled_by": user.username}
        )

        return permit

    @classmethod
    def request_extension(cls, permit, user, hours, reason):
        """
        Requester requests +N hours extension before validity expires.
        """
        permit.check_and_update_expiry()

        if permit.status not in [Permit.Status.ACTIVE, Permit.Status.APPROVED]:
            raise ValidationError("Extensions can only be requested for ACTIVE or APPROVED permits.")

        if user != permit.requester and not user.is_admin_user():
            raise PermissionDenied("Only the permit requester or admin can request an extension.")

        if hours < 1 or hours > 8:
            raise ValidationError({'hours': "Extension must be between 1 and 8 hours."})

        if not reason or not reason.strip():
            raise ValidationError({'reason': "Reason for extension is mandatory."})

        permit.extension_hours = hours
        permit.extension_reason = reason.strip()
        permit.extension_requested_at = timezone.now()
        permit.extension_status = 'REQUESTED'
        permit.save(update_fields=[
            'extension_hours', 'extension_reason',
            'extension_requested_at', 'extension_status', 'updated_at'
        ])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="EXTENSION_REQUESTED",
            from_status=permit.status,
            to_status=permit.status,
            comment=f"Extension requested for +{hours} hours. Justification: {reason.strip()}",
            details={"requested_hours": hours}
        )

        return permit

    @classmethod
    def approve_extension(cls, permit, user, approved=True, comment=""):
        """
        Safety officer reviews and approves or rejects extension request.
        """
        if permit.extension_status != 'REQUESTED':
            raise ValidationError("No pending extension request found on this permit.")

        if not user.is_safety_officer() and not user.is_admin_user():
            raise PermissionDenied("Only a Safety Officer or Admin can approve permit extensions.")

        if approved:
            permit.planned_end = permit.planned_end + timedelta(hours=permit.extension_hours)
            permit.extension_status = 'APPROVED'
            action_name = "EXTENSION_APPROVED"
            audit_comment = f"Extension approved by {user.get_full_name() or user.username}. Validity extended to {permit.planned_end.isoformat()}."
        else:
            permit.extension_status = 'REJECTED'
            action_name = "EXTENSION_REJECTED"
            audit_comment = f"Extension rejected: {comment or 'Safety conditions do not permit extension.'}"

        permit.save(update_fields=['planned_end', 'extension_status', 'updated_at'])

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action=action_name,
            from_status=permit.status,
            to_status=permit.status,
            comment=audit_comment,
            details={"new_planned_end": permit.planned_end.isoformat(), "comment": comment}
        )

        return permit

    @classmethod
    def log_work(cls, permit, user, task_description, hours_spent=1.0, worker_name=""):
        """
        Logs technician work execution against an active permit.
        Enforces Rule: Work cannot be logged against a permit that isn't ACTIVE.
        """
        permit.check_and_update_expiry()

        if permit.status != Permit.Status.ACTIVE:
            raise ValidationError(
                f"SAFETY VIOLATION: Work cannot be logged against a permit that isn't ACTIVE. "
                f"Current permit status is '{permit.status}'."
            )

        if not task_description or not task_description.strip():
            raise ValidationError({'task_description': "Task description is required to log work."})

        try:
            hrs = float(hours_spent)
            if hrs <= 0 or hrs > 24:
                raise ValidationError({'hours_spent': "Logged work hours must be between 0.1 and 24 hours."})
        except (ValueError, TypeError):
            raise ValidationError({'hours_spent': "Valid numeric hours required."})

        name = worker_name.strip() or user.get_full_name() or user.username

        work_log = PermitWorkLog.objects.create(
            permit=permit,
            worker=user,
            worker_name=name,
            task_description=task_description.strip(),
            hours_spent=hrs,
            logged_at=timezone.now()
        )

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="WORK_LOGGED",
            from_status=permit.status,
            to_status=permit.status,
            comment=f"Logged {hrs}h work: {task_description.strip()[:80]}",
            details={"hours_spent": hrs, "worker": name, "work_log_id": work_log.id}
        )

        return work_log

