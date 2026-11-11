import { pathToFileURL } from 'node:url';

export function check(results) {
  if (!results || typeof results !== 'object' || Array.isArray(results)) {
    throw new Error('The gate requires the complete needs object.');
  }
  const jobs = Object.entries(results);
  if (!jobs.length || !jobs.some(([, job]) => job?.result === 'success')) {
    throw new Error('At least one required job must succeed.');
  }
  const rejected = jobs.filter(([, job]) => !['success', 'skipped'].includes(job?.result));
  if (rejected.length) {
    throw new Error(`Required jobs did not pass: ${rejected.map(([name, job]) => `${name}=${job?.result}`).join(', ')}`);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    check(JSON.parse(process.env.GATE_RESULTS));
    console.log('All required jobs passed.');
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
