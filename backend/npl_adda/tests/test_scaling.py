"""Guards against N+1 queries and checks leaderboard caching, so list endpoints stay flat as data grows."""
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.fanengagement.models import Poll
from apps.fanengagement.services import cast_vote, switch_team

from .conftest import auth_client

pytestmark = pytest.mark.django_db


def count_queries(client, url):
    with CaptureQueriesContext(connection) as ctx:
        assert client.get(url).status_code == 200
    return len(ctx.captured_queries)


def make_polls(staff, n, voter=None):
    now = timezone.now()
    for i in range(n):
        poll = Poll.objects.create(question=f"Q{i}?", created_by=staff, status=Poll.Status.OPEN,
                                   opens_at=now - timedelta(hours=1), closes_at=now + timedelta(hours=1),
                                   results_visibility=Poll.ResultsVisibility.ALWAYS)
        a = poll.options.create(text="A", display_order=1)
        poll.options.create(text="B", display_order=2)
        if voter:
            cast_vote(voter, poll, a)


def test_poll_list_query_count_is_flat(make_user, make_profile):
    staff, fan = make_user(is_staff=True), make_profile()
    client = auth_client(fan.user)
    make_polls(staff, 2, voter=fan)
    small = count_queries(client, "/api/v1/fanpage/polls")
    make_polls(staff, 8, voter=fan)
    assert count_queries(client, "/api/v1/fanpage/polls") == small


def test_profile_list_query_count_is_flat(make_profile, make_team, api):
    team = make_team()
    for _ in range(2):
        switch_team(make_profile(), team)
    small = count_queries(api, "/api/v1/fanpage")
    for _ in range(8):
        switch_team(make_profile(), team)
    assert count_queries(api, "/api/v1/fanpage") == small


def test_content_feed_query_count_is_flat(make_profile, api):
    from apps.content.models import CommunityPost

    author = make_profile()
    def add(n):
        for i in range(n):
            CommunityPost.objects.create(author=author, body=f"post {i} {timezone.now()}", status="published",
                                         published_at=timezone.now())
    add(2)
    small = count_queries(api, "/api/v1/content")
    add(8)
    assert count_queries(api, "/api/v1/content") == small


def test_leaderboards_are_cached(api, make_profile, make_team):
    switch_team(make_profile(), make_team())
    first = count_queries(api, "/api/v1/fanpage/leaderboard/teams")
    assert first > 0
    assert count_queries(api, "/api/v1/fanpage/leaderboard/teams") == 0
    count_queries(api, "/api/v1/fanpage/leaderboard")
    assert count_queries(api, "/api/v1/fanpage/leaderboard") == 0
