import {Config} from "@remotion/cli/config";

// Machine-local overrides only. By default Remotion uses the headless shell it
// downloads into node_modules, so no absolute path is committed here.
//   REMOTION_BROWSER_EXECUTABLE  path to a Chrome/Chromium binary
//   REMOTION_RENDERER_PORT       fixed port for the local render server
const browser = process.env.REMOTION_BROWSER_EXECUTABLE;
if (browser) {
  Config.setBrowserExecutable(browser);
}
const port = Number(process.env.REMOTION_RENDERER_PORT);
if (Number.isInteger(port) && port > 0) {
  Config.setRendererPort(port);
}
