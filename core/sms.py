import logging
from django.conf import settings
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)

def send_sms(phone_number, message):
    """
    Send an SMS using Twilio.
    
    Args:
        phone_number (str): The recipient's phone number.
        message (str): The message content.
        
    Returns:
        bool: True if sent successfully, False otherwise.
    """
    try:
        # Check if Twilio settings are configured
        if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_PHONE_NUMBER]):
            logger.warning("Twilio credentials not fully configured. Skipping SMS send.")
            return False

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        logger.info(f"Attempting to send SMS via Twilio Account: {settings.TWILIO_ACCOUNT_SID[:6]}...{settings.TWILIO_ACCOUNT_SID[-4:]}")
        logger.info(f"From: {settings.TWILIO_PHONE_NUMBER}, To: {phone_number}")

        client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=str(phone_number)
        )
        logger.info(f"SMS sent successfully to {phone_number}")
        return True
        
    except TwilioRestException as e:
        logger.error(f"Twilio error sending SMS: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending SMS: {e}")
        return False
