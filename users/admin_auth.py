from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def admin_jwt_login(request):
    if request.method == 'POST':
        username = request.data.get('username')
        password = request.data.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            # Generate JWT token
            refresh = RefreshToken.for_user(user)
            
            # Also log the user in for the admin interface
            login(request, user)
            
            return JsonResponse({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
            })
        return JsonResponse(
            {'error': 'Invalid credentials or not a staff user'}, 
            status=400
        )
