from django.db import models
from django.contrib.auth.models import User
import uuid

class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('analyst', 'Analyst'),
        ('auditor', 'Auditor'),
        ('admin', 'Admin'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='analyst')

    def __str__(self):
        return f"{self.user.username} ({self.role}) - {self.organization.name}"

class Facility(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='facilities')
    name = models.CharField(max_length=255)
    facility_code = models.CharField(max_length=100, help_text="SAP Plant Code or Utility Meter/Account number")
    region = models.CharField(max_length=100, help_text="Used for regional electricity grid factor lookup (e.g. US-CA, US-NY, DE, UK)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'facility_code')
        verbose_name_plural = "Facilities"

    def __str__(self):
        return f"{self.name} ({self.facility_code}) - {self.organization.name}"

class IngestionJob(models.Model):
    SOURCE_CHOICES = (
        ('SAP', 'SAP ERP (Fuel & Procurement)'),
        ('UTILITY', 'Utility Portal (Electricity)'),
        ('CONCUR', 'Corporate Travel (Concur/Navan)'),
    )
    STATUS_CHOICES = (
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ingestion_jobs')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RUNNING')
    filename = models.CharField(max_length=255, blank=True, null=True)
    summary = models.JSONField(default=dict, help_text="Stores counts: {total, success, failed, suspicious}")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.source_type} Ingest - {self.created_at.strftime('%Y-%m-%d %H:%M')} - {self.status}"

class RawRecord(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('SUSPICIOUS', 'Suspicious (Requires Verification)'),
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='raw_records')
    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='raw_records')
    row_index = models.IntegerField(help_text="Line number or sequence index in the source data")
    raw_data = models.JSONField(help_text="Exact raw key-value pairs ingested from source")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    validation_errors = models.JSONField(default=list, blank=True, help_text="List of validation failures or reasons for suspicious tag")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['job', 'row_index']

    def __str__(self):
        return f"Raw Record {self.row_index} [{self.job.source_type}] - {self.status}"

class NormalizedRecord(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='normalized_records')
    raw_record = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name='normalized_record')
    facility = models.ForeignKey(Facility, on_delete=models.SET_NULL, null=True, blank=True, help_text="Mapped plant or facility")
    
    scope = models.IntegerField(choices=((1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')))
    category = models.CharField(max_length=100, help_text="e.g. Stationary Combustion, Purchased Electricity, Business Travel")
    
    activity_date = models.DateField(help_text="Normalized transaction date or month-start")
    start_date = models.DateField(blank=True, null=True, help_text="Start of billing or activity period")
    end_date = models.DateField(blank=True, null=True, help_text="End of billing or activity period")
    
    raw_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    raw_unit = models.CharField(max_length=50)
    
    normalized_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    normalized_unit = models.CharField(max_length=50, help_text="Base unit (e.g. kWh, Liters, Passenger-km)")
    
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4)
    calculation_metadata = models.JSONField(default=dict, help_text="Calculated using: formula, emission_factor, source_factor_link")
    
    is_locked = models.BooleanField(default=False, help_text="Locked once approved. Edits blocked unless unlocked by Admin")
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approvals')

    def __str__(self):
        return f"Normalized Scope {self.scope} [{self.category}] - {self.co2e_kg} kg CO2e"

class AuditLog(models.Model):
    ACTION_CHOICES = (
        ('CREATE', 'Created Record'),
        ('UPDATE', 'Updated Value'),
        ('APPROVE', 'Approved & Locked'),
        ('REJECT', 'Rejected Record'),
        ('UNLOCK', 'Unlocked Record'),
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    record_type = models.CharField(max_length=50, help_text="RAW_RECORD or NORMALIZED_RECORD")
    record_id = models.IntegerField()
    field_name = models.CharField(max_length=100, blank=True, null=True, help_text="Name of the edited field, if applicable")
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    reason = models.TextField(help_text="Justification provided by the analyst")

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"{user_str} - {self.action} on {self.record_type} #{self.record_id} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

class EmissionFactor(models.Model):
    category = models.CharField(max_length=100, help_text="e.g. diesel, natural_gas, electricity, flight_short, flight_long, hotel_night, car_diesel, car_petrol, car_electric")
    raw_unit = models.CharField(max_length=50, help_text="Unit we expect from input (e.g. L, Gallon, m3, kWh, MWh, mi, km)")
    normalized_unit = models.CharField(max_length=50, help_text="Base unit (e.g. L, m3, kWh, pkm, room_night)")
    conversion_multiplier = models.DecimalField(max_digits=12, decimal_places=6, default=1.0, help_text="Multiply raw quantity by this to get normalized quantity")
    factor_kg_co2e = models.DecimalField(max_digits=12, decimal_places=6, help_text="Emissions factor per normalized unit")
    region = models.CharField(max_length=100, default="GLOBAL", help_text="e.g. US-CA (California grid), DE (German grid), UK, GLOBAL")
    scope = models.IntegerField(choices=((1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')))

    class Meta:
        unique_together = ('category', 'raw_unit', 'region')

    def __str__(self):
        return f"{self.category} ({self.raw_unit} -> {self.normalized_unit}) in {self.region}: {self.factor_kg_co2e} kg CO2e"
