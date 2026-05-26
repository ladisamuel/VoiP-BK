
import os
import time
import threading
from twilio.rest import Client
from twilio.request_validator import RequestValidator

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN"))

_system_lock = threading.Lock()
_system_state = {
    "status": "offline",
    "last_seen": 0,
    "browser_connected": False,
    "current_call_sid": None,
    "pending_call_sid": None,
    "pending_from_number": None,
    "pending_timer": None,
}

VOIP_GROUP = "voip_user"


def get_state():
    with _system_lock:
        return dict(_system_state)


def update_presence(browser_connected=True):
    with _system_lock:
        _system_state["last_seen"] = time.time()
        _system_state["browser_connected"] = browser_connected
        if _system_state["status"] not in ("busy", "ringing"):
            _system_state["status"] = "online" if browser_connected else "offline"


def set_busy(call_sid):
    with _system_lock:
        _cancel_pending_timer()
        _system_state["status"] = "busy"
        _system_state["current_call_sid"] = call_sid
        _system_state["pending_call_sid"] = None
        _system_state["pending_from_number"] = None


def set_ringing(call_sid, from_number=None):
    with _system_lock:
        _system_state["status"] = "ringing"
        _system_state["pending_call_sid"] = call_sid
        _system_state["pending_from_number"] = from_number


def set_idle():
    with _system_lock:
        _cancel_pending_timer()
        _system_state["status"] = "online"
        _system_state["current_call_sid"] = None
        _system_state["pending_call_sid"] = None
        _system_state["pending_from_number"] = None


def _cancel_pending_timer():
    timer = _system_state.get("pending_timer")
    if timer:
        timer.cancel()
        _system_state["pending_timer"] = None


def set_pending_timer(callback, timeout=15):
    with _system_lock:
        _cancel_pending_timer()
        timer = threading.Timer(timeout, callback)
        timer.daemon = True
        timer.start()
        _system_state["pending_timer"] = timer


def can_initiate_call():
    state = get_state()
    if state["status"] == "busy":
        return False, "System is busy"
    if state["status"] == "ringing":
        return False, "Call already ringing"
    if not state["browser_connected"]:
        return False, "Browser not connected"
    if time.time() - state["last_seen"] > 30:
        return False, "User idle"
    return True, "OK"


def can_receive_call():
    state = get_state()
    if state["status"] in ("busy", "ringing"):
        return False, "System is busy"
    if not state["browser_connected"]:
        return False, "Browser offline"
    if time.time() - state["last_seen"] > 30:
        return False, "User idle"
    return True, "OK"


def validate_twilio_request(request):
    url = request.build_absolute_uri()
    signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
    post_vars = request.POST.dict() if hasattr(request.POST, "dict") else dict(request.POST)
    return validator.validate(url, post_vars, signature)
