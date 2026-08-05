# middleware.py (new file in the app or project)
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta
from .models import Membership, Tenant

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            membership = Membership.objects.filter(user=request.user).first()
            if membership:
                request.membership = membership
                request.tenant = membership.tenant
            else:
                request.tenant = None
        else:
            request.tenant = None

        response = self.get_response(request)
        return response

class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.tenant and not request.user.is_superuser:
            tenant = request.tenant
            today = timezone.now().date()
            if tenant.is_trial and today > tenant.subscription_start + timedelta(days=30):
                tenant.is_active = False
                tenant.is_trial = False
                tenant.save()
            elif not tenant.is_trial and tenant.subscription_end and today > tenant.subscription_end:
                tenant.is_active = False
                tenant.save()

            if not tenant.is_active and not request.path.startswith('/subscription/'):
                return redirect('subscription_expired')

        response = self.get_response(request)
        return response
    
