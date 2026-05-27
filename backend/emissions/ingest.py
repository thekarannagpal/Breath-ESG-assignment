import csv
import json
import math
from datetime import datetime, timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import IngestionJob, RawRecord, NormalizedRecord, Facility, EmissionFactor, AuditLog

# Standard airport coordinates database for travel distance calculations
AIRPORT_COORDINATES = {
    'JFK': (40.6398, -73.7789),
    'LHR': (51.4700, -0.4543),
    'CDG': (49.0097, 2.5479),
    'SIN': (1.3502, 103.9944),
    'DXB': (25.2532, 55.3657),
    'HND': (35.5494, 139.7798),
    'SFO': (37.6190, -122.3749),
    'LAX': (33.9416, -118.4085),
    'ORD': (41.9742, -87.9073),
    'BOS': (42.3656, -71.0096),
    'FRA': (50.0333, 8.5705),
    'SYD': (-33.9461, 151.1772),
    'HNL': (21.3187, -157.9225),
    'NRT': (35.7720, 140.3929),
    'HKG': (22.3080, 113.9185),
    'DEL': (28.5562, 77.1000),
    'BOM': (19.0896, 72.8656),
}

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) in kilometers.
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

def parse_decimal(val_str):
    """
    Parses a decimal value from string, handling European/German number format
    where '.' is the thousands separator and ',' is the decimal separator.
    """
    if not val_str:
        return Decimal('0.0')
    val_str = val_str.strip()
    # Check if this looks like a German number (e.g. 1.250,50 or 250,00)
    if ',' in val_str:
        # If there's a dot and a comma, and the dot comes first, remove dot and replace comma with dot
        if '.' in val_str and val_str.find('.') < val_str.find(','):
            val_str = val_str.replace('.', '')
        val_str = val_str.replace(',', '.')
    # Remove any thousands separator dot if it remains and there is no comma
    elif val_str.count('.') > 1:
        val_str = val_str.replace('.', '')
    
    try:
        return Decimal(val_str)
    except Exception:
        raise ValueError(f"Invalid decimal format: '{val_str}'")

def parse_date(date_str):
    """
    Parses dates in YYYYMMDD, YYYY-MM-DD, or German DD.MM.YYYY format.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    
    # Try YYYY-MM-DD
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y%m%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: '{date_str}'")

def split_utility_period(start_date, end_date, total_usage):
    """
    Splits billing period usage proportionally across the calendar months it covers.
    Returns list of dicts: [{'month_start': date, 'days': int, 'usage': Decimal}]
    """
    if start_date >= end_date:
        raise ValueError("Start date must be before end date")
        
    total_days = (end_date - start_date).days + 1
    if total_days <= 0:
        total_days = 1
        
    daily_rate = Decimal(total_usage) / Decimal(total_days)
    splits = []
    
    current_date = start_date
    while current_date <= end_date:
        # Determine the end of the current month or end_date (whichever is earlier)
        year = current_date.year
        month = current_date.month
        
        # Start of next month
        if month == 12:
            next_month_start = datetime(year + 1, 1, 1).date()
        else:
            next_month_start = datetime(year, month + 1, 1).date()
            
        chunk_end = min(next_month_start - timedelta(days=1), end_date)
        chunk_days = (chunk_end - current_date).days + 1
        
        # Month start date
        month_start = datetime(year, month, 1).date()
        
        chunk_usage = daily_rate * Decimal(chunk_days)
        
        # Aggregate if month is already in splits
        existing = next((s for s in splits if s['month_start'] == month_start), None)
        if existing:
            existing['days'] += chunk_days
            existing['usage'] += chunk_usage
        else:
            splits.append({
                'month_start': month_start,
                'days': chunk_days,
                'usage': chunk_usage
            })
            
        current_date = chunk_end + timedelta(days=1)
        
    return splits

@transaction.atomic
def run_sap_ingestion(job_id, file_content):
    """
    Ingests SAP procurement & fuel movement data from a CSV file content.
    Returns (success_count, failed_count, suspicious_count)
    """
    job = IngestionJob.objects.select_for_update().get(id=job_id)
    org = job.organization
    
    reader = csv.reader(file_content.splitlines())
    header = next(reader, None)
    if not header:
        job.status = 'FAILED'
        job.summary = {'error': 'Empty CSV file'}
        job.save()
        return 0, 0, 0
        
    # Map headers (case insensitive, support German translations)
    # German headers commonly: Materialbeleg (MBLNR), Buchungsdatum (BUDAT), Materialnummer (MATNR),
    # Materialkurztext (MAKTX), Menge (MENGE), Einheit (MEINS), Werk (WERKS), Einkaufsbeleg (EBELN)
    header_map = {}
    for idx, col in enumerate(header):
        col_clean = col.strip().lower()
        if col_clean in ('mblnr', 'materialbeleg', 'doc_num', 'document'):
            header_map['doc'] = idx
        elif col_clean in ('budat', 'buchungsdatum', 'post_date', 'date'):
            header_map['date'] = idx
        elif col_clean in ('matnr', 'materialnummer', 'material_num'):
            header_map['material'] = idx
        elif col_clean in ('maktx', 'materialkurztext', 'material_text', 'description'):
            header_map['desc'] = idx
        elif col_clean in ('menge', 'menge_qty', 'quantity', 'qty'):
            header_map['qty'] = idx
        elif col_clean in ('meins', 'einheit', 'unit', 'uom'):
            header_map['unit'] = idx
        elif col_clean in ('werks', 'werk', 'plant', 'plant_code'):
            header_map['plant'] = idx
        elif col_clean in ('ebeln', 'einkaufsbeleg', 'po_number', 'purchase_order'):
            header_map['po'] = idx
            
    required_keys = ['doc', 'date', 'qty', 'unit', 'plant']
    missing_keys = [k for k in required_keys if k not in header_map]
    if missing_keys:
        job.status = 'FAILED'
        job.summary = {'error': f'Missing required columns: {", ".join(missing_keys)}. Found headers: {header}'}
        job.save()
        return 0, 0, 0

    success_cnt = 0
    failed_cnt = 0
    suspicious_cnt = 0
    
    row_idx = 1
    for row in reader:
        row_idx += 1
        if not row or not any(row):
            continue
            
        raw_payload = {header[i]: row[i] for i in range(len(row)) if i < len(header)}
        validation_errors = []
        is_suspicious = False
        
        try:
            # Parse row data
            doc_val = row[header_map['doc']].strip()
            date_raw = row[header_map['date']].strip()
            qty_raw = row[header_map['qty']].strip()
            unit_raw = row[header_map['unit']].strip().upper()
            plant_code = row[header_map['plant']].strip()
            mat_num = row[header_map['material']].strip() if 'material' in header_map else ''
            mat_desc = row[header_map['desc']].strip() if 'desc' in header_map else ''
            po_num = row[header_map['po']].strip() if 'po' in header_map else ''
            
            # 1. Parse Date
            try:
                activity_date = parse_date(date_raw)
            except Exception as e:
                raise ValueError(f"Invalid date format: {str(e)}")
                
            # 2. Parse Quantity
            try:
                quantity = parse_decimal(qty_raw)
            except Exception as e:
                raise ValueError(f"Invalid quantity format: {str(e)}")
                
            # 3. Look up Plant / Facility
            facility = Facility.objects.filter(organization=org, facility_code=plant_code).first()
            if not facility:
                validation_errors.append(f"Plant code '{plant_code}' is not mapped to any Facility. Please map it first.")
                is_suspicious = True
                
            # 4. Map fuel type to emission factor category
            # Let's map mat_num or mat_desc to standard categories: diesel, natural_gas
            category = None
            mat_desc_lower = mat_desc.lower()
            mat_num_lower = mat_num.lower()
            
            if 'diesel' in mat_desc_lower or 'diesel' in mat_num_lower or 'fuel' in mat_desc_lower:
                category = 'diesel'
            elif 'natural gas' in mat_desc_lower or 'erdgas' in mat_desc_lower or 'gas' in mat_desc_lower:
                category = 'natural_gas'
            elif 'oil' in mat_desc_lower or 'heizöl' in mat_desc_lower:
                category = 'heavy_oil'
            else:
                validation_errors.append(f"Unmapped material '{mat_num}' / '{mat_desc}'. Material must be classified as diesel, natural_gas, or oil.")
                is_suspicious = True
                
            # 5. Look up Emission Factor and Normalization rules
            ef = None
            if category:
                # Resolve unit naming (German/SAP specific: e.g. Ltr -> L, TO -> TON)
                resolved_unit = unit_raw
                if resolved_unit in ('LTR', 'L', 'LIT'):
                    resolved_unit = 'L'
                elif resolved_unit in ('TO', 'TON', 'T'):
                    resolved_unit = 'TO'
                elif resolved_unit in ('KG', 'KILO'):
                    resolved_unit = 'KG'
                elif resolved_unit in ('M3', 'M³', 'CUM'):
                    resolved_unit = 'm3'
                
                # Check for region. SAP plants are region specific (facility location)
                region = facility.region if facility else 'GLOBAL'
                ef = EmissionFactor.objects.filter(category=category, raw_unit=resolved_unit, region=region).first()
                if not ef:
                    # Fallback to GLOBAL
                    ef = EmissionFactor.objects.filter(category=category, raw_unit=resolved_unit, region='GLOBAL').first()
                    
                if not ef:
                    validation_errors.append(f"No emission factor found for category '{category}' and raw unit '{unit_raw}' in region '{region}'")
                    is_suspicious = True

            # Anomaly Checks
            if quantity < 0:
                validation_errors.append("Negative fuel quantity detected.")
                is_suspicious = True
                
            if quantity > 100000:
                validation_errors.append(f"Extremely high quantity detected: {quantity} {unit_raw}. Flagged for safety review.")
                is_suspicious = True

            # Save Raw Record
            status = 'SUSPICIOUS' if is_suspicious else 'PENDING'
            if validation_errors and not any("is not mapped" in e or "No emission factor" in e for e in validation_errors):
                # If there are hard errors that prevent calculation, it's failed, but here we can still save as pending/suspicious
                pass
                
            raw_rec = RawRecord.objects.create(
                organization=org,
                job=job,
                row_index=row_idx,
                raw_data=raw_payload,
                status=status,
                validation_errors=validation_errors
            )
            
            if not validation_errors and ef:
                # Perform calculation and save normalized record
                norm_qty = quantity * ef.conversion_multiplier
                co2e = norm_qty * ef.factor_kg_co2e
                
                calc_metadata = {
                    "formula": "Quantity * ConversionMultiplier * EmissionFactor",
                    "conversion_multiplier": str(ef.conversion_multiplier),
                    "factor_kg_co2e": str(ef.factor_kg_co2e),
                    "factor_id": ef.id,
                    "region_applied": ef.region
                }
                
                NormalizedRecord.objects.create(
                    organization=org,
                    raw_record=raw_rec,
                    facility=facility,
                    scope=ef.scope,
                    category=f"Stationary Combustion ({category.replace('_', ' ').title()})",
                    activity_date=activity_date,
                    start_date=activity_date,
                    end_date=activity_date,
                    raw_quantity=quantity,
                    raw_unit=unit_raw,
                    normalized_quantity=norm_qty,
                    normalized_unit=ef.normalized_unit,
                    co2e_kg=co2e,
                    calculation_metadata=calc_metadata
                )
                success_cnt += 1
            else:
                suspicious_cnt += 1
                
        except Exception as e:
            # Hard parser failures are stored as REJECTED raw records
            validation_errors.append(f"Parsing crash: {str(e)}")
            RawRecord.objects.create(
                organization=org,
                job=job,
                row_index=row_idx,
                raw_data=raw_payload,
                status='REJECTED',
                validation_errors=validation_errors
            )
            failed_cnt += 1

    job.status = 'COMPLETED'
    job.summary = {
        'total': row_idx - 1,
        'success': success_cnt,
        'failed': failed_cnt,
        'suspicious': suspicious_cnt
    }
    job.save()
    return success_cnt, failed_cnt, suspicious_cnt

@transaction.atomic
def run_utility_ingestion(job_id, file_content):
    """
    Ingests electricity utility portal CSV data.
    Accommodates billing periods that do not align with calendar months.
    Splits billing periods proportionally by day to calendarize carbon.
    """
    job = IngestionJob.objects.select_for_update().get(id=job_id)
    org = job.organization
    
    reader = csv.reader(file_content.splitlines())
    header = next(reader, None)
    if not header:
        job.status = 'FAILED'
        job.summary = {'error': 'Empty CSV file'}
        job.save()
        return 0, 0, 0
        
    header_map = {}
    for idx, col in enumerate(header):
        col_clean = col.strip().lower()
        if col_clean in ('account number', 'account_num', 'account'):
            header_map['account'] = idx
        elif col_clean in ('meter number', 'meter_num', 'meter'):
            header_map['meter'] = idx
        elif col_clean in ('bill period start', 'start_date', 'from_date', 'billing_start'):
            header_map['start'] = idx
        elif col_clean in ('bill period end', 'end_date', 'to_date', 'billing_end'):
            header_map['end'] = idx
        elif col_clean in ('usage', 'quantity', 'kwh', 'consumption'):
            header_map['usage'] = idx
        elif col_clean in ('unit', 'uom'):
            header_map['unit'] = idx
        elif col_clean in ('tariff', 'rate_class'):
            header_map['tariff'] = idx
        elif col_clean in ('total charge ($)', 'cost', 'charge', 'amount'):
            header_map['cost'] = idx
            
    required_keys = ['meter', 'start', 'end', 'usage', 'unit']
    missing_keys = [k for k in required_keys if k not in header_map]
    if missing_keys:
        job.status = 'FAILED'
        job.summary = {'error': f'Missing required columns: {", ".join(missing_keys)}. Found headers: {header}'}
        job.save()
        return 0, 0, 0

    success_cnt = 0
    failed_cnt = 0
    suspicious_cnt = 0
    
    row_idx = 1
    for row in reader:
        row_idx += 1
        if not row or not any(row):
            continue
            
        raw_payload = {header[i]: row[i] for i in range(len(row)) if i < len(header)}
        validation_errors = []
        is_suspicious = False
        
        try:
            meter_val = row[header_map['meter']].strip()
            start_raw = row[header_map['start']].strip()
            end_raw = row[header_map['end']].strip()
            usage_raw = row[header_map['usage']].strip()
            unit_raw = row[header_map['unit']].strip().upper()
            account_val = row[header_map['account']].strip() if 'account' in header_map else ''
            
            # Parse Date
            try:
                start_date = parse_date(start_raw)
                end_date = parse_date(end_raw)
            except Exception as e:
                raise ValueError(f"Invalid date formats: {str(e)}")
                
            # Parse Usage
            try:
                usage = parse_decimal(usage_raw)
            except Exception as e:
                raise ValueError(f"Invalid usage format: {str(e)}")

            if start_date >= end_date:
                validation_errors.append(f"Billing period start date ({start_date}) must be before end date ({end_date})")
                is_suspicious = True
                
            # Lookup Facility using either Meter Number or Account Number
            facility = Facility.objects.filter(organization=org, facility_code=meter_val).first()
            if not facility and account_val:
                facility = Facility.objects.filter(organization=org, facility_code=account_val).first()
                
            if not facility:
                validation_errors.append(f"Meter/Account '{meter_val}' is not mapped to any Facility.")
                is_suspicious = True

            # Check emission factor
            region = facility.region if facility else 'GLOBAL'
            resolved_unit = unit_raw
            if resolved_unit in ('KWH', 'KILO WATT HOUR'):
                resolved_unit = 'kWh'
            elif resolved_unit in ('MWH', 'MEGA WATT HOUR'):
                resolved_unit = 'MWh'
                
            ef = EmissionFactor.objects.filter(category='electricity', raw_unit=resolved_unit, region=region).first()
            if not ef:
                # Fallback to global
                ef = EmissionFactor.objects.filter(category='electricity', raw_unit=resolved_unit, region='GLOBAL').first()
                
            if not ef:
                validation_errors.append(f"No electricity emission factor found for unit '{unit_raw}' in region '{region}'")
                is_suspicious = True
                
            # Anomaly Checks
            period_days = (end_date - start_date).days
            if period_days > 45:
                validation_errors.append(f"Billing period is unusually long: {period_days} days (expected ~30 days)")
                is_suspicious = True
            elif period_days < 7:
                validation_errors.append(f"Billing period is unusually short: {period_days} days")
                is_suspicious = True
                
            if usage < 0:
                validation_errors.append("Negative electricity usage detected.")
                is_suspicious = True
                
            daily_kwh = (usage * (ef.conversion_multiplier if ef else 1)) / Decimal(max(period_days, 1))
            if daily_kwh > 10000:
                validation_errors.append(f"Extremely high daily usage rate: {daily_kwh:.2f} kWh/day")
                is_suspicious = True

            status = 'SUSPICIOUS' if is_suspicious else 'PENDING'
            raw_rec = RawRecord.objects.create(
                organization=org,
                job=job,
                row_index=row_idx,
                raw_data=raw_payload,
                status=status,
                validation_errors=validation_errors
            )
            
            if not validation_errors and ef:
                # Calendarize/split the utility period
                splits = split_utility_period(start_date, end_date, usage)
                
                # We can save multiple NormalizedRecords if it crosses month boundaries,
                # but RawRecord has a OneToOneField in Django. Wait! A OneToOneField 
                # means only ONE NormalizedRecord per RawRecord.
                # To handle this, we can either:
                # A. Link them ForeignKey (one RawRecord can have multiple NormalizedRecords)
                # B. Keep it OneToOne, and store the array of split breakdowns inside NormalizedRecord's calculation_metadata
                #    and set the primary activity_date as the billing period mid-point or start_date.
                # Let's check: in models.py, we defined: `raw_record = models.OneToOneField(RawRecord, ...)`
                # Let's adjust to Option B to match our models, or wait! If we want true pro-rating,
                # we can save the main record with total activity, but in the `calculation_metadata`
                # we specify the detailed calendarized breakdown:
                # `splits: [{"month": "2026-04", "usage": "1500.00", "co2e_kg": "330.00"}, ...]`
                # This keeps the exact 1-to-1 mapping clean, while preserving calendar split details!
                # Let's implement this Option B. It is extremely clean and avoids database bloating,
                # while allowing the frontend chart to sum by monthly split if needed!
                
                norm_qty = usage * ef.conversion_multiplier
                co2e = norm_qty * ef.factor_kg_co2e
                
                # Build calendar splits
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
                
                calc_metadata = {
                    "formula": "Quantity * ConversionMultiplier * EmissionFactor",
                    "conversion_multiplier": str(ef.conversion_multiplier),
                    "factor_kg_co2e": str(ef.factor_kg_co2e),
                    "factor_id": ef.id,
                    "region_applied": ef.region,
                    "calendar_splits": split_breakdowns
                }
                
                NormalizedRecord.objects.create(
                    organization=org,
                    raw_record=raw_rec,
                    facility=facility,
                    scope=ef.scope,
                    category="Purchased Electricity",
                    activity_date=start_date,
                    start_date=start_date,
                    end_date=end_date,
                    raw_quantity=usage,
                    raw_unit=unit_raw,
                    normalized_quantity=norm_qty,
                    normalized_unit=ef.normalized_unit,
                    co2e_kg=co2e,
                    calculation_metadata=calc_metadata
                )
                success_cnt += 1
            else:
                suspicious_cnt += 1
                
        except Exception as e:
            validation_errors.append(f"Parsing crash: {str(e)}")
            RawRecord.objects.create(
                organization=org,
                job=job,
                row_index=row_idx,
                raw_data=raw_payload,
                status='REJECTED',
                validation_errors=validation_errors
            )
            failed_cnt += 1

    job.status = 'COMPLETED'
    job.summary = {
        'total': row_idx - 1,
        'success': success_cnt,
        'failed': failed_cnt,
        'suspicious': suspicious_cnt
    }
    job.save()
    return success_cnt, failed_cnt, suspicious_cnt

@transaction.atomic
def run_concur_ingestion(job_id, api_payload):
    """
    Ingests Concur/Navan JSON API data representing travel bookings.
    Calculates distances from airport codes, applies cabin class multipliers,
    and maps hotel stays or ground transport.
    """
    job = IngestionJob.objects.select_for_update().get(id=job_id)
    org = job.organization
    
    try:
        bookings = json.loads(api_payload) if isinstance(api_payload, str) else api_payload
    except Exception as e:
        job.status = 'FAILED'
        job.summary = {'error': f'Invalid JSON payload: {str(e)}'}
        job.save()
        return 0, 0, 0
        
    if not isinstance(bookings, list):
        job.status = 'FAILED'
        job.summary = {'error': 'Payload must be a JSON array of bookings'}
        job.save()
        return 0, 0, 0

    success_cnt = 0
    failed_cnt = 0
    suspicious_cnt = 0
    
    for idx, booking in enumerate(bookings):
        row_idx = idx + 1
        validation_errors = []
        is_suspicious = False
        
        try:
            booking_type = booking.get('type', '').strip().lower()
            start_raw = booking.get('start_date', '').strip()
            end_raw = booking.get('end_date', '').strip()
            amount_val = booking.get('amount', 0.0)
            
            try:
                start_date = parse_date(start_raw)
                end_date = parse_date(end_raw) if end_raw else start_date
            except Exception as e:
                raise ValueError(f"Invalid date formats: {str(e)}")
                
            if start_date and end_date and start_date > end_date:
                validation_errors.append(f"Travel start date ({start_date}) must be before end date ({end_date})")
                is_suspicious = True
                
            ef = None
            raw_qty = Decimal('0.0')
            raw_unit = ''
            norm_qty = Decimal('0.0')
            norm_unit = ''
            co2e = Decimal('0.0')
            calc_metadata = {}
            category = ''
            
            # Sub-category routing
            if booking_type == 'flight':
                origin = booking.get('origin', '').strip().upper()
                dest = booking.get('destination', '').strip().upper()
                cabin = booking.get('cabin_class', 'Economy').strip().title()
                pax = int(booking.get('passengers', 1))
                
                if not origin or not dest:
                    raise ValueError("Flight bookings must include both origin and destination airport codes.")
                    
                # Calculate distance using coordinates database
                coord1 = AIRPORT_COORDINATES.get(origin)
                coord2 = AIRPORT_COORDINATES.get(dest)
                
                if not coord1 or not coord2:
                    validation_errors.append(f"Unknown airport code(s): '{origin}' or '{dest}'. Distance could not be calculated.")
                    is_suspicious = True
                    distance_km = 0
                else:
                    distance_km = haversine_distance(coord1[0], coord1[1], coord2[0], coord2[1])
                    
                raw_qty = Decimal(str(distance_km))
                raw_unit = 'km'
                
                # Determine Flight classification (DEFRA standard: short-haul vs long-haul)
                # Short-haul threshold is typically 300 miles / 480 km
                is_short_haul = distance_km < 480
                ef_cat = 'flight_short' if is_short_haul else 'flight_long'
                
                ef = EmissionFactor.objects.filter(category=ef_cat, raw_unit='km', region='GLOBAL').first()
                if not ef:
                    validation_errors.append(f"No flight emission factor found for category '{ef_cat}'")
                    is_suspicious = True
                else:
                    # Cabin class multipliers (standard DEFRA indices)
                    cabin_multipliers = {
                        'Economy': Decimal('1.0'),
                        'Premium Economy': Decimal('1.6'),
                        'Business': Decimal('2.9'),
                        'First': Decimal('4.0'),
                    }
                    multiplier = cabin_multipliers.get(cabin, Decimal('1.0'))
                    
                    norm_qty = raw_qty * pax
                    norm_unit = 'pkm'
                    co2e = norm_qty * ef.factor_kg_co2e * multiplier
                    
                    calc_metadata = {
                        "formula": "DistanceKM * Passengers * Factor * CabinMultiplier",
                        "distance_km": f"{distance_km:.2f}",
                        "passengers": pax,
                        "cabin_class": cabin,
                        "cabin_multiplier": str(multiplier),
                        "factor_kg_co2e_per_pkm": str(ef.factor_kg_co2e),
                        "factor_id": ef.id
                    }
                category = "Business Travel (Flights)"
                
                if distance_km > 15000:
                    validation_errors.append(f"Unusually long flight leg: {distance_km:.1f} km")
                    is_suspicious = True
                    
            elif booking_type == 'hotel':
                city = booking.get('hotel_city', '').strip()
                nights = int(booking.get('hotel_nights', 1))
                rooms = int(booking.get('hotel_rooms', 1))
                
                raw_qty = Decimal(str(nights * rooms))
                raw_unit = 'room_nights'
                
                # Hotel night emission factor (region specific lookup, falls back to global)
                # Let's map city to country regions if possible, default to GLOBAL
                country_region = 'GLOBAL'
                if any(c in city.lower() for c in ('london', 'uk', 'united kingdom')):
                    country_region = 'UK'
                elif any(c in city.lower() for c in ('new york', 'sf', 'la', 'boston', 'chicago', 'us', 'usa')):
                    country_region = 'US'
                elif any(c in city.lower() for c in ('frankfurt', 'munich', 'germany', 'de')):
                    country_region = 'DE'
                    
                ef = EmissionFactor.objects.filter(category='hotel_night', raw_unit='room_nights', region=country_region).first()
                if not ef and country_region != 'GLOBAL':
                    ef = EmissionFactor.objects.filter(category='hotel_night', raw_unit='room_nights', region='GLOBAL').first()
                    
                if not ef:
                    validation_errors.append(f"No emission factor found for hotel stays in region '{country_region}'")
                    is_suspicious = True
                else:
                    norm_qty = raw_qty
                    norm_unit = 'room_nights'
                    co2e = norm_qty * ef.factor_kg_co2e
                    
                    calc_metadata = {
                        "formula": "RoomNights * Factor",
                        "rooms": rooms,
                        "nights": nights,
                        "factor_kg_co2e_per_room_night": str(ef.factor_kg_co2e),
                        "region_applied": ef.region,
                        "factor_id": ef.id
                    }
                category = "Business Travel (Hotels)"
                
                if nights > 30:
                    validation_errors.append(f"Unusually long hotel stay: {nights} nights")
                    is_suspicious = True
                    
            elif booking_type in ('car_rental', 'car'):
                dist_val = parse_decimal(str(booking.get('distance_value', 0)))
                dist_unit = booking.get('distance_unit', 'km').strip().lower()
                fuel_type = booking.get('fuel_type', 'Petrol').strip().title() # Petrol, Diesel, Electric
                
                if dist_unit in ('mi', 'mile', 'miles'):
                    raw_qty = dist_val
                    raw_unit = 'mi'
                    # Convert to km internally (1 mile = 1.60934 km)
                    conv_multiplier = Decimal('1.60934')
                else:
                    raw_qty = dist_val
                    raw_unit = 'km'
                    conv_multiplier = Decimal('1.0')
                    
                ef_cat = 'car_petrol'
                if fuel_type == 'Diesel':
                    ef_cat = 'car_diesel'
                elif fuel_type == 'Electric':
                    ef_cat = 'car_electric'
                    
                ef = EmissionFactor.objects.filter(category=ef_cat, raw_unit='km', region='GLOBAL').first()
                if not ef:
                    validation_errors.append(f"No car rental emission factor found for type '{ef_cat}'")
                    is_suspicious = True
                else:
                    norm_qty = raw_qty * conv_multiplier
                    norm_unit = 'km'
                    co2e = norm_qty * ef.factor_kg_co2e
                    
                    calc_metadata = {
                        "formula": "Distance * UnitConversion * Factor",
                        "raw_distance": str(dist_val),
                        "raw_unit": dist_unit,
                        "converted_distance_km": f"{norm_qty:.2f}",
                        "fuel_type": fuel_type,
                        "factor_kg_co2e_per_km": str(ef.factor_kg_co2e),
                        "factor_id": ef.id
                    }
                category = "Business Travel (Ground Transport)"
                
            else:
                raise ValueError(f"Unsupported travel booking type: '{booking_type}'")

            # Check financial limit anomalies
            if amount_val > 10000:
                validation_errors.append(f"High booking expenditure detected: ${amount_val:.2f}")
                is_suspicious = True

            status = 'SUSPICIOUS' if is_suspicious else 'PENDING'
            raw_rec = RawRecord.objects.create(
                organization=org,
                job=job,
                row_index=row_idx,
                raw_data=booking,
                status=status,
                validation_errors=validation_errors
            )
            
            if not validation_errors and ef:
                NormalizedRecord.objects.create(
                    organization=org,
                    raw_record=raw_rec,
                    facility=None,  # Travel is corporate-wide, not facility-bound
                    scope=3,        # Scope 3 (Category 6: Business Travel)
                    category=category,
                    activity_date=start_date,
                    start_date=start_date,
                    end_date=end_date,
                    raw_quantity=raw_qty,
                    raw_unit=raw_unit,
                    normalized_quantity=norm_qty,
                    normalized_unit=norm_unit,
                    co2e_kg=co2e,
                    calculation_metadata=calc_metadata
                )
                success_cnt += 1
            else:
                suspicious_cnt += 1
                
        except Exception as e:
            validation_errors.append(f"Parsing crash: {str(e)}")
            RawRecord.objects.create(
                organization=org,
                job=job,
                row_index=row_idx,
                raw_data=booking,
                status='REJECTED',
                validation_errors=validation_errors
            )
            failed_cnt += 1
            
    job.status = 'COMPLETED'
    job.summary = {
        'total': len(bookings),
        'success': success_cnt,
        'failed': failed_cnt,
        'suspicious': suspicious_cnt
    }
    job.save()
    return success_cnt, failed_cnt, suspicious_cnt
