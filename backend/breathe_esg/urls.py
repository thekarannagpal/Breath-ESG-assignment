from django.contrib import admin
from django.urls import path
from emissions import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Auth
    path('api/auth/login/', views.login_view),
    path('api/auth/me/', views.CurrentUserView.as_view()),
    
    # Dashboard stats
    path('api/dashboard/stats/', views.DashboardStatsView.as_view()),
    
    # Ingestion
    path('api/ingest/upload/', views.IngestUploadView.as_view()),
    path('api/ingest/sync/', views.IngestSyncView.as_view()),
    
    # Records
    path('api/records/raw/', views.RawRecordListView.as_view()),
    path('api/records/normalized/', views.NormalizedRecordListView.as_view()),
    
    # Review & approval workflow
    path('api/records/raw/<int:pk>/approve/', views.ApproveRecordView.as_view()),
    path('api/records/raw/<int:pk>/reject/', views.RejectRecordView.as_view()),
    path('api/records/raw/<int:pk>/unlock/', views.UnlockRecordView.as_view()),
    path('api/records/raw/<int:pk>/edit/', views.EditRecordView.as_view()),
    
    # Aux
    path('api/audit-logs/', views.AuditLogListView.as_view()),
    path('api/facilities/', views.FacilityListView.as_view()),
    path('api/seed/', views.TriggerSeedView.as_view()),
]
