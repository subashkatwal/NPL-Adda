from rest_framework.throttling import SimpleRateThrottle

from apps.fanengagement.identity import get_fan_profile


class FanRateThrottle(SimpleRateThrottle):
    """Limits a Meme Zone action per fan profile, falling back to the client IP."""

    def get_cache_key(self, request, view):
        profile = get_fan_profile(request)
        ident = f"fan:{profile.pk}" if profile else f"ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class MemeGenerationThrottle(FanRateThrottle):
    scope = "meme_generation"


class MemeRenderThrottle(FanRateThrottle):
    scope = "meme_render"


class MemeUploadThrottle(FanRateThrottle):
    scope = "meme_upload"


class MemeEngageThrottle(FanRateThrottle):
    scope = "meme_engage"


class MemeCommentThrottle(FanRateThrottle):
    scope = "meme_comment"
