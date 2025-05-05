# core/views.py
from django.views.generic import TemplateView

class PrivacyPolicyView(TemplateView):
    template_name = "core/privacy_policy.html"

class TermsServiceView(TemplateView):
    template_name = "core/terms_service.html"

class HelpCentreView(TemplateView):
    template_name = "core/help_centre.html"

class ContactUsView(TemplateView):
    template_name = "core/contact_us.html"

# Add a simple view for the Add Item landing if needed,
# or handle directly in template/JS later.
# For now, the '+' button links directly.