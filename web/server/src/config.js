import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

export const PROJECT_ROOT = path.resolve(here, '..', '..', '..');
export const DATA_DIR = path.join(PROJECT_ROOT, 'data');
export const WEB_DIR = path.join(DATA_DIR, 'web');
export const DB_PATH = process.env.CRM_DB_PATH || path.join(DATA_DIR, 'crm_app.db');
export const CLIENT_DIST = path.resolve(here, '..', '..', 'client', 'dist');
export const PORT = Number(process.env.PORT || 4000);

const venvPython = process.platform === 'win32'
  ? path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
  : path.join(PROJECT_ROOT, '.venv', 'bin', 'python');
export const PYTHON = process.env.PYTHON || (existsSync(venvPython) ? venvPython : 'python');

export const STAGES = ['Prospecting', 'Engaging', 'Won', 'Lost'];
export const OPEN_STAGES = ['Prospecting', 'Engaging'];
export const CLOSED_STAGES = ['Won', 'Lost'];
export const NOT_ASSIGNED = '(Not assigned)';
