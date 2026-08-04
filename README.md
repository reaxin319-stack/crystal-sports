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

## Live data setup

Set one or more of these environment variables before launching the app:

- `SPORTS_API_URL`: a free JSON endpoint that returns events or matches
- `SPORTS_API_TOKEN` or `SPORTS_API_KEY`: optional bearer or api key headers
- `SCRAPE_URL`: a public page to scrape for match rows
- `SCRAPE_SELECTOR`: a CSS selector for the table rows to parse

A good starting point is a public sports feed that returns an `events` or `matches` array. If you provide a working endpoint, the app will populate predictions with that data automatically.

Example:

```bash
set SPORTS_API_URL=https://example.com/api/events
set SCRAPE_URL=https://example.com/fixtures
set SCRAPE_SELECTOR=tr
python app.py
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
