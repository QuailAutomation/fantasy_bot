import pytest
from csh_fantasy_bot.draft import generate_snake_draft_picks


def test_snake_generator():
    result = generate_snake_draft_picks(draft_position=1, n_teams=4, n_rounds=6)
    result = generate_snake_draft_picks(draft_position=5, n_teams=4, n_rounds=6)
    print(result)