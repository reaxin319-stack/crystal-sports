LEAGUES = [
    {
        "name": "Premier League",
        "country": "England",
        "sample_teams": [("Arsenal", "Chelsea"), ("Liverpool", "Manchester City")],
    },
    {
        "name": "Ligue 2",
        "country": "France",
        "sample_teams": [("Auxerre", "Toulouse"), ("Lorient", "Le Havre")],
    },
    {
        "name": "NBA",
        "country": "USA",
        "sample_teams": [("Cleveland Cavaliers", "Boston Celtics"), ("Denver Nuggets", "Golden State Warriors")],
    },
]

SPORTS = {
    "soccer": {"name": "Soccer", "leagues": ["Premier League", "Ligue 2"]},
    "hockey": {"name": "Hockey", "leagues": ["NHL"]},
    "tennis": {"name": "Tennis", "leagues": ["ATP", "WTA"]},
}

ALL_MARKETS = ["WLD", "Over/Under", "Cards", "Who Wins Set"]
