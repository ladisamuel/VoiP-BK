
from datetime import datetime
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import CallLog
from .utils import (
    twilio_client, can_initiate_call, set_ringing, set_busy, set_idle,
    get_state, set_pending_timer, VOIP_GROUP
)


def create_outbound_call(to_number):
    ok, msg = can_initiate_call()
    if not ok:
        return {"approved": False, "error": msg}

    call_log = CallLog.objects.create(
        call_sid="pending",
        direction="outbound",
        from_number=settings.TWILIO_PHONE_NUMBER,
        to_number=to_number,
        status="initiated"
    )

    twiml_url = f"{settings.BASE_URL}/twiml/outbound-dial?to={to_number}"

    try:
        call = twilio_client.calls.create(
            to="client:user",
            from_=settings.TWILIO_PHONE_NUMBER,
            url=twiml_url,
            status_callback=f"{settings.BASE_URL}/webhooks/voice/status/",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST"
        )
        call_log.call_sid = call.sid
        call_log.status = "ringing"
        call_log.save()
        set_ringing(call.sid)
        return {"approved": True, "call_sid": call.sid}
    except Exception as e:
        call_log.status = "failed"
        call_log.save()
        set_idle()
        return {"approved": False, "error": str(e)}


def handle_incoming_call(call_sid, from_number):
    ok, msg = can_receive_call()
    if not ok:
        return False

    if CallLog.objects.filter(call_sid=call_sid).exists():
        return True

    CallLog.objects.create(
        call_sid=call_sid,
        direction="inbound",
        from_number=from_number,
        to_number=settings.TWILIO_PHONE_NUMBER,
        status="ringing"
    )

    set_ringing(call_sid, from_number)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(VOIP_GROUP, {
        "type": "voip_event",
        "event_type": "incoming_call",
        "payload": {
            "call_sid": call_sid,
            "from_number": from_number,
        }
    })

    def auto_reject():
        state = get_state()
        if state.get("pending_call_sid") == call_sid:
            try:
                twilio_client.calls(call_sid).update(status="completed")
            except Exception:
                pass
            CallLog.objects.filter(call_sid=call_sid).update(
                status="missed", end_time=datetime.now()
            )
            set_idle()
            async_to_sync(channel_layer.group_send)(VOIP_GROUP, {
                "type": "voip_event",
                "event_type": "call_missed",
                "payload": {"call_sid": call_sid}
            })

    set_pending_timer(auto_reject, timeout=15)
    return True


def hangup_call(call_sid):
    try:
        twilio_client.calls(call_sid).update(status="completed")
    except Exception:
        pass
    log = CallLog.objects.filter(call_sid=call_sid).first()
    if log:
        log.status = "completed"
        log.end_time = datetime.now()
        if log.start_time:
            log.duration = int((log.end_time - log.start_time).total_seconds())
        log.save()
