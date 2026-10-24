from apps.common.admin import register_all

from .models import CommunityPost, ContentVote, PostComment, PostReaction

register_all(CommunityPost, ContentVote, PostComment, PostReaction)
