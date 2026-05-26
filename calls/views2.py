
from datetime import datetime
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from django.conf import settings
from .models import CallLog, SMSLog
from .utils import validate_twilio_request, get_state, VOIP_GROUP, set_idle
from .services import create_outbound_call, handle_incoming_call, hangup_call


@api_view(["GET"])
def get_token(request):
    identity = "user"
    token = AccessToken(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY,
        settings.TWILIO_API_SECRET,
        identity=identity
    )
    voice_grant = VoiceGrant(incoming_allow=True)
    token.add_grant(voice_grant)
    return Response({"token": token.to_jwt(), "identity": identity})


@api_view(["POST"])
def start_call(request):
    to_number = request.data.get("to")
    if not to_number:
        return Response({"error": "Number required"}, status=400)
    result = create_outbound_call(to_number)
    if result["approved"]:
        return Response(result, status=200)
    return Response(result, status=409)


@api_view(["POST"])
def end_call(request):
    state = get_state()
    call_sid = state.get("current_call_sid") or state.get("pending_call_sid")
    if call_sid:
        hangup_call(call_sid)
        set_idle()
        async_to_sync(get_channel_layer().group_send)(VOIP_GROUP, {
            "type": "voip_event",
            "event_type": "call_ended",
            "payload": {}
        })
    return Response({"status": "ok"})


@api_view(["GET"])
def call_logs(request):
    logs = CallLog.objects.all()[:100]
    data = [{
        "call_sid": l.call_sid,
        "direction": l.direction,
        "from_number": l.from_number,
        "to_number": l.to_number,
        "status": l.status,
        "duration": l.duration,
        "created_at": l.created_at.isoformat(),
    } for l in logs]
    return Response(data)


@api_view(["GET"])
def sms_inbox(request):
    messages = SMSLog.objects.all()[:100]
    data = [{
        "sms_sid": m.sms_sid,
        "from_number": m.from_number,
        "to_number": m.to_number,
        "body": m.body,
        "created_at": m.created_at.isoformat(),
    } for m in messages]
    return Response(data)


@csrf_exempt
def incoming_voice_webhook(request):
    if not validate_twilio_request(request):
        return HttpResponse("Invalid", status=403)

    call_sid = request.POST.get("CallSid")
    from_number = request.POST.get("From")

    if CallLog.objects.filter(call_sid=call_sid).exists():
        return HttpResponse('<Response><Reject/></Response>', content_type='text/xml')

    available = handle_incoming_call(call_sid, from_number)

    if not available:
        return HttpResponse('<Response><Reject/></Response>', content_type='text/xml')

    room = f"room-{call_sid}"
    hold_url = f"{settings.BASE_URL}/twiml/hold-music"

    twiml = f'''<Response>
        <Dial>
            <Conference waitUrl="{hold_url}" beep="false" startConferenceOnEnter="false" endConferenceOnExit="true">
                {room}
            </Conference>
        </Dial>
    </Response>'''

    return HttpResponse(twiml, content_type='text/xml')


@csrf_exempt
def voice_status_webhook(request):
    if not validate_twilio_request(request):
        return HttpResponse("Invalid", status=403)

    call_sid = request.POST.get("CallSid")
    status = request.POST.get("CallStatus")
    direction = request.POST.get("Direction", "")
    from_number = request.POST.get("From", "")
    to_number = request.POST.get("To", "")
    duration = request.POST.get("Duration")

    log, created = CallLog.objects.get_or_create(
        call_sid=call_sid,
        defaults={
            "direction": "inbound" if "inbound" in direction.lower() else "outbound",
            "from_number": from_number,
            "to_number": to_number,
            "status": status,
        }
    )

    if not created:
        log.status = status
        if status in ("completed", "busy", "failed", "no-answer", "canceled"):
            log.end_time = datetime.now()
            if duration:
                log.duration = int(duration)
        if status == "in-progress" and not log.start_time:
            log.start_time = datetime.now()
        log.save()

    if status in ("completed", "busy", "failed", "no-answer", "canceled"):
        state = get_state()
        if state.get("current_call_sid") == call_sid or state.get("pending_call_sid") == call_sid:
            set_idle()
            async_to_sync(get_channel_layer().group_send)(VOIP_GROUP, {
                "type": "voip_event",
                "event_type": "call_ended",
                "payload": {"call_sid": call_sid, "status": status}
            })

    return HttpResponse("OK", status=200)


@csrf_exempt
def incoming_sms_webhook(request):
    if not validate_twilio_request(request):
        return HttpResponse("Invalid", status=403)

    sms_sid = request.POST.get("SmsSid")
    from_number = request.POST.get("From")
    to_number = request.POST.get("To")
    body = request.POST.get("Body")

    if not SMSLog.objects.filter(sms_sid=sms_sid).exists():
        SMSLog.objects.create(
            sms_sid=sms_sid,
            from_number=from_number,
            to_number=to_number,
            body=body
        )
        async_to_sync(get_channel_layer().group_send)(VOIP_GROUP, {
            "type": "voip_event",
            "event_type": "sms_received",
            "payload": {
                "sms_sid": sms_sid,
                "from_number": from_number,
                "body": body,
                "created_at": datetime.now().isoformat()
            }
        })

    return HttpResponse('<Response/>', content_type='text/xml')


@csrf_exempt
def outbound_dial_twiml(request):
    to_number = request.GET.get("to") or request.POST.get("to")
    if not to_number:
        return HttpResponse('<Response><Hangup/></Response>', content_type='text/xml')

    twiml = f'''<Response>
        <Dial callerId="{settings.TWILIO_PHONE_NUMBER}" answerOnBridge="true">
            {to_number}
        </Dial>
    </Response>'''

    return HttpResponse(twiml, content_type='text/xml')


@csrf_exempt
def join_conference_twiml(request):
    room = request.GET.get("room") or request.POST.get("room")
    if not room:
        return HttpResponse('<Response><Hangup/></Response>', content_type='text/xml')

    twiml = f'''<Response>
        <Dial>
            <Conference startConferenceOnEnter="true" endConferenceOnExit="true" beep="false">
                {room}
            </Conference>
        </Dial>
    </Response>'''

    return HttpResponse(twiml, content_type='text/xml')


@csrf_exempt
def hold_music_twiml(request):
    twiml = f'''<Response>
        <Say>Please wait while we connect your call.</Say>
        <Pause length="5"/>
        <Redirect>{settings.BASE_URL}/twiml/hold-music</Redirect>
    </Response>'''
    return HttpResponse(twiml, content_type='text/xml')
