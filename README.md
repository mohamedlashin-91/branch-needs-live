# branch-needs-live

Half-hourly branch stock for the Branch Needs site. A scheduled GitHub Action downloads the store stock export,
keeps branch stock only (no warehouse stock), and publishes small files on GitHub Pages under a hidden folder.
The website address is kept in the repository secret `STOCK_URL`. Nothing is stored in this repository.

Timing: every 30 minutes (:07 and :37) from 6:07 AM to 2:07 AM Riyadh time. The job keeps itself running day
and night: each run starts the next one, waits through the night and starts the 6:07 AM run itself, and retries if
GitHub refuses to start it. GitHub's own schedule is only a backup. Manual restart: Actions > Live branch stock >
Run workflow. To pause the live stock (pages then show the morning numbers), add an empty file `live/OFF`; delete it
to resume.

## Laptop backup (since 26 Nov 2026)

Since about 5:37 PM on 26 Nov 2026 the store website answers the server with a bot-check page ("One moment, please...")
instead of the Excel file. The job does not try to get past that page: it tries the website once per run (no retries on
that page) and otherwise uses the laptop backup. On the laptop, the Windows task "Branch Needs Live Stock"
(every 30 minutes, 5:50 AM - 1:50 AM, set by `L-install-live-stock-backup.bat` in Downloads\firebase-deploy) downloads
the export and runs `branch-needs-pc-live\pc-live.js`, which keeps only branch stock and uploads one packed file to a
small Firebase site (`pc.json.gz` under the same hidden folder name). The job uses that file only when it is newer than
both the morning stock and the live stock already published. When the laptop is off and the website still shows the
check page, branch pages keep the last good stock with "Not updated since". Optional secrets for later, if the website
team allows the job in: `STOCK_EXPORT_URL`, `STOCK_HEADER`.
