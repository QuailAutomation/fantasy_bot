
""" Generates the draft pick #s for a snake style draft. """
def generate_snake_draft_picks(n_teams=12, n_rounds=16, draft_position=1):
    if n_rounds % 2 != 0:
        raise Exception("Number of rounds must be even for snake draft.")

    draft_picks = []
    for round in range(0, n_rounds,2):
        draft_picks.append((round) * n_teams + draft_position)
        draft_picks.append((round +2) * n_teams - draft_position + 1)

    return draft_picks