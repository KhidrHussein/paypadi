import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def send_sms(phone_number, message):
    """
    Send an SMS using Termii.
    
    Args:
        phone_number (str): The recipient's phone number.
        message (str): The message content.
        
    Returns:
        bool: True if sent successfully, False otherwise.
    """
    try:
        # Check if Termii settings are configured
        if not all([settings.TERMII_API_KEY, settings.TERMII_SENDER_ID, settings.TERMII_BASE_URL]):
            logger.warning("Termii credentials not fully configured. Skipping SMS send.")
            return False

        # Termii expects phone numbers in format 23480...
        # If it starts with +, remove it.
        target_phone = str(phone_number).strip().replace(' ', '').replace('+', '')
        
        payload = {
            "to": target_phone,
            "from": settings.TERMII_SENDER_ID,
            "sms": message,
            "type": "plain",
            "channel": "dnd", # Use dnd for better delivery in Nigeria
            "api_key": settings.TERMII_API_KEY
        }
        
        # Ensure the URL is correctly formed (append path if only domain is provided)
        url = settings.TERMII_BASE_URL
        if url and not url.endswith('/api/sms/send'):
            url = f"{url.rstrip('/')}/api/sms/send"
            
        logger.info(f"Attempting to send SMS via Termii to {target_phone}")
        
        response = requests.post(url, json=payload, timeout=10)
        response_data = response.json()
        
        if response.status_code == 200:
            logger.info(f"SMS sent successfully to {phone_number}. Termii ID: {response_data.get('message_id')}")
            return True
        else:
            logger.error(f"Termii error sending SMS to {url}: {response_data}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error sending SMS via Termii: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending SMS via Termii: {e}")
        return False
