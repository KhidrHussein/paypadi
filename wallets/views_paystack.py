"""
Views for handling Paystack payment gateway integration.
"""
import json
import logging
import hmac
import hashlib
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
    # Verify the webhook signature
    signature = request.headers.get('X-Paystack-Signature')
    if not signature:
        return Response({'status': False, 'message': 'Missing signature'}, status=status.HTTP_400_BAD_REQUEST)
        
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '').encode('utf-8')
    expected_sign = hmac.new(secret_key, request.body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected_sign, signature):
        logger.warning(f"Invalid Paystack webhook signature")
        return Response({'status': False, 'message': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
    
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
        
        # Handle different webhook events
        if event == 'charge.success':
            data = payload.get('data', {})
            reference = data.get('reference')
            
            if not reference:
                return Response(
                    {'status': False, 'message': 'Missing reference in webhook payload'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                from wallets.services.payment_service import PaymentService
                service = PaymentService()
                service.verify_payment(reference)
                logger.info(f"Successfully processed Paystack webhook for reference: {reference}")
                return Response({'status': True, 'message': 'Webhook processed successfully'})
            except Exception as e:
                logger.error(f"Error verifying payment from webhook: {str(e)}", exc_info=True)
                return Response(
                    {'status': False, 'message': 'Payment verification failed'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Handle transfer webhooks (withdrawals and external transfers)
        elif event in ['transfer.success', 'transfer.failed', 'transfer.reversed']:
            data = payload.get('data', {})
            reference = data.get('reference')
            
            if not reference:
                return Response(
                    {'status': False, 'message': 'Missing reference in webhook payload'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                from django.db import transaction as db_transaction
                from wallets.models import Wallet
                
                with db_transaction.atomic():
                    txn = Transaction.objects.select_for_update().get(reference=reference)
                    
                    if txn.status == Transaction.TransactionStatus.COMPLETED:
                        if event != 'transfer.reversed':
                            return Response({'status': True, 'message': 'Transaction already finalized as COMPLETED'})
                        
                    if event == 'transfer.success':
                        if txn.status == Transaction.TransactionStatus.FAILED:
                            # CRITICAL ALERT: marked failed locally but succeeded on Paystack!
                            logger.critical(f"DOUBLE SPEND ALERT: Transfer {reference} succeeded on Paystack but is marked FAILED locally!")
                            txn.metadata['critical_discrepancy'] = True
                            txn.metadata['paystack_transfer_response'] = data
                            txn.save(update_fields=['metadata'])
                        else:
                            txn.status = Transaction.TransactionStatus.COMPLETED
                            txn.metadata['paystack_transfer_response'] = data
                            txn.save(update_fields=['status', 'metadata'])
                        logger.info(f"Successfully processed transfer.success for: {reference}")
                        
                    elif event in ['transfer.failed', 'transfer.reversed']:
                        if txn.status == Transaction.TransactionStatus.FAILED:
                            return Response({'status': True, 'message': 'Transaction already marked FAILED'})
                            
                        txn.status = Transaction.TransactionStatus.FAILED
                        txn.metadata['paystack_transfer_failure'] = data
                        txn.save(update_fields=['status', 'metadata'])
                        
                        # Refund the user's wallet since balance was deducted at initiation
                        wallet = Wallet.objects.select_for_update().get(id=txn.wallet_id)
                        wallet.balance += txn.amount
                        wallet.save(update_fields=['balance'])
                        logger.info(f"Processed {event} and refunded wallet for: {reference}")
                        
                return Response({'status': True, 'message': f'Webhook {event} processed successfully'})
                
            except Transaction.DoesNotExist:
                logger.error(f"Transaction with reference {reference} not found")
                return Response(
                    {'status': False, 'message': 'Transaction not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
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
