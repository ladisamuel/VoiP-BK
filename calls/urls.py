
from django.urls import path
from . import views

urlpatterns = [
    path("token/", views.get_token, name="token"),
    path("call/start/", views.start_call, name="start_call"),
    path("call/end/", views.end_call, name="end_call"),
    path("call/logs/", views.call_logs, name="call_logs"),
    path("sms/inbox/", views.sms_inbox, name="sms_inbox"),
    path("webhooks/voice/incoming/", views.incoming_voice_webhook, name="incoming_voice"),
    path("webhooks/voice/status/", views.voice_status_webhook, name="voice_status"),
    path("webhooks/sms/incoming/", views.incoming_sms_webhook, name="incoming_sms"),
    path("twiml/outbound-dial/", views.outbound_dial_twiml, name="outbound_dial"),
    path("twiml/join-conference/", views.join_conference_twiml, name="join_conference"),
    path("twiml/hold-music/", views.hold_music_twiml, name="hold_music"),
]
