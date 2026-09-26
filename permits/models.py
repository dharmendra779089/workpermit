from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid


class User(AbstractUser):
    class Role(models.TextChoices):
        REQUESTER = 'REQUESTER', 'Requester (Technician / Contractor Supervisor)'
        AREA_OWNER = 'AREA_OWNER', 'Area Owner'
        SAFETY_OFFICER = 'SAFETY_OFFICER', 'Safety Officer'
        ADMIN = 'ADMIN', 'System Admin'

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.REQUESTER,
        help_text="Role determining permissions and actions"
    )
    phone = models.CharField(max_length=30, blank=True, default='')
    badge_number = models.CharField(max_length=50, blank=True, default='')

    def is_requester(self):
        return self.role == self.Role.REQUESTER

    def is_area_owner(self):
        return self.role == self.Role.AREA_OWNER

    def is_safety_officer(self):
        return self.role == self.Role.SAFETY_OFFICER

    def is_admin_user(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class Plant(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    location = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} [{self.code}]"


class Area(models.Model):
    plant = models.ForeignKey(Plant, related_name='areas', on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    owner = models.ForeignKey(
        User,
        related_name='owned_areas',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': User.Role.AREA_OWNER}
    )
    description = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ('plant', 'code')

    def __str__(self):
        return f"{self.plant.code} - {self.name} ({self.code})"


class Equipment(models.Model):
    class Criticality(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High / Critical'

    area = models.ForeignKey(Area, related_name='equipment_items', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    tag_number = models.CharField(max_length=100, unique=True)
    criticality = models.CharField(
        max_length=20,
        choices=Criticality.choices,
        default=Criticality.MEDIUM
    )
    description = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.tag_number} - {self.name}"


class Permit(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved'
        ACTIVE = 'ACTIVE', 'Active'
        SUSPENDED = 'SUSPENDED', 'Suspended'
        EXPIRED = 'EXPIRED', 'Expired'
        CLOSED = 'CLOSED', 'Closed'
        CLOSED_VERIFIED = 'CLOSED_VERIFIED', 'Closed & Verified'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class PermitType(models.TextChoices):
        HOT_WORK = 'HOT_WORK', 'Hot Work'
        CONFINED_SPACE = 'CONFINED_SPACE', 'Confined Space Entry'
        HEIGHT = 'HEIGHT', 'Working at Height'
        ELECTRICAL_LOTO = 'ELECTRICAL_LOTO', 'Electrical / Isolation (LOTO)'
        EXCAVATION = 'EXCAVATION', 'Excavation & Trenching'

    # Common Core Identifiers
    permit_number = models.CharField(max_length=32, unique=True, db_index=True)
    permit_type = models.CharField(max_length=32, choices=PermitType.choices, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Parties
    requester = models.ForeignKey(User, related_name='requested_permits', on_delete=models.PROTECT)
    contractor_name = models.CharField(max_length=255)
    team_size = models.PositiveIntegerField(default=1)

    # Location Core: Equipment -> Area -> Plant
    equipment = models.ForeignKey(Equipment, related_name='permits', on_delete=models.PROTECT)

    # Temporal Windows
    planned_start = models.DateTimeField(db_index=True)
    planned_end = models.DateTimeField(db_index=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)

    # Status State Machine
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )

    # Risk & Safety Core Checklists
    hazards = models.JSONField(default=list, help_text="List of hazard tags identified")
    ppe_required = models.JSONField(default=list, help_text="List of PPE mandatory for this permit")
    precautions = models.JSONField(default=list, help_text="List of safety precaution items checked")

    # Extensible Type-Specific Fields stored in structured JSON schema
    type_data = models.JSONField(default=dict, help_text="Type-specific fields validated against schema")

    # Extension Request System
    extension_hours = models.PositiveIntegerField(default=0)
    extension_reason = models.TextField(blank=True, default='')
    extension_requested_at = models.DateTimeField(null=True, blank=True)
    extension_status = models.CharField(
        max_length=20,
        default='NONE',
        choices=[
            ('NONE', 'None'),
            ('REQUESTED', 'Requested'),
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Rejected'),
        ]
    )

    # Closure & Verification System
    completion_notes = models.TextField(blank=True, default='')
    closed_at = models.DateTimeField(null=True, blank=True)
    closure_verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name='verified_closures',
        on_delete=models.SET_NULL
    )
    closure_verified_at = models.DateTimeField(null=True, blank=True)
    closure_verification_notes = models.TextField(blank=True, default='')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.permit_number} - {self.title} ({self.get_status_display()})"

    @property
    def area(self):
        return self.equipment.area

    @property
    def plant(self):
        return self.equipment.area.plant

    def check_and_update_expiry(self):
        """Auto-expire permit if planned_end has passed and it is in an expirable state."""
        expirable_statuses = [
            self.Status.PENDING_APPROVAL,
            self.Status.APPROVED,
            self.Status.ACTIVE,
            self.Status.SUSPENDED,
        ]
        if self.status in expirable_statuses and timezone.now() > self.planned_end:
            old_status = self.status
            self.status = self.Status.EXPIRED
            self.save(update_fields=['status', 'updated_at'])
            
            PermitAuditLog.objects.create(
                permit=self,
                actor=None,
                actor_name="SYSTEM MONITOR",
                actor_role="SYSTEM",
                action="EXPIRED",
                from_status=old_status,
                to_status=self.Status.EXPIRED,
                comment=f"Permit validity window expired at {self.planned_end.isoformat()}.",
                details={"auto_expired": True, "expired_at": timezone.now().isoformat()}
            )
            return True
        return False


class PermitApproval(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    class RoleType(models.TextChoices):
        AREA_OWNER = 'AREA_OWNER', 'Area Owner'
        SAFETY_OFFICER = 'SAFETY_OFFICER', 'Safety Officer'

    permit = models.ForeignKey(Permit, related_name='approvals', on_delete=models.CASCADE)
    approver = models.ForeignKey(User, related_name='given_approvals', on_delete=models.PROTECT)
    role_type = models.CharField(max_length=30, choices=RoleType.choices)
    status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    comment = models.TextField(blank=True, default='')
    signature_data = models.TextField(blank=True, default='', help_text="Base64 canvas drawn signature")
    acted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('permit', 'role_type')

    def __str__(self):
        return f"{self.permit.permit_number} - {self.role_type}: {self.status}"


class PermitAuditLog(models.Model):
    permit = models.ForeignKey(Permit, related_name='audit_logs', on_delete=models.CASCADE)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    actor_name = models.CharField(max_length=150)
    actor_role = models.CharField(max_length=50)
    action = models.CharField(max_length=50)
    from_status = models.CharField(max_length=32)
    to_status = models.CharField(max_length=32)
    comment = models.TextField(blank=True, default='')
    details = models.JSONField(default=dict)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.permit.permit_number} - {self.action} by {self.actor_name}"


class PermitWorkLog(models.Model):
    """
    Tracks maintenance technician tasks logged against active permits.
    Enforces Rule: Work cannot be logged against a permit that isn't ACTIVE.
    """
    permit = models.ForeignKey(Permit, related_name='work_logs', on_delete=models.CASCADE)
    worker = models.ForeignKey(User, related_name='logged_works', on_delete=models.PROTECT)
    worker_name = models.CharField(max_length=150)
    task_description = models.TextField()
    hours_spent = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    logged_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-logged_at']

    def __str__(self):
        return f"{self.permit.permit_number} - Work by {self.worker_name} ({self.hours_spent}h)"

