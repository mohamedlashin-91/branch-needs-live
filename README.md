# branch-needs-live

Half-hourly branch stock for the Branch Needs site. A scheduled GitHub Action downloads the store stock export,
keeps branch stock only (no warehouse stock), and publishes small files on GitHub Pages under a hidden folder.
The website address is kept in the repository secret `STOCK_URL`. Nothing is stored in this repository.

Timing: every 30 minutes (:07 and :37) from 6:07 AM to 2:07 AM Riyadh time. The job keeps itself running day
and night: each run starts the next one, waits through the night and starts the 6:07 AM run itself, and retries if
GitHub refuses to start it. GitHub's own schedule is only a backup. Manual restart: Actions > Live branch stock >
Run workflow. To pause the live stock (pages then show the morning numbers), add an empty file `live/OFF`; delete it
to resume.
