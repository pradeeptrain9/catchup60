import {audioUrl, fetchRecap, NotStarted, type Manifest} from '../src/api';

const manifest = (audio: string | null): Manifest =>
  ({audioUrl: audio} as Manifest);

describe('audioUrl', () => {
  it('moves audio onto the https listener', () => {
    // Vega's media player refuses http:// outright, so a manifest served over
    // http must still hand back an https audio URL.
    expect(audioUrl(manifest('http://10.0.2.2:8080/audio/x/narration.mp3')))
      .toBe('https://10.0.2.2:8443/audio/x/narration.mp3');
  });

  it('leaves the path untouched', () => {
    expect(audioUrl(manifest('http://h:1/audio/849832-latest/narration.mp3')))
      .toBe('https://10.0.2.2:8443/audio/849832-latest/narration.mp3');
  });

  it('returns null when there is no audio', () => {
    expect(audioUrl(manifest(null))).toBeNull();
  });
});

describe('fetchRecap', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('raises NotStarted on 409 rather than a generic failure', async () => {
    // "No plays yet" is information, not an error: the app returns the viewer
    // to the game list instead of showing a failure.
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({error: 'CWS @ CLE is scheduled — no plays yet'}),
    }) as any;
    await expect(fetchRecap('1')).rejects.toBeInstanceOf(NotStarted);
  });

  it('raises a plain error on a server fault', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({error: 'upstream'}),
    }) as any;
    await expect(fetchRecap('1')).rejects.not.toBeInstanceOf(NotStarted);
  });

  it('returns the manifest on success', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({totalSeconds: 58.1}),
    }) as any;
    await expect(fetchRecap('1')).resolves.toEqual({totalSeconds: 58.1});
  });
});
