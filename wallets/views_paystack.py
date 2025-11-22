"""
Views for handling Paystack payment gateway integration.
"""
import json
import logging
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from wallets.models import Transaction
from wallets.payment_gateways import get_payment_gateway

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def paystack_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle Paystack webhook notifications.
    """
    # Verify the webhook signature if needed
    # You can implement signature verification here for security
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
        event = payload.get('event')
        
        if not event:
            return Response(
                {'status': False, 'message': 'Invalid webhook event'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"Received Paystack webhook event: {event}")
        logger.debug(f"Webhook payload: {payload}")
        
        gateway = get_payment_gateway('paystack')
        
        # Handle different webhook events
        if event == 'charge.success':
            data = payload.get('data', {})
            reference = data.get('reference')
            
            if not reference:
                return Response(
                    {'status': False, 'message': 'Missing reference in webhook payload'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify the transaction with Paystack
            result = gateway.verify_payment(reference)
            
            if result.get('status'):
                # Update the transaction status in your database
                try:
                    transaction = Transaction.objects.get(reference=reference)
                    transaction.status = Transaction.TransactionStatus.COMPLETED
                    transaction.metadata['paystack_response'] = result
                    transaction.save()
                    
                    # Update the wallet balance if needed
                    if transaction.transaction_type == 'deposit':
                        wallet = transaction.wallet
                        wallet.balance += transaction.amount
                        wallet.save()
                    
                    logger.info(f"Successfully processed Paystack webhook for reference: {reference}")
                    return Response({'status': True, 'message': 'Webhook processed successfully'})
                
                except Transaction.DoesNotExist:
                    logger.error(f"Transaction with reference {reference} not found")
                    return Response(
                        {'status': False, 'message': 'Transaction not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            return Response(
                {'status': False, 'message': 'Payment verification failed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle other webhook events if needed
        elif event == 'transfer.success':
            # Handle successful transfers
            pass
        
        return Response({'status': True, 'message': 'Webhook received but no action taken'})
    
    except json.JSONDecodeError:
        return Response(
            {'status': False, 'message': 'Invalid JSON payload'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.exception("Error processing Paystack webhook")
        return Response(
            {'status': False, 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
