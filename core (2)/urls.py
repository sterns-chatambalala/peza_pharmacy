# urls.py
from django.urls import path
from . import views
from .views import RobotsTxtView

# For password reset, add to urls.py
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("robots.txt", RobotsTxtView.as_view()),
    # landing 
    path('', views.landing_page, name='landing_page'),


    # Authentication
    path('register/', views.signup_view, name='register'),  # Changed from signup
    path('check-username/', views.check_username, name='check_username'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('verify/<int:user_id>/', views.verify_account, name='verify_account'),
    path('resend-otp/<int:user_id>/', views.resend_otp, name='resend_otp'),
    path('clear-otp-sent/<int:user_id>/', views.clear_otp_sent, name='clear_otp_sent'),

    path('validate-field/', views.validate_field, name='validate_field'),

    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<uidb64>/<token>/', views.reset_password, name='reset_password'),


    # path('password-reset/', auth_views.PasswordResetView.as_view(
    #     template_name='auth/password_reset.html',
    #     email_template_name='auth/password_reset_email.html',
    #     subject_template_name='auth/password_reset_subject.txt'
    # ), name='password_reset'),
    # path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
    #     template_name='auth/password_reset_done.html'
    # ), name='password_reset_done'),
    # path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
    #     template_name='auth/password_reset_confirm.html'
    # ), name='password_reset_confirm'),
    # path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
    #     template_name='auth/password_reset_complete.html'
    # ), name='password_reset_complete'),

    
    # Subscription
    path('subscription/details/', views.subscription_detail, name='subscription_detail'),
    path('subscription/expired/', views.subscription_expired, name='subscription_expired'),
    path('subscription/renew/', views.renew_subscription, name='renew_subscription'),
    path('subscription/payment-status/<str:transaction_id>/', views.check_subscription_payment_status, name='check_subscription_payment_status'),
    
    # User Management
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:membership_id>/edit/', views.user_update, name='user_update'),
    path('users/<int:membership_id>/delete/', views.user_delete, name='user_delete'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    # Global search and profile
    path('search/', views.global_search, name='global_search'),
    path('profile/', views.profile_view, name='profile'),
    path('notifications/json/', views.notifications_json, name='notifications_json'),
    
    # Pharmacy/Inventory
    path('drugs/', views.drug_list, name='drug_list'),
    path('drug/<int:id>/', views.drug_detail, name='drug_detail'),
    path('drug/new/', views.drug_create, name='drug_create'),
    path('drug/<int:id>/edit/', views.drug_update, name='drug_update'),
    path('drug/<int:id>/delete/', views.drug_delete, name='drug_delete'),
    path('drug/bulk-upload/', views.drug_bulk_upload, name='drug_bulk_upload'),
    path('drug/download-data/', views.download_drug_data, name='download_drug_data'),
    path('drug/download-sample-excel/', views.download_sample_template, name='download_sample_template'),
    path('barcode-lookup/', views.barcode_lookup, name='barcode_lookup'),
    
    # Prescriptions
    path('prescriptions/', views.prescription_list, name='prescription_list'),
    path('prescription/<int:id>/', views.prescription_detail, name='prescription_detail'),
    path('prescription/new/', views.prescription_create, name='prescription_create'),
    path('prescription/<int:id>/edit/', views.prescription_update, name='prescription_update'),
    path('prescriptions/download/', views.download_prescriptions_excel, name='download_prescriptions'),
    path('prescriptions/<int:prescription_id>/send-email/', views.send_prescription_email, name='send_prescription_email'),
    path('prescriptions/send-bulk-emails/', views.send_bulk_prescription_emails, name='send_bulk_prescription_emails'),
    
    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('supplier/<int:id>/', views.supplier_detail, name='supplier_detail'),
    path('supplier/new/', views.supplier_create, name='supplier_create'),
    path('supplier/<int:id>/edit/', views.supplier_update, name='supplier_update'),
    path('supplier/<int:id>/delete/', views.supplier_delete, name='supplier_delete'),
    path('suppliers/download/', views.download_supplier_data, name='download_supplier_data'),
    path('suppliers/bulk-upload/', views.supplier_bulk_upload, name='supplier_bulk_upload'),
    path('suppliers/download-sample-excel/', views.download_supplier_template, name='download_supplier_template'),
    
    # Sales
    path('sales/', views.sales_history, name='sales_history'),
    path('pos/', views.pos_system, name='pos_system'),
    path('process-sale/', views.process_sale, name='process_sale'),
    path('sale/<int:id>/', views.sale_detail, name='sale_detail'),
    path('sale/<int:sale_id>/void/', views.void_sale, name='void_sale'),
    path('sale/<int:sale_id>/email-receipt/', views.email_receipt, name='email_receipt'),
    path('sales/download/', views.download_sales_excel, name='download_sales_excel'),
    path('void-request/<int:request_id>/process/', views.process_void_request, name='process_void_request'),
    path('void-requests/', views.void_requests_list, name='void_requests_list'),
    
    # Insurance
    path('insurance-claims/', views.insurance_claim_list, name='insurance_claim_list'),
    path('insurance-claim/<int:id>/', views.insurance_claim_detail, name='insurance_claim_detail'),
    path('insurance-claim/new/', views.insurance_claim_create, name='insurance_claim_create'),
    path('insurance-claim/<int:id>/edit/', views.insurance_claim_update, name='insurance_claim_update'),
    path('insurance-claim/<int:id>/delete/', views.insurance_claim_delete, name='insurance_claim_delete'),
    path('insurance/bulk-upload/', views.insurance_claim_bulk_upload, name='insurance_claim_bulk_upload'),
    path('insurance/download-template/', views.download_insurance_claim_template, name='download_insurance_claim_template'),
    path('insurance/download-data/', views.download_insurance_claim_data, name='download_insurance_claim_data'),

    # Customers
    path('customers/', views.customer_list, name='customer_list'),
    path('customer/<int:id>/', views.customer_detail, name='customer_detail'),
    path('customer/new/', views.customer_create, name='customer_create'),
    path('customer/<int:id>/edit/', views.customer_update, name='customer_update'),
    path('customer/<int:id>/delete/', views.customer_delete, name='customer_delete'),

    # Purchase Orders
    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),
    path('purchase-order/new/', views.purchase_order_create, name='purchase_order_create'),
    path('purchase-order/<int:id>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-order/<int:id>/receive/', views.purchase_order_receive, name='purchase_order_receive'),
    path('purchase-order/<int:id>/cancel/', views.purchase_order_cancel, name='purchase_order_cancel'),

    # Stock Adjustments
    path('stock-adjustments/', views.stock_adjustment_list, name='stock_adjustment_list'),
    path('drug/<int:drug_id>/adjust-stock/', views.stock_adjustment_create, name='stock_adjustment_create'),

    # Sale Returns
    path('returns/', views.sale_return_list, name='sale_return_list'),
    path('sale/<int:sale_id>/return/', views.sale_return_create, name='sale_return_create'),
    path('return/<int:id>/process/', views.sale_return_process, name='sale_return_process'),

    # Alerts
    path('alerts/', views.inventory_alerts, name='inventory_alerts'),

    # Settings
    path('settings/', views.settings_view, name='settings'),
    path('settings/change-password/', views.change_password, name='change_password'),
    path('settings/delete-account/', views.delete_account, name='delete_account'),
    path('settings/delete-tenant/', views.delete_tenant, name='delete_tenant'),
    
    # Placeholder for other systems
    # path('school/dashboard/', views.school_dashboard, name='school_dashboard'),
    path('school/dashboard/', views.dashboard_school, name='dashboard_school'),
    # Add more URLs for other systems
]