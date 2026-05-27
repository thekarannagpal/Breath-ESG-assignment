from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Organization, UserProfile, Facility, IngestionJob, RawRecord, NormalizedRecord, AuditLog, EmissionFactor

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source='profile.role', read_only=True)
    organization_id = serializers.UUIDField(source='profile.organization.id', read_only=True)
    organization_name = serializers.CharField(source='profile.organization.name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'organization_id', 'organization_name']

class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ['id', 'name', 'facility_code', 'region']

class IngestionJobSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = IngestionJob
        fields = ['id', 'source_type', 'status', 'filename', 'summary', 'created_at', 'created_by_username']

class NormalizedRecordSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    facility_code = serializers.CharField(source='facility.facility_code', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True)

    class Meta:
        model = NormalizedRecord
        fields = [
            'id', 'facility', 'facility_name', 'facility_code', 'scope', 'category',
            'activity_date', 'start_date', 'end_date', 'raw_quantity', 'raw_unit',
            'normalized_quantity', 'normalized_unit', 'co2e_kg', 'calculation_metadata',
            'is_locked', 'approved_at', 'approved_by_username'
        ]

class RawRecordSerializer(serializers.ModelSerializer):
    normalized_record = NormalizedRecordSerializer(read_only=True)
    job_source = serializers.CharField(source='job.source_type', read_only=True)
    job_date = serializers.DateTimeField(source='job.created_at', read_only=True)

    class Meta:
        model = RawRecord
        fields = [
            'id', 'row_index', 'raw_data', 'status', 'validation_errors',
            'created_at', 'updated_at', 'normalized_record', 'job_source', 'job_date'
        ]

class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'username', 'timestamp', 'action', 'record_type', 'record_id', 'field_name', 'old_value', 'new_value', 'reason']

class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = '__all__'
