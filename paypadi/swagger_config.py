from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

# Swagger/OpenAPI configuration
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT Token',
        }
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR': True,
    'DEFAULT_MODEL_RENDERING': 'example',
}

# Schema view for API documentation
schema_view = get_schema_view(
    openapi.Info(
        title="Paypadi API",
        default_version='v1',
        description="API documentation for Paypadi",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@paypadi.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)
