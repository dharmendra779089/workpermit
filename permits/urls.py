from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView, CurrentUserView, PermitTypeListView, DashboardStatsView,
    PlantViewSet, AreaViewSet, EquipmentViewSet, PermitViewSet
)

router = DefaultRouter()
router.register(r'plants', PlantViewSet, basename='plant')
router.register(r'areas', AreaViewSet, basename='area')
router.register(r'equipment', EquipmentViewSet, basename='equipment')
router.register(r'permits', PermitViewSet, basename='permit')

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/me/', CurrentUserView.as_view(), name='auth-me'),
    path('permit-types/', PermitTypeListView.as_view(), name='permit-types'),
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('', include(router.urls)),
]
