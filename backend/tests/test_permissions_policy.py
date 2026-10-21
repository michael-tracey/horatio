"""The permission policy, checked against what CONTEXT.md says each role can do."""

import pytest

from horatio.permissions import TROUPE_POLICY, Role, TroupeAction, allows

LEAD_ONLY = {TroupeAction.RENAME, TroupeAction.EDIT_DESCRIPTION, TroupeAction.ARCHIVE}
STORYTELLERS_ONLY = {
    TroupeAction.MANAGE_STAFF,
    TroupeAction.MANAGE_HOUSE_RULES,
    TroupeAction.MANAGE_CONNECTORS,
    TroupeAction.EDIT_PROFILE,
}
NARRATOR_CAN = {TroupeAction.VIEW_STAFF, TroupeAction.ANSWER_ASSIGNED_RESPONSES}


def test_every_action_has_a_policy() -> None:
    assert set(TROUPE_POLICY) == set(TroupeAction)


@pytest.mark.parametrize("action", list(TroupeAction))
def test_the_lead_storyteller_can_do_everything_in_their_troupe(action: TroupeAction) -> None:
    assert allows(Role.LEAD_STORYTELLER, action)


@pytest.mark.parametrize("action", list(TroupeAction))
def test_storytellers_can_do_everything_but_rename_describe_or_archive(
    action: TroupeAction,
) -> None:
    assert allows(Role.STORYTELLER, action) == (action not in LEAD_ONLY)


@pytest.mark.parametrize("action", list(TroupeAction))
def test_assistant_storytellers_cannot_manage_staff_house_rules_connectors_or_profile(
    action: TroupeAction,
) -> None:
    assert allows(Role.ASSISTANT_STORYTELLER, action) == (
        action not in LEAD_ONLY | STORYTELLERS_ONLY
    )


@pytest.mark.parametrize("action", list(TroupeAction))
def test_narrators_only_see_the_staff_and_answer_assigned_downtimes(
    action: TroupeAction,
) -> None:
    assert allows(Role.NARRATOR, action) == (action in NARRATOR_CAN)


@pytest.mark.parametrize("action", list(TroupeAction))
def test_people_without_a_role_can_do_none_of_it(action: TroupeAction) -> None:
    assert not allows(None, action)


@pytest.mark.parametrize("action", list(TroupeAction))
def test_the_custodian_can_do_everything(action: TroupeAction) -> None:
    assert allows(None, action, is_custodian=True)


def test_narrators_never_see_character_sheets() -> None:
    """Not even for downtime actions they answer (CONTEXT.md: Narrator)."""
    assert not allows(Role.NARRATOR, TroupeAction.VIEW_MEMBER_CHARACTERS)
