import logging
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import os

logger = logging.getLogger(__name__)

def initialize_firebase():
    """
    Initialize Firebase app if not already initialized.
    Uses FIREBASE_SERVICE_ACCOUNT_KEY from settings.
    """
    if not firebase_admin._apps:
        try:
            cred_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_KEY', None)
            if cred_path and os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase successfully initialized.")
            else:
                logger.warning("FIREBASE_SERVICE_ACCOUNT_KEY not found or path invalid. Push notifications will not be sent.")
        except Exception as e:
            logger.error(f"Error initializing Firebase: {e}")

class NotificationService:
    """
    Utility service to send push notifications using Firebase Cloud Messaging (FCM).
    """
    
    @staticmethod
    def send_push_notification(user, title, body, data=None):
        """
        Send a push notification to a specific user using their fcm_token.
        
        Args:
            user: User model instance
            title: Notification title
            body: Notification message body
            data: Optional dictionary with extra data payload
        """
        if not hasattr(user, 'fcm_token') or not user.fcm_token:
            logger.info(f"User {user.id} has no FCM token. Skipping notification.")
            return False

        initialize_firebase()
        
        if not firebase_admin._apps:
            return False

        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=user.fcm_token,
            )
            response = messaging.send(message)
            logger.info(f"Successfully sent push notification to user {user.id}: {response}")
            return True
        except Exception as e:
            logger.error(f"Error sending push notification to user {user.id}: {e}")
            # If the token is invalid, we might want to clear it
            # if "registration-token-not-registered" in str(e):
            #     user.fcm_token = None
            #     user.save(update_fields=['fcm_token'])
            return False

    @staticmethod
    def send_multicast_notification(users, title, body, data=None):
        """
        Send a push notification to multiple users.
        """
        tokens = [u.fcm_token for u in users if hasattr(u, 'fcm_token') and u.fcm_token]
        if not tokens:
            return False

        initialize_firebase()
        
        if not firebase_admin._apps:
            return False

        try:
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                tokens=tokens,
            )
            response = messaging.send_multicast(message)
            logger.info(f"Multicast notification results: {response.success_count} success, {response.failure_count} failure")
            return True
        except Exception as e:
            logger.error(f"Error sending multicast notification: {e}")
            return False
