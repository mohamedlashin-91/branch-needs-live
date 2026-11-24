# branch-needs-live

Half-hourly branch stock for the Branch Needs site. A scheduled GitHub Action downloads the store stock export,
keeps branch stock only (no warehouse stock), and publishes small files on GitHub Pages under a hidden folder.
The website address is kept in the repository secret `STOCK_URL`. Nothing is stored in this repository.
