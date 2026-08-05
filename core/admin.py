from django.contrib import admin
from .models import *

# admin.py (register the new model)
from .models import UserVerification

class UserVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_verified', 'verification_expiry')
    search_fields = ('user__username', 'user__email')

admin.site.register(UserVerification, UserVerificationAdmin)



class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'registration_number', 'system', 'owner', 'subscription_plan', 'subscription_start', 'subscription_end', 'is_trial', 'is_active', 'created_at')
    list_filter = ('system', 'subscription_plan', 'is_trial', 'is_active')
    search_fields = ('name', 'registration_number', 'owner__username')
    readonly_fields = ('created_at',)

class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role', 'joined_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'tenant__name')

class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 1

class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ('prescription_id', 'patient_name', 'patient_age', 'doctor_name', 'date_prescribed', 'created_by', 'tenant')
    search_fields = ('prescription_id', 'patient_name', 'doctor_name')
    inlines = [PrescriptionItemInline]

class DrugAdmin(admin.ModelAdmin):
    list_display = ('name', 'batch_no', 'category', 'price', 'quantity', 'expiry_date', 'barcode', 'created_by', 'tenant', 'is_low_stock', 'is_expired')
    list_filter = ('category',)
    search_fields = ('name', 'batch_no', 'barcode')

class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'email', 'phone', 'created_by', 'tenant')
    search_fields = ('name', 'email', 'phone')

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1

class SaleAdmin(admin.ModelAdmin):
    list_display = ('sale_id', 'customer_name', 'date', 'total_amount', 'discount_percentage', 'processed_by', 'tenant')
    search_fields = ('sale_id', 'customer_name')
    inlines = [SaleItemInline]

class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = ('claim_id', 'insurance_provider', 'patient_name', 'claim_amount', 'status', 'date_submitted', 'submitted_by', 'tenant')
    list_filter = ('status',)
    search_fields = ('claim_id', 'patient_name', 'insurance_provider')


class VoidRequestAdmin(admin.ModelAdmin):
    list_display = ('sale', 'requested_by', 'reason', 'status', 'requested_at', 'processed_at')
    list_filter = ('status',)
    search_fields = ('sale__sale_id', 'requested_by__username')

# class SubscriptionPaymentTransactionAdmin(admin.ModelAdmin):
#     list_display = ('transaction_id', 'tenant', 'amount', 'payment_method', 'status', 'transaction_date')
#     list_filter = ('payment_method', 'status')
#     search_fields = ('transaction_id', 'tenant__name')

admin.site.register(SubscriptionPaymentTransaction)
    
admin.site.register(VoidRequest, VoidRequestAdmin)
admin.site.register(Tenant, TenantAdmin)
admin.site.register(Membership, MembershipAdmin)
admin.site.register(Drug, DrugAdmin)
admin.site.register(Prescription, PrescriptionAdmin)
admin.site.register(Supplier, SupplierAdmin)
admin.site.register(Sale, SaleAdmin)
admin.site.register(InsuranceClaim, InsuranceClaimAdmin)