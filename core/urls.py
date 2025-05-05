# core/urls.py
from django.urls import path
from .views import (
    PrivacyPolicyView, TermsServiceView,
    HelpCentreView, ContactUsView
)

app_name = 'core'
urlpatterns = [
    path('privacy-policy/', PrivacyPolicyView.as_view(), name='privacy-policy'),
    path('terms-of-service/', TermsServiceView.as_view(), name='terms-service'),
    path('help-centre/', HelpCentreView.as_view(), name='help-centre'),
    path('contact-us/', ContactUsView.as_view(), name='contact-us'),
]