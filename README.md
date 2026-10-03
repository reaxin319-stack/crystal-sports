# Crystal Sports

Crystal Sports is a Python-based sports prediction framework for showing daily picks across soccer, hockey, and tennis. The site offers subscription tiers that control sports access, market access, and slip size.

- Free: 1 month access and 3-odds slip
- Pro: 1 month access and 5-odds slip
- Elite: 1 month access and 10-odds slip
- VIP: 1 month access and up to 20-odds magic combinations

## Features

- Multiple markets: WLD, Over/Under, Cards, and Who Wins Set
- Multi-sport support for soccer, hockey, and tennis
- Admin control panel for sports and market permissions
- Subscription-based access and VIP combination slips
- Live data support from a free API endpoint or a scraped public page
- Graceful fallback to demo data when no live source is available

## Automatic daily picks

The first visit to the predictions page each UTC day automatically generates that day's shared match set. The set is reused for subsequent requests in the running app, while subscription plans still control which picks each user can see. An administrator can regenerate the current day's set from the Admin Control Panel when the live feed changes.

## Live data setup
## LSTM predictions

The predictions page uses one PyTorch LSTM sequence model trained from picks
marked Won or Lost by an administrator. It starts producing picks after at least
40 resolved results are available, including at least 15 wins and 15 losses.
Until then it shows a training-status message and does not fall back to another
prediction model. Resolved results are ordered by scheduled match time.
The Results page reports pick success rate as wins divided by wins plus losses;
pending picks are excluded from the calculation.


Set one or more of these environment variables before launching the app:

- `SPORTS_API_URL`: a free JSON endpoint that returns events or matches. The default free option is the ESPN scoreboard feed for English Premier League.
- `SPORTS_API_TOKEN` or `SPORTS_API_KEY`: optional bearer or api key headers
- `SCRAPE_URL`: a public page to scrape for match rows
- `SCRAPE_SELECTOR`: a CSS selector for the table rows to parse

The app includes a working default free source that returns live match data in the ESPN scoreboard format. If you provide a different endpoint, it will populate predictions from that feed automatically as long as the JSON includes `events` or `matches` plus team names and odds.

Example:

```bash
set SPORTS_API_URL=https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard
set SCRAPE_URL=https://example.com/fixtures
set SCRAPE_SELECTOR=tr
python app.py
```

## Free scraper script

Run this to fetch public live odds from a few free sources and print prediction-ready JSON:

```bash
python scripts/free_scraper.py --pretty
```

You can also override the source pages:

```bash
python scripts/free_scraper.py --url https://www.oddschecker.com/hockey/nhl --pretty
```

## Local run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## Stripe webhook and ngrok

To test Stripe webhooks locally, run ngrok and forward to port 5000:

```bash
ngrok http 5000
```

Then add a webhook endpoint in the Stripe Dashboard pointing to `https://<your-ngrok>/stripe-webhook` and subscribe to `checkout.session.completed` events. Set `STRIPE_ENDPOINT_SECRET` in your environment from the webhook settings.

If you don't provide SMTP settings, confirmation and reset emails will be printed to the console for development.

## Deploy online

### Option 1: Render
1. Create a new Web Service on Render.
2. Connect this repository.
3. Set the build command to `pip install -r requirements.txt`.
4. Set the start command to `gunicorn app:app`.
5. Add environment variables if needed.

### Option 2: Railway or Fly.io
1. Push the repo to GitHub.
2. Import the repo into Railway or Fly.io.
3. Keep the default Python runtime and use the same start command.

## Notes

The current implementation uses a free API attempt plus a scraping placeholder and falls back to demo data when external services are unavailable. To make it fully live, replace the data source in services/data_service.py with your preferred free provider and keep the same schema.
