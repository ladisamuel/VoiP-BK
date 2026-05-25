
from django.db import models

class CallLog(models.Model):
    DIRECTION_CHOICES = [("inbound", "Inbound"), ("outbound", "Outbound")]
    STATUS_CHOICES = [
        ("initiated", "Initiated"),
        ("ringing", "Ringing"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("missed", "Missed"),
        ("failed", "Failed"),
        ("rejected", "Rejected"),
        ("voicemail", "Voicemail"),
    ]

    call_sid = models.CharField(max_length=64, unique=True, db_index=True)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    from_number = models.CharField(max_length=20)
    to_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="initiated")
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.direction} {self.call_sid} {self.status}"


class SMSLog(models.Model):
    sms_sid = models.CharField(max_length=64, unique=True, db_index=True)
    from_number = models.CharField(max_length=20)
    to_number = models.CharField(max_length=20)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SMS from {self.from_number}"
