const { readFileSync } = require('node:fs');
const path = require('node:path');
const { build } = require('../package.json');

const { version } = JSON.parse(readFileSync(path.join(__dirname, '../dist-desktop/credits-assets.json'), 'utf8'));
if (typeof version !== 'string' || !/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error('Build desktop assets first; credits must contain a valid release version.');
}

module.exports = { ...build, extraMetadata: { version } };