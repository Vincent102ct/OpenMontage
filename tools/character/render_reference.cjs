// Render only explicit reference PNGs with installed Remotion/Chrome; never an MP4.
const fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '../..'), nm = path.join(root, 'remotion-composer/node_modules');
const resolve = name => require(require.resolve(name, {paths: [nm]}));
const {bundle} = resolve('@remotion/bundler');
const {openBrowser, selectComposition, renderStill} = resolve('@remotion/renderer');
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let browser;
(async () => {
  browser = await openBrowser('chrome', {browserExecutable: job.chrome, logLevel: 'error'});
  const serveUrl = await bundle({entryPoint: job.entry, publicDir: job.publicDir, outDir: job.bundle,
    enableCaching: false, gitSource: null, webpackOverride: config => ({...config,
      resolve: {...config.resolve, modules: [nm, ...(config.resolve.modules ?? [])]}})});
  for (const ref of job.references) {
    const composition = await selectComposition({serveUrl, id: 'StoryVideo', inputProps: ref.props,
      puppeteerInstance: browser, browserExecutable: job.chrome, logLevel: 'error'});
    await renderStill({serveUrl, composition, inputProps: ref.props, frame: ref.frame,
      output: ref.output, imageFormat: 'png', puppeteerInstance: browser,
      browserExecutable: job.chrome, logLevel: 'error'});
  }
})().catch(error => {console.error(error); process.exitCode = 1;})
  .finally(async () => {if (browser) await browser.close({silent: true});});
