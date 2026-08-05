from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random
import string

class UserVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    verification_expiry = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)

class Tenant(models.Model):
    SYSTEMS = [
        ('PHARMACY', 'Pharmacy'),
        ('SCHOOL', 'School'),
        # ('INVENTORY', 'Inventory'),
        # ('SALES', 'Sales'),
        # ('HR', 'HR'),
        # ('FINANCIAL', 'Financial'),
    ]
    PLANS = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual'),
    ]
    name = models.CharField(max_length=200)
    registration_number = models.CharField(max_length=100, blank=True, null=True)
    system = models.CharField(max_length=20, choices=SYSTEMS)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_tenants')
    subscription_plan = models.CharField(max_length=20, choices=PLANS, default='monthly')
    subscription_start = models.DateField(default=timezone.now)
    subscription_end = models.DateField(null=True, blank=True)
    is_trial = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_trial and not self.subscription_end:
            # Change from 30 days to 3 days for trial
            self.subscription_end = timezone.now().date() + timedelta(days=14)
        super().save(*args, **kwargs)

    @property
    def is_subscription_valid(self):
        today = timezone.now().date()
        if self.is_trial:
            return today <= self.subscription_end
        if self.subscription_end and today <= self.subscription_end:
            return True
        return False
    
    def extend_subscription(self, plan):
        """Extend subscription based on selected plan. Add days to existing subscription."""
        today = timezone.now().date()
        
        # Determine days to add based on plan
        if plan == 'monthly':
            days_to_add = 30
        elif plan == 'quarterly':
            days_to_add = 90
        elif plan == 'annual':
            days_to_add = 365
        else:
            days_to_add = 0
        
        # Calculate new end date
        if self.is_trial or not self.subscription_end or self.subscription_end < today:
            # If no active subscription or trial expired, start from today
            new_end_date = today + timedelta(days=days_to_add)
        else:
            # If active subscription exists, add days to current end date
            new_end_date = self.subscription_end + timedelta(days=days_to_add)
        
        # Update subscription details
        self.subscription_end = new_end_date
        self.is_trial = False
        self.is_active = True
        self.subscription_plan = plan
        self.subscription_start = today  # Reset start date to today for renewal
        self.save()
        
        return new_end_date
    
    @property
    def days_remaining(self):
        """Calculate days remaining in subscription."""
        today = timezone.now().date()
        if not self.subscription_end:
            return 0
        remaining = (self.subscription_end - today).days
        return max(remaining, 0)  # Ensure no negative days


class SubscriptionPaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payment_transactions')
    charge_id = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    mobile = models.CharField(max_length=20)
    operator_ref_id = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True, help_text="Raw PayChangu API response")
    user_email = models.EmailField(null=True, blank=True, help_text="User's email for notifications")
    subscription_plan = models.CharField(max_length=20, choices=Tenant.PLANS, help_text="Selected subscription plan")

    def __str__(self):
        return f"{self.charge_id} - {self.status} for Tenant {self.tenant.name}"

    class Meta:
        indexes = [
            models.Index(fields=['charge_id']),
            models.Index(fields=['status']),
        ]

class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    role = models.CharField(max_length=50)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'tenant')

    def __str__(self):
        return f"{self.user.username} - {self.tenant.name} ({self.role})"

def get_roles_for_system(system):
    if system == 'PHARMACY':
        return [
            ('owner', 'Owner'),
            ('admin', 'Admin'),
            ('seller', 'Seller'),
            ('inventory_manager', 'Inventory Manager'),
        ]
    elif system == 'SCHOOL':
        return [
            ('owner', 'Owner'),
            ('admin', 'Admin'),
            ('lecturer', 'Lecturer'),
            ('student', 'Student'),
            ('accountant', 'Accountant'),
        ]
    return [('owner', 'Owner'), ('admin', 'Admin')]

class Drug(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    batch_no = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.IntegerField(validators=[MinValueValidator(0)])
    expiry_date = models.DateField()
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='drugs_created')
    last_modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='drugs_modified')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} (Batch: {self.batch_no})"
    
    @property
    def is_low_stock(self):
        return self.quantity < 10
    
    @property
    def is_expired(self):
        from datetime import date
        return self.expiry_date < date.today()

class Prescription(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    prescription_id = models.CharField(max_length=100, unique=True)
    patient_name = models.CharField(max_length=200)
    patient_age = models.IntegerField()
    patient_address = models.TextField()
    patient_phone = models.CharField(max_length=15, blank=True)
    doctor_name = models.CharField(max_length=200)
    doctor_license = models.CharField(max_length=100, blank=True)
    prescribed_drugs = models.ManyToManyField(Drug, through='PrescriptionItem')
    date_prescribed = models.DateField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='prescriptions_created')
    
    def __str__(self):
        return f"Prescription #{self.prescription_id} for {self.patient_name}"

class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE)
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    instructions = models.TextField(blank=True)

class Supplier(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15)
    address = models.TextField(blank=True)
    supplied_drugs = models.ManyToManyField(Drug, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='suppliers_created')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Sale(models.Model):
    PAYMENT_METHODS = (
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('MOBILE_MONEY', 'Mobile Money'),
    )
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    sale_id = models.CharField(max_length=100, unique=True)
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    customer_address = models.TextField(blank=True)
    customer_email = models.EmailField(blank=True, null=True)  # Allow null to avoid NOT NULL constraint
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sales_processed')
    is_voided = models.BooleanField(default=False)
    voided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sales_voided')
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    
    def __str__(self):
        return f"Sale #{self.sale_id}"

    @property
    def is_same_day(self):
        return self.date.date() == timezone.now().date()

class VoidRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='void_requests_requested')
    requested_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='void_requests_processed')
    processed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"Void Request for Sale #{self.sale.sale_id} - {self.status}"

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    @property
    def total(self):
        return self.quantity * self.price

class InsuranceClaim(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('processed', 'Processed'),
    ]
    
    claim_id = models.CharField(max_length=100, unique=True)
    insurance_provider = models.CharField(max_length=200)
    patient_name = models.CharField(max_length=200)
    patient_id = models.CharField(max_length=100, blank=True)
    claim_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_submitted = models.DateField(auto_now_add=True)
    date_processed = models.DateField(blank=True, null=True)
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='claims_submitted')
    
    def __str__(self):
        return f"Claim #{self.claim_id} - {self.patient_name}"