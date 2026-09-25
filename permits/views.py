"""
API Views for Opmaint Permit to Work (PTW) CMMS module.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import render
from datetime import timedelta

from .models import User, Plant, Area, Equipment, Permit, PermitApproval, PermitAuditLog
from .schemas import PERMIT_TYPE_REGISTRY
from .serializers import (
    UserSerializer, PlantSerializer, AreaSerializer, EquipmentSerializer,
    PermitListSerializer, PermitDetailSerializer, PermitCreateUpdateSerializer,
    PermitApprovalSerializer, PermitAuditLogSerializer
)
from .services import PermitStateMachine, ConflictDetector


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data


class LoginView(TokenObtainPairView):
    """
    Login endpoint returning JWT tokens and user profile.
    """
    serializer_class = CustomTokenObtainPairSerializer


class CurrentUserView(APIView):
    """
    Returns current authenticated user profile.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PermitTypeListView(APIView):
    """
    Exposes declarative Permit Type Registry.
    Frontend dynamically renders type-specific forms from this specification.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(list(PERMIT_TYPE_REGISTRY.values()))


class PlantViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Plant.objects.all().order_by('name')
    serializer_class = PlantSerializer
    permission_classes = [permissions.IsAuthenticated]


class AreaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Area.objects.all().select_related('plant', 'owner').order_by('name')
    serializer_class = AreaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        plant_id = self.request.query_params.get('plant')
        if plant_id:
            qs = qs.filter(plant_id=plant_id)
        return qs


class EquipmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Equipment.objects.all().select_related('area__plant').order_by('name')
    serializer_class = EquipmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        area_id = self.request.query_params.get('area')
        plant_id = self.request.query_params.get('plant')
        if area_id:
            qs = qs.filter(area_id=area_id)
        elif plant_id:
            qs = qs.filter(area__plant_id=plant_id)
        return qs


class DashboardStatsView(APIView):
    """
    KPI Statistics for CMMS Safety Operations Center.
    - Active right now
    - Expiring in next 2 hours
    - Pending my approval
    - Suspended
    - Total permits
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        two_hours_later = now + timedelta(hours=2)

        # Trigger auto-expiry updates across expirable permits
        expirable = Permit.objects.filter(
            status__in=[Permit.Status.PENDING_APPROVAL, Permit.Status.APPROVED, Permit.Status.ACTIVE, Permit.Status.SUSPENDED],
            planned_end__lt=now
        )
        for p in expirable:
            p.check_and_update_expiry()

        total_permits = Permit.objects.count()
        active_count = Permit.objects.filter(status=Permit.Status.ACTIVE).count()
        expiring_soon_count = Permit.objects.filter(
            status__in=[Permit.Status.ACTIVE, Permit.Status.APPROVED],
            planned_end__gt=now,
            planned_end__lte=two_hours_later
        ).count()
        suspended_count = Permit.objects.filter(status=Permit.Status.SUSPENDED).count()

        # Compute pending my approvals
        pending_my_approval = 0
        if user.is_safety_officer() or user.is_area_owner() or user.is_admin_user():
            pending_candidates = Permit.objects.filter(status=Permit.Status.PENDING_APPROVAL).exclude(requester=user)
            for p in pending_candidates:
                can_app, _ = PermitStateMachine.can_user_approve(p, user)
                if can_app:
                    role_type = PermitApproval.RoleType.SAFETY_OFFICER if user.is_safety_officer() else PermitApproval.RoleType.AREA_OWNER
                    already_approved = p.approvals.filter(role_type=role_type, status=PermitApproval.ApprovalStatus.APPROVED).exists()
                    if not already_approved:
                        pending_my_approval += 1

        return Response({
            'total_permits': total_permits,
            'active_count': active_count,
            'expiring_soon_count': expiring_soon_count,
            'pending_my_approval_count': pending_my_approval,
            'suspended_count': suspended_count,
            'timestamp': now.isoformat()
        })


class PermitViewSet(viewsets.ModelViewSet):
    """
    Core Permit to Work API ViewSet.
    Manages CRUD and server-side state machine lifecycle transitions.
    """
    queryset = Permit.objects.all().select_related('requester', 'equipment__area__plant')
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PermitCreateUpdateSerializer
        if self.action == 'retrieve':
            return PermitDetailSerializer
        return PermitListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        now = timezone.now()

        # Auto-expire permits on query
        expired_candidates = qs.filter(
            status__in=[Permit.Status.PENDING_APPROVAL, Permit.Status.APPROVED, Permit.Status.ACTIVE, Permit.Status.SUSPENDED],
            planned_end__lt=now
        )
        for p in expired_candidates:
            p.check_and_update_expiry()

        # Filters
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        permit_type = self.request.query_params.get('permit_type')
        if permit_type:
            qs = qs.filter(permit_type=permit_type)

        area_id = self.request.query_params.get('area')
        if area_id:
            qs = qs.filter(equipment__area_id=area_id)

        plant_id = self.request.query_params.get('plant')
        if plant_id:
            qs = qs.filter(equipment__area__plant_id=plant_id)

        expiring_soon = self.request.query_params.get('expiring_soon')
        if expiring_soon == 'true':
            two_hours = now + timedelta(hours=2)
            qs = qs.filter(
                status__in=[Permit.Status.ACTIVE, Permit.Status.APPROVED],
                planned_end__gt=now,
                planned_end__lte=two_hours
            )

        my_approvals = self.request.query_params.get('my_approvals')
        if my_approvals == 'true':
            # Filter permits pending current user's approval
            if user.is_safety_officer():
                # Pending permits where safety approval not yet given and not requested by user
                qs = qs.filter(status=Permit.Status.PENDING_APPROVAL).exclude(requester=user).exclude(
                    approvals__role_type=PermitApproval.RoleType.SAFETY_OFFICER,
                    approvals__status=PermitApproval.ApprovalStatus.APPROVED
                )
            elif user.is_area_owner():
                # Owned area permits where area approval not yet given and not requested by user
                owned_areas = Area.objects.filter(Q(owner=user) | Q(id=user.assigned_area_id if hasattr(user, 'assigned_area_id') else None))
                qs = qs.filter(
                    status=Permit.Status.PENDING_APPROVAL,
                    equipment__area__in=owned_areas
                ).exclude(requester=user).exclude(
                    approvals__role_type=PermitApproval.RoleType.AREA_OWNER,
                    approvals__status=PermitApproval.ApprovalStatus.APPROVED
                )
            elif user.is_admin_user():
                qs = qs.filter(status=Permit.Status.PENDING_APPROVAL).exclude(requester=user)
            else:
                qs = qs.none()

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(permit_number__icontains=search) |
                Q(title__icontains=search) |
                Q(contractor_name__icontains=search) |
                Q(equipment__tag_number__icontains=search) |
                Q(equipment__name__icontains=search)
            )

        start_date = self.request.query_params.get('start_date')
        if start_date:
            qs = qs.filter(planned_start__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            qs = qs.filter(planned_end__lte=end_date)

        return qs

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        permit = self.get_object()
        updated_permit = PermitStateMachine.submit(permit, request.user)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        permit = self.get_object()
        comment = request.data.get('comment', '')
        signature_data = request.data.get('signature_data', '')
        updated_permit = PermitStateMachine.approve(permit, request.user, comment=comment, signature_data=signature_data)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        permit = self.get_object()
        reason = request.data.get('reason', '')
        updated_permit = PermitStateMachine.reject(permit, request.user, reason=reason)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        permit = self.get_object()
        updated_permit = PermitStateMachine.activate(permit, request.user)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        permit = self.get_object()
        reason = request.data.get('reason', '')
        updated_permit = PermitStateMachine.suspend(permit, request.user, reason=reason)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        permit = self.get_object()
        notes = request.data.get('notes', '')
        updated_permit = PermitStateMachine.resume(permit, request.user, notes=notes)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        permit = self.get_object()
        completion_notes = request.data.get('completion_notes', '')
        updated_permit = PermitStateMachine.close(permit, request.user, completion_notes=completion_notes)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def verify_closure(self, request, pk=None):
        permit = self.get_object()
        notes = request.data.get('notes', '')
        updated_permit = PermitStateMachine.verify_closure(permit, request.user, notes=notes)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        permit = self.get_object()
        reason = request.data.get('reason', '')
        updated_permit = PermitStateMachine.cancel(permit, request.user, reason=reason)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def request_extension(self, request, pk=None):
        permit = self.get_object()
        hours = int(request.data.get('hours', 2))
        reason = request.data.get('reason', '')
        updated_permit = PermitStateMachine.request_extension(permit, request.user, hours=hours, reason=reason)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def approve_extension(self, request, pk=None):
        permit = self.get_object()
        approved = bool(request.data.get('approved', True))
        comment = request.data.get('comment', '')
        updated_permit = PermitStateMachine.approve_extension(permit, request.user, approved=approved, comment=comment)
        return Response(PermitDetailSerializer(updated_permit, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def conflicts(self, request, pk=None):
        permit = self.get_object()
        conflict_list = ConflictDetector.check_conflicts(permit)
        return Response(conflict_list)

    @action(detail=False, methods=['post'])
    def pre_check_conflicts(self, request):
        """
        Pre-checks conflicts prior to permit submission during wizard form creation.
        """
        eq_id = request.data.get('equipment_id')
        start = request.data.get('planned_start')
        end = request.data.get('planned_end')
        p_type = request.data.get('permit_type')

        if not eq_id or not start or not end or not p_type:
            return Response({'conflicts': []})

        try:
            eq = Equipment.objects.get(id=eq_id)
            conflicts = ConflictDetector.check_conflicts(
                permit=None, equipment=eq, start_time=start, end_time=end, permit_type=p_type
            )
            return Response({'conflicts': conflicts})
        except Equipment.DoesNotExist:
            return Response({'conflicts': []})


def frontend_index(request):
    """
    Renders SPA HTML index.
    """
    return render(request, 'index.html')
