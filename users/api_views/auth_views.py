from rest_framework import status, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from drf_yasg.utils import swagger_auto_schema

from users.serializers import UserSerializer


class LoginRequestSerializer(serializers.Serializer):
    """Serializer for login request body."""
    phone_number = serializers.CharField(required=True, help_text="User's phone number")
    password = serializers.CharField(
        required=True, 
        style={'input_type': 'password'},
        help_text="User's password"
    )


class LoginResponseSerializer(serializers.Serializer):
    """Serializer for login response."""
    refresh = serializers.CharField(help_text="JWT refresh token")
    access = serializers.CharField(help_text="JWT access token")
    user = UserSerializer(help_text="Authenticated user details")


class UserLoginView(TokenObtainPairView):
    """
    Authenticate user and return JWT tokens.
    
    ## Request Body
    - `phone_number`: User's registered phone number
    - `password`: User's password
    
    ## Response
    - `refresh`: JWT refresh token
    - `access`: JWT access token
    - `user`: Serialized user data
    
    ### Example Request
    ```json
    {
        "phone_number": "+1234567890",
        "password": "securepassword123"
    }
    ```
    
    ### Example Response
    ```json
    {
        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "user": {
            "id": 1,
            "phone_number": "+1234567890",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "is_active": true,
            "is_verified": true,
            "is_driver": false,
            "date_joined": "2023-01-01T00:00:00Z"
        }
    }
    """
    permission_classes = [AllowAny]
    serializer_class = None  # We're not using the default serializer

    @swagger_auto_schema(
        operation_description="Authenticate user and get JWT tokens",
        request_body=LoginRequestSerializer,
        responses={
            200: LoginResponseSerializer(),
            400: "Invalid input data",
            401: "Invalid credentials"
        }
    )
    def post(self, request, *args, **kwargs):
        """Handle user login and return JWT tokens with user data."""
        serializer = self.get_serializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return Response(
                {"detail": "Invalid credentials"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        user = authenticate(
            phone_number=request.data.get('phone_number'),
            password=request.data.get('password')
        )
        
        if not user:
            return Response(
                {"detail": "Invalid credentials"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        })
