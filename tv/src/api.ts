/**
 * Backend access, against either of two origins.
 *
 * Local is the development server on this Mac, and it is two listeners on two
 * ports: Vega's media player refuses http:// outright, while fetch() rejects
 * that server's self-signed certificate. So manifests come over http and audio
 * over https, and an audio URL has to be moved between them.
 *
 * Cloud is the deployed stack, and it has neither problem. API Gateway
 * terminates a real certificate, and audio is a presigned S3 URL that already
 * answers Range requests — so the manifest's audioUrl is used exactly as it
 * arrives. Rewriting it would strip the signature and break it.
 *
 * Both are kept because they demonstrate different things: local drives the
 * replay clock, which is how a live game can be shown without one being on,
 * and cloud is the real deployment. The switch is at the bottom of the game
 * list, so neither needs a rebuild.
 *
 * The choice lives in memory. Vega has no storage that does not cost a native
 * dependency, and this project has none; relaunching the app returns to local.
 */

/** 10.0.2.2 is the host as seen from the virtual device, as on Android. */
const LOCAL_HOST = '10.0.2.2';

export type Origin = 'local' | 'cloud';

type Backend = {label: string; api: string; audio: string | null};

const BACKENDS: Record<Origin, Backend> = {
  local: {
    label: 'Local server',
    api: `http://${LOCAL_HOST}:8080`,
    // Audio lives on the other listener, so it has to be rewritten.
    audio: `https://${LOCAL_HOST}:8443`,
  },
  cloud: {
    label: 'AWS',
    api: 'https://vbww5kcz7l.execute-api.us-east-1.amazonaws.com',
    // null means "the manifest's URL is already correct". It is a presigned
    // S3 link whose signature covers the query string.
    audio: null,
  },
};

let current: Origin = 'local';

export const getOrigin = (): Origin => current;
export const originLabel = (origin: Origin): string => BACKENDS[origin].label;
export const setOrigin = (origin: Origin): void => {
  current = origin;
};
export const toggleOrigin = (): Origin => {
  current = current === 'local' ? 'cloud' : 'local';
  return current;
};

export const API = (): string => BACKENDS[current].api;

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
  const response = await fetch(`${API()}/playable`);
  if (!response.ok) {
    throw new Error(`playable: HTTP ${response.status}`);
  }
  return response.json();
};

export const fetchRecap = async (gameId: string): Promise<Manifest> => {
  const response = await fetch(`${API()}/recap/${gameId}`);
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

export const audioUrl = (manifest: Manifest): string | null => {
  if (!manifest.audioUrl) {
    return null;
  }
  const {audio} = BACKENDS[current];
  if (audio === null) {
    // Already absolute, already signed. Touching it invalidates it.
    return manifest.audioUrl;
  }
  const path = manifest.audioUrl.replace(/^https?:\/\/[^/]+/, '');
  return `${audio}${path}`;
};
