from apps.common.admin import register_all

from .models import ContestEntry, ContestVote, MemeContest, MemeDraft, MemeGenerationRequest, MemeTemplate, MemeUpload

register_all(MemeDraft, MemeGenerationRequest, MemeTemplate, MemeUpload, MemeContest, ContestEntry, ContestVote)
