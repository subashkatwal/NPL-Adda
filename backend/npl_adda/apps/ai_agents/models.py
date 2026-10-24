from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.common.models import BaseModel, alive
from apps.fanengagement.models import FanProfile
from apps.matches.models import Match
from apps.teams.models import Team


class AgentRun(BaseModel):
    """One execution of an agent workflow. Stores structured output only, never model reasoning."""

    class Workflow(models.TextChoices):
        MATCHDAY_CONTENT = "matchday_content", "Matchday content"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        WAITING_FOR_REVIEW = "waiting_for_review", "Waiting for review"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    TERMINAL = {Status.WAITING_FOR_REVIEW, Status.SUCCEEDED, Status.FAILED, Status.CANCELLED}

    workflow_name = models.CharField(max_length=50, choices=Workflow.choices, help_text="Workflow identifier.")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_runs",
        help_text="Account that started the run (audit).",
    )
    fan_profile = models.ForeignKey(
        FanProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="agent_runs", help_text="Fan context."
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT, related_name="+", help_text="Team context."
    )
    match = models.ForeignKey(
        Match, null=True, blank=True, on_delete=models.PROTECT, related_name="agent_runs", help_text="Match context."
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True, help_text="Execution state."
    )
    input_data = models.JSONField(default=dict, blank=True, help_text="Validated workflow input.")
    output_data = models.JSONField(default=dict, blank=True, help_text="Structured workflow output.")
    error_code = models.CharField(max_length=50, blank=True, help_text="Safe machine-readable failure code.")
    error_message = models.CharField(max_length=255, blank=True, help_text="Safe human-readable failure message.")
    retry_count = models.PositiveSmallIntegerField(default=0, help_text="Draft regeneration attempts after the first.")
    provider = models.CharField(max_length=40, blank=True, help_text="LLM provider used, or 'mock'.")
    model_name = models.CharField(max_length=80, blank=True, help_text="Model identifier used.")
    prompt_version = models.CharField(max_length=40, blank=True, help_text="Prompt template version.")
    usage_metadata = models.JSONField(default=dict, blank=True, help_text="Token usage and cost, where available.")
    checkpoint_thread_id = models.CharField(
        max_length=100, blank=True, db_index=True, help_text="LangGraph thread ID for resumable state."
    )
    idempotency_key = models.CharField(
        max_length=100, null=True, blank=True, help_text="Client key; repeats by the same user return the same run."
    )
    started_at = models.DateTimeField(null=True, blank=True, help_text="When execution started.")
    finished_at = models.DateTimeField(null=True, blank=True, help_text="When execution finished.")

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["requested_by", "idempotency_key"],
                condition=alive(idempotency_key__isnull=False),
                name="agentrun_unique_idempotency",
            ),
            models.CheckConstraint(
                condition=Q(finished_at__isnull=True) | Q(started_at__isnull=True) | Q(finished_at__gte=F("started_at")),
                name="agentrun_finished_after_started",
            ),
        ]

    def __str__(self):
        return f"{self.workflow_name} {self.pk} ({self.status})"


class AgentToolCall(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    agent_run = models.ForeignKey(
        AgentRun, on_delete=models.CASCADE, related_name="tool_calls", help_text="Run that made the call."
    )
    tool_name = models.CharField(max_length=60, help_text="Tool identifier.")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, help_text="Outcome of this attempt."
    )
    attempt_number = models.PositiveSmallIntegerField(default=1, help_text="1-based attempt counter.")
    input_summary = models.JSONField(default=dict, blank=True, help_text="Safe summary of tool arguments.")
    output_summary = models.JSONField(default=dict, blank=True, help_text="Safe summary of the tool result.")
    error_type = models.CharField(max_length=100, blank=True, help_text="Exception class or failure category.")
    started_at = models.DateTimeField(null=True, blank=True, help_text="When the attempt started.")
    finished_at = models.DateTimeField(null=True, blank=True, help_text="When the attempt finished.")

    class Meta(BaseModel.Meta):
        ordering = ("created_at",)
        constraints = [models.CheckConstraint(condition=Q(attempt_number__gte=1), name="toolcall_attempt_positive")]

    def __str__(self):
        return f"{self.tool_name} #{self.attempt_number} ({self.status})"
