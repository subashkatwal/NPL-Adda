"""Mounted at /api/v1/fanpage."""
from django.urls import path

from apps.common.routing import resource_routes

from . import views

app_name = "fanengagement"

urlpatterns = [
    path("/me", views.MyProfileView.as_view(), name="me"),
    path("/me/membership", views.MyMembershipView.as_view(), name="me-membership"),
    path("/me/memberships", views.MyMembershipHistoryView.as_view(), name="me-memberships"),
    path("/me/activities", views.MyActivityView.as_view(), name="me-activities"),
    path("/me/badges", views.MyBadgesView.as_view(), name="me-badges"),
    path("/me/card", views.MyCardView.as_view(), name="me-card"),
    path("/me/avatar", views.MyAvatarView.as_view(), name="me-avatar"),
    path("/<uuid:pk>/card", views.FanCardView.as_view(), name="profile-card"),
    path("/me/challenges", views.MyChallengesView.as_view(), name="me-challenges"),
    path("/me/season-summary", views.MySeasonSummaryView.as_view(), name="me-season-summary"),
    path("/badges", views.BadgeListView.as_view(), name="badges"),
    path("/leaderboard", views.LeaderboardView.as_view(), name="leaderboard"),
    path("/leaderboard/teams", views.TeamLeaderboardView.as_view(), name="leaderboard-teams"),
    path("/matches/<uuid:pk>/prediction-summary", views.PredictionSummaryView.as_view(), name="prediction-summary"),
    *resource_routes(views.PollViewSet, "/polls", "poll"),
    path("/polls/<uuid:pk>/vote", views.PollVoteView.as_view(), name="poll-vote"),
    path("/polls/<uuid:pk>/results", views.PollResultsView.as_view(), name="poll-results"),
    *resource_routes(views.PredictionViewSet, "/predictions", "prediction"),
    path("/matches/<uuid:pk>/score-predictions", views.ScorePredictionsView.as_view(), name="score-predictions"),
    *resource_routes(views.FanProfileViewSet, "", "profile"),
]
