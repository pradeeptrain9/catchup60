/**
 * Backend access.
 *
 * Manifests come over http and audio over https, which is not an oversight:
 * Vega's media player refuses http:// outright, while fetch() rejects the
 * development server's self-signed certificate. In production both are https
 * from one trusted origin and these two constants collapse into one.
 *
 * The host is 10.0.2.2 because the Vega Virtual Device does not share the
 * host's loopback — same convention as the Android emulator.
 */
const HOST = '10.0.2.2';
export const API = `http://${HOST}:8080`;
const AUDIO_ORIGIN = `https://${HOST}:8443`;

export type Game = {
  id: string;
  away: string;
  home: string;
  status: string;
  abstract: string;
  series: string | null;
  playable: boolean;
  live: boolean;
};

export type Segment = {
  kind: 'intro' | 'play' | 'outro';
  text: string;
  start: number;
  dur: number;
  playIndex?: number;
};

export type Manifest = {
  gamePk: number | string;
  asOfPlayIndex: number;
  away: string;
  home: string;
  awayName: string;
  homeName: string;
  gameStatus: string;
  gameState: {inning: number; half: string; away: number; home: number};
  totalSeconds: number;
  timingSource: 'tts' | 'estimate';
  audioUrl: string | null;
  segments: Segment[];
  engine: {
    selected: number;
    considered: number;
    runsExplained: number;
    runsTotal: number;
  };
};

export class NotStarted extends Error {}

export const fetchPlayable = async (): Promise<Game[]> => {
  const response = await fetch(`${API}/playable`);
  if (!response.ok) {
    throw new Error(`playable: HTTP ${response.status}`);
  }
  return response.json();
};

export const fetchRecap = async (gameId: string): Promise<Manifest> => {
  const response = await fetch(`${API}/recap/${gameId}`);
  if (response.status === 409) {
    // The game exists but has no plays yet. A distinct type, because this is
    // "come back after the first pitch", not a failure.
    const body = await response.json().catch(() => ({error: 'not started'}));
    throw new NotStarted(body.error);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error ?? `recap: HTTP ${response.status}`);
  }
  return response.json();
};

/** Audio lives on the https listener, whatever origin served the manifest. */
export const audioUrl = (manifest: Manifest): string | null => {
  if (!manifest.audioUrl) {
    return null;
  }
  const path = manifest.audioUrl.replace(/^https?:\/\/[^/]+/, '');
  return `${AUDIO_ORIGIN}${path}`;
};
