"""ITD API Views — Excel VBA向けREST API (§5.2 / §5.3 / §5.3.1)

全エンドポイントでJEPX通信例外をキャッチし、
error_code / message をJSON返却する。
"""
import json
import logging

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from apps.jepx_client.client import JepxApiClient
from apps.jepx_client.exceptions import (
    JepxFormatError,
    JepxAuthError,
    JepxSystemError,
    JepxBusinessError,
    JepxConnectionError,
    JepxTimeoutError,
    JepxError,
)
from apps.common.validators import BidValidator
from . import services
from . import serializers

logger = logging.getLogger('jepx.api')
error_logger = logging.getLogger('jepx.error')


def _handle_jepx_error(e: Exception) -> JsonResponse:
    """JEPX例外をエラーコード付きJsonResponseに変換する (§5.3)"""
    if isinstance(e, JepxFormatError):
        return JsonResponse(
            serializers.serialize_error('JEPX_FORMAT_ERROR', str(e)), status=502
        )
    elif isinstance(e, JepxAuthError):
        return JsonResponse(
            serializers.serialize_error('JEPX_AUTH_ERROR', str(e)), status=502
        )
    elif isinstance(e, JepxSystemError):
        return JsonResponse(
            serializers.serialize_error('JEPX_SYSTEM_ERROR', str(e)), status=502
        )
    elif isinstance(e, JepxBusinessError):
        return JsonResponse(
            serializers.serialize_error('JEPX_BUSINESS_ERROR', str(e)), status=400
        )
    elif isinstance(e, JepxConnectionError):
        return JsonResponse(
            serializers.serialize_error('JEPX_CONNECTION_ERROR', str(e)), status=503
        )
    elif isinstance(e, JepxTimeoutError):
        return JsonResponse(
            serializers.serialize_error('JEPX_TIMEOUT', str(e)), status=504
        )
    else:
        error_logger.error("[INTERNAL] 予期しないエラー: %s", e, exc_info=True)
        return JsonResponse(
            serializers.serialize_error('INTERNAL_ERROR', str(e)), status=500
        )


@method_decorator(csrf_exempt, name='dispatch')
class ItdBidView(View):
    """POST /api/v1/itd/bid — ITD入札 (ITD1001)"""

    async def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                serializers.serialize_error('VALIDATION_ERROR', 'JSONパースエラー'),
                status=400,
            )

        # バリデーション
        validator = BidValidator()
        errors = validator.validate([data], market='ITD')
        if errors:
            return JsonResponse(
                serializers.serialize_error(
                    'VALIDATION_ERROR',
                    '; '.join(e.message for e in errors),
                ),
                status=400,
            )

        # 二重送信チェック (§5.3.1)
        try:
            dup = await services.check_duplicate_bid(data)
            if dup:
                return JsonResponse({
                    'success': False,
                    'error_code': 'DUPLICATE_BID',
                    'message': f'同一条件の入札が既に存在します (bidNo={dup.get("bidNo")})',
                }, status=409)

            result = await services.execute_itd_bid(data)
            return JsonResponse(serializers.serialize_bid_response(result))
        except JepxError as e:
            return _handle_jepx_error(e)


@method_decorator(csrf_exempt, name='dispatch')
class ItdDeleteView(View):
    """POST /api/v1/itd/delete — ITD入札削除 (ITD1002)"""

    async def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                serializers.serialize_error('VALIDATION_ERROR', 'JSONパースエラー'),
                status=400,
            )

        if not data.get('bidNo'):
            return JsonResponse(
                serializers.serialize_error('VALIDATION_ERROR', 'bidNoは必須です'),
                status=400,
            )

        try:
            result = await services.execute_itd_delete(data)
            return JsonResponse(serializers.serialize_delete_response(result))
        except JepxError as e:
            return _handle_jepx_error(e)


@method_decorator(csrf_exempt, name='dispatch')
class ItdInquiryView(View):
    """GET /api/v1/itd/inquiry — ITD入札照会 (ITD1003)"""

    async def get(self, request):
        delivery_date = request.GET.get('deliveryDate', '')
        if not delivery_date:
            return JsonResponse(
                serializers.serialize_error('VALIDATION_ERROR', 'deliveryDateは必須です'),
                status=400,
            )

        data = {
            'deliveryDate': delivery_date,
            'timeCd': request.GET.get('timeCd', ''),
        }

        try:
            result = await services.execute_itd_inquiry(data)
            return JsonResponse(serializers.serialize_inquiry_response(result))
        except JepxError as e:
            return _handle_jepx_error(e)


@method_decorator(csrf_exempt, name='dispatch')
class ItdContractView(View):
    """GET /api/v1/itd/contract — ITD約定照会 (ITD1004)"""

    async def get(self, request):
        delivery_date = request.GET.get('deliveryDate', '')
        if not delivery_date:
            return JsonResponse(
                serializers.serialize_error('VALIDATION_ERROR', 'deliveryDateは必須です'),
                status=400,
            )

        try:
            result = await services.execute_itd_contract({'deliveryDate': delivery_date})
            return JsonResponse(serializers.serialize_contract_response(result))
        except JepxError as e:
            return _handle_jepx_error(e)


@method_decorator(csrf_exempt, name='dispatch')
class ItdSettlementView(View):
    """GET /api/v1/itd/settlement — ITD清算照会 (ITD9001)"""

    async def get(self, request):
        from_date = request.GET.get('fromDate', '')
        if not from_date:
            return JsonResponse(
                serializers.serialize_error('VALIDATION_ERROR', 'fromDateは必須です'),
                status=400,
            )

        data = {
            'fromDate': from_date,
            'toDate': request.GET.get('toDate', ''),
        }

        try:
            result = await services.execute_itd_settlement(data)
            return JsonResponse(serializers.serialize_settlement_response(result))
        except JepxError as e:
            return _handle_jepx_error(e)


class HealthCheckView(View):
    """GET /health — ヘルスチェック (§5.2)"""

    async def get(self, request):
        from config.asgi import itn_store

        pool_status = JepxApiClient.get_pool_status()
        itn_snapshot = itn_store.get_snapshot()

        return JsonResponse({
            'status': 'ok',
            'environment': getattr(settings, 'JEPX_ENVIRONMENT', 'unknown'),
            'jepx_pool': pool_status,
            'itn_connection': itn_snapshot.get('connection', {}),
        })
