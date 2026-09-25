"""
Serializers for Opmaint Permit to Work (PTW) CMMS module.
"""

from rest_framework import serializers
from django.utils import timezone
from .models import User, Plant, Area, Equipment, Permit, PermitApproval, PermitAuditLog
from .schemas import PERMIT_TYPE_REGISTRY, validate_type_data
from .services import PermitStateMachine, ConflictDetector


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'role', 'role_display', 'phone', 'badge_number'
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class PlantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plant
        fields = ['id', 'name', 'code', 'location', 'description']


class AreaSerializer(serializers.ModelSerializer):
    plant_name = serializers.CharField(source='plant.name', read_only=True)
    plant_code = serializers.CharField(source='plant.code', read_only=True)
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = Area
        fields = ['id', 'plant', 'plant_name', 'plant_code', 'name', 'code', 'owner', 'owner_name', 'description']

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.get_full_name() or obj.owner.username
        return None


class EquipmentSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source='area.name', read_only=True)
    area_code = serializers.CharField(source='area.code', read_only=True)
    plant_name = serializers.CharField(source='area.plant.name', read_only=True)
    plant_id = serializers.IntegerField(source='area.plant.id', read_only=True)

    class Meta:
        model = Equipment
        fields = [
            'id', 'name', 'tag_number', 'criticality', 'area',
            'area_name', 'area_code', 'plant_id', 'plant_name', 'description'
        ]


class PermitApprovalSerializer(serializers.ModelSerializer):
    approver_name = serializers.SerializerMethodField()
    approver_role = serializers.CharField(source='approver.get_role_display', read_only=True)
    role_type_display = serializers.CharField(source='get_role_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PermitApproval
        fields = [
            'id', 'role_type', 'role_type_display', 'approver', 'approver_name',
            'approver_role', 'status', 'status_display', 'comment',
            'signature_data', 'acted_at'
        ]

    def get_approver_name(self, obj):
        if obj.approver:
            return obj.approver.get_full_name() or obj.approver.username
        return "Unassigned"


class PermitAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermitAuditLog
        fields = [
            'id', 'actor_name', 'actor_role', 'action',
            'from_status', 'to_status', 'comment', 'details', 'timestamp'
        ]


class PermitListSerializer(serializers.ModelSerializer):
    permit_type_display = serializers.CharField(source='get_permit_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    requester_name = serializers.SerializerMethodField()
    equipment_tag = serializers.CharField(source='equipment.tag_number', read_only=True)
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)
    area_name = serializers.CharField(source='equipment.area.name', read_only=True)
    area_id = serializers.IntegerField(source='equipment.area.id', read_only=True)
    plant_name = serializers.CharField(source='equipment.area.plant.name', read_only=True)
    plant_id = serializers.IntegerField(source='equipment.area.plant.id', read_only=True)
    is_expiring_soon = serializers.SerializerMethodField()
    seconds_remaining = serializers.SerializerMethodField()
    needs_my_approval = serializers.SerializerMethodField()
    type_meta = serializers.SerializerMethodField()

    class Meta:
        model = Permit
        fields = [
            'id', 'permit_number', 'permit_type', 'permit_type_display', 'type_meta',
            'title', 'status', 'status_display', 'requester', 'requester_name',
            'contractor_name', 'team_size', 'equipment', 'equipment_tag',
            'equipment_name', 'area_id', 'area_name', 'plant_id', 'plant_name',
            'planned_start', 'planned_end', 'actual_start', 'actual_end',
            'is_expiring_soon', 'seconds_remaining', 'needs_my_approval',
            'extension_status', 'created_at', 'updated_at'
        ]

    def get_requester_name(self, obj):
        return obj.requester.get_full_name() or obj.requester.username

    def get_type_meta(self, obj):
        info = PERMIT_TYPE_REGISTRY.get(obj.permit_type, {})
        return {
            'color': info.get('color', '#64748b'),
            'icon': info.get('icon', 'file-text')
        }

    def get_seconds_remaining(self, obj):
        now = timezone.now()
        if obj.status in [Permit.Status.ACTIVE, Permit.Status.APPROVED, Permit.Status.PENDING_APPROVAL]:
            diff = (obj.planned_end - now).total_seconds()
            return max(0, int(diff))
        return 0

    def get_is_expiring_soon(self, obj):
        if obj.status in [Permit.Status.ACTIVE, Permit.Status.APPROVED]:
            now = timezone.now()
            diff = (obj.planned_end - now).total_seconds()
            return 0 < diff <= 7200  # Within 2 hours
        return False

    def get_needs_my_approval(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        if obj.status != Permit.Status.PENDING_APPROVAL:
            return False
        if user == obj.requester:
            return False
        can_approve, _ = PermitStateMachine.can_user_approve(obj, user)
        if not can_approve:
            return False

        # Check if already approved by this user's role
        role_type = PermitApproval.RoleType.SAFETY_OFFICER if user.is_safety_officer() else PermitApproval.RoleType.AREA_OWNER
        return not obj.approvals.filter(role_type=role_type, status=PermitApproval.ApprovalStatus.APPROVED).exists()


class PermitDetailSerializer(PermitListSerializer):
    approvals = PermitApprovalSerializer(many=True, read_only=True)
    audit_logs = PermitAuditLogSerializer(many=True, read_only=True)
    available_actions = serializers.SerializerMethodField()
    conflicts = serializers.SerializerMethodField()
    closure_verified_by_name = serializers.SerializerMethodField()

    class Meta(PermitListSerializer.Meta):
        fields = PermitListSerializer.Meta.fields + [
            'description', 'hazards', 'ppe_required', 'precautions',
            'type_data', 'approvals', 'audit_logs', 'available_actions',
            'conflicts', 'extension_hours', 'extension_reason',
            'extension_requested_at', 'completion_notes', 'closed_at',
            'closure_verified_by', 'closure_verified_by_name',
            'closure_verified_at', 'closure_verification_notes'
        ]

    def get_closure_verified_by_name(self, obj):
        if obj.closure_verified_by:
            return obj.closure_verified_by.get_full_name() or obj.closure_verified_by.username
        return None

    def get_conflicts(self, obj):
        return ConflictDetector.check_conflicts(obj)

    def get_available_actions(self, obj):
        """
        Calculates exactly what actions the current user can perform on this permit.
        Enforces "A user should never see a button they aren't allowed to press." (PDF Page 4)
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []

        user = request.user
        actions = []
        now = timezone.now()

        # DRAFT state actions
        if obj.status == Permit.Status.DRAFT:
            if user == obj.requester or user.is_admin_user():
                actions.append('EDIT')
                actions.append('SUBMIT')
                actions.append('CANCEL')

        # PENDING_APPROVAL state actions
        elif obj.status == Permit.Status.PENDING_APPROVAL:
            # Check approval ability
            can_approve, _ = PermitStateMachine.can_user_approve(obj, user)
            if can_approve:
                role_type = PermitApproval.RoleType.SAFETY_OFFICER if user.is_safety_officer() else PermitApproval.RoleType.AREA_OWNER
                already_acted = obj.approvals.filter(role_type=role_type, status__in=[
                    PermitApproval.ApprovalStatus.APPROVED,
                    PermitApproval.ApprovalStatus.REJECTED
                ]).exists()
                if not already_acted:
                    actions.append('APPROVE')
                    actions.append('REJECT')

            if user == obj.requester or user.is_admin_user() or user.is_safety_officer():
                actions.append('CANCEL')

        # APPROVED state actions
        elif obj.status == Permit.Status.APPROVED:
            # Can activate if planned start has arrived or passed, and not expired
            if user == obj.requester or user.is_safety_officer() or user.is_admin_user():
                if now >= obj.planned_start and now <= obj.planned_end:
                    actions.append('ACTIVATE')
                actions.append('CANCEL')

        # ACTIVE state actions
        elif obj.status == Permit.Status.ACTIVE:
            # Safety officer or admin can suspend
            if user.is_safety_officer() or user.is_admin_user():
                actions.append('SUSPEND')

            # Requester can close their own permit
            if user == obj.requester or user.is_admin_user():
                actions.append('CLOSE')
                if obj.extension_status != 'REQUESTED' and now <= obj.planned_end:
                    actions.append('REQUEST_EXTENSION')

            if user == obj.requester or user.is_safety_officer() or user.is_admin_user():
                actions.append('CANCEL')

        # SUSPENDED state actions
        elif obj.status == Permit.Status.SUSPENDED:
            if user.is_safety_officer() or user.is_admin_user():
                actions.append('RESUME')
                actions.append('CANCEL')

        # CLOSED state actions
        elif obj.status == Permit.Status.CLOSED:
            # Safety officer verifies closure
            if user.is_safety_officer() or user.is_admin_user():
                actions.append('VERIFY_CLOSURE')

        # Extension review action
        if obj.extension_status == 'REQUESTED' and (user.is_safety_officer() or user.is_admin_user()):
            actions.append('REVIEW_EXTENSION')

        return actions


class PermitCreateUpdateSerializer(serializers.ModelSerializer):
    submit_immediately = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Permit
        fields = [
            'id', 'permit_number', 'permit_type', 'title', 'description',
            'contractor_name', 'team_size', 'equipment',
            'planned_start', 'planned_end', 'hazards', 'ppe_required',
            'precautions', 'type_data', 'submit_immediately'
        ]
        read_only_fields = ['permit_number']

    def validate(self, attrs):
        planned_start = attrs.get('planned_start')
        planned_end = attrs.get('planned_end')

        if self.instance:
            planned_start = planned_start or self.instance.planned_start
            planned_end = planned_end or self.instance.planned_end

        if planned_start and planned_end and planned_end <= planned_start:
            raise serializers.ValidationError({
                'planned_end': "Planned end time must be after planned start time."
            })

        # Validate type_data if submitted immediately or updating
        p_type = attrs.get('permit_type') or (self.instance.permit_type if self.instance else None)
        t_data = attrs.get('type_data') or (self.instance.type_data if self.instance else {})

        if attrs.get('submit_immediately'):
            validate_type_data(p_type, t_data)

        return attrs

    def create(self, validated_data):
        submit_now = validated_data.pop('submit_immediately', False)
        request = self.context['request']
        user = request.user

        # Generate unique permit number: PTW-YYYY-XXXX
        year = timezone.now().year
        last_permit = Permit.objects.filter(permit_number__startswith=f"PTW-{year}-").order_by('-id').first()
        seq = 1
        if last_permit and last_permit.permit_number:
            try:
                seq = int(last_permit.permit_number.split('-')[-1]) + 1
            except ValueError:
                seq = Permit.objects.count() + 1

        permit_number = f"PTW-{year}-{seq:04d}"

        permit = Permit.objects.create(
            permit_number=permit_number,
            requester=user,
            status=Permit.Status.DRAFT,
            **validated_data
        )

        PermitAuditLog.objects.create(
            permit=permit,
            actor=user,
            actor_name=user.get_full_name() or user.username,
            actor_role=user.get_role_display(),
            action="CREATED",
            from_status="NONE",
            to_status=Permit.Status.DRAFT,
            comment=f"Created {permit.get_permit_type_display()} draft.",
            details={"equipment": permit.equipment.name}
        )

        if submit_now:
            PermitStateMachine.submit(permit, user)

        return permit

    def update(self, instance, validated_data):
        submit_now = validated_data.pop('submit_immediately', False)
        request = self.context['request']
        user = request.user

        if instance.status != Permit.Status.DRAFT and not user.is_admin_user():
            raise serializers.ValidationError("Cannot edit a permit that has already been submitted.")

        # Track changes for audit log
        changed_fields = {}
        for k, v in validated_data.items():
            old_val = getattr(instance, k)
            if old_val != v:
                changed_fields[k] = {"from": str(old_val), "to": str(v)}
                setattr(instance, k, v)

        instance.save()

        if changed_fields:
            PermitAuditLog.objects.create(
                permit=instance,
                actor=user,
                actor_name=user.get_full_name() or user.username,
                actor_role=user.get_role_display(),
                action="UPDATED",
                from_status=instance.status,
                to_status=instance.status,
                comment=f"Updated fields: {', '.join(changed_fields.keys())}",
                details={"changed_fields": changed_fields}
            )

        if submit_now:
            PermitStateMachine.submit(instance, user)

        return instance
