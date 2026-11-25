# branch-needs-live

Half-hourly branch stock for the Branch Needs site. A scheduled GitHub Action downloads the store stock export,
keeps branch stock only (no warehouse stock), and publishes small files on GitHub Pages under a hidden folder.
The website address is kept in the repository secret `STOCK_URL`. Nothing is stored in this repository.

Timing: every 30 minutes (:07 and :37) from 10:07 AM to 12:07 AM Riyadh time. GitHub's own schedule is often
late or skipped, so each run starts the next one itself; the schedule only has to fire once each morning.
To pause the live stock (pages then show the morning numbers), add an empty file `live/OFF`; delete it to resume.
