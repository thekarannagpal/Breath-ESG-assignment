from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from decimal import Decimal
from emissions.models import Organization, UserProfile, Facility, EmissionFactor

class Command(BaseCommand):
    help = 'Seeds the database with test organizations, users, facilities, and emission factors.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding database...')

        # 1. Create Organizations
        acme, created = Organization.objects.get_or_create(
            name='Acme Corporation (Global)',
            domain='acme.com'
        )
        if created:
            self.stdout.write(f'Created Organization: {acme.name}')

        beta, created = Organization.objects.get_or_create(
            name='Beta Services LLC',
            domain='beta.com'
        )
        if created:
            self.stdout.write(f'Created Organization: {beta.name}')

        # 2. Create Users
        # Acme Analyst
        if not User.objects.filter(username='acme_analyst').exists():
            user = User.objects.create_user(username='acme_analyst', password='password123', email='analyst@acme.com')
            UserProfile.objects.create(user=user, organization=acme, role='analyst')
            self.stdout.write('Created user: acme_analyst')
            
        # Acme Auditor
        if not User.objects.filter(username='acme_auditor').exists():
            user = User.objects.create_user(username='acme_auditor', password='password123', email='auditor@acme.com')
            UserProfile.objects.create(user=user, organization=acme, role='auditor')
            self.stdout.write('Created user: acme_auditor')

        # Acme Admin
        if not User.objects.filter(username='acme_admin').exists():
            user = User.objects.create_user(username='acme_admin', password='password123', email='admin@acme.com')
            UserProfile.objects.create(user=user, organization=acme, role='admin')
            self.stdout.write('Created user: acme_admin')

        # Beta Analyst (Multi-tenant Check)
        if not User.objects.filter(username='beta_analyst').exists():
            user = User.objects.create_user(username='beta_analyst', password='password123', email='analyst@beta.com')
            UserProfile.objects.create(user=user, organization=beta, role='analyst')
            self.stdout.write('Created user: beta_analyst')

        # Superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(username='admin', password='adminpassword', email='admin@breatheesg.com')
            self.stdout.write('Created superuser: admin')

        # 3. Create Facilities
        # Mappings for Acme Corp
        facilities_acme = [
            {'name': 'Heidelberg Plant', 'facility_code': '1000', 'region': 'DE'},
            {'name': 'Munich R&D Center', 'facility_code': '1100', 'region': 'DE'},
            {'name': 'Silicon Valley HQ', 'facility_code': 'E-MTR-8899', 'region': 'US-CA'},
            {'name': 'New York Sales Hub', 'facility_code': 'E-MTR-1234', 'region': 'US-NY'},
            {'name': 'London Office', 'facility_code': 'E-MTR-7721', 'region': 'UK'},
        ]
        for f in facilities_acme:
            obj, created = Facility.objects.get_or_create(
                organization=acme,
                facility_code=f['facility_code'],
                defaults={'name': f['name'], 'region': f['region']}
            )
            if created:
                self.stdout.write(f"Created Acme Facility: {f['name']} ({f['facility_code']})")

        # Mappings for Beta LLC
        facilities_beta = [
            {'name': 'Dallas Operations', 'facility_code': '2000', 'region': 'US-TX'},
            {'name': 'Beta Austin Meter', 'facility_code': 'E-MTR-9900', 'region': 'US-TX'},
        ]
        for f in facilities_beta:
            obj, created = Facility.objects.get_or_create(
                organization=beta,
                facility_code=f['facility_code'],
                defaults={'name': f['name'], 'region': f['region']}
            )
            if created:
                self.stdout.write(f"Created Beta Facility: {f['name']} ({f['facility_code']})")

        # 4. Populate Emission Factors
        # Categories: diesel, natural_gas, electricity, flight_short, flight_long, hotel_night, car_petrol, car_diesel, car_electric
        factors = [
            # Scope 1: Diesel
            {'category': 'diesel', 'raw_unit': 'L', 'normalized_unit': 'L', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 2.68, 'region': 'GLOBAL', 'scope': 1},
            {'category': 'diesel', 'raw_unit': 'LTR', 'normalized_unit': 'L', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 2.68, 'region': 'GLOBAL', 'scope': 1},
            {'category': 'diesel', 'raw_unit': 'KG', 'normalized_unit': 'L', 'conversion_multiplier': 1.18, 'factor_kg_co2e': 2.68, 'region': 'GLOBAL', 'scope': 1}, # ~1.18 L per kg
            
            # Scope 1: Natural Gas
            {'category': 'natural_gas', 'raw_unit': 'm3', 'normalized_unit': 'm3', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 2.02, 'region': 'GLOBAL', 'scope': 1},
            {'category': 'natural_gas', 'raw_unit': 'M3', 'normalized_unit': 'm3', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 2.02, 'region': 'GLOBAL', 'scope': 1},
            
            # Scope 2: Purchased Electricity (Region Specific)
            # US California (CAMX)
            {'category': 'electricity', 'raw_unit': 'kWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.22, 'region': 'US-CA', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'KWH', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.22, 'region': 'US-CA', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'MWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1000.0, 'factor_kg_co2e': 0.22, 'region': 'US-CA', 'scope': 2},
            
            # US New York (NYUP)
            {'category': 'electricity', 'raw_unit': 'kWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.11, 'region': 'US-NY', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'KWH', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.11, 'region': 'US-NY', 'scope': 2},
            
            # US Texas (ERCOT)
            {'category': 'electricity', 'raw_unit': 'kWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.36, 'region': 'US-TX', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'KWH', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.36, 'region': 'US-TX', 'scope': 2},

            # Germany
            {'category': 'electricity', 'raw_unit': 'kWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.38, 'region': 'DE', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'KWH', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.38, 'region': 'DE', 'scope': 2},

            # UK
            {'category': 'electricity', 'raw_unit': 'kWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.25, 'region': 'UK', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'KWH', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.25, 'region': 'UK', 'scope': 2},

            # Global/Generic Grid Fallback
            {'category': 'electricity', 'raw_unit': 'kWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.40, 'region': 'GLOBAL', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'KWH', 'normalized_unit': 'kWh', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.40, 'region': 'GLOBAL', 'scope': 2},
            {'category': 'electricity', 'raw_unit': 'MWh', 'normalized_unit': 'kWh', 'conversion_multiplier': 1000.0, 'factor_kg_co2e': 0.40, 'region': 'GLOBAL', 'scope': 2},

            # Scope 3: Flight Short Haul
            {'category': 'flight_short', 'raw_unit': 'km', 'normalized_unit': 'pkm', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.15, 'region': 'GLOBAL', 'scope': 3},
            # Scope 3: Flight Long Haul
            {'category': 'flight_long', 'raw_unit': 'km', 'normalized_unit': 'pkm', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.14, 'region': 'GLOBAL', 'scope': 3},

            # Scope 3: Hotel Nights
            {'category': 'hotel_night', 'raw_unit': 'room_nights', 'normalized_unit': 'room_nights', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 18.0, 'region': 'US', 'scope': 3},
            {'category': 'hotel_night', 'raw_unit': 'room_nights', 'normalized_unit': 'room_nights', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 10.0, 'region': 'UK', 'scope': 3},
            {'category': 'hotel_night', 'raw_unit': 'room_nights', 'normalized_unit': 'room_nights', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 15.0, 'region': 'DE', 'scope': 3},
            {'category': 'hotel_night', 'raw_unit': 'room_nights', 'normalized_unit': 'room_nights', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 16.0, 'region': 'GLOBAL', 'scope': 3},

            # Scope 3: Rental Cars
            {'category': 'car_petrol', 'raw_unit': 'km', 'normalized_unit': 'km', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.18, 'region': 'GLOBAL', 'scope': 3},
            {'category': 'car_diesel', 'raw_unit': 'km', 'normalized_unit': 'km', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.17, 'region': 'GLOBAL', 'scope': 3},
            {'category': 'car_electric', 'raw_unit': 'km', 'normalized_unit': 'km', 'conversion_multiplier': 1.0, 'factor_kg_co2e': 0.05, 'region': 'GLOBAL', 'scope': 3},

            # With Mile Conversions
            {'category': 'car_petrol', 'raw_unit': 'mi', 'normalized_unit': 'km', 'conversion_multiplier': 1.60934, 'factor_kg_co2e': 0.18, 'region': 'GLOBAL', 'scope': 3},
            {'category': 'car_diesel', 'raw_unit': 'mi', 'normalized_unit': 'km', 'conversion_multiplier': 1.60934, 'factor_kg_co2e': 0.17, 'region': 'GLOBAL', 'scope': 3},
            {'category': 'car_electric', 'raw_unit': 'mi', 'normalized_unit': 'km', 'conversion_multiplier': 1.60934, 'factor_kg_co2e': 0.05, 'region': 'GLOBAL', 'scope': 3},
        ]

        for f in factors:
            obj, created = EmissionFactor.objects.get_or_create(
                category=f['category'],
                raw_unit=f['raw_unit'],
                region=f['region'],
                defaults={
                    'normalized_unit': f['normalized_unit'],
                    'conversion_multiplier': Decimal(str(f['conversion_multiplier'])),
                    'factor_kg_co2e': Decimal(str(f['factor_kg_co2e'])),
                    'scope': f['scope']
                }
            )
            if created:
                self.stdout.write(f"Created Emission Factor: {f['category']} ({f['raw_unit']} in {f['region']})")

        self.stdout.write('Database seeding complete!')
