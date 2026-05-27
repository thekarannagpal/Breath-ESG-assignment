from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date
import json

from emissions.models import Organization, Facility, IngestionJob, RawRecord, NormalizedRecord, AuditLog, EmissionFactor
from emissions.ingest import (
    haversine_distance, parse_decimal, parse_date, split_utility_period,
    run_sap_ingestion, run_utility_ingestion, run_concur_ingestion
)

class EmissionsIngestTestCase(TestCase):
    def setUp(self):
        # Create Organizations
        self.org_a = Organization.objects.create(name="Org A", domain="orga.com")
        self.org_b = Organization.objects.create(name="Org B", domain="orgb.com")

        # Create Facilities
        self.fac_a1 = Facility.objects.create(organization=self.org_a, name="Heidelberg Plant", facility_code="1000", region="DE")
        self.fac_a2 = Facility.objects.create(organization=self.org_a, name="SV Office", facility_code="E-MTR-8899", region="US-CA")
        self.fac_b1 = Facility.objects.create(organization=self.org_b, name="Dallas Hub", facility_code="2000", region="US-TX")

        # Create standard Emission Factors
        # Scope 1
        EmissionFactor.objects.create(category="diesel", raw_unit="L", normalized_unit="L", conversion_multiplier=1.0, factor_kg_co2e=Decimal("2.68"), region="GLOBAL", scope=1)
        EmissionFactor.objects.create(category="natural_gas", raw_unit="m3", normalized_unit="m3", conversion_multiplier=1.0, factor_kg_co2e=Decimal("2.02"), region="GLOBAL", scope=1)
        
        # Scope 2
        EmissionFactor.objects.create(category="electricity", raw_unit="kWh", normalized_unit="kWh", conversion_multiplier=1.0, factor_kg_co2e=Decimal("0.38"), region="DE", scope=2)
        EmissionFactor.objects.create(category="electricity", raw_unit="kWh", normalized_unit="kWh", conversion_multiplier=1.0, factor_kg_co2e=Decimal("0.22"), region="US-CA", scope=2)
        EmissionFactor.objects.create(category="electricity", raw_unit="MWh", normalized_unit="kWh", conversion_multiplier=1000.0, factor_kg_co2e=Decimal("0.22"), region="US-CA", scope=2)
        
        # Scope 3
        EmissionFactor.objects.create(category="flight_short", raw_unit="km", normalized_unit="pkm", conversion_multiplier=1.0, factor_kg_co2e=Decimal("0.15"), region="GLOBAL", scope=3)
        EmissionFactor.objects.create(category="flight_long", raw_unit="km", normalized_unit="pkm", conversion_multiplier=1.0, factor_kg_co2e=Decimal("0.14"), region="GLOBAL", scope=3)
        EmissionFactor.objects.create(category="hotel_night", raw_unit="room_nights", normalized_unit="room_nights", conversion_multiplier=1.0, factor_kg_co2e=Decimal("15.0"), region="DE", scope=3)
        EmissionFactor.objects.create(category="hotel_night", raw_unit="room_nights", normalized_unit="room_nights", conversion_multiplier=1.0, factor_kg_co2e=Decimal("16.0"), region="GLOBAL", scope=3)

    def test_haversine_distance(self):
        # JFK to LHR is roughly 5567 km
        dist = haversine_distance(40.6398, -73.7789, 51.4700, -0.4543)
        self.assertAlmostEqual(dist, 5567, delta=50)

    def test_parse_decimal(self):
        # Test standard format
        self.assertEqual(parse_decimal("1250.50"), Decimal("1250.50"))
        # Test German format (comma decimal, dot thousands)
        self.assertEqual(parse_decimal("1.250,50"), Decimal("1250.50"))
        self.assertEqual(parse_decimal("250,00"), Decimal("250.00"))

    def test_parse_date(self):
        self.assertEqual(parse_date("2026-05-15"), date(2026, 5, 15))
        self.assertEqual(parse_date("15.05.2026"), date(2026, 5, 15))
        self.assertEqual(parse_date("20260515"), date(2026, 5, 15))

    def test_split_utility_period(self):
        # Test pro-rating a billing period that spans April and May
        start = date(2026, 4, 15)
        end = date(2026, 5, 14) # 30 days total
        total_usage = 3000
        
        splits = split_utility_period(start, end, total_usage)
        self.assertEqual(len(splits), 2)
        # April has 16 days (April 15 to April 30 inclusive)
        # May has 14 days (May 1 to May 14 inclusive)
        april_split = next(s for s in splits if s['month_start'] == date(2026, 4, 1))
        may_split = next(s for s in splits if s['month_start'] == date(2026, 5, 1))
        
        self.assertEqual(april_split['days'], 16)
        self.assertEqual(may_split['days'], 14)
        self.assertEqual(april_split['usage'], Decimal("1600.0"))
        self.assertEqual(may_split['usage'], Decimal("1400.0"))

    def test_sap_ingestion_success(self):
        # Setup Job
        job = IngestionJob.objects.create(organization=self.org_a, source_type='SAP')
        csv_data = "Materialbeleg,Buchungsdatum,Materialnummer,Materialkurztext,Menge,Einheit,Werk,Einkaufsbeleg\n" \
                   "50001001,15.04.2026,DIESEL,Diesel Fuel,\"1.500,00\",LTR,1000,45000981"
                   
        success, failed, suspicious = run_sap_ingestion(job.id, csv_data)
        
        # Verify counts
        self.assertEqual(success, 1)
        self.assertEqual(failed, 0)
        self.assertEqual(suspicious, 0)
        
        # Verify records created
        raw = RawRecord.objects.filter(job=job).first()
        self.assertIsNotNone(raw)
        self.assertEqual(raw.status, 'PENDING')
        
        norm = NormalizedRecord.objects.get(raw_record=raw)
        self.assertEqual(norm.facility, self.fac_a1)
        self.assertEqual(norm.scope, 1)
        # 1500 * 2.68 = 4020.0
        self.assertEqual(norm.co2e_kg, Decimal("4020.0"))

    def test_sap_ingestion_suspicious_plant(self):
        # Setup Job
        job = IngestionJob.objects.create(organization=self.org_a, source_type='SAP')
        # Plant 1300 is not mapped
        csv_data = "Materialbeleg,Buchungsdatum,Materialnummer,Materialkurztext,Menge,Einheit,Werk,Einkaufsbeleg\n" \
                   "50001001,15.04.2026,DIESEL,Diesel Fuel,1500,LTR,1300,45000981"
                   
        success, failed, suspicious = run_sap_ingestion(job.id, csv_data)
        self.assertEqual(success, 0)
        self.assertEqual(suspicious, 1)
        
        raw = RawRecord.objects.filter(job=job).first()
        self.assertEqual(raw.status, 'SUSPICIOUS')
        self.assertTrue(any("not mapped" in err for err in raw.validation_errors))

    def test_utility_ingestion_success(self):
        job = IngestionJob.objects.create(organization=self.org_a, source_type='UTILITY')
        csv_data = "Account Number,Meter Number,Bill Period Start,Bill Period End,Usage,Unit,Tariff,Total Cost\n" \
                   "9876,E-MTR-8899,2026-04-15,2026-05-14,3000,kWh,E-19,500.00"
                   
        success, failed, suspicious = run_utility_ingestion(job.id, csv_data)
        self.assertEqual(success, 1)
        
        raw = RawRecord.objects.filter(job=job).first()
        norm = NormalizedRecord.objects.get(raw_record=raw)
        self.assertEqual(norm.facility, self.fac_a2)
        self.assertEqual(norm.scope, 2)
        # 3000 * 0.22 = 660.0
        self.assertEqual(norm.co2e_kg, Decimal("660.0"))
        # Check pro-rating splits are saved in metadata
        splits = norm.calculation_metadata['calendar_splits']
        self.assertEqual(len(splits), 2)
        self.assertEqual(splits[0]['co2e_kg'], "352.0000") # 1600 * 0.22
        self.assertEqual(splits[1]['co2e_kg'], "308.0000") # 1400 * 0.22

    def test_concur_ingestion_success(self):
        job = IngestionJob.objects.create(organization=self.org_a, source_type='CONCUR')
        # SFO to JFK flight
        payload = [
            {
                "booking_id": "BK-01",
                "type": "flight",
                "start_date": "2026-05-01",
                "origin": "SFO",
                "destination": "JFK",
                "cabin_class": "Business",
                "passengers": 1,
                "amount": 1200.00
            },
            {
                "booking_id": "BK-02",
                "type": "hotel",
                "start_date": "2026-05-01",
                "end_date": "2026-05-04",
                "hotel_city": "Munich, Germany",
                "hotel_nights": 3,
                "hotel_rooms": 1,
                "amount": 600.00
            }
        ]
        
        success, failed, suspicious = run_concur_ingestion(job.id, payload)
        self.assertEqual(success, 2)
        
        # Flight checks (Business multiplier 2.9, long-haul factor 0.14)
        flight_raw = RawRecord.objects.get(job=job, row_index=1)
        flight_norm = NormalizedRecord.objects.get(raw_record=flight_raw)
        self.assertEqual(flight_norm.scope, 3)
        self.assertIn("Business", flight_norm.calculation_metadata['cabin_class'])
        self.assertEqual(flight_norm.calculation_metadata['cabin_multiplier'], "2.9")
        
        # Hotel checks (DE region has factor 15)
        hotel_raw = RawRecord.objects.get(job=job, row_index=2)
        hotel_norm = NormalizedRecord.objects.get(raw_record=hotel_raw)
        self.assertEqual(hotel_norm.co2e_kg, Decimal("45.0")) # 3 nights * 15.0 = 45.0

    def test_multi_tenancy_isolation(self):
        # Load SAP data in Org A
        job_a = IngestionJob.objects.create(organization=self.org_a, source_type='SAP')
        csv_a = "Materialbeleg,Buchungsdatum,Materialnummer,Materialkurztext,Menge,Einheit,Werk,Einkaufsbeleg\n" \
                "50001001,15.04.2026,DIESEL,Diesel Fuel,1000,LTR,1000,45000981"
        run_sap_ingestion(job_a.id, csv_a)
        
        # Load SAP data in Org B
        job_b = IngestionJob.objects.create(organization=self.org_b, source_type='SAP')
        csv_b = "Materialbeleg,Buchungsdatum,Materialnummer,Materialkurztext,Menge,Einheit,Werk,Einkaufsbeleg\n" \
                "50001002,15.04.2026,DIESEL,Diesel Fuel,2000,LTR,2000,45000982"
        run_sap_ingestion(job_b.id, csv_b)
        
        # Check query isolation
        records_a = RawRecord.objects.filter(organization=self.org_a)
        records_b = RawRecord.objects.filter(organization=self.org_b)
        
        self.assertEqual(records_a.count(), 1)
        self.assertEqual(records_b.count(), 1)
        self.assertEqual(records_a.first().raw_data['Materialbeleg'], '50001001')
        self.assertEqual(records_b.first().raw_data['Materialbeleg'], '50001002')
