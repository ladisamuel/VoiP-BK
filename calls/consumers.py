
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .utils import (
    update_presence, set_busy, set_ringing, set_idle,
    set_pending_timer, get_state, VOIP_GROUP
)
from django.conf import settings
from .models import CallLog
from .services import create_outbound_call, hangup_call
from datetime import datetime
from twilio.rest import Client


class VoipConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = VOIP_GROUP
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await sync_to_async(update_presence)(browser_connected=True)
        await self.broadcast_state()

    async def disconnect(self, close_code):
        await sync_to_async(update_presence)(browser_connected=False)
        await self.broadcast_state()
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")

        if action == "ping":
            await sync_to_async(update_presence)(browser_connected=True)
            await self.broadcast_state()
        elif action == "start_outbound_call":
            await self.handle_start_outbound(data)
        elif action == "accept_incoming":
            await self.handle_accept_incoming(data)
        elif action == "reject_incoming":
            await self.handle_reject_incoming(data)
        elif action == "hangup":
            await self.handle_hangup(data)

    async def handle_start_outbound(self, data):
        to_number = data.get("to")
        result = await sync_to_async(create_outbound_call)(to_number)
        await self.send(text_data=json.dumps({
            "event_type": "outbound_initiated",
            "payload": result
        }))
        if result.get("approved"):
            await self.broadcast_state()

    async def handle_accept_incoming(self, data):
        call_sid = data.get("call_sid")
        state = await sync_to_async(get_state)()

        if state.get("pending_call_sid") != call_sid:
            await self.send(text_data=json.dumps({
                "event_type": "error",
                "payload": {"message": "Call no longer pending"}
            }))
            return

        room = f"room-{call_sid}"
        twiml_url = f"{settings.BASE_URL}/twiml/join-conference?room={room}"

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            await sync_to_async(client.calls.create)(
                to="client:user",
                from_=settings.TWILIO_PHONE_NUMBER,
                url=twiml_url,
            )
            await sync_to_async(set_busy)(call_sid)
            await sync_to_async(CallLog.objects.filter(call_sid=call_sid).update)(
                status="in_progress", start_time=datetime.now()
            )
            await self.broadcast_state()
            await self.broadcast_event("call_accepted", {"call_sid": call_sid})
        except Exception as e:
            await self.send(text_data=json.dumps({
                "event_type": "error",
                "payload": {"message": str(e)}
            }))

    async def handle_reject_incoming(self, data):
        call_sid = data.get("call_sid")
        state = await sync_to_async(get_state)()

        if state.get("pending_call_sid") == call_sid:
            await sync_to_async(hangup_call)(call_sid)
            await sync_to_async(CallLog.objects.filter(call_sid=call_sid).update)(
                status="rejected", end_time=datetime.now()
            )
            await sync_to_async(set_idle)()
            await self.broadcast_state()
            await self.broadcast_event("call_rejected", {"call_sid": call_sid})

    async def handle_hangup(self, data):
        state = await sync_to_async(get_state)()
        call_sid = state.get("current_call_sid") or state.get("pending_call_sid")
        if call_sid:
            await sync_to_async(hangup_call)(call_sid)
        await sync_to_async(set_idle)()
        await self.broadcast_state()
        await self.broadcast_event("call_ended", {})

    async def voip_event(self, event):
        await self.send(text_data=json.dumps({
            "event_type": event.get("event_type"),
            "payload": event.get("payload", {})
        }))

    async def broadcast_state(self):
        state = await sync_to_async(get_state)()
        await self.channel_layer.group_send(self.group_name, {
            "type": "voip_event",
            "event_type": "state_update",
            "payload": state
        })

    async def broadcast_event(self, event_type, payload):
        await self.channel_layer.group_send(self.group_name, {
            "type": "voip_event",
            "event_type": event_type,
            "payload": payload
        })
