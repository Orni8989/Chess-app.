# Chess Insight

A local-first Flask app for studying your own Chess.com opening results. It imports games into SQLite, supports multiple usernames, and analyzes win/draw/loss rates and expected points without repeatedly downloading your full history.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open <http://127.0.0.1:5000>, choose **Add games**, and import a Chess.com username. The first import reads the selected history; later imports begin with the latest stored month.

## What is included

- Opening Explorer with account, date, speed, and color filters
- Top five moves at every position with W/D/L percentages and expected points
- Click-through opponent responses and deeper lines
- Decision Points analysis that ranks recurring positions by expected-score spread
- Local SQLite storage with multi-account game associations and deduplication
- Chess.com archive sync that only revisits new/recent archives after the initial import

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

The tests use synthetic PGNs and do not call Chess.com.
