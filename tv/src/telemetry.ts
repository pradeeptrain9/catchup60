/**
 * Tell the host what the device is doing.
 *
 * `console.log` is not reliable here. The w3cmedia library's own lines reach
 * `vega device start-log-stream` while the app's do not, which makes on-device
 * debugging guesswork — and the simulator offers no screenshot and no way to
 * inject a key press, so without this there is no way to know what the app
 * rendered except to watch the window.
 *
 * An HTTP GET always arrives. It is fire-and-forget on purpose: telemetry that
 * can fail a render is worse than no telemetry.
 */
import {API} from './api';

export const report = (message: string): void => {
  try {
    void fetch(`${API}/log?m=${encodeURIComponent(message)}`).catch(() => {});
  } catch {
    // Never let the reporting channel break the thing it reports on.
  }
};
