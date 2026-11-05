/**
 * Pipeline CRM API server.
 *
 *   npm start            -> http://localhost:4000 (serves the built React app too, if present)
 *
 * On first start, if the CRM database does not exist yet, the Python job `all` is run to
 * download the dataset from GitHub, seed the database, build the data review and score deals.
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import express from 'express';

import { CLIENT_DIST, DB_PATH, PORT, WEB_DIR } from './config.js';
import * as db from './db.js';
import { runJob } from './jobs.js';
import { router } from './routes.js';

async function bootstrap() {
  if (!existsSync(DB_PATH) || !existsSync(path.join(WEB_DIR, 'review.json'))) {
    console.log('First run: downloading the dataset and preparing the CRM database (Python job "all")...');
    await runJob('all');
  }
  db.open();

  const app = express();
  app.use(express.json({ limit: '1mb' }));
  app.use('/api', router);
  if (existsSync(CLIENT_DIST)) {
    app.use(express.static(CLIENT_DIST));
    app.get(/^\/(?!api).*/, (req, res) => res.sendFile(path.join(CLIENT_DIST, 'index.html')));
  }
  app.listen(PORT, () => console.log(`Pipeline CRM API listening on http://localhost:${PORT}`));
}

bootstrap().catch((e) => {
  console.error('Startup failed:', e.message);
  process.exit(1);
});
