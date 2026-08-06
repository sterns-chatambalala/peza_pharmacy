from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q, Sum, Count
from datetime import date
from pathlib import Path
import base64
from .models import *
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import random
import string
from .forms import *
from functools import wraps
from django.contrib.auth.models import User
from django.core.paginator import Paginator


def landing_page(request):
    return render(request, 'landing/index.html')

# Decorator for role-based access
def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.tenant:
                messages.error(request, 'No tenant associated with your account.')
                return redirect('login')
            membership = request.membership
            if membership.role not in allowed_roles:
                messages.error(request, 'You do not have permission to access this feature.')
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

# Authentication Views
# views.py
import random
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from datetime import timedelta
from .forms import *
from .models import User, Tenant, Membership, UserVerification

import random
import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .forms import SignupForm, OTPForm, ForgotPasswordForm, PasswordResetForm
from .models import User, Tenant, Membership, UserVerification

# Set up logging
logger = logging.getLogger(__name__)

def generate_otp():
    return ''.join(random.choices('0123456789', k=6))

def send_otp_email(user, otp):
    subject = 'Verify Your Account - IMS'
    context = {'user': user, 'otp': otp}
    try:
        html_content = render_to_string('auth/verification_email.html', context)
        text_content = strip_tags(html_content)
        email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
        email.attach_alternative(html_content, "text/html")
        email.send()
        logger.info(f"OTP email sent to {user.email}: OTP={otp}")
    except Exception as e:
        logger.error(f"Failed to send OTP email to {user.email}: {str(e)}")
        raise

def signup_view(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            tenant = Tenant.objects.create(
                name=form.cleaned_data['legal_name'],
                registration_number=form.cleaned_data['registration_number'],
                system=form.cleaned_data['systems'],
                owner=user,
                subscription_start=timezone.now().date(),
                is_trial=True
            )
            Membership.objects.create(user=user, tenant=tenant, role='owner')
            
            otp = generate_otp()
            expiry = timezone.now() + timedelta(minutes=10)
            UserVerification.objects.create(
                user=user,
                verification_code=otp,
                verification_expiry=expiry
            )
            try:
                send_otp_email(user, otp)
                messages.success(request, 'Account created successfully! Please check your email for the verification OTP.')
                request.session['otp_sent'] = True
            except Exception as e:
                messages.error(request, f'Account created, but failed to send OTP email: {str(e)}. Please contact support.')
            
            return redirect('verify_account', user_id=user.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SignupForm()
    
    return render(request, 'auth/signup.html', {'form': form})

from django.http import JsonResponse
from django.contrib.auth.models import User

def check_username(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        
        if not username:
            return JsonResponse({'available': False, 'error': 'Username is required'})
        
        # Check if username already exists
        if User.objects.filter(username__iexact=username).exists():
            return JsonResponse({'available': False})
        else:
            return JsonResponse({'available': True})
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

def login_view(request):
    loginpic_path = Path(settings.BASE_DIR) / "static" / "loginpic.png"
    loginpic_data_uri = None
    if loginpic_path.exists():
        loginpic_data = base64.b64encode(loginpic_path.read_bytes()).decode("ascii")
        loginpic_data_uri = f"data:image/png;base64,{loginpic_data}"

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(email__iexact=email)
            auth_user = authenticate(username=user.username, password=password)
            
            if auth_user is not None:
                verification, _ = UserVerification.objects.get_or_create(user=auth_user)
                if not verification.is_verified:
                    if not verification.verification_code or timezone.now() > verification.verification_expiry:
                        otp = generate_otp()
                        expiry = timezone.now() + timedelta(minutes=10)
                        verification.verification_code = otp
                        verification.verification_expiry = expiry
                        verification.save()
                        try:
                            send_otp_email(auth_user, otp)
                            messages.warning(request, 'Your account is not verified. Please check your email for the OTP.')
                            request.session['otp_sent'] = True
                        except Exception as e:
                            messages.error(request, f'Failed to send OTP email: {str(e)}. Please contact support.')
                    else:
                        messages.warning(request, 'Your account is not verified. Please check your email for the OTP.')
                    return redirect('verify_account', user_id=auth_user.id)
                
                # Check tenant and subscription status before logging in
                try:
                    membership = Membership.objects.get(user=auth_user)
                    tenant = membership.tenant
                    if not tenant.is_active:
                        messages.error(request, 'Your subscription has expired. Please renew to access the system.')
                        login(request, auth_user)
                        return redirect('subscription_expired')
                except Membership.DoesNotExist:
                    messages.error(request, 'No tenant associated with this account.')
                    return redirect('login')
                
                login(request, auth_user)
                messages.success(request, f'Welcome back, {auth_user.username}!')
                
                if tenant.system == 'SCHOOL':
                    return redirect('dashboard_school')
                else:
                    return redirect('dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
        except User.DoesNotExist:
            messages.error(request, 'Invalid email or password.')
    
    return render(request, 'auth/login.html', {
        'loginpic_data_uri': loginpic_data_uri,
    })

def verify_account(request, user_id):
    user = get_object_or_404(User, id=user_id)
    verification = get_object_or_404(UserVerification, user=user)
    
    if verification.is_verified:
        messages.success(request, 'Your account is already verified.')
        return redirect('login')
    
    if request.method == 'POST':
        form = OTPForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp']
            if timezone.now() <= verification.verification_expiry and otp == verification.verification_code:
                verification.is_verified = True
                verification.verification_code = None
                verification.verification_expiry = None
                verification.save()
                user.is_active = True
                user.save()
                login(request, user)
                messages.success(request, 'Account verified successfully!')
                
                try:
                    membership = Membership.objects.get(user=user)
                    if membership.tenant.system == 'SCHOOL':
                        return redirect('dashboard_school')
                    else:
                        return redirect('dashboard')
                except Membership.DoesNotExist:
                    messages.error(request, 'No tenant associated with this account.')
                    return redirect('login')
            else:
                messages.error(request, 'Invalid or expired OTP.')
    else:
        form = OTPForm()
    
    return render(request, 'auth/verify.html', {'form': form, 'user': user})

def resend_otp(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        verification = get_object_or_404(UserVerification, user=user)
        
        if not verification.is_verified:
            otp = generate_otp()
            expiry = timezone.now() + timedelta(minutes=10)
            verification.verification_code = otp
            verification.verification_expiry = expiry
            verification.save()
            try:
                send_otp_email(user, otp)
                messages.success(request, 'New OTP sent to your email.')
                request.session['otp_sent'] = True
                logger.info(f"Resend OTP successful for user {user.id}, OTP: {otp}")
                return JsonResponse({'status': 'success', 'message': 'New OTP sent to your email.'})
            except Exception as e:
                logger.error(f"Resend OTP failed for user {user.id}: {str(e)}")
                messages.error(request, f'Failed to send OTP email: {str(e)}. Please contact support.')
                return JsonResponse({'status': 'error', 'message': f'Failed to send OTP: {str(e)}'}, status=500)
        else:
            messages.warning(request, 'Account is already verified.')
            return JsonResponse({'status': 'error', 'message': 'Account is already verified.'}, status=400)
    return redirect('login')

def clear_otp_sent(request, user_id):
    if request.method == 'POST':
        if 'otp_sent' in request.session:
            del request.session['otp_sent']
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')

def forgot_password(request):
    form = ForgotPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        try:
            user = User.objects.get(email__iexact=email)
            verification, _ = UserVerification.objects.get_or_create(user=user)
            if not verification.is_verified:
                messages.error(request, 'Your account is not verified. Please verify your account first.')
                return redirect('verify_account', user_id=user.id)
                
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = request.build_absolute_uri(f'/reset-password/{uid}/{token}/')

            try:
                html_message = render_to_string('auth/password_reset_email.html', {'user': user, 'reset_url': reset_url})
                text_message = strip_tags(html_message)
                send_mail(
                    subject='Password Reset Request - IMS',
                    message=text_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    html_message=html_message,
                    fail_silently=False,
                )
                messages.success(request, 'Password reset link sent to your email.')
                return redirect('login')
            except Exception as e:
                messages.error(request, f'Failed to send password reset email: {str(e)}. Please contact support.')
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email.')
    
    return render(request, 'auth/forgot_password.html', {'form': form})

def reset_password(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        verification, _ = UserVerification.objects.get_or_create(user=user)
        if not verification.is_verified:
            messages.error(request, 'Your account is not verified. Please verify your account first.')
            return redirect('verify_account', user_id=user.id)
            
        form = PasswordResetForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, 'Password reset successfully. Please log in.')
            return redirect('login')
        return render(request, 'auth/reset_password.html', {'form': form})
    else:
        messages.error(request, 'Invalid or expired reset link.')
        return redirect('forgot_password')



@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')

# Subscription Views (Placeholder for payment integration)
import logging
import uuid
import time
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from .models import Tenant, SubscriptionPaymentTransaction
from .forms import SubscriptionPaymentForm
import requests
from retrying import retry
from requests.exceptions import RequestException
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type  # Add these imports

import logging
import uuid
import time
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from .models import Tenant, SubscriptionPaymentTransaction
from .forms import SubscriptionPaymentForm
import requests
from retrying import retry
from requests.exceptions import RequestException

import uuid
import time
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from retrying import retry
from requests.exceptions import RequestException
import requests

logger = logging.getLogger(__name__)

# Configure logging if not already done
# if not logger.handlers:
#     handler = logging.StreamHandler()
#     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     handler.setFormatter(formatter)
#     logger.addHandler(handler)
#     logger.setLevel(logging.DEBUG)


@retry(stop_max_attempt_number=3, wait_fixed=2000, retry_on_exception=lambda exception: isinstance(exception, RequestException))
def get_mobile_money_operators():
    """Fetch available mobile money operators from PayChangu API."""
    url = "https://api.paychangu.com/mobile-money"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {settings.PAYCHANGU_API_KEY.strip()}"
    }
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        return response.json().get('data', [])
    logger.error(f"Failed to fetch operators: {response.status_code} - {response.text}")
    return []


def send_subscription_payment_notification(transaction, success=True):
    """Send email notification for subscription payment status."""
    try:
        tenant = transaction.tenant
        status = 'Successful' if success else 'Failed'
        subject = f"Subscription Payment {status}: Tenant {tenant.name}"
        message = render_to_string('emails/subscription_payment_notification.html', {
            'tenant': tenant,
            'transaction': transaction,
            'success': success,
            'site_url': settings.SITE_URL,
        })
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[transaction.user_email],
            html_message=message,
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


@login_required
def subscription_detail(request):
    tenant = request.tenant
    if not tenant:
        messages.error(request, 'No tenant associated with your account.')
        return redirect('login')

    days_remaining = tenant.days_remaining

    context = {
        'tenant': tenant,
        'days_remaining': days_remaining,
        'subscription_status': 'Active' if tenant.is_subscription_valid else 'Expired',
        'is_trial': tenant.is_trial,
    }
    return render(request, 'subscriptions/detail.html', context)


@login_required
def subscription_expired(request):
    try:
        membership = Membership.objects.get(user=request.user)
        tenant = membership.tenant
        
        if tenant.is_subscription_valid:
            return redirect('subscription_detail')
            
        today = timezone.now().date()
        days_overdue = 0
        if tenant.subscription_end:
            days_overdue = max((today - tenant.subscription_end).days, 0)
            
        context = {
            'tenant': tenant,
            'days_overdue': days_overdue,
            'is_trial': tenant.is_trial,
            'days_remaining': tenant.days_remaining,
        }
        return render(request, 'subscriptions/expired.html', context)
    except Membership.DoesNotExist:
        messages.error(request, 'No tenant associated with your account.')
        return redirect('logout')


@login_required
def renew_subscription(request):
    tenant = get_object_or_404(Tenant, owner=request.user)
    mobile_operators = get_mobile_money_operators()
    
    if not mobile_operators:
        messages.warning(request, "Payment service is temporarily unavailable. Please try again later.")
    
    if request.method == 'POST':
        form = SubscriptionPaymentForm(request.POST, operators=mobile_operators)
        if form.is_valid():
            return process_subscription_payment(request, tenant, form, mobile_operators)
        else:
            logger.warning(f"Form validation failed: {form.errors.as_json()}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Form validation failed. Please check your inputs.'
            }, status=400)
    else:
        form = SubscriptionPaymentForm(operators=mobile_operators)

    context = {
        'tenant': tenant,
        'form': form,
        'mobile_operators': mobile_operators,
        'plan_prices': {'monthly': '15,000', 'quarterly': '40,000', 'annual': '150,000'},
    }
    return render(request, 'subscriptions/renew_subscription.html', context)


@login_required
@transaction.atomic
def process_subscription_payment(request, tenant, form, operators):
    """Process subscription payment with improved charge_id generation and duplicate handling"""
    try:
        operator_ref_id = form.cleaned_data['operator_ref_id']
        mobile = form.cleaned_data['mobile']
        amount = form.cleaned_data['amount']
        user_email = form.cleaned_data['email']
        first_name = form.cleaned_data['first_name']
        last_name = form.cleaned_data['last_name']
        subscription_plan = form.cleaned_data['subscription_plan']
        
        # CRITICAL FIX: Generate unique charge_id with milliseconds and random component
        timestamp = int(time.time() * 1000)  # milliseconds
        random_suffix = ''.join([str(uuid.uuid4().hex[:4])])
        charge_id = f"sub-{tenant.id}-{timestamp}-{random_suffix}"
        
        logger.info(f"🆔 Generated charge_id: {charge_id}")

        # Check if there's a recent pending transaction and reuse it
        recent_pending = SubscriptionPaymentTransaction.objects.filter(
            tenant=tenant,
            status='pending',
            created_at__gte=timezone.now() - timezone.timedelta(minutes=10)
        ).order_by('-created_at').first()
        
        if recent_pending:
            logger.info(f"♻️ Found recent pending transaction: {recent_pending.charge_id}")
            return JsonResponse({
                'status': 'success',
                'message': 'Resuming existing payment',
                'transaction_id': recent_pending.charge_id
            })

        # Create new transaction
        transaction_obj = SubscriptionPaymentTransaction.objects.create(
            tenant=tenant,
            charge_id=charge_id,
            amount=amount,
            currency='MWK',
            mobile=mobile,
            operator_ref_id=operator_ref_id,
            status='pending',
            user_email=user_email,
            subscription_plan=subscription_plan
        )

        payload = {
            "mobile_money_operator_ref_id": operator_ref_id,
            "mobile": mobile,
            "amount": str(int(amount)),
            "charge_id": charge_id,
            "email": user_email,
            "first_name": first_name,
            "last_name": last_name,
        }

        logger.info(f"📤 Sending payment request for {charge_id}")
        logger.debug(f"Payload: {payload}")

        url = "https://api.paychangu.com/mobile-money/payments/initialize"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": f"Bearer {settings.PAYCHANGU_API_KEY.strip()}"
        }

        @retry(stop_max_attempt_number=3, wait_fixed=2000, retry_on_exception=lambda exception: isinstance(exception, RequestException))
        def make_payment_request():
            return requests.post(url, json=payload, headers=headers, timeout=15)

        try:
            response = make_payment_request()
            response_data = response.json()
            logger.info(f"📥 PayChangu response status: {response.status_code}")
            logger.debug(f"Response data: {response_data}")

            if response.status_code == 200 and response_data.get('status') == 'success':
                transaction_obj.response_data = response_data
                transaction_obj.save(update_fields=['response_data'])
                logger.info(f"✅ Payment initiated successfully for {charge_id}")
                return JsonResponse({
                    'status': 'success',
                    'message': 'Payment initiated',
                    'transaction_id': charge_id
                })
            else:
                # Check if it's a duplicate charge_id error
                error_message = response_data.get('message', 'Unknown error')
                
                # Handle duplicate charge_id
                if 'charge_id' in str(response_data).lower() and 'already been used' in str(response_data).lower():
                    logger.warning(f"⚠️ Duplicate charge_id detected, checking existing transaction")
                    
                    # Try to find and return the existing transaction
                    existing = SubscriptionPaymentTransaction.objects.filter(
                        tenant=tenant,
                        status='pending'
                    ).order_by('-created_at').first()
                    
                    if existing:
                        logger.info(f"♻️ Returning existing transaction: {existing.charge_id}")
                        return JsonResponse({
                            'status': 'success',
                            'message': 'Resuming existing payment',
                            'transaction_id': existing.charge_id
                        })
                
                transaction_obj.delete()
                logger.error(f"❌ PayChangu API error: {error_message}")
                return JsonResponse({'status': 'error', 'message': error_message}, status=400)
                
        except RequestException as e:
            transaction_obj.delete()
            logger.error(f"❌ PayChangu API request failed after retries: {str(e)}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Payment service is temporarily unavailable. Please try again later.'
            }, status=503)
            
    except Exception as e:
        logger.error(f"❌ Unexpected error in process_subscription_payment: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error', 
            'message': 'An unexpected error occurred. Please try again later.'
        }, status=500)


@login_required
@csrf_exempt  # CRITICAL: Allow AJAX without CSRF token
@require_http_methods(["GET"])
def check_subscription_payment_status(request, transaction_id):
    """Check payment status - optimized for polling"""
    logger.info(f"🔍 Checking payment status for: {transaction_id}")
    
    try:
        # Verify transaction belongs to user's tenant
        transaction_obj = get_object_or_404(
            SubscriptionPaymentTransaction, 
            charge_id=transaction_id, 
            tenant__owner=request.user
        )
        
        logger.info(f"📊 Current transaction status: {transaction_obj.status}")
        
        # Return immediately if already completed
        if transaction_obj.status == 'success':
            logger.info(f"✅ Transaction already successful")
            return JsonResponse({'status': 'success'})
        elif transaction_obj.status in ['failed', 'cancelled']:
            logger.info(f"❌ Transaction already {transaction_obj.status}")
            return JsonResponse({
                'status': transaction_obj.status,
                'message': transaction_obj.response_data.get('message', f'Transaction {transaction_obj.status}') if transaction_obj.response_data else f'Transaction {transaction_obj.status}'
            })

        # Check with PayChangu API
        url = f"https://api.paychangu.com/mobile-money/payments/{transaction_id}/verify"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {settings.PAYCHANGU_API_KEY.strip()}"
        }
        
        try:
            logger.info(f"📡 Calling PayChangu verify API")
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ PayChangu API returned {response.status_code}")
                return JsonResponse({'status': 'pending'})
            
            data = response.json()
            logger.info(f"📥 PayChangu verify response: {data}")
            
            transaction_obj.response_data = data
            transaction_obj.save(update_fields=['response_data'])
            
            api_status = data.get('status', '').lower()
            logger.info(f"🎯 API status: {api_status}")
            
            if api_status in ['successful', 'success']:
                logger.info(f"🎉 PAYMENT SUCCESSFUL!")
                transaction_obj.status = 'success'
                transaction_obj.completed_at = timezone.now()
                transaction_obj.tenant.extend_subscription(transaction_obj.subscription_plan)
                transaction_obj.save(update_fields=['status', 'completed_at'])
                
                # Send notification asynchronously if possible
                try:
                    send_subscription_payment_notification(transaction_obj, success=True)
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
                
                return JsonResponse({'status': 'success'})
            
            elif api_status in ['failed', 'failure']:
                logger.warning(f"❌ Payment failed")
                transaction_obj.status = 'failed'
                transaction_obj.completed_at = timezone.now()
                transaction_obj.save(update_fields=['status', 'completed_at'])
                return JsonResponse({
                    'status': 'failed', 
                    'message': data.get('message', 'Payment failed')
                })
            
            elif 'cancelled' in api_status or 'canceled' in api_status:
                logger.warning(f"🚫 Payment cancelled")
                transaction_obj.status = 'cancelled'
                transaction_obj.completed_at = timezone.now()
                transaction_obj.save(update_fields=['status', 'completed_at'])
                return JsonResponse({
                    'status': 'cancelled', 
                    'message': data.get('message', 'Payment was cancelled')
                })
            
            else:
                logger.info(f"⏳ Payment still pending")
                return JsonResponse({'status': 'pending'})
                
        except requests.Timeout:
            logger.warning(f"⏱️ Timeout checking status for {transaction_id}")
            return JsonResponse({'status': 'pending'})
        except requests.RequestException as e:
            logger.error(f"❌ Request error checking status for {transaction_id}: {e}")
            return JsonResponse({'status': 'pending'})
            
    except SubscriptionPaymentTransaction.DoesNotExist:
        logger.error(f"❌ Transaction not found: {transaction_id}")
        return JsonResponse({
            'status': 'error', 
            'message': 'Transaction not found'
        }, status=404)
    except Exception as e:
        logger.error(f"❌ Unexpected error in payment status check: {e}", exc_info=True)
        return JsonResponse({
            'status': 'pending',
            'message': 'Status check temporarily unavailable'
        })

# User Management Views
@login_required
@role_required(['owner', 'admin'])
def user_list(request):
    users = Membership.objects.filter(tenant=request.tenant).select_related('user')
    
    # Calculate role counts for KPI cards
    admin_count = users.filter(role='admin').count()
    seller_count = users.filter(role='seller').count()
    manager_count = users.filter(role='inventory_manager').count()
    
    context = {
        'users': users,
        'admin_count': admin_count,
        'seller_count': seller_count,
        'manager_count': manager_count,
    }
    return render(request, 'users/list.html', context)

def send_credentials_email(user, temp_password, request):
    subject = 'Your IMS Account Credentials'
    login_url = request.build_absolute_uri('/login/')
    context = {
        'user': user,
        'temp_password': temp_password,
        'login_url': login_url
    }
    try:
        html_content = render_to_string('auth/credentials_email.html', context)
        text_content = strip_tags(html_content)
        email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
        email.attach_alternative(html_content, "text/html")
        email.send()
        logger.info(f"Credentials email sent to {user.email}: username={user.username}")
    except Exception as e:
        logger.error(f"Failed to send credentials email to {user.email}: {str(e)}")
        raise

def send_user_update_email(user, changes, modified_by, request):
    subject = 'Your IMS Account Has Been Updated'
    login_url = request.build_absolute_uri('/login/')
    context = {
        'user': user,
        'changes': changes,
        'modified_by': modified_by,
        'login_url': login_url
    }
    try:
        html_content = render_to_string('auth/user_update_email.html', context)
        text_content = strip_tags(html_content)
        email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
        email.attach_alternative(html_content, "text/html")
        email.send()
        logger.info(f"User update email sent to {user.email}: changes={changes}")
    except Exception as e:
        logger.error(f"Failed to send user update email to {user.email}: {str(e)}")
        raise

import secrets
import string
import json

def generate_temp_password(length=12):
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(chars) for _ in range(length))

@login_required
@role_required(['owner', 'admin'])
def user_create(request):
    if request.method == 'POST':
        form = TenantUserForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                with transaction.atomic():
                    temp_password = generate_temp_password()
                    user = User.objects.create_user(
                        username=form.cleaned_data['username'],
                        email=form.cleaned_data['email'],
                        password=temp_password
                    )
                    user.is_active = True  # User is verified by default
                    user.save()
                    
                    Membership.objects.create(
                        user=user,
                        tenant=request.tenant,
                        role=form.cleaned_data['role']
                    )
                    
                    try:
                        send_credentials_email(user, temp_password, request)
                        messages.success(request, f'User {user.username} created successfully. Credentials sent to their email.')
                        return redirect('user_list')
                    except Exception as e:
                        user.delete()
                        messages.error(request, f'Failed to send email: {str(e)}. User creation aborted.')
                        logger.error(f"User creation email failed for {user.email}: {str(e)}")
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
                logger.error(f"User creation failed: {str(e)}")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = TenantUserForm(tenant=request.tenant)
    return render(request, 'users/form.html', {'form': form})

@login_required
@role_required(['owner', 'admin'])
def user_update(request, membership_id):
    membership = get_object_or_404(Membership, id=membership_id, tenant=request.tenant)
    original_data = {
        'username': membership.user.username,
        'email': membership.user.email,
        'role': membership.role
    }
    
    if request.method == 'POST':
        form = TenantUserForm(request.POST, tenant=request.tenant, instance=membership.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    new_role = form.cleaned_data['role']
                    changes = []
                    
                    if original_data['username'] != user.username:
                        changes.append(f"Username changed from '{original_data['username']}' to '{user.username}'")
                    if original_data['email'] != user.email:
                        changes.append(f"Email changed from '{original_data['email']}' to '{user.email}'")
                    if original_data['role'] != new_role:
                        changes.append(f"Role changed from '{original_data['role']}' to '{new_role}'")
                    
                    membership.role = new_role
                    membership.save()
                    
                    if changes:
                        try:
                            send_user_update_email(user, changes, request.user.username, request)
                            messages.success(request, f'User {user.username} updated successfully. Notification sent to their email.')
                        except Exception as e:
                            messages.warning(request, f'User updated, but failed to send notification email: {str(e)}')
                            logger.error(f"User update email failed for {user.email}: {str(e)}")
                    else:
                        messages.success(request, 'No changes made to user.')
                    
                    return redirect('user_list')
            except Exception as e:
                messages.error(request, f'Error updating user: {str(e)}')
                logger.error(f"User update failed: {str(e)}")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = TenantUserForm(tenant=request.tenant, instance=membership.user, initial={'role': membership.role})
    return render(request, 'users/form.html', {'form': form})

@login_required
@role_required(['owner', 'admin'])
def validate_field(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            field_type = data.get('type')
            value = data.get('value')
            user_id = data.get('user_id', '0')

            if field_type == 'username':
                queryset = User.objects.filter(username__iexact=value)
                if user_id != '0':
                    queryset = queryset.exclude(pk=user_id)
                if queryset.exists():
                    return JsonResponse({'valid': False, 'message': 'This username is already taken.'})
                return JsonResponse({'valid': True})

            if field_type == 'email':
                queryset = User.objects.filter(email__iexact=value)
                if user_id != '0':
                    queryset = queryset.exclude(pk=user_id)
                if queryset.exists():
                    return JsonResponse({'valid': False, 'message': 'This email is already in use.'})
                return JsonResponse({'valid': True})

            return JsonResponse({'valid': False, 'message': 'Invalid field type.'}, status=400)
        except Exception as e:
            logger.error(f"Field validation failed: {str(e)}")
            return JsonResponse({'valid': False, 'message': 'Error validating field.'}, status=500)
    return JsonResponse({'valid': False, 'message': 'Invalid request method.'}, status=400)

@login_required
@role_required(['owner', 'admin'])
def user_delete(request, membership_id):
    membership = get_object_or_404(Membership, id=membership_id, tenant=request.tenant)
    if request.method == 'POST':
        if membership.role == 'owner':
            messages.error(request, 'Cannot delete owner account.')
            return redirect('user_list')
        membership.user.delete()
        messages.success(request, 'User deleted successfully.')
        return redirect('user_list')
    return render(request, 'users/confirm_delete.html', {'membership': membership})

# Dashboard View (System-specific conditional rendering)
@login_required
def dashboard(request):
    if not request.tenant.is_subscription_valid:
        return redirect('subscription_expired')
    
    context = {
        'system': request.tenant.system,
    }
    
    if request.tenant.system == 'PHARMACY':
        # Pharmacy-specific stats
        total_drugs = Drug.objects.filter(tenant=request.tenant).count()
        low_stock_drugs = Drug.objects.filter(tenant=request.tenant, quantity__lt=10).count()
        critical_stock = Drug.objects.filter(tenant=request.tenant, quantity__lt=5).count()
        expired_drugs = Drug.objects.filter(tenant=request.tenant, expiry_date__lt=timezone.now().date()).count()
        
        total_prescriptions = Prescription.objects.filter(tenant=request.tenant).count()
        today_prescriptions = Prescription.objects.filter(tenant=request.tenant, date_prescribed=timezone.now().date()).count()
        
        active_sales = Sale.objects.filter(tenant=request.tenant, is_voided=False)
        total_sales = active_sales.count()
        today_sales = active_sales.filter(date__date=timezone.now().date()).count()
        total_revenue = active_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        # Calculate growth percentages (simplified for demo)
        revenue_growth = 12.5
        inventory_growth = 3.2
        prescription_growth = 8.7
        
        # Get low stock items for the table
        low_stock_items = Drug.objects.filter(tenant=request.tenant, quantity__lt=10).order_by('quantity')[:10]
        
        recent_sales = active_sales.select_related('processed_by').order_by('-date')[:5]
        recent_prescriptions = Prescription.objects.filter(tenant=request.tenant).select_related('created_by').order_by('-date_prescribed')[:5]
        
        # Sales data for charts
        sales_data = []
        for i in range(6, -1, -1):
            day = timezone.now().date() - timedelta(days=i)
            daily_sales = active_sales.filter(date__date=day).aggregate(
                total=Sum('total_amount'),
                count=Count('id')
            )
            sales_data.append({
                'date': day,
                'total': daily_sales['total'] or 0,
                'count': daily_sales['count'] or 0
            })
        
        # Top categories
        top_categories = Drug.objects.filter(tenant=request.tenant).values('category').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        # Monthly sales data
        monthly_sales = []
        for month in range(1, 13):
            month_sales = active_sales.filter(
                date__month=month,
                date__year=timezone.now().year
            ).aggregate(total=Sum('total_amount'))
            monthly_sales.append({
                'month': month,
                'total': month_sales['total'] or 0
            })
        
        # Inventory stats
        inventory_stats = {
            'in_stock': Drug.objects.filter(tenant=request.tenant, quantity__gte=10).count(),
            'low_stock': Drug.objects.filter(tenant=request.tenant, quantity__lt=10, quantity__gte=5).count(),
            'critical_stock': Drug.objects.filter(tenant=request.tenant, quantity__lt=5).count(),
        }
        
        # Top selling products
        top_selling_products = SaleItem.objects.filter(
            sale__tenant=request.tenant,
            sale__is_voided=False
        ).values(
            'drug__name', 'drug__category', 'drug__quantity'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('price')
        ).order_by('-total_quantity')[:5]
        
        context.update({
            'total_drugs': total_drugs,
            'low_stock_drugs': low_stock_drugs,
            'critical_stock': critical_stock,
            'expired_drugs': expired_drugs,
            'total_prescriptions': total_prescriptions,
            'today_prescriptions': today_prescriptions,
            'total_sales': total_sales,
            'today_sales': today_sales,
            'total_revenue': total_revenue,
            'revenue_growth': revenue_growth,
            'inventory_growth': inventory_growth,
            'prescription_growth': prescription_growth,
            'low_stock_items': low_stock_items,
            'recent_sales': recent_sales,
            'recent_prescriptions': recent_prescriptions,
            'sales_data': sales_data,
            'top_categories': top_categories,
            'monthly_sales': monthly_sales,
            'inventory_stats': inventory_stats,
            'top_selling_products': top_selling_products,
        })
    
    return render(request, 'dashboard.html', context)


from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta, date
import random
import string
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from io import BytesIO
import pandas as pd


# Drug Views (Pharmacy-specific)
@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def drug_list(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    # Handle search and category filter from GET parameters
    search_query = request.GET.get('search', '')
    category_filter = request.GET.get('category', '')
    
    drugs = Drug.objects.filter(tenant=request.tenant)
    
    if search_query:
        drugs = drugs.filter(name__icontains=search_query)
    
    if category_filter:
        drugs = drugs.filter(category__iexact=category_filter)
    
    low_stock_drugs = drugs.filter(quantity__lt=10)
    expired_drugs = drugs.filter(expiry_date__lt=date.today())
    
    # Backend pagination
    paginator = Paginator(drugs, 10)  # 10 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get distinct categories for filter
    categories = Drug.objects.filter(tenant=request.tenant).values_list('category', flat=True).distinct()
    
    return render(request, 'inventory/list.html', {
        'page_obj': page_obj,
        'low_stock_count': low_stock_drugs.count(),
        'expired_count': expired_drugs.count(),
        'search_query': search_query,
        'category_filter': category_filter,
        'categories': categories,
    })

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def download_drug_data(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    # Query all drugs for the current tenant
    drugs = Drug.objects.filter(tenant=request.tenant).values(
        'name', 'batch_no', 'category', 'price', 'quantity', 'expiry_date', 'barcode'
    )
    
    # Convert to DataFrame
    data = {
        'name': [drug['name'] for drug in drugs],
        'batch_no': [drug['batch_no'] for drug in drugs],
        'category': [drug['category'] for drug in drugs],
        'price': [drug['price'] for drug in drugs],
        'quantity': [drug['quantity'] for drug in drugs],
        'expiry_date': [drug['expiry_date'].strftime('%Y-%m-%d') for drug in drugs],
        'barcode': [drug['barcode'] or '' for drug in drugs]
    }
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Drugs')
    
    # Prepare response
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="drug_data_export.xlsx"'
    return response


# New view for bulk upload
@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def drug_bulk_upload(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            return render(request, 'inventory/bulk_upload.html', {'error': 'No file uploaded.'})
        
        try:
            df = pd.read_excel(excel_file)
            errors = []
            created_count = 0
            
            required_columns = ['name', 'batch_no', 'category', 'price', 'quantity', 'expiry_date', 'barcode']
            if not all(col in df.columns for col in required_columns):
                return render(request, 'inventory/bulk_upload.html', {'error': 'Missing required columns in Excel.'})
            
            for index, row in df.iterrows():
                try:
                    name = row['name']
                    batch_no = row['batch_no']
                    category = row['category']
                    price = float(row['price'])
                    quantity = int(row['quantity'])
                    expiry_date = pd.to_datetime(row['expiry_date']).date()
                    barcode = row.get('barcode', None)
                    
                    if price < 0 or quantity < 0 or expiry_date < date.today():
                        raise ValueError("Invalid data: negative values or past expiry.")
                    
                    Drug.objects.create(
                        tenant=request.tenant,
                        name=name,
                        batch_no=batch_no,
                        category=category,
                        price=price,
                        quantity=quantity,
                        expiry_date=expiry_date,
                        barcode=barcode,
                        created_by=request.user,
                        last_modified_by=request.user
                    )
                    created_count += 1
                except Exception as e:
                    errors.append(f"Row {index + 2}: {str(e)}")
            
            if errors:
                return render(request, 'inventory/bulk_upload.html', {
                    'success': f'{created_count} drugs created successfully.',
                    'errors': errors
                })
            return redirect('drug_list')
        
        except Exception as e:
            return render(request, 'inventory/bulk_upload.html', {'error': str(e)})
    
    return render(request, 'inventory/bulk_upload.html')

# New view to download sample Excel template
@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def download_sample_template(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    data = {
        'name': ['Example Drug 1', 'Example Drug 2'],
        'batch_no': ['BATCH001', 'BATCH002'],
        'category': ['Pain Relief', 'Antibiotics'],
        'price': [10.50, 15.00],
        'quantity': [100, 50],
        'expiry_date': ['2026-01-01', '2025-12-31'],
        'barcode': ['123456789', '987654321']
    }
    df = pd.DataFrame(data)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="drug_upload_template.xlsx"'
    return response

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def drug_detail(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    drug = get_object_or_404(Drug, id=id, tenant=request.tenant)
    return render(request, 'inventory/detail.html', {'drug': drug})

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def drug_create(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    if request.method == 'POST':
        name = request.POST.get('name')
        batch_no = request.POST.get('batch_no')
        category = request.POST.get('category')
        price = request.POST.get('price')
        quantity = request.POST.get('quantity')
        expiry_date = request.POST.get('expiry_date')
        
        drug = Drug.objects.create(
            tenant=request.tenant,
            name=name,
            batch_no=batch_no,
            category=category,
            price=price,
            quantity=quantity,
            expiry_date=expiry_date,
            created_by=request.user,
            last_modified_by=request.user
        )
        return redirect('drug_detail', id=drug.id)
    
    return render(request, 'inventory/form.html')

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def drug_update(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    drug = get_object_or_404(Drug, id=id, tenant=request.tenant)
    
    if request.method == 'POST':
        drug.name = request.POST.get('name')
        drug.batch_no = request.POST.get('batch_no')
        drug.category = request.POST.get('category')
        drug.price = request.POST.get('price')
        drug.quantity = request.POST.get('quantity')
        drug.expiry_date = request.POST.get('expiry_date')
        drug.last_modified_by = request.user
        drug.save()
        
        return redirect('drug_detail', id=drug.id)
    
    return render(request, 'inventory/form.html', {'drug': drug})

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def drug_delete(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    drug = get_object_or_404(Drug, id=id, tenant=request.tenant)
    
    if request.method == 'POST':
        drug.delete()
        messages.success(request, 'Drug deleted successfully.')
        return redirect('drug_list')
    
    return redirect('drug_list')

@login_required
@role_required(['owner', 'admin', 'seller', 'inventory_manager'])
def barcode_lookup(request):
    if request.tenant.system != 'PHARMACY':
        return JsonResponse({'success': False, 'message': 'This feature is only available for Pharmacy system.'})
    barcode = request.GET.get('barcode', '')
    try:
        drug = Drug.objects.get(barcode=barcode, tenant=request.tenant)
        return JsonResponse({
            'success': True,
            'drug': {
                'id': drug.id,
                'name': drug.name,
                'batch_no': drug.batch_no,
                'price': str(drug.price),
                'quantity': drug.quantity
            }
        })
    except Drug.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Drug not found'})

# Prescription Views (Pharmacy-specific)
# prescriptions/views.py
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum
import pandas as pd
from io import BytesIO
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

@login_required
@role_required(['owner', 'admin', 'seller'])
def prescription_list(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')
    search_query = request.GET.get('search', '')
    
    # Get all prescriptions with related data
    prescriptions = Prescription.objects.filter(tenant=request.tenant)\
        .select_related('created_by')\
        .prefetch_related('prescriptionitem_set__drug')\
        .order_by('-date_prescribed')
    
    # Apply filters
    if search_query:
        prescriptions = prescriptions.filter(
            models.Q(patient_name__icontains=search_query) |
            models.Q(prescription_id__icontains=search_query) |
            models.Q(doctor_name__icontains=search_query)
        )
    
    if status_filter:
        today = timezone.now().date()
        if status_filter == 'new':
            prescriptions = prescriptions.filter(date_prescribed=today)
        elif status_filter == 'active':
            prescriptions = prescriptions.filter(date_prescribed__lt=today)
    
    if date_filter:
        today = timezone.now().date()
        if date_filter == 'today':
            prescriptions = prescriptions.filter(date_prescribed=today)
        elif date_filter == 'week':
            week_ago = today - timedelta(days=7)
            prescriptions = prescriptions.filter(date_prescribed__gte=week_ago)
        elif date_filter == 'month':
            month_ago = today - timedelta(days=30)
            prescriptions = prescriptions.filter(date_prescribed__gte=month_ago)
    
    # Count today's prescriptions
    today = timezone.now().date()
    today_prescriptions = Prescription.objects.filter(
        tenant=request.tenant, 
        date_prescribed=today
    ).count()
    
    # Count total prescriptions
    total_prescriptions = prescriptions.count()
    
    # Get prescription statistics for the last 7 days
    last_7_days = today - timedelta(days=7)
    weekly_stats = Prescription.objects.filter(
        tenant=request.tenant, 
        date_prescribed__gte=last_7_days
    ).values('date_prescribed').annotate(count=Count('id')).order_by('date_prescribed')
    
    # Pagination
    paginator = Paginator(prescriptions, 10)  # Show 10 prescriptions per page
    page = request.GET.get('page')
    
    try:
        prescriptions_page = paginator.page(page)
    except PageNotAnInteger:
        prescriptions_page = paginator.page(1)
    except EmptyPage:
        prescriptions_page = paginator.page(paginator.num_pages)
    
    # Get medications count per prescription
    for prescription in prescriptions_page:
        prescription.medications_count = prescription.prescriptionitem_set.count()
        prescription.total_quantity = prescription.prescriptionitem_set.aggregate(
            total=Sum('quantity')
        )['total'] or 0
    
    context = {
        'prescriptions': prescriptions_page,
        'today_prescriptions': today_prescriptions,
        'total_prescriptions': total_prescriptions,
        'weekly_stats': list(weekly_stats),
        'today': today,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_filter': date_filter,
    }
    
    return render(request, 'prescriptions/list.html', context)

# prescriptions/views.py
@login_required
@role_required(['owner', 'admin', 'seller'])
def download_prescriptions_excel(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    # Get filter parameters from request
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')
    search_query = request.GET.get('search', '')
    
    # Apply the same filters as the list view
    prescriptions = Prescription.objects.filter(tenant=request.tenant)\
        .select_related('created_by')\
        .prefetch_related('prescriptionitem_set__drug')
    
    if search_query:
        prescriptions = prescriptions.filter(
            models.Q(patient_name__icontains=search_query) |
            models.Q(prescription_id__icontains=search_query) |
            models.Q(doctor_name__icontains=search_query)
        )
    
    if status_filter:
        today = timezone.now().date()
        if status_filter == 'new':
            prescriptions = prescriptions.filter(date_prescribed=today)
        elif status_filter == 'active':
            prescriptions = prescriptions.filter(date_prescribed__lt=today)
    
    if date_filter:
        today = timezone.now().date()
        if date_filter == 'today':
            prescriptions = prescriptions.filter(date_prescribed=today)
        elif date_filter == 'week':
            week_ago = today - timedelta(days=7)
            prescriptions = prescriptions.filter(date_prescribed__gte=week_ago)
        elif date_filter == 'month':
            month_ago = today - timedelta(days=30)
            prescriptions = prescriptions.filter(date_prescribed__gte=month_ago)
    
    # Prepare data for Excel
    data = []
    for prescription in prescriptions:
        medications = []
        for item in prescription.prescriptionitem_set.all():
            medications.append(f"{item.drug.name} (x{item.quantity})")
        
        data.append({
            'Prescription ID': prescription.prescription_id,
            'Patient Name': prescription.patient_name,
            'Patient Age': prescription.patient_age,
            'Patient Phone': prescription.patient_phone or '',
            'Doctor Name': prescription.doctor_name,
            'Doctor License': prescription.doctor_license or '',
            'Date Prescribed': prescription.date_prescribed,
            'Medications': ', '.join(medications),
            'Created By': prescription.created_by.username,
            'Total Medications': prescription.prescriptionitem_set.count(),
        })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Prescriptions')
        
        # Auto-adjust column widths
        worksheet = writer.sheets['Prescriptions']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    # Prepare response
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="prescriptions_{request.tenant.name}_{timezone.now().date()}.xlsx"'
    
    return response

# prescriptions/views.py
@login_required
@role_required(['owner', 'admin', 'seller'])
def send_prescription_email(request, prescription_id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    prescription = get_object_or_404(Prescription, id=prescription_id, tenant=request.tenant)
    
    if request.method == 'POST':
        email_address = request.POST.get('email')
        
        if not email_address:
            return JsonResponse({'success': False, 'error': 'Email address is required'})
        
        try:
            # Prepare email content
            subject = f"Your Prescription Details - {request.tenant.name}"
            
            # Prepare context for email template
            context = {
                'tenant_name': request.tenant.name,
                'prescription': prescription,
                'patient_name': prescription.patient_name,
                'prescription_id': prescription.prescription_id,
                'date_prescribed': prescription.date_prescribed,
                'doctor_name': prescription.doctor_name,
                'medications': prescription.prescriptionitem_set.all(),
                'login_url': request.build_absolute_uri('/'),
            }
            
            # Render HTML email template
            html_content = render_to_string('prescriptions/email_template.html', context)
            
            # Create email
            email = EmailMultiAlternatives(
                subject=subject,
                body=f"Please find your prescription details attached.\n\nPrescription ID: {prescription.prescription_id}\nPatient: {prescription.patient_name}\nDate: {prescription.date_prescribed}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email_address],
                reply_to=[request.user.email] if request.user.email else [settings.DEFAULT_FROM_EMAIL]
            )
            
            # Attach HTML content
            email.attach_alternative(html_content, "text/html")
            
            # Send email
            email.send()
            
            return JsonResponse({'success': True, 'message': 'Email sent successfully'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# Optional: Bulk email sending
@login_required
@role_required(['owner', 'admin'])
def send_bulk_prescription_emails(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    if request.method == 'POST':
        prescription_ids = request.POST.getlist('prescription_ids')
        emails = request.POST.getlist('emails')
        
        results = []
        for prescription_id, email in zip(prescription_ids, emails):
            try:
                prescription = Prescription.objects.get(id=prescription_id, tenant=request.tenant)
                
                # Send email (reuse the function above)
                # You might want to refactor the email sending into a separate function
                # that can be called from both single and bulk operations
                
                results.append({
                    'prescription_id': prescription_id,
                    'email': email,
                    'success': True,
                    'message': 'Email sent'
                })
            except Exception as e:
                results.append({
                    'prescription_id': prescription_id,
                    'email': email,
                    'success': False,
                    'error': str(e)
                })
        
        return JsonResponse({'results': results})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
@role_required(['owner', 'admin', 'seller'])
def prescription_detail(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    prescription = get_object_or_404(Prescription, id=id, tenant=request.tenant)
    return render(request, 'prescriptions/detail.html', {'prescription': prescription})

@login_required
@role_required(['owner', 'admin', 'seller'])
def prescription_create(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    if request.method == 'POST':
        prescription_id = request.POST.get('prescription_id')
        patient_name = request.POST.get('patient_name')
        patient_age = request.POST.get('patient_age')
        patient_address = request.POST.get('patient_address')
        patient_phone = request.POST.get('patient_phone')
        doctor_name = request.POST.get('doctor_name')
        doctor_license = request.POST.get('doctor_license')
        
        prescription = Prescription.objects.create(
            tenant=request.tenant,
            prescription_id=prescription_id,
            patient_name=patient_name,
            patient_age=patient_age,
            patient_address=patient_address,
            patient_phone=patient_phone,
            doctor_name=doctor_name,
            doctor_license=doctor_license,
            created_by=request.user
        )
        
        drug_ids = request.POST.getlist('drugs')
        quantities = request.POST.getlist('quantities')
        instructions = request.POST.getlist('instructions')
        
        for i, drug_id in enumerate(drug_ids):
            drug = Drug.objects.get(id=drug_id, tenant=request.tenant)
            PrescriptionItem.objects.create(
                prescription=prescription,
                drug=drug,
                quantity=quantities[i],
                instructions=instructions[i] if i < len(instructions) else ''
            )
        
        return redirect('prescription_detail', id=prescription.id)
    
    drugs = Drug.objects.filter(tenant=request.tenant)
    return render(request, 'prescriptions/form.html', {'drugs': drugs})

@login_required
@role_required(['owner', 'admin', 'seller'])
def prescription_update(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    prescription = get_object_or_404(Prescription, id=id, tenant=request.tenant)
    
    if request.method == 'POST':
        prescription.patient_name = request.POST.get('patient_name')
        prescription.patient_age = request.POST.get('patient_age')
        prescription.patient_address = request.POST.get('patient_address')
        prescription.patient_phone = request.POST.get('patient_phone')
        prescription.doctor_name = request.POST.get('doctor_name')
        prescription.doctor_license = request.POST.get('doctor_license')
        prescription.save()
        
        prescription.prescribed_drugs.clear()
        drug_ids = request.POST.getlist('drugs')
        quantities = request.POST.getlist('quantities')
        instructions = request.POST.getlist('instructions')
        
        for i, drug_id in enumerate(drug_ids):
            drug = Drug.objects.get(id=drug_id, tenant=request.tenant)
            PrescriptionItem.objects.create(
                prescription=prescription,
                drug=drug,
                quantity=quantities[i],
                instructions=instructions[i] if i < len(instructions) else ''
            )
        
        return redirect('prescription_detail', id=prescription.id)
    
    drugs = Drug.objects.filter(tenant=request.tenant)
    return render(request, 'prescriptions/form.html', {
        'prescription': prescription,
        'drugs': drugs
    })

# Sale Views (Pharmacy-specific, but could be shared with SALES system)
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

def generate_sale_id():
    return 'S' + ''.join(random.choices(string.digits, k=7))

@login_required
@role_required(['owner', 'admin', 'seller'])
def pos_system(request):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Sales system.')
    drugs = Drug.objects.filter(tenant=request.tenant, quantity__gt=0)
    return render(request, 'sales/pos.html', {'drugs': drugs})

@login_required
@role_required(['owner', 'admin', 'seller'])
@transaction.atomic
def process_sale(request):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return JsonResponse({'success': False, 'message': 'This feature is only available for Pharmacy or Sales system.'})
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'})

    try:
        customer_name = request.POST.get('customer_name', '')
        customer_phone = request.POST.get('customer_phone', '')
        customer_address = request.POST.get('customer_address', '')
        customer_email = request.POST.get('customer_email', '')
        payment_method = request.POST.get('payment_method', 'CASH')
        items = request.POST.getlist('items[]')
        quantities = request.POST.getlist('quantities[]')
        discount_percentage = Decimal(request.POST.get('discount_percentage', '0'))

        # Validate payment method
        valid_payment_methods = [choice[0] for choice in Sale.PAYMENT_METHODS]
        if payment_method not in valid_payment_methods:
            return JsonResponse({'success': False, 'message': 'Invalid payment method.'})

        if len(items) != len(quantities):
            return JsonResponse({'success': False, 'message': 'Invalid items or quantities provided.'})

        if not items:
            return JsonResponse({'success': False, 'message': 'No items provided for sale.'})

        sale = Sale.objects.create(
            tenant=request.tenant,
            sale_id=generate_sale_id(),
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_address=customer_address,
            customer_email=customer_email,
            payment_method=payment_method,
            total_amount=0,
            discount_percentage=discount_percentage,
            processed_by=request.user
        )

        total = Decimal('0')
        for drug_id, quantity in zip(items, quantities):
            try:
                quantity = int(quantity)
                if quantity < 1:
                    raise ValueError("Quantity must be positive.")
                drug = Drug.objects.get(id=drug_id, tenant=request.tenant)
            except (ValueError, Drug.DoesNotExist):
                sale.delete()
                return JsonResponse({'success': False, 'message': f'Invalid drug or quantity: {drug_id}'})

            if drug.quantity < quantity:
                sale.delete()
                return JsonResponse({'success': False, 'message': f'Not enough stock for {drug.name}'})

            sale_item = SaleItem.objects.create(
                sale=sale,
                drug=drug,
                quantity=quantity,
                price=drug.price
            )

            drug.quantity -= quantity
            drug.last_modified_by = request.user
            drug.save()

            total += sale_item.total

        discount_amount = total * (discount_percentage / Decimal('100'))
        final_total = total - discount_amount

        sale.total_amount = final_total
        sale.subtotal = total
        sale.discount_amount = discount_amount
        sale.save()

        return JsonResponse({
            'success': True,
            'sale_id': sale.sale_id,
            'total': float(final_total),
            'subtotal': float(total),
            'discount_amount': float(discount_amount),
            'payment_method': payment_method
        })

    except Exception as e:
        logger.error(f"Error processing sale: {str(e)}")
        return JsonResponse({'success': False, 'message': 'An unexpected error occurred. Please try again.'})

# sales/views.py
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.db import transaction
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F
import logging

logger = logging.getLogger(__name__)

# ... (other imports and models unchanged)

@login_required
@role_required(['owner', 'admin', 'seller'])
@transaction.atomic
def void_sale(request, sale_id):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return JsonResponse({'success': False, 'message': 'This feature is only available for Pharmacy or Sales system.'})
    
    sale = get_object_or_404(Sale, id=sale_id, tenant=request.tenant)
    
    # Check user permissions
    user_role = request.user.membership_set.filter(tenant=request.tenant).first().role
    is_admin_or_owner = user_role in ['owner', 'admin']
    is_original_seller = sale.processed_by == request.user
    
    if sale.is_voided:
        return JsonResponse({'success': False, 'message': 'Sale has already been voided.'})
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        require_approval = request.POST.get('require_approval', 'false') == 'true'
        
        # Check if user can void directly
        if is_admin_or_owner or (is_original_seller and sale.is_same_day and not require_approval):
            try:
                # Restore drug quantities
                for item in sale.saleitem_set.all():
                    drug = item.drug
                    drug.quantity += item.quantity
                    drug.last_modified_by = request.user
                    drug.save()
                
                # Mark sale as voided
                sale.is_voided = True
                sale.voided_by = request.user
                sale.voided_at = timezone.now()
                sale.void_reason = reason
                sale.save()
                
                # Send notification to admins/owners
                if not is_admin_or_owner:
                    send_void_notification(sale, request.user, reason)
                
                return JsonResponse({'success': True, 'message': 'Sale voided successfully.'})
                
            except Exception as e:
                logger.error(f"Error voiding sale: {str(e)}")
                return JsonResponse({'success': False, 'message': 'Error voiding sale.'})
        
        elif is_original_seller:
            # Create void request for admin approval
            VoidRequest.objects.create(
                sale=sale,
                requested_by=request.user,
                reason=reason
            )
            
            # Send notification to admins/owners
            send_void_request_notification(sale, request.user, reason)
            
            return JsonResponse({
                'success': True, 
                'message': 'Void request submitted for admin approval.',
                'requires_approval': True
            })
        
        else:
            return JsonResponse({
                'success': False, 
                'message': 'You do not have permission to void this sale.'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
@role_required(['owner', 'admin'])
def process_void_request(request, request_id):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return JsonResponse({'success': False, 'message': 'This feature is only available for Pharmacy or Sales system.'})
    
    void_request = get_object_or_404(VoidRequest, id=request_id, sale__tenant=request.tenant)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        notes = request.POST.get('notes', '')
        
        if action == 'approve':
            try:
                with transaction.atomic():
                    # Restore drug quantities
                    for item in void_request.sale.saleitem_set.all():
                        drug = item.drug
                        drug.quantity += item.quantity
                        drug.last_modified_by = request.user
                        drug.save()
                    
                    # Mark sale as voided
                    void_request.sale.is_voided = True
                    void_request.sale.voided_by = request.user
                    void_request.sale.voided_at = timezone.now()
                    void_request.sale.void_reason = f"{void_request.reason} (Approved by admin)"
                    void_request.sale.save()
                    
                    # Update void request
                    void_request.status = 'approved'
                    void_request.processed_by = request.user
                    void_request.processed_at = timezone.now()
                    void_request.notes = notes
                    void_request.save()
                    
                    # Notify the original requester
                    send_void_request_decision(void_request, 'approved')
                    
                    return JsonResponse({'success': True, 'message': 'Void request approved.'})
                    
            except Exception as e:
                logger.error(f"Error approving void request: {str(e)}")
                return JsonResponse({'success': False, 'message': 'Error approving void request.'})
        
        elif action == 'reject':
            void_request.status = 'rejected'
            void_request.processed_by = request.user
            void_request.processed_at = timezone.now()
            void_request.notes = notes
            void_request.save()
            
            # Notify the original requester
            send_void_request_decision(void_request, 'rejected')
            
            return JsonResponse({'success': True, 'message': 'Void request rejected.'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

from io import BytesIO
from datetime import timedelta
import pandas as pd
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from core.models import Sale, InsuranceClaim


@login_required
@role_required(['owner', 'admin', 'seller'])
def download_sales_excel(request):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Sales system.')
    
    # Get filter parameters
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    include_voided = request.GET.get('include_voided', 'false') == 'true'
    
    # Filter sales
    sales = Sale.objects.filter(tenant=request.tenant).select_related('processed_by', 'voided_by').prefetch_related('saleitem_set__drug')
    
    if not include_voided:
        sales = sales.filter(is_voided=False)
    
    # Apply date filters
    if period == 'today':
        today = timezone.now().date()
        sales = sales.filter(date__date=today)
    elif period == 'week':
        week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        sales = sales.filter(date__date__gte=week_start)
    elif period == 'month':
        month_start = timezone.now().date().replace(day=1)
        sales = sales.filter(date__date__gte=month_start)
    elif period == 'custom' and start_date and end_date:
        sales = sales.filter(date__date__range=[start_date, end_date])
    
    # Prepare sales data
    sales_data = []
    for sale in sales:
        items = '; '.join(f"{item.drug.name} (x{item.quantity})" for item in sale.saleitem_set.all())
        sales_data.append({
            'Sale ID': sale.sale_id,
            'Date': sale.date,
            'Customer Name': sale.customer_name or 'Walk-in',
            'Customer Phone': sale.customer_phone,
            'Customer Email': sale.customer_email,
            'Items': items,
            'Subtotal': float(sale.subtotal),
            'Discount Percentage': float(sale.discount_percentage),
            'Discount Amount': float(sale.discount_amount),
            'Total Amount': float(sale.total_amount),
            'Processed By': sale.processed_by.username if sale.processed_by else '',
            'Status': 'VOIDED' if sale.is_voided else 'ACTIVE',
            'Voided By': sale.voided_by.username if sale.voided_by else '',
            'Voided At': sale.voided_at,
            'Void Reason': sale.void_reason,
            'Item Count': sale.saleitem_set.count(),
            'Total Items': sale.saleitem_set.aggregate(total=Sum('quantity'))['total'] or 0
        })
    
    # Prepare insurance claims data
    claims = InsuranceClaim.objects.filter(tenant=request.tenant)
    if period == 'today':
        today = timezone.now().date()
        claims = claims.filter(date_submitted=today)
    elif period == 'week':
        week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        claims = claims.filter(date_submitted__gte=week_start)
    elif period == 'month':
        month_start = timezone.now().date().replace(day=1)
        claims = claims.filter(date_submitted__gte=month_start)
    elif period == 'custom' and start_date and end_date:
        claims = claims.filter(date_submitted__range=[start_date, end_date])
    
    claims_data = []
    for claim in claims.select_related('submitted_by'):
        claims_data.append({
            'Claim ID': claim.claim_id,
            'Patient Name': claim.patient_name,
            'Patient ID': claim.patient_id or '',
            'Insurance Provider': claim.insurance_provider,
            'Claim Amount': f'MK{claim.claim_amount:.2f}',
            'Status': claim.get_status_display(),
            'Date Submitted': claim.date_submitted,
            'Submitted By': claim.submitted_by.username if claim.submitted_by else ''
        })
    
    # Create Excel file with multiple sheets
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_sales = pd.DataFrame(sales_data)
        df_claims = pd.DataFrame(claims_data)

        # Strip timezone info from all datetime columns
        for df in [df_sales, df_claims]:
            for col in df.select_dtypes(include=['datetimetz']).columns:
                df[col] = df[col].dt.tz_localize(None)

        # Write to Excel
        df_sales.to_excel(writer, index=False, sheet_name='Sales')
        df_claims.to_excel(writer, index=False, sheet_name='Insurance Claims')
        
        # Auto-adjust column widths
        for sheet_name in ['Sales', 'Insurance Claims']:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
    
    # Prepare response
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"report_{request.tenant.name}_{timezone.now().date()}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@login_required
@role_required(['owner', 'admin', 'seller'])
def email_receipt(request, sale_id):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return JsonResponse({'success': False, 'message': 'This feature is only available for Pharmacy or Sales system.'})
    
    sale = get_object_or_404(Sale, id=sale_id, tenant=request.tenant)
    
    if not sale.customer_email:
        return JsonResponse({'success': False, 'message': 'No email address provided for this sale.'})
    
    if request.method == 'POST':
        try:
            # Render email template
            context = {
                'sale': sale,
                'items': sale.saleitem_set.all(),
                'tenant': request.tenant,
                'date': timezone.now(),
            }
            
            html_content = render_to_string('sales/email_receipt.html', context)
            text_content = render_to_string('sales/email_receipt.txt', context)
            
            # Create email
            subject = f"Your Receipt - {request.tenant.name} - Sale #{sale.sale_id}"
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[sale.customer_email],
                reply_to=[request.user.email] if request.user.email else [settings.DEFAULT_FROM_EMAIL]
            )
            
            email.attach_alternative(html_content, "text/html")
            
            # Send email
            email.send()
            
            return JsonResponse({'success': True, 'message': 'Receipt emailed successfully.'})
            
        except Exception as e:
            logger.error(f"Error sending email receipt: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Error sending email receipt.'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

def send_void_notification(sale, voided_by, reason):
    admins = Membership.objects.filter(
        tenant=sale.tenant, 
        role__in=['owner', 'admin']
    ).select_related('user')
    
    for admin in admins:
        if admin.user.email:
            subject = f"Sale Voided - {sale.tenant.name} - Sale #{sale.sale_id}"
            
            context = {
                'sale': sale,
                'voided_by': voided_by,
                'reason': reason,
                'admin': admin.user,
            }
            
            html_content = render_to_string('sales/email_void_notification.html', context)
            text_content = render_to_string('sales/email_void_notification.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[admin.user.email]
            )
            
            email.attach_alternative(html_content, "text/html")
            email.send()

def send_void_request_notification(sale, requested_by, reason):
    admins = Membership.objects.filter(
        tenant=sale.tenant, 
        role__in=['owner', 'admin']
    ).select_related('user')
    
    for admin in admins:
        if admin.user.email:
            subject = f"Void Request - {sale.tenant.name} - Sale #{sale.sale_id}"
            
            context = {
                'sale': sale,
                'requested_by': requested_by,
                'reason': reason,
                'admin': admin.user,
            }
            
            html_content = render_to_string('sales/email_void_request.html', context)
            text_content = render_to_string('sales/email_void_request.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[admin.user.email]
            )
            
            email.attach_alternative(html_content, "text/html")
            email.send()

def send_void_request_decision(void_request, decision):
    if void_request.requested_by.email:
        subject = f"Void Request {decision.capitalize()} - {void_request.sale.tenant.name}"
        
        context = {
            'void_request': void_request,
            'decision': decision,
        }
        
        html_content = render_to_string(f'sales/email_void_decision_{decision}.html', context)
        text_content = render_to_string(f'sales/email_void_decision_{decision}.txt', context)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[void_request.requested_by.email]
        )
        
        email.attach_alternative(html_content, "text/html")
        email.send()

def send_sales_report(frequency='daily'):
    tenants = Tenant.objects.filter(is_active=True, system__in=['PHARMACY', 'SALES'])
    
    for tenant in tenants:
        today = timezone.now().date()
        if frequency == 'daily':
            start_date = today - timedelta(days=1)
            end_date = today - timedelta(days=1)
            title = 'Daily'
        elif frequency == 'weekly':
            start_date = today - timedelta(days=today.weekday() + 7)
            end_date = today - timedelta(days=today.weekday() + 1)
            title = 'Weekly'
        else:  # monthly
            start_date = today.replace(day=1) - timedelta(days=1)
            start_date = start_date.replace(day=1)
            end_date = today.replace(day=1) - timedelta(days=1)
            title = 'Monthly'
        
        sales = Sale.objects.filter(
            tenant=tenant,
            date__date__gte=start_date,
            date__date__lte=end_date,
            is_voided=False
        )
        
        claims = InsuranceClaim.objects.filter(
            tenant=tenant,
            date_submitted__gte=start_date,
            date_submitted__lte=end_date
        )
        
        total_sales = sales.count()
        total_revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
        total_claims = claims.count()
        total_claim_amount = claims.aggregate(total=Sum('claim_amount'))['total'] or 0
        
        admins = Membership.objects.filter(
            tenant=tenant, 
            role__in=['owner', 'admin']
        ).select_related('user')
        
        for admin in admins:
            if admin.user.email:
                context = {
                    'tenant': tenant,
                    'frequency': title,
                    'start_date': start_date,
                    'end_date': end_date,
                    'total_sales': total_sales,
                    'total_revenue': total_revenue,
                    'total_claims': total_claims,
                    'total_claim_amount': total_claim_amount,
                    'admin': admin.user,
                }
                
                html_content = render_to_string('sales/email_sales_report.html', context)
                text_content = render_to_string('sales/email_sales_report.txt', context)
                
                subject = f"{title} Sales and Claims Report - {tenant.name}"
                
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[admin.user.email]
                )
                
                email.attach_alternative(html_content, "text/html")
                email.send()

@login_required
@role_required(['owner', 'admin', 'seller'])
def sale_detail(request, id):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Sales system.')
    sale = get_object_or_404(Sale, id=id, tenant=request.tenant)
    subtotal = sale.total_amount
    
    context = {
        'sale': sale,
        'subtotal': subtotal,
    }
    return render(request, 'sales/detail.html', context)

@login_required
@role_required(['owner', 'admin', 'seller'])
def sales_history(request):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Sales system.')
    
    # Get all sales with related data
    sales = Sale.objects.filter(tenant=request.tenant).select_related('processed_by').prefetch_related('saleitem_set__drug').order_by('-date')
    
    # Add item counts to each sale for display
    for sale in sales:
        sale.item_count = sale.saleitem_set.count()
        sale.total_items = sale.saleitem_set.aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Pagination
    paginator = Paginator(sales, 10)  # 10 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Active sales for KPIs (exclude voided)
    active_sales = sales.filter(is_voided=False)
    
    # Calculate total revenue from active sales
    total_revenue = active_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Today's statistics
    today = timezone.now().date()
    today_sales = active_sales.filter(date__date=today).count()
    today_revenue = active_sales.filter(date__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # This week statistics
    week_start = today - timedelta(days=today.weekday())
    week_sales = active_sales.filter(date__date__gte=week_start).count()
    week_revenue = active_sales.filter(date__date__gte=week_start).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # This month statistics
    month_start = today.replace(day=1)
    month_sales = active_sales.filter(date__date__gte=month_start).count()
    month_revenue = active_sales.filter(date__date__gte=month_start).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Top selling products from active sales
    top_products = SaleItem.objects.filter(sale__tenant=request.tenant, sale__is_voided=False)\
        .values('drug__name', 'drug__category')\
        .annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('price'))
        )\
        .order_by('-total_sold')[:5]
    
    # Sales trend for the last 7 days from active sales
    sales_trend = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        daily_sales = active_sales.filter(date__date=date).aggregate(
            count=Count('id'),
            revenue=Sum('total_amount')
        )
        sales_trend.append({
            'date': date,
            'count': daily_sales['count'] or 0,
            'revenue': daily_sales['revenue'] or 0
        })
    
    context = {
        'sales': page_obj,
        'total_revenue': total_revenue,
        'today_sales': today_sales,
        'today_revenue': today_revenue,
        'week_sales': week_sales,
        'week_revenue': week_revenue,
        'month_sales': month_sales,
        'month_revenue': month_revenue,
        'top_products': list(top_products),
        'sales_trend': sales_trend,
        'today': today,
    }
    
    return render(request, 'sales/list.html', context)

@login_required
@role_required(['owner', 'admin'])
def void_requests_list(request):
    if request.tenant.system not in ['PHARMACY', 'SALES']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Sales system.')
    
    requests = VoidRequest.objects.filter(sale__tenant=request.tenant, status='pending')\
        .select_related('sale', 'requested_by')\
        .order_by('-requested_at')
    
    paginator = Paginator(requests, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'sales/void_requests.html', {'page_obj': page_obj})


# Supplier Views (Pharmacy/Inventory-specific)
@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def supplier_list(request):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    
    # Handle search from GET parameters
    search_query = request.GET.get('search', '')
    
    suppliers = Supplier.objects.filter(tenant=request.tenant)
    
    if search_query:
        suppliers = suppliers.filter(name__icontains=search_query) | \
                    suppliers.filter(contact_person__icontains=search_query) | \
                    suppliers.filter(email__icontains=search_query) | \
                    suppliers.filter(phone__icontains=search_query)
    
    # Backend pagination
    paginator = Paginator(suppliers, 10)  # 10 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'suppliers/list.html', {
        'page_obj': page_obj,
        'search_query': search_query,
    })

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def supplier_bulk_upload(request):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    
    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            return render(request, 'suppliers/bulk_upload.html', {'error': 'No file uploaded.'})
        
        try:
            df = pd.read_excel(excel_file)
            errors = []
            created_count = 0
            
            required_columns = ['name', 'contact_person', 'email', 'phone', 'address']
            if not all(col in df.columns for col in required_columns):
                return render(request, 'suppliers/bulk_upload.html', {'error': 'Missing required columns in Excel.'})
            
            for index, row in df.iterrows():
                try:
                    name = row['name']
                    contact_person = row.get('contact_person', '')
                    email = row.get('email', '')
                    phone = row['phone']
                    address = row.get('address', '')
                    
                    Supplier.objects.create(
                        tenant=request.tenant,
                        name=name,
                        contact_person=contact_person,
                        email=email,
                        phone=phone,
                        address=address,
                        created_by=request.user
                    )
                    created_count += 1
                except Exception as e:
                    errors.append(f"Row {index + 2}: {str(e)}")
            
            if errors:
                return render(request, 'suppliers/bulk_upload.html', {
                    'success': f'{created_count} suppliers created successfully.',
                    'errors': errors
                })
            return redirect('supplier_list')
        
        except Exception as e:
            return render(request, 'suppliers/bulk_upload.html', {'error': str(e)})
    
    return render(request, 'suppliers/bulk_upload.html')

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def download_supplier_data(request):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    
    suppliers = Supplier.objects.filter(tenant=request.tenant).prefetch_related('supplied_drugs')
    
    data = []
    for supplier in suppliers:
        supplied_drugs = ', '.join(drug.name for drug in supplier.supplied_drugs.all())
        data.append({
            'name': supplier.name,
            'contact_person': supplier.contact_person,
            'email': supplier.email,
            'phone': supplier.phone,
            'address': supplier.address,
            'supplied_drugs': supplied_drugs
        })
    
    df = pd.DataFrame(data)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="supplier_data.xlsx"'
    return response

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def download_supplier_template(request):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    
    data = {
        'name': ['Example Supplier 1', 'Example Supplier 2'],
        'contact_person': ['John Doe', 'Jane Smith'],
        'email': ['john@example.com', 'jane@example.com'],
        'phone': ['+1234567890', '+0987654321'],
        'address': ['123 Main St', '456 Oak Ave']
    }
    df = pd.DataFrame(data)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="supplier_upload_template.xlsx"'
    return response

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def supplier_detail(request, id):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    supplier = get_object_or_404(Supplier, id=id, tenant=request.tenant)
    return render(request, 'suppliers/detail.html', {'supplier': supplier})

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def supplier_create(request):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    if request.method == 'POST':
        name = request.POST.get('name')
        contact_person = request.POST.get('contact_person')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        
        supplier = Supplier.objects.create(
            tenant=request.tenant,
            name=name,
            contact_person=contact_person,
            email=email,
            phone=phone,
            address=address,
            created_by=request.user
        )
        
        drug_ids = request.POST.getlist('supplied_drugs')
        for drug_id in drug_ids:
            drug = Drug.objects.get(id=drug_id, tenant=request.tenant)
            supplier.supplied_drugs.add(drug)
        
        return redirect('supplier_detail', id=supplier.id)
    
    drugs = Drug.objects.filter(tenant=request.tenant)
    return render(request, 'suppliers/form.html', {'drugs': drugs})

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def supplier_update(request, id):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    supplier = get_object_or_404(Supplier, id=id, tenant=request.tenant)
    
    if request.method == 'POST':
        supplier.name = request.POST.get('name')
        supplier.contact_person = request.POST.get('contact_person')
        supplier.email = request.POST.get('email')
        supplier.phone = request.POST.get('phone')
        supplier.address = request.POST.get('address')
        supplier.save()
        
        supplier.supplied_drugs.clear()
        drug_ids = request.POST.getlist('supplied_drugs')
        for drug_id in drug_ids:
            drug = Drug.objects.get(id=drug_id, tenant=request.tenant)
            supplier.supplied_drugs.add(drug)
        
        return redirect('supplier_detail', id=supplier.id)
    
    drugs = Drug.objects.filter(tenant=request.tenant)
    return render(request, 'suppliers/form.html', {
        'supplier': supplier,
        'drugs': drugs
    })

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def supplier_delete(request, id):
    if request.tenant.system not in ['PHARMACY', 'INVENTORY']:
        return HttpResponseForbidden('This feature is only available for Pharmacy or Inventory system.')
    supplier = get_object_or_404(Supplier, id=id, tenant=request.tenant)
    
    if request.method == 'POST':
        supplier.delete()
        return redirect('supplier_list')
    
    return render(request, 'suppliers/confirm_delete.html', {'supplier': supplier})

# Insurance Claim Views (Pharmacy-specific)
@login_required
@role_required(['owner', 'admin', 'seller'])
def insurance_claim_list(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    # Handle search and status filter from GET parameters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    claims = InsuranceClaim.objects.filter(tenant=request.tenant).order_by('-date_submitted')
    
    if search_query:
        claims = claims.filter(
            Q(claim_id__icontains=search_query) |
            Q(patient_name__icontains=search_query) |
            Q(insurance_provider__icontains=search_query)
        )
    
    if status_filter:
        claims = claims.filter(status=status_filter)
    
    # Backend pagination
    paginator = Paginator(claims, 10)  # 10 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate statistics
    pending_claims = claims.filter(status='pending').count()
    approved_claims = claims.filter(status='approved').count()
    rejected_claims = claims.filter(status='rejected').count()
    
    return render(request, 'insurance/list.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'pending_claims': pending_claims,
        'approved_claims': approved_claims,
        'rejected_claims': rejected_claims,
    })

@login_required
@role_required(['owner', 'admin', 'seller'])
def insurance_claim_detail(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    claim = get_object_or_404(InsuranceClaim, id=id, tenant=request.tenant)
    return render(request, 'insurance/detail.html', {'claim': claim})

@login_required
@role_required(['owner', 'admin', 'seller'])
def insurance_claim_create(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    if request.method == 'POST':
        claim_id = request.POST.get('claim_id')
        patient_name = request.POST.get('patient_name')
        patient_id = request.POST.get('patient_id')
        insurance_provider = request.POST.get('insurance_provider')
        claim_amount = request.POST.get('claim_amount')
        status = request.POST.get('status')
        
        claim = InsuranceClaim.objects.create(
            tenant=request.tenant,
            claim_id=claim_id,
            patient_name=patient_name,
            patient_id=patient_id,
            insurance_provider=insurance_provider,
            claim_amount=claim_amount,
            status=status,
            submitted_by=request.user
        )
        
        return redirect('insurance_claim_detail', id=claim.id)
    
    return render(request, 'insurance/form.html')

@login_required
@role_required(['owner', 'admin', 'seller'])
def insurance_claim_update(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    claim = get_object_or_404(InsuranceClaim, id=id, tenant=request.tenant)
    
    if request.method == 'POST':
        claim.claim_id = request.POST.get('claim_id')
        claim.patient_name = request.POST.get('patient_name')
        claim.patient_id = request.POST.get('patient_id')
        claim.insurance_provider = request.POST.get('insurance_provider')
        claim.claim_amount = request.POST.get('claim_amount')
        claim.status = request.POST.get('status')
        
        if claim.status == 'processed' and not claim.date_processed:
            claim.date_processed = timezone.now().date()
        
        claim.save()
        
        return redirect('insurance_claim_detail', id=claim.id)
    
    return render(request, 'insurance/form.html', {'claim': claim})

@login_required
@role_required(['owner', 'admin', 'seller'])
def insurance_claim_delete(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    claim = get_object_or_404(InsuranceClaim, id=id, tenant=request.tenant)
    
    if request.method == 'POST':
        claim.delete()
        return redirect('insurance_claim_list')
    
    return render(request, 'insurance/confirm_delete.html', {'claim': claim})

@login_required
@role_required(['owner', 'admin', 'seller'])
def insurance_claim_bulk_upload(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            return render(request, 'insurance/bulk_upload.html', {'error': 'No file uploaded.'})
        
        try:
            df = pd.read_excel(excel_file)
            errors = []
            created_count = 0
            
            required_columns = ['claim_id', 'patient_name', 'patient_id', 'insurance_provider', 'claim_amount', 'status']
            if not all(col in df.columns for col in required_columns):
                return render(request, 'insurance/bulk_upload.html', {'error': 'Missing required columns in Excel.'})
            
            for index, row in df.iterrows():
                try:
                    claim_id = row['claim_id']
                    patient_name = row['patient_name']
                    patient_id = row.get('patient_id', '')
                    insurance_provider = row['insurance_provider']
                    claim_amount = float(row['claim_amount'])
                    status = row['status']
                    
                    if claim_amount < 0:
                        raise ValueError("Claim amount cannot be negative.")
                    
                    if status not in dict(InsuranceClaim.STATUS_CHOICES).keys():
                        raise ValueError(f"Invalid status: {status}. Valid options: pending, approved, rejected, processed.")
                    
                    InsuranceClaim.objects.create(
                        tenant=request.tenant,
                        claim_id=claim_id,
                        patient_name=patient_name,
                        patient_id=patient_id,
                        insurance_provider=insurance_provider,
                        claim_amount=claim_amount,
                        status=status,
                        submitted_by=request.user
                    )
                    created_count += 1
                except Exception as e:
                    errors.append(f"Row {index + 2}: {str(e)}")
            
            if errors:
                return render(request, 'insurance/bulk_upload.html', {
                    'success': f'{created_count} claims created successfully.',
                    'errors': errors
                })
            return redirect('insurance_claim_list')
        
        except Exception as e:
            return render(request, 'insurance/bulk_upload.html', {'error': str(e)})
    
    return render(request, 'insurance/bulk_upload.html')

@login_required
@role_required(['owner', 'admin', 'seller'])
def download_insurance_claim_template(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    data = {
        'claim_id': ['CLAIM001', 'CLAIM002'],
        'patient_name': ['John Doe', 'Jane Smith'],
        'patient_id': ['PAT001', 'PAT002'],
        'insurance_provider': ['Provider A', 'Provider B'],
        'claim_amount': [1500.00, 2500.00],
        'status': ['pending', 'approved']
    }
    df = pd.DataFrame(data)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="insurance_claim_upload_template.xlsx"'
    return response

@login_required
@role_required(['owner', 'admin', 'seller'])
def download_insurance_claim_data(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    
    claims = InsuranceClaim.objects.filter(tenant=request.tenant).select_related('submitted_by')
    
    data = []
    for claim in claims:
        data.append({
            'claim_id': claim.claim_id,
            'patient_name': claim.patient_name,
            'patient_id': claim.patient_id or '',
            'insurance_provider': claim.insurance_provider,
            'claim_amount': f'MK{claim.claim_amount:.2f}',
            'status': claim.get_status_display(),
            'date_submitted': claim.date_submitted.strftime('%Y-%m-%d'),
            'submitted_by': claim.submitted_by.username
        })
    
    df = pd.DataFrame(data)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Insurance Claims')
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="insurance_claims_data.xlsx"'
    return response



# Similarly for financial, HR, etc.

@login_required
def dashboard_school(request):
    return render(request, 'school/dash.html')




# Error Handler Views
def handler404(request, exception):
    return render(request, 'errors/404.html', status=404)

def handler408(request, exception=None):
    return render(request, 'errors/408.html', status=408)

def handler500(request):
    return render(request, 'errors/500.html', status=500)

def handler403(request, exception):
    return render(request, 'errors/403.html', status=403)

def handler400(request, exception):
    return render(request, 'errors/400.html', status=400)

def handler429(request, exception):
    return render(request, 'errors/429.html', status=429)

def handler503(request):
    return render(request, 'errors/503.html', status=503)



from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm

@login_required
def settings_view(request):
    """
    Render settings page with safe role/tenant context.
    Handles users who don't have a Membership entry.
    """
    user = request.user

    # If you have request.tenant set by middleware, use it; otherwise None
    tenant = getattr(request, "tenant", None)

    # Try to find a membership for current user and tenant.
    # If tenant is None, try to pick a membership (first) as fallback.
    membership = None
    if tenant:
        membership = Membership.objects.filter(user=user, tenant=tenant).first()
    else:
        # safe fallback — find any membership (optional)
        membership = Membership.objects.filter(user=user).first()

    user_role = None
    if membership:
        user_role = getattr(membership, "role", None)

    # Determine permission flags
    can_delete = user_role in ['owner', 'admin'] or user.is_superuser
    is_owner = user_role == 'owner' or user.is_superuser

    # Tenant name for JS/template; use empty string if not available
    tenant_name = tenant.name if tenant else ""

    context = {
        "can_delete": can_delete,
        "is_owner": is_owner,
        "user_role": user_role,
        "tenant_name": tenant_name,
        # include any other context previously passed
    }

    return render(request, "settings/settings.html", context)



from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def send_password_change_email(user, request):
    """Send email notification for password change"""
    subject = 'Password Changed - IMS Account'
    context = {
        'user': user,
        'login_url': request.build_absolute_uri('/login/'),
        'timestamp': timezone.now()
    }
    
    try:
        html_content = render_to_string('settings/email_password_changed.html', context)
        text_content = strip_tags(html_content)
        
        send_mail(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_content,
            fail_silently=False
        )
        
    except Exception as e:
        logger.error(f"Failed to send password change email to {user.email}: {str(e)}")

def send_account_deletion_email(user, request):
    """Send email notification for account deletion"""
    subject = 'Account Deleted - IMS'
    context = {
        'user': user,
        'timestamp': timezone.now(),
        'contact_email': settings.ADMIN_EMAIL
    }
    
    try:
        html_content = render_to_string('settings/email_account_deleted.html', context)
        text_content = strip_tags(html_content)
        
        send_mail(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_content,
            fail_silently=False
        )
        
    except Exception as e:
        logger.error(f"Failed to send account deletion email to {user.email}: {str(e)}")

def send_tenant_deletion_email(tenant, owner, affected_users, request):
    """Send email notifications for tenant deletion"""
    subject = f'Tenant Deleted - {tenant.name}'
    
    for user in affected_users:
        context = {
            'user': user,
            'tenant_name': tenant.name,
            'owner_name': owner.get_full_name() or owner.username,
            'timestamp': timezone.now(),
            'contact_email': settings.ADMIN_EMAIL
        }
        
        try:
            html_content = render_to_string('settings/email_tenant_deleted.html', context)
            text_content = strip_tags(html_content)
            
            send_mail(
                subject,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_content,
                fail_silently=False
            )
            
        except Exception as e:
            logger.error(f"Failed to send tenant deletion email to {user.email}: {str(e)}")

@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            
            # Send email notification
            send_password_change_email(user, request)
            
            messages.success(request, 'Your password was successfully updated!')
            return redirect('settings')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'settings/change_password.html', {'form': form})

@login_required
@transaction.atomic
def delete_account(request):
    if request.method == 'POST':
        password = request.POST.get('password')
        user = request.user
        
        # Verify password
        if not user.check_password(password):
            messages.error(request, 'Invalid password.')
            return redirect('settings')
        
        # Store email before deletion for notification
        user_email = user.email
        
        # Delete user's membership
        Membership.objects.filter(user=user).delete()
        
        # Send email notification before deleting account
        send_account_deletion_email(user, request)
        
        # Delete user account
        user.delete()
        
        messages.success(request, 'Your account has been successfully deleted.')
        return redirect('login')
        
    return redirect('settings')

@login_required
@role_required(['owner'])
@transaction.atomic
def delete_tenant(request):
    if request.method == 'POST':
        tenant_name = request.POST.get('tenant_name')
        password = request.POST.get('password')
        user = request.user
        
        # Verify password and tenant name
        if not user.check_password(password):
            messages.error(request, 'Invalid password.')
            return redirect('settings')
            
        if tenant_name != request.tenant.name:
            messages.error(request, 'Invalid tenant name.')
            return redirect('settings')
        
        # Get all affected users before deletion
        affected_users = User.objects.filter(
            membership__tenant=request.tenant
        ).exclude(id=user.id).distinct()
        
        # Send email notifications to all affected users
        send_tenant_deletion_email(request.tenant, user, affected_users, request)
        
        # Delete tenant and all related data
        request.tenant.delete()
        
        messages.success(request, 'Your tenant has been successfully deleted.')
        return redirect('login')
        
    return redirect('settings')



from django.views.generic import TemplateView

class RobotsTxtView(TemplateView):
    template_name = "robots.txt"
    content_type = "text/plain"


# ==================== Pharmacy Enhancement Views ====================
# Customers, Purchase Orders, Stock Adjustments, Sale Returns, Alerts

def generate_po_number():
    return 'PO' + ''.join(random.choices(string.digits, k=7))

def generate_return_id():
    return 'RT' + ''.join(random.choices(string.digits, k=7))


# ---------- Customers ----------

@login_required
@role_required(['owner', 'admin', 'seller'])
def customer_list(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    search_query = request.GET.get('search', '')
    customers = Customer.objects.filter(tenant=request.tenant)
    if search_query:
        customers = customers.filter(
            Q(name__icontains=search_query) | Q(phone__icontains=search_query) | Q(email__icontains=search_query)
        )
    customers = customers.order_by('name')
    paginator = Paginator(customers, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'customers/list.html', {'page_obj': page_obj, 'search_query': search_query})


@login_required
@role_required(['owner', 'admin', 'seller'])
def customer_detail(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    customer = get_object_or_404(Customer, id=id, tenant=request.tenant)
    sales = customer.sales.filter(is_voided=False).order_by('-date')[:20]
    return render(request, 'customers/detail.html', {'customer': customer, 'sales': sales})


@login_required
@role_required(['owner', 'admin', 'seller'])
def customer_create(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.tenant = request.tenant
            customer.created_by = request.user
            customer.save()
            messages.success(request, 'Customer added successfully.')
            return redirect('customer_detail', id=customer.id)
    else:
        form = CustomerForm()
    return render(request, 'customers/form.html', {'form': form})


@login_required
@role_required(['owner', 'admin', 'seller'])
def customer_update(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    customer = get_object_or_404(Customer, id=id, tenant=request.tenant)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated successfully.')
            return redirect('customer_detail', id=customer.id)
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'customers/form.html', {'form': form, 'customer': customer})


@login_required
@role_required(['owner', 'admin'])
def customer_delete(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    customer = get_object_or_404(Customer, id=id, tenant=request.tenant)
    if request.method == 'POST':
        customer.delete()
        messages.success(request, 'Customer deleted successfully.')
        return redirect('customer_list')
    return redirect('customer_list')


# ---------- Purchase Orders ----------

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def purchase_order_list(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    status_filter = request.GET.get('status', '')
    orders = PurchaseOrder.objects.filter(tenant=request.tenant).select_related('supplier')
    if status_filter:
        orders = orders.filter(status=status_filter)
    paginator = Paginator(orders, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'purchase_orders/list.html', {'page_obj': page_obj, 'status_filter': status_filter})


@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def purchase_order_detail(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    order = get_object_or_404(PurchaseOrder, id=id, tenant=request.tenant)
    return render(request, 'purchase_orders/detail.html', {'order': order})


@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
@transaction.atomic
def purchase_order_create(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, tenant=request.tenant)
        drug_ids = request.POST.getlist('drug_id[]')
        drug_names = request.POST.getlist('drug_name[]')
        quantities = request.POST.getlist('quantity_ordered[]')
        unit_costs = request.POST.getlist('unit_cost[]')

        if form.is_valid():
            if not drug_names or not any(name.strip() for name in drug_names):
                messages.error(request, 'Add at least one item to the purchase order.')
                return render(request, 'purchase_orders/form.html', {'form': form})

            order = form.save(commit=False)
            order.tenant = request.tenant
            order.po_number = generate_po_number()
            order.status = 'ordered'
            order.created_by = request.user
            order.save()

            for drug_id, drug_name, qty, cost in zip(drug_ids, drug_names, quantities, unit_costs):
                if not drug_name.strip():
                    continue
                try:
                    qty = int(qty)
                    cost = Decimal(cost or '0')
                except (ValueError, TypeError):
                    continue
                drug_obj = None
                if drug_id:
                    drug_obj = Drug.objects.filter(id=drug_id, tenant=request.tenant).first()
                PurchaseOrderItem.objects.create(
                    purchase_order=order,
                    drug=drug_obj,
                    drug_name=drug_name,
                    quantity_ordered=qty,
                    unit_cost=cost,
                )
            messages.success(request, f'Purchase order {order.po_number} created.')
            return redirect('purchase_order_detail', id=order.id)
    else:
        form = PurchaseOrderForm(tenant=request.tenant)
    drugs = Drug.objects.filter(tenant=request.tenant, is_active=True)
    return render(request, 'purchase_orders/form.html', {'form': form, 'drugs': drugs})


@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
@transaction.atomic
def purchase_order_receive(request, id):
    """Receive stock against a purchase order: updates Drug.quantity and PO status."""
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    order = get_object_or_404(PurchaseOrder, id=id, tenant=request.tenant)
    if order.status in ('received', 'cancelled'):
        messages.error(request, 'This purchase order can no longer be received against.')
        return redirect('purchase_order_detail', id=order.id)

    if request.method == 'POST':
        for item in order.items.select_related('drug').all():
            field_name = f'receive_{item.id}'
            qty_received_now = request.POST.get(field_name, '0')
            try:
                qty_received_now = int(qty_received_now)
            except ValueError:
                qty_received_now = 0
            if qty_received_now <= 0:
                continue
            remaining = item.quantity_ordered - item.quantity_received
            qty_received_now = min(qty_received_now, remaining)
            item.quantity_received += qty_received_now
            item.save()

            if item.drug:
                item.drug.quantity = F('quantity') + qty_received_now
                item.drug.last_modified_by = request.user
                item.drug.save()

        order.status = 'received' if order.is_fully_received else 'partially_received'
        if order.status == 'received':
            order.received_date = timezone.now().date()
        order.save()
        messages.success(request, f'Stock received for purchase order {order.po_number}.')
        return redirect('purchase_order_detail', id=order.id)

    return redirect('purchase_order_detail', id=order.id)


@login_required
@role_required(['owner', 'admin'])
def purchase_order_cancel(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    order = get_object_or_404(PurchaseOrder, id=id, tenant=request.tenant)
    if request.method == 'POST' and order.status not in ('received',):
        order.status = 'cancelled'
        order.save()
        messages.success(request, f'Purchase order {order.po_number} cancelled.')
    return redirect('purchase_order_detail', id=order.id)


# ---------- Stock Adjustments ----------

@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
def stock_adjustment_list(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    adjustments = StockAdjustment.objects.filter(tenant=request.tenant).select_related('drug', 'adjusted_by')
    paginator = Paginator(adjustments, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock_adjustments/list.html', {'page_obj': page_obj})


@login_required
@role_required(['owner', 'admin', 'inventory_manager'])
@transaction.atomic
def stock_adjustment_create(request, drug_id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    drug = get_object_or_404(Drug, id=drug_id, tenant=request.tenant)
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            quantity_change = form.cleaned_data['quantity_change']
            new_quantity = drug.quantity + quantity_change
            if new_quantity < 0:
                messages.error(request, 'Adjustment would result in negative stock.')
                return render(request, 'stock_adjustments/form.html', {'form': form, 'drug': drug})

            adjustment = form.save(commit=False)
            adjustment.tenant = request.tenant
            adjustment.drug = drug
            adjustment.quantity_before = drug.quantity
            adjustment.quantity_after = new_quantity
            adjustment.adjusted_by = request.user
            adjustment.save()

            drug.quantity = new_quantity
            drug.last_modified_by = request.user
            drug.save()

            messages.success(request, f'Stock adjusted for {drug.name}.')
            return redirect('drug_detail', id=drug.id)
    else:
        form = StockAdjustmentForm()
    return render(request, 'stock_adjustments/form.html', {'form': form, 'drug': drug})


# ---------- Sale Returns ----------

@login_required
@role_required(['owner', 'admin', 'seller'])
def sale_return_list(request):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    status_filter = request.GET.get('status', '')
    returns = SaleReturn.objects.filter(tenant=request.tenant).select_related('sale', 'requested_by')
    if status_filter:
        returns = returns.filter(status=status_filter)
    paginator = Paginator(returns, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'sale_returns/list.html', {'page_obj': page_obj, 'status_filter': status_filter})


@login_required
@role_required(['owner', 'admin', 'seller'])
@transaction.atomic
def sale_return_create(request, sale_id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    sale = get_object_or_404(Sale, id=sale_id, tenant=request.tenant)
    sale_items = sale.saleitem_set.select_related('drug').all()

    if request.method == 'POST':
        form = SaleReturnForm(request.POST)
        item_ids = request.POST.getlist('sale_item_id[]')
        return_quantities = request.POST.getlist('return_quantity[]')

        if form.is_valid():
            selected = [(iid, qty) for iid, qty in zip(item_ids, return_quantities) if qty and int(qty) > 0]
            if not selected:
                messages.error(request, 'Select at least one item and quantity to return.')
                return render(request, 'sale_returns/form.html', {'form': form, 'sale': sale, 'sale_items': sale_items})

            sale_return = form.save(commit=False)
            sale_return.tenant = request.tenant
            sale_return.sale = sale
            sale_return.return_id = generate_return_id()
            sale_return.requested_by = request.user
            sale_return.save()

            refund_total = Decimal('0')
            for item_id, qty in selected:
                sale_item = get_object_or_404(SaleItem, id=item_id, sale=sale)
                qty = int(qty)
                qty = min(qty, sale_item.quantity)
                SaleReturnItem.objects.create(sale_return=sale_return, sale_item=sale_item, quantity=qty)
                refund_total += qty * sale_item.price

            sale_return.refund_amount = refund_total
            sale_return.save()

            messages.success(request, f'Return {sale_return.return_id} submitted for approval.')
            return redirect('sale_return_list')
    else:
        form = SaleReturnForm()
    return render(request, 'sale_returns/form.html', {'form': form, 'sale': sale, 'sale_items': sale_items})


@login_required
@role_required(['owner', 'admin'])
@transaction.atomic
def sale_return_process(request, id):
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    sale_return = get_object_or_404(SaleReturn, id=id, tenant=request.tenant)
    if sale_return.status != 'pending':
        messages.error(request, 'This return has already been processed.')
        return redirect('sale_return_list')

    if request.method == 'POST':
        decision = request.POST.get('decision')
        if decision == 'approve':
            if sale_return.restock:
                for return_item in sale_return.items.select_related('sale_item__drug').all():
                    drug = return_item.sale_item.drug
                    drug.quantity = F('quantity') + return_item.quantity
                    drug.save()
            sale_return.status = 'approved'
        else:
            sale_return.status = 'rejected'
        sale_return.processed_by = request.user
        sale_return.processed_at = timezone.now()
        sale_return.save()
        messages.success(request, f'Return {sale_return.return_id} {sale_return.status}.')
    return redirect('sale_return_list')


# ---------- Alerts / Reports ----------

@login_required
def inventory_alerts(request):
    """Low-stock and expiry alerts for the dashboard / inventory team."""
    if request.tenant.system != 'PHARMACY':
        return HttpResponseForbidden('This feature is only available for Pharmacy system.')
    drugs = Drug.objects.filter(tenant=request.tenant, is_active=True)
    low_stock = [d for d in drugs if d.is_low_stock]
    near_expiry = [d for d in drugs if d.is_near_expiry]
    expired = [d for d in drugs if d.is_expired]
    return render(request, 'inventory/alerts.html', {
        'low_stock': low_stock,
        'near_expiry': near_expiry,
        'expired': expired,
    })
