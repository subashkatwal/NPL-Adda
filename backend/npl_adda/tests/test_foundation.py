import uuid

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.urls import Resolver404, resolve

from apps.common import cricket
from apps.common.models import BaseModel
from apps.teams.models import Team


@pytest.mark.parametrize("url", ["/api/docs", "/api/schema", "/api/redoc", "/api/v1/health",
                                 "/api/v1/teams", "/api/v1/matches", "/api/v1/fanpage", "/api/v1/content"])
def test_public_urls_without_trailing_slash(db, client, url):
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("url", ["/api/docs/", "/api/v1/health/", "/api/v1/teams/", "/api/v1/fanpage/"])
def test_trailing_slash_is_not_served(db, client, url):
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("prefix", ["fanpage", "teams", "matches"])
def test_collection_and_uuid_detail_resolve(prefix):
    pk = uuid.uuid4()
    assert resolve(f"/api/v1/{prefix}").url_name.endswith("-list")
    assert resolve(f"/api/v1/{prefix}/{pk}").url_name.endswith("-detail")
    for bad in (f"/api/v1/{prefix}/{pk}/", f"/api/v1/{prefix}/not-a-uuid"):
        with pytest.raises(Resolver404):
            resolve(bad)


def test_every_project_model_uses_base_model_and_documents_fields():
    missing = []
    for model in apps.get_models():
        if not model.__module__.startswith("apps."):
            continue
        assert issubclass(model, BaseModel), model
        assert isinstance(model._meta.pk, type(BaseModel._meta.get_field("id")))
        for field in model._meta.local_fields + model._meta.local_many_to_many:
            if not field.help_text:
                missing.append(f"{model.__name__}.{field.name}")
    assert not missing, missing


def test_soft_delete_restore_and_managers(make_team):
    team = make_team(slug="kathmandu")
    team.soft_delete()
    assert not Team.objects.filter(pk=team.pk).exists()
    assert Team.all_objects.filter(pk=team.pk).exists()
    team.restore()
    assert Team.objects.filter(pk=team.pk).exists()


def test_conditional_unique_allows_recreate_after_soft_delete(make_team):
    first = make_team(slug="pokhara", name="Pokhara")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_team(slug="pokhara", name="Other")
    first.soft_delete()
    assert make_team(slug="pokhara", name="Pokhara").pk != first.pk


def test_cricket_calculations_are_deterministic():
    assert cricket.overs(112) == "18.4"
    assert str(cricket.run_rate(145, 112)) == "7.77"
    assert str(cricket.required_run_rate(150, 100, 90, 120)) == "10.00"
    assert str(cricket.strike_rate(52, 31)) == "167.74"
    assert cricket.economy(10, 0) is None
