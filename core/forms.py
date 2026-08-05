from django import forms
from .models import *

class DrugForm(forms.ModelForm):
    class Meta:
        model = Drug
        fields = ['name', 'batch_no', 'category', 'price', 'quantity', 'expiry_date', 'barcode']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'barcode': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }

class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ['prescription_id', 'patient_name', 'patient_age', 'patient_address', 
                 'patient_phone', 'doctor_name', 'doctor_license', 'prescribed_drugs']

# class PatientForm(forms.ModelForm):
#     class Meta:
#         model = Patient 
#         fields = ['name', 'email', 'allergies', 'medication_history']
#         widgets = {
#             'allergies': forms.Textarea(attrs={'rows': 4}),
#             'medication_history': forms.Textarea(attrs={'rows': 4}),
#         }



from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Tenant

# forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Tenant, get_roles_for_system

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)
    legal_name = forms.CharField(max_length=200, required=True, label="Business Name")
    registration_number = forms.CharField(max_length=100, required=False, label="Business Registration Number")
    systems = forms.ChoiceField(choices=Tenant.SYSTEMS, required=True, label="Management System")

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'legal_name', 'registration_number', 'systems']

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

class OTPForm(forms.Form):
    otp = forms.CharField(
        max_length=6, 
        min_length=6, 
        label='OTP Code',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 6-digit OTP code',
            'autocomplete': 'off'
        })
    )

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email address'}),
        label="Email Address"
    )
        

class PasswordResetForm(forms.Form): 
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter new password'}),
        label="New Password"
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm new password'}),
        label="Confirm Password"
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data



class TenantUserForm(forms.ModelForm):
    role = forms.ChoiceField(choices=[], required=True)

    def __init__(self, *args, tenant=None, instance=None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)
        if tenant:
            self.fields['role'].choices = get_roles_for_system(tenant.system)
        # if instance:  # Editing existing user
        #     self.fields.pop('password1', None)
        #     self.fields.pop('password2', None)

    class Meta:
        model = User
        fields = ['username', 'email', 'role']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'data-validate': 'username'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'data-validate': 'email'}),
        }

    def clean_username(self):
        username = self.cleaned_data['username']
        # Check if username is taken by another user (excluding the current user if editing)
        queryset = User.objects.filter(username__iexact=username)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        # Check if email is taken by another user (excluding the current user if editing)
        queryset = User.objects.filter(email__iexact=email)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("This email is already in use.")
        return email

class TenantUpdateForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['name', 'registration_number', 'subscription_plan']


from django import forms
import re

class SubscriptionPaymentForm(forms.Form):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=True)
    operator_ref_id = forms.ChoiceField(choices=[], required=True, label="Mobile Money Provider")
    mobile = forms.CharField(max_length=20, required=True, label="Mobile Number")
    amount = forms.DecimalField(max_digits=10, decimal_places=2, required=True)
    subscription_plan = forms.ChoiceField(choices=[('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('annual', 'Annual')], required=True)

    def __init__(self, *args, operators=None, **kwargs):
        super().__init__(*args, **kwargs)
        if operators:
            self.fields['operator_ref_id'].choices = [(op['ref_id'], op['name']) for op in operators]

    def clean_mobile(self):
        mobile = self.cleaned_data['mobile'].strip().replace(' ', '').replace('-', '')
        if mobile.startswith('+265'):
            mobile = mobile[4:]
        elif mobile.startswith('0'):
            mobile = mobile[1:]
        if not re.match(r'^\d{9}$', mobile):
            raise forms.ValidationError('Enter a valid 9-digit mobile number.')
        operator_name = next((op[1].lower() for op in self.fields['operator_ref_id'].choices if op[0] == self.cleaned_data.get('operator_ref_id')), '')
        if operator_name:
            if 'tnm' in operator_name and not mobile.startswith('8'):
                raise forms.ValidationError('TNM number must start with 8.')
            elif 'airtel' in operator_name and not mobile.startswith('9'):
                raise forms.ValidationError('Airtel number must start with 9.')
        return mobile

    def clean(self):
        cleaned_data = super().clean()
        plan = cleaned_data.get('subscription_plan')
        amount = cleaned_data.get('amount')
        expected_amounts = {'monthly': 15000, 'quarterly': 40000, 'annual': 150000}
        if plan and amount and float(amount) != expected_amounts.get(plan, 0):
            raise forms.ValidationError(f"Invalid amount for {plan} plan. Expected MWK {expected_amounts.get(plan)}.")
        return cleaned_data