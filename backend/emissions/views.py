from django.shortcuts import render
from django.contrib.auth import authenticate, login
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from decimal import Decimal
import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes

from .models import Organization, UserProfile, Facility, IngestionJob, RawRecord, NormalizedRecord, AuditLog, EmissionFactor
from .serializers import (
    UserSerializer, OrganizationSerializer, FacilitySerializer, IngestionJobSerializer,
    RawRecordSerializer, NormalizedRecordSerializer, AuditLogSerializer, EmissionFactorSerializer
)
from .ingest import run_sap_ingestion, run_utility_ingestion, run_concur_ingestion

def get_organization(request):
    """
    Resolves organization from request header X-Tenant-ID (for demo switching)
    or falls back to the authenticated user's organization.
    """
    tenant_id = request.headers.get('X-Tenant-ID')
    if tenant_id and tenant_id != 'null' and tenant_id != 'undefined':
        try:
            return Organization.objects.get(id=tenant_id)
        except Exception:
            pass
            
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        return request.user.profile.organization
        
    # Default to first organization as a backup for demonstrations
    first_org = Organization.objects.first()
    return first_org

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    """
    Authenticates a user and returns profile + list of organizations for tenant-switching.
    """
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    
    if user is not None:
        login(request, user)
        user_serializer = UserSerializer(user)
        # Fetch all organizations to let frontend toggle between clients for demo
        orgs = Organization.objects.all()
        orgs_serializer = OrganizationSerializer(orgs, many=True)
        return Response({
            'user': user_serializer.data,
            'organizations': orgs_serializer.data
        })
    else:
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)

class CurrentUserView(APIView):
    def get(self, request):
        if request.user.is_authenticated:
            serializer = UserSerializer(request.user)
            orgs = Organization.objects.all()
            orgs_serializer = OrganizationSerializer(orgs, many=True)
            return Response({
                'user': serializer.data,
                'organizations': orgs_serializer.data
            })
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)

class DashboardStatsView(APIView):
    def get(self, request):
        org = get_organization(request)
        if not org:
            return Response({'error': 'No organization resolved'}, status=400)
            
        # 1. Total approved emissions (in metric tons CO2e: kg / 1000)
        approved_emissions_kg = NormalizedRecord.objects.filter(
            organization=org,
            raw_record__status='APPROVED'
        ).aggregate(total=Sum('co2e_kg'))['total'] or Decimal('0.0')
        approved_emissions_mt = approved_emissions_kg / Decimal('1000.0')
        
        # 2. Counts of raw records by status
        status_counts = RawRecord.objects.filter(organization=org).values('status').annotate(count=Count('id'))
        status_dict = {'PENDING': 0, 'APPROVED': 0, 'REJECTED': 0, 'SUSPICIOUS': 0}
        for entry in status_counts:
            status_dict[entry['status']] = entry['count']
            
        # 3. Scope Breakdown (in kg CO2e) for Approved records
        scope_breakdown = NormalizedRecord.objects.filter(
            organization=org,
            raw_record__status='APPROVED'
        ).values('scope').annotate(total_kg=Sum('co2e_kg'))
        
        scope_dict = {1: 0.0, 2: 0.0, 3: 0.0}
        for entry in scope_breakdown:
            scope_dict[entry['scope']] = float(entry['total_kg'])
            
        # 4. Ingestion Job List
        jobs = IngestionJob.objects.filter(organization=org).order_by('-created_at')[:10]
        jobs_serializer = IngestionJobSerializer(jobs, many=True)
        
        # 5. Monthly Emissions Trend (aggregating monthly pro-ratings)
        # For electricity utility records, we must sum from calendar_splits in calculation_metadata.
        # For other records, we group by activity_date month.
        monthly_data = {}
        
        # Non-electricity records
        non_elec = NormalizedRecord.objects.filter(
            organization=org,
            raw_record__status='APPROVED'
        ).exclude(category="Purchased Electricity")
        
        for rec in non_elec:
            month_str = rec.activity_date.strftime("%Y-%m")
            monthly_data[month_str] = monthly_data.get(month_str, 0.0) + float(rec.co2e_kg)
            
        # Electricity records (parsing their daily splits)
        elec = NormalizedRecord.objects.filter(
            organization=org,
            raw_record__status='APPROVED',
            category="Purchased Electricity"
        )
        
        for rec in elec:
            splits = rec.calculation_metadata.get('calendar_splits', [])
            if splits:
                for split in splits:
                    # split['month_start'] is YYYY-MM-DD
                    m_str = split['month_start'][:7] # YYYY-MM
                    monthly_data[m_str] = monthly_data.get(m_str, 0.0) + float(split['co2e_kg'])
            else:
                month_str = rec.activity_date.strftime("%Y-%m")
                monthly_data[month_str] = monthly_data.get(month_str, 0.0) + float(rec.co2e_kg)
                
        # Format trend list sorted by month
        trend_list = sorted(
            [{'month': m, 'co2e_mt': val / 1000.0} for m, val in monthly_data.items()],
            key=lambda x: x['month']
        )
        
        # 6. Category breakdown
        category_breakdown = NormalizedRecord.objects.filter(
            organization=org,
            raw_record__status='APPROVED'
        ).values('category').annotate(total_kg=Sum('co2e_kg'))
        
        cat_list = [{'category': item['category'], 'co2e_mt': float(item['total_kg']) / 1000.0} for item in category_breakdown]
        
        return Response({
            'organization': org.name,
            'approved_emissions_mt': float(approved_emissions_mt),
            'status_counts': status_dict,
            'scope_breakdown': scope_dict,
            'monthly_trend': trend_list,
            'category_breakdown': cat_list,
            'recent_jobs': jobs_serializer.data
        })

class IngestUploadView(APIView):
    def post(self, request):
        org = get_organization(request)
        source_type = request.data.get('source_type')
        uploaded_file = request.FILES.get('file')
        
        if not source_type or not uploaded_file:
            return Response({'error': 'source_type and file are required fields.'}, status=400)
            
        # Read file contents
        try:
            file_content = uploaded_file.read().decode('utf-8')
        except Exception as e:
            return Response({'error': f'Failed to decode file: {str(e)}'}, status=400)
            
        # Create Ingestion Job
        job = IngestionJob.objects.create(
            organization=org,
            source_type=source_type,
            status='RUNNING',
            filename=uploaded_file.name,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        # Dispatch parser
        success_cnt, failed_cnt, suspicious_cnt = 0, 0, 0
        if source_type == 'SAP':
            success_cnt, failed_cnt, suspicious_cnt = run_sap_ingestion(job.id, file_content)
        elif source_type == 'UTILITY':
            success_cnt, failed_cnt, suspicious_cnt = run_utility_ingestion(job.id, file_content)
        else:
            job.status = 'FAILED'
            job.summary = {'error': f'Unsupported source type for upload: {source_type}'}
            job.save()
            return Response({'error': 'Unsupported source type'}, status=400)
            
        return Response({
            'job_id': job.id,
            'status': job.status,
            'summary': {
                'success': success_cnt,
                'failed': failed_cnt,
                'suspicious': suspicious_cnt,
                'total': success_cnt + failed_cnt + suspicious_cnt
            }
        })

class IngestSyncView(APIView):
    """
    Simulates sync integration with corporate travel platforms (Concur/Navan).
    Uses realistic mock data representing flights (legs, cabins), hotels, and ground transport.
    """
    def post(self, request):
        org = get_organization(request)
        
        # Generate realistic corporate travel data payload
        mock_bookings = [
            {
                "booking_id": "BK-88091",
                "traveler_email": "jane.doe@acme.com",
                "type": "flight",
                "start_date": "2026-05-10",
                "end_date": "2026-05-10",
                "origin": "JFK",
                "destination": "LHR",
                "cabin_class": "Business",
                "passengers": 1,
                "amount": 2450.00
            },
            {
                "booking_id": "BK-88092",
                "traveler_email": "jane.doe@acme.com",
                "type": "hotel",
                "start_date": "2026-05-10",
                "end_date": "2026-05-15",
                "hotel_city": "London, UK",
                "hotel_nights": 5,
                "hotel_rooms": 1,
                "amount": 1250.00
            },
            {
                "booking_id": "BK-88093",
                "traveler_email": "john.smith@acme.com",
                "type": "flight",
                "start_date": "2026-05-12",
                "end_date": "2026-05-12",
                "origin": "SFO",
                "destination": "JFK",
                "cabin_class": "Economy",
                "passengers": 1,
                "amount": 420.00
            },
            {
                "booking_id": "BK-88094",
                "traveler_email": "john.smith@acme.com",
                "type": "car_rental",
                "start_date": "2026-05-12",
                "end_date": "2026-05-15",
                "distance_value": "150",
                "distance_unit": "miles",
                "fuel_type": "Petrol",
                "amount": 180.00
            },
            # Anomaly entry (flights over 15000 km or unknown airport codes)
            {
                "booking_id": "BK-88095",
                "traveler_email": "richard.hendricks@acme.com",
                "type": "flight",
                "start_date": "2026-05-15",
                "end_date": "2026-05-15",
                "origin": "JFK",
                "destination": "XYZ",  # Unknown airport code
                "cabin_class": "Economy",
                "passengers": 1,
                "amount": 900.00
            },
            # Financial Anomaly
            {
                "booking_id": "BK-88096",
                "traveler_email": "ceo@acme.com",
                "type": "hotel",
                "start_date": "2026-05-20",
                "end_date": "2026-05-21",
                "hotel_city": "New York, USA",
                "hotel_nights": 1,
                "hotel_rooms": 1,
                "amount": 12000.00 # > $10,000 limit
            }
        ]
        
        job = IngestionJob.objects.create(
            organization=org,
            source_type='CONCUR',
            status='RUNNING',
            filename='API_SYNC_CONCUR_MOCK',
            created_by=request.user if request.user.is_authenticated else None
        )
        
        success_cnt, failed_cnt, suspicious_cnt = run_concur_ingestion(job.id, mock_bookings)
        
        return Response({
            'job_id': job.id,
            'status': job.status,
            'summary': {
                'success': success_cnt,
                'failed': failed_cnt,
                'suspicious': suspicious_cnt,
                'total': len(mock_bookings)
            }
        })

class RawRecordListView(APIView):
    def get(self, request):
        org = get_organization(request)
        status_filter = request.query_params.get('status')
        source_filter = request.query_params.get('source_type')
        search_query = request.query_params.get('search')
        
        records = RawRecord.objects.filter(organization=org).select_related('job', 'normalized_record', 'normalized_record__facility')
        
        if status_filter:
            records = records.filter(status=status_filter)
        if source_filter:
            records = records.filter(job__source_type=source_filter)
        if search_query:
            # Simple text search on raw data values and errors
            records = records.filter(
                models.Q(raw_data__icontains=search_query) |
                models.Q(validation_errors__icontains=search_query)
            )
            
        serializer = RawRecordSerializer(records, many=True)
        return Response(serializer.data)

class NormalizedRecordListView(APIView):
    def get(self, request):
        org = get_organization(request)
        records = NormalizedRecord.objects.filter(organization=org).select_related('raw_record', 'facility')
        serializer = NormalizedRecordSerializer(records, many=True)
        return Response(serializer.data)

class ApproveRecordView(APIView):
    def post(self, request, pk):
        org = get_organization(request)
        try:
            raw_record = RawRecord.objects.get(id=pk, organization=org)
        except RawRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
            
        if not hasattr(raw_record, 'normalized_record'):
            return Response({'error': 'Record does not have a valid calculation mapping. Please fix errors first.'}, status=400)
            
        norm_record = raw_record.normalized_record
        if norm_record.is_locked:
            return Response({'error': 'Record is already approved and locked.'}, status=400)
            
        # Update raw record status
        raw_record.status = 'APPROVED'
        raw_record.save()
        
        # Update normalized record
        norm_record.is_locked = True
        norm_record.approved_at = timezone.now()
        norm_record.approved_by = request.user if request.user.is_authenticated else None
        norm_record.save()
        
        # Audit Log
        AuditLog.objects.create(
            organization=org,
            user=request.user if request.user.is_authenticated else None,
            action='APPROVE',
            record_type='RAW_RECORD',
            record_id=raw_record.id,
            reason=request.data.get('reason', 'Analyst review and sign off')
        )
        
        return Response({'message': 'Record successfully approved and locked for auditing.'})

class RejectRecordView(APIView):
    def post(self, request, pk):
        org = get_organization(request)
        try:
            raw_record = RawRecord.objects.get(id=pk, organization=org)
        except RawRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
            
        # Update status
        old_status = raw_record.status
        raw_record.status = 'REJECTED'
        raw_record.save()
        
        # Delete normalized counterpart if it existed, so it does not count in totals
        if hasattr(raw_record, 'normalized_record'):
            raw_record.normalized_record.delete()
            
        # Audit Log
        AuditLog.objects.create(
            organization=org,
            user=request.user if request.user.is_authenticated else None,
            action='REJECT',
            record_type='RAW_RECORD',
            record_id=raw_record.id,
            reason=request.data.get('reason', 'Analyst rejected raw entry')
        )
        
        return Response({'message': 'Record successfully rejected.'})

class UnlockRecordView(APIView):
    def post(self, request, pk):
        org = get_organization(request)
        
        # Strict user-role check: only admins can unlock records
        is_admin = False
        if request.user.is_authenticated and hasattr(request.user, 'profile'):
            is_admin = (request.user.profile.role == 'admin')
            
        # For prototype flexibility, we can bypass role check if it is done via demo
        bypass_role = request.headers.get('X-Bypass-Admin') == 'true'
        if not is_admin and not bypass_role:
            return Response({'error': 'Only users with the Admin role can unlock records.'}, status=403)
            
        try:
            raw_record = RawRecord.objects.get(id=pk, organization=org)
        except RawRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
            
        if not hasattr(raw_record, 'normalized_record'):
            return Response({'error': 'Record does not have a normalized counterpart'}, status=400)
            
        norm_record = raw_record.normalized_record
        norm_record.is_locked = False
        norm_record.approved_at = None
        norm_record.approved_by = None
        norm_record.save()
        
        raw_record.status = 'PENDING'
        raw_record.save()
        
        # Audit Log
        AuditLog.objects.create(
            organization=org,
            user=request.user if request.user.is_authenticated else None,
            action='UNLOCK',
            record_type='RAW_RECORD',
            record_id=raw_record.id,
            reason=request.data.get('reason', 'Admin unlocked record for adjustments')
        )
        
        return Response({'message': 'Record successfully unlocked for editing.'})

class EditRecordView(APIView):
    def post(self, request, pk):
        org = get_organization(request)
        try:
            raw_record = RawRecord.objects.get(id=pk, organization=org)
        except RawRecord.DoesNotExist:
            return Response({'error': 'Record not found'}, status=404)
            
        if hasattr(raw_record, 'normalized_record') and raw_record.normalized_record.is_locked:
            return Response({'error': 'Locked records cannot be edited. Please unlock first.'}, status=400)
            
        new_quantity_str = request.data.get('quantity')
        new_unit = request.data.get('unit')
        reason = request.data.get('reason', '')
        
        if not new_quantity_str or not reason:
            return Response({'error': 'Quantity and Reason are required.'}, status=400)
            
        try:
            new_quantity = Decimal(str(new_quantity_str))
        except Exception:
            return Response({'error': 'Invalid quantity decimal.'}, status=400)
            
        # Find category and previous values for auditing
        old_qty = Decimal('0.0')
        old_unit = ''
        category = 'diesel'
        
        # Determine category & current values
        job_source = raw_record.job.source_type
        if job_source == 'SAP':
            old_qty = parse_decimal(raw_record.raw_data.get('Menge', raw_record.raw_data.get('MENGE', '0')))
            old_unit = raw_record.raw_data.get('Einheit', raw_record.raw_data.get('MEINS', 'L')).upper()
            desc = raw_record.raw_data.get('Materialkurztext', raw_record.raw_data.get('MAKTX', '')).lower()
            category = 'natural_gas' if 'gas' in desc else 'diesel'
        elif job_source == 'UTILITY':
            old_qty = parse_decimal(raw_record.raw_data.get('Usage', raw_record.raw_data.get('usage', '0')))
            old_unit = raw_record.raw_data.get('Unit', raw_record.raw_data.get('unit', 'kWh')).upper()
            category = 'electricity'
        elif job_source == 'CONCUR':
            booking_type = raw_record.raw_data.get('type', '').lower()
            if booking_type == 'flight':
                old_qty = Decimal(str(raw_record.raw_data.get('distance_value', 100))) # flights default km
                old_unit = 'km'
                category = 'flight_long' if old_qty > 480 else 'flight_short'
            elif booking_type == 'hotel':
                old_qty = Decimal(str(int(raw_record.raw_data.get('hotel_nights', 1)) * int(raw_record.raw_data.get('hotel_rooms', 1))))
                old_unit = 'room_nights'
                category = 'hotel_night'
            else:
                old_qty = Decimal(str(raw_record.raw_data.get('distance_value', '0')))
                old_unit = raw_record.raw_data.get('distance_unit', 'km')
                category = 'car_petrol'
                
        # Perform recalculation
        resolved_unit = new_unit or old_unit
        
        # Normalize unit names
        norm_lookup_unit = resolved_unit.upper()
        if norm_lookup_unit in ('LTR', 'L', 'LIT'):
            norm_lookup_unit = 'L'
        elif norm_lookup_unit in ('TO', 'TON', 'T'):
            norm_lookup_unit = 'TO'
        elif norm_lookup_unit in ('KG', 'KILO'):
            norm_lookup_unit = 'KG'
        elif norm_lookup_unit in ('M3', 'M³', 'CUM'):
            norm_lookup_unit = 'm3'
        elif norm_lookup_unit in ('KWH', 'KILO WATT HOUR'):
            norm_lookup_unit = 'kWh'
        elif norm_lookup_unit in ('MWH', 'MEGA WATT HOUR'):
            norm_lookup_unit = 'MWh'
            
        region = 'GLOBAL'
        facility = None
        if hasattr(raw_record, 'normalized_record') and raw_record.normalized_record.facility:
            facility = raw_record.normalized_record.facility
            region = facility.region
            
        ef = EmissionFactor.objects.filter(category=category, raw_unit=norm_lookup_unit, region=region).first()
        if not ef:
            ef = EmissionFactor.objects.filter(category=category, raw_unit=norm_lookup_unit, region='GLOBAL').first()
            
        if not ef:
            return Response({'error': f'No emission factor found for category {category} and unit {resolved_unit}'}, status=400)
            
        norm_qty = new_quantity * ef.conversion_multiplier
        co2e = norm_qty * ef.factor_kg_co2e
        
        # Update raw record payload and clear errors
        raw_payload = dict(raw_record.raw_data)
        # Update the respective field in the raw data JSON payload to represent the override
        if job_source == 'SAP':
            for k in raw_payload.keys():
                if k.lower() in ('menge', 'quantity', 'qty'):
                    raw_payload[k] = str(new_quantity)
                if k.lower() in ('meins', 'einheit', 'unit'):
                    raw_payload[k] = resolved_unit
        elif job_source == 'UTILITY':
            for k in raw_payload.keys():
                if k.lower() in ('usage', 'quantity'):
                    raw_payload[k] = str(new_quantity)
                if k.lower() in ('unit', 'uom'):
                    raw_payload[k] = resolved_unit
        elif job_source == 'CONCUR':
            booking_type = raw_payload.get('type', '').lower()
            if booking_type == 'flight':
                raw_payload['distance_value'] = str(new_quantity)
            elif booking_type == 'hotel':
                raw_payload['hotel_nights'] = str(new_quantity)
                raw_payload['hotel_rooms'] = "1"
            else:
                raw_payload['distance_value'] = str(new_quantity)
                raw_payload['distance_unit'] = resolved_unit
                
        raw_record.raw_data = raw_payload
        raw_record.status = 'PENDING'  # Needs approval again
        raw_record.validation_errors = []
        raw_record.save()
        
        # Build split breakdown if Utility electricity
        calc_metadata = {
            "formula": "Quantity * ConversionMultiplier * EmissionFactor (Manual Override)",
            "conversion_multiplier": str(ef.conversion_multiplier),
            "factor_kg_co2e": str(ef.factor_kg_co2e),
            "factor_id": ef.id,
            "region_applied": ef.region
        }
        
        if category == 'electricity' and hasattr(raw_record, 'normalized_record') and raw_record.normalized_record.start_date:
            from .ingest import split_utility_period
            splits = split_utility_period(
                raw_record.normalized_record.start_date,
                raw_record.normalized_record.end_date,
                new_quantity
            )
            split_breakdowns = []
            for s in splits:
                split_qty = s['usage'] * ef.conversion_multiplier
                split_co2e = split_qty * ef.factor_kg_co2e
                split_breakdowns.append({
                    "month_start": s['month_start'].strftime("%Y-%m-%d"),
                    "days_in_month": s['days'],
                    "usage_kwh": str(split_qty.quantize(Decimal('0.0001'))),
                    "co2e_kg": str(split_co2e.quantize(Decimal('0.0001')))
                })
            calc_metadata["calendar_splits"] = split_breakdowns

        # Update or create NormalizedRecord
        normalized_record, _ = NormalizedRecord.objects.update_or_create(
            organization=org,
            raw_record=raw_record,
            defaults={
                'facility': facility,
                'scope': ef.scope,
                'category': raw_record.normalized_record.category if hasattr(raw_record, 'normalized_record') else 'Manual Override',
                'activity_date': raw_record.normalized_record.activity_date if hasattr(raw_record, 'normalized_record') else timezone.now().date(),
                'start_date': raw_record.normalized_record.start_date if hasattr(raw_record, 'normalized_record') else None,
                'end_date': raw_record.normalized_record.end_date if hasattr(raw_record, 'normalized_record') else None,
                'raw_quantity': new_quantity,
                'raw_unit': resolved_unit,
                'normalized_quantity': norm_qty,
                'normalized_unit': ef.normalized_unit,
                'co2e_kg': co2e,
                'calculation_metadata': calc_metadata,
                'is_locked': False
            }
        )
        
        # Log Audit Trail for quantity edit
        AuditLog.objects.create(
            organization=org,
            user=request.user if request.user.is_authenticated else None,
            action='UPDATE',
            record_type='RAW_RECORD',
            record_id=raw_record.id,
            field_name='Quantity',
            old_value=f"{old_qty} {old_unit}",
            new_value=f"{new_quantity} {resolved_unit}",
            reason=reason
        )
        
        return Response({
            'message': 'Record updated and recalculated successfully.',
            'raw_record_status': raw_record.status,
            'new_co2e_kg': float(co2e)
        })

class AuditLogListView(APIView):
    def get(self, request):
        org = get_organization(request)
        logs = AuditLog.objects.filter(organization=org).order_by('-timestamp')
        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data)

class FacilityListView(APIView):
    def get(self, request):
        org = get_organization(request)
        facilities = Facility.objects.filter(organization=org)
        serializer = FacilitySerializer(facilities, many=True)
        return Response(serializer.data)
        
    def post(self, request):
        org = get_organization(request)
        serializer = FacilitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(organization=org)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TriggerSeedView(APIView):
    @permission_classes([permissions.AllowAny])
    def post(self, request):
        from django.core.management import call_command
        try:
            call_command('seed_data')
            return Response({'message': 'Seeding trigger completed successfully!'})
        except Exception as e:
            return Response({'error': str(e)}, status=500)
