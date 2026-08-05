import os
import django
from django.utils import timezone
from decimal import Decimal
import random
import uuid
from datetime import date, timedelta

# Add Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'phamarcy.settings')  # Replace 'your_project' with your actual project name
django.setup()

from django.contrib.auth.models import User
from core.models import Drug, Prescription, PrescriptionItem, Supplier, Sale, SaleItem, InsuranceClaim


def create_users():
    """Create sample users if they don't exist"""
    users = [
        {'username': 'admin', 'email': 'admin@pharmacy.com', 'password': 'admin123'},
        {'username': 'pharmacist1', 'email': 'pharma1@pharmacy.com', 'password': 'pharma123'},
        {'username': 'pharmacist2', 'email': 'pharma2@pharmacy.com', 'password': 'pharma123'},
    ]
    
    created_users = []
    for user_data in users:
        user, created = User.objects.get_or_create(
            username=user_data['username'],
            defaults={
                'email': user_data['email'],
                'is_active': True,
                'is_staff': True
            }
        )
        if created:
            user.set_password(user_data['password'])
            user.save()
        created_users.append(user)
    return created_users

def create_drugs(users):
    """Create sample drugs"""
    drugs_data = [
        {
            'name': 'Paracetamol',
            'batch_no': 'PARA2023',
            'category': 'Analgesic',
            'price': Decimal('5.99'),
            'quantity': 100,
            'expiry_date': date.today() + timedelta(days=365),
            'barcode': 'PAR123456',
        },
        {
            'name': 'Amoxicillin',
            'batch_no': 'AMOX2023',
            'category': 'Antibiotic',
            'price': Decimal('12.50'),
            'quantity': 50,
            'expiry_date': date.today() + timedelta(days=180),
            'barcode': 'AMOX789012',
        },
        {
            'name': 'Ibuprofen',
            'batch_no': 'IBU2023',
            'category': 'NSAID',
            'price': Decimal('8.75'),
            'quantity': 75,
            'expiry_date': date.today() + timedelta(days=270),
            'barcode': 'IBU345678',
        },
    ]
    
    created_drugs = []
    for drug_data in drugs_data:
        drug = Drug.objects.create(
            name=drug_data['name'],
            batch_no=drug_data['batch_no'],
            category=drug_data['category'],
            price=drug_data['price'],
            quantity=drug_data['quantity'],
            expiry_date=drug_data['expiry_date'],
            barcode=drug_data['barcode'],
            created_by=random.choice(users),
            last_modified_by=random.choice(users),
        )
        created_drugs.append(drug)
    return created_drugs

def create_suppliers(users, drugs):
    """Create sample suppliers"""
    suppliers_data = [
        {
            'name': 'MediSupply Inc',
            'contact_person': 'John Smith',
            'email': 'john@medisupply.com',
            'phone': '555-0100',
            'address': '123 Medical Lane, Health City',
        },
        {
            'name': 'PharmaCorp',
            'contact_person': 'Sarah Johnson',
            'email': 'sarah@pharmacorp.com',
            'phone': '555-0101',
            'address': '456 Wellness Road, Care Town',
        },
    ]
    
    created_suppliers = []
    for supplier_data in suppliers_data:
        supplier = Supplier.objects.create(
            name=supplier_data['name'],
            contact_person=supplier_data['contact_person'],
            email=supplier_data['email'],
            phone=supplier_data['phone'],
            address=supplier_data['address'],
            created_by=random.choice(users),
        )
        # Assign random drugs to supplier
        supplier.supplied_drugs.set(random.sample(drugs, k=random.randint(1, len(drugs))))
        created_suppliers.append(supplier)
    return created_suppliers

def create_prescriptions(users, drugs):
    """Create sample prescriptions with items"""
    prescriptions_data = [
        {
            'prescription_id': f'PRES-{uuid.uuid4().hex[:8]}',
            'patient_name': 'John Doe',
            'patient_age': 45,
            'patient_address': '789 Health Street, Wellness City',
            'patient_phone': '555-0123',
            'doctor_name': 'Dr. Emily Brown',
            'doctor_license': 'DOC12345',
            'items': [
                {'drug_index': 0, 'quantity': 30, 'instructions': 'Take 1 tablet daily'},
                {'drug_index': 1, 'quantity': 20, 'instructions': 'Take 1 capsule twice daily'},
            ],
        },
        {
            'prescription_id': f'PRES-{uuid.uuid4().hex[:8]}',
            'patient_name': 'Jane Smith',
            'patient_age': 32,
            'patient_address': '456 Care Avenue, Health Town',
            'patient_phone': '555-0124',
            'doctor_name': 'Dr. Michael Lee',
            'doctor_license': 'DOC67890',
            'items': [
                {'drug_index': 2, 'quantity': 15, 'instructions': 'Take 1 tablet every 6 hours'},
            ],
        },
    ]
    
    created_prescriptions = []
    for pres_data in prescriptions_data:
        prescription = Prescription.objects.create(
            prescription_id=pres_data['prescription_id'],
            patient_name=pres_data['patient_name'],
            patient_age=pres_data['patient_age'],
            patient_address=pres_data['patient_address'],
            patient_phone=pres_data['patient_phone'],
            doctor_name=pres_data['doctor_name'],
            doctor_license=pres_data['doctor_license'],
            created_by=random.choice(users),
        )
        
        # Create prescription items
        for item in pres_data['items']:
            PrescriptionItem.objects.create(
                prescription=prescription,
                drug=drugs[item['drug_index']],
                quantity=item['quantity'],
                instructions=item['instructions'],
            )
        
        created_prescriptions.append(prescription)
    return created_prescriptions

def create_sales(users, drugs):
    """Create sample sales with items"""
    sales_data = [
        {
            'sale_id': f'SALE-{uuid.uuid4().hex[:8]}',
            'customer_name': 'Alice Johnson',
            'customer_phone': '555-0145',
            'items': [
                {'drug_index': 0, 'quantity': 10, 'price': Decimal('5.99')},
                {'drug_index': 2, 'quantity': 5, 'price': Decimal('8.75')},
            ],
        },
        {
            'sale_id': f'SALE-{uuid.uuid4().hex[:8]}',
            'customer_name': 'Bob Wilson',
            'customer_phone': '555-0146',
            'items': [
                {'drug_index': 1, 'quantity': 7, 'price': Decimal('12.50')},
            ],
        },
    ]
    
    created_sales = []
    for sale_data in sales_data:
        total_amount = sum(item['quantity'] * item['price'] for item in sale_data['items'])
        sale = Sale.objects.create(
            sale_id=sale_data['sale_id'],
            customer_name=sale_data['customer_name'],
            customer_phone=sale_data['customer_phone'],
            total_amount=total_amount,
            processed_by=random.choice(users),
        )
        
        # Create sale items
        for item in sale_data['items']:
            SaleItem.objects.create(
                sale=sale,
                drug=drugs[item['drug_index']],
                quantity=item['quantity'],
                price=item['price'],
            )
        
        created_sales.append(sale)
    return created_sales

def create_insurance_claims(users):
    """Create sample insurance claims"""
    claims_data = [
        {
            'claim_id': f'CLAIM-{uuid.uuid4().hex[:8]}',
            'insurance_provider': 'HealthCare Plus',
            'patient_name': 'John Doe',
            'patient_id': 'PAT12345',
            'claim_amount': Decimal('150.75'),
            'status': 'pending',
        },
        {
            'claim_id': f'CLAIM-{uuid.uuid4().hex[:8]}',
            'insurance_provider': 'MediCare Inc',
            'patient_name': 'Jane Smith',
            'patient_id': 'PAT67890',
            'claim_amount': Decimal('89.50'),
            'status': 'approved',
            'date_processed': date.today(),
        },
    ]
    
    created_claims = []
    for claim_data in claims_data:
        claim = InsuranceClaim.objects.create(
            claim_id=claim_data['claim_id'],
            insurance_provider=claim_data['insurance_provider'],
            patient_name=claim_data['patient_name'],
            patient_id=claim_data['patient_id'],
            claim_amount=claim_data['claim_amount'],
            status=claim_data['status'],
            submitted_by=random.choice(users),
            date_processed=claim_data.get('date_processed'),
        )
        created_claims.append(claim)
    return created_claims

def populate_data():
    """Main function to populate all data"""
    print("Starting data population...")
    
    # Create users
    users = create_users()
    print(f"Created {len(users)} users")
    
    # Create drugs
    drugs = create_drugs(users)
    print(f"Created {len(drugs)} drugs")
    
    # Create suppliers
    suppliers = create_suppliers(users, drugs)
    print(f"Created {len(suppliers)} suppliers")
    
    # Create prescriptions
    prescriptions = create_prescriptions(users, drugs)
    print(f"Created {len(prescriptions)} prescriptions")
    
    # Create sales
    sales = create_sales(users, drugs)
    print(f"Created {len(sales)} sales")
    
    # Create insurance claims
    claims = create_insurance_claims(users)
    print(f"Created {len(claims)} insurance claims")
    
    print("Data population completed!")

if __name__ == '__main__':
    populate_data()