import 'react-native';
import {render, screen, fireEvent, waitFor, act} from '@testing-library/react-native';
import * as React from 'react';

import {App} from '../src/App';

// The simulator has no audio sink, and jest has no media stack at all. The app
// must treat audio as optional everywhere, so the mock simply fails.
jest.mock('@amazon-devices/react-native-w3cmedia', () => ({
  AudioPlayer: class {
    async initialize() {
      throw new Error('no audio in tests');
    }
  },
}));

const GAMES = [
  {id: '849832', away: 'Guardians', home: 'White Sox', status: 'Final',
   abstract: 'Final', series: 'ALDS', playable: true, live: false},
  {id: '849809', away: 'Dodgers', home: 'Brewers', status: 'Scheduled',
   abstract: 'Preview', series: 'NLCS', playable: false, live: false},
  {id: 'synthetic', away: 'Harbor Gulls', home: 'Cedar Foxes',
   status: 'Demo game', abstract: 'Live', series: 'Offline fixture',
   playable: true, live: false},
];

const MANIFEST = {
  gamePk: 849832, asOfPlayIndex: 77, away: 'CLE', home: 'CWS',
  awayName: 'Guardians', homeName: 'White Sox', gameStatus: 'Final',
  gameState: {inning: 9, half: 'bottom', away: 9, home: 5},
  totalSeconds: 20, timingSource: 'tts', audioUrl: null,
  engine: {selected: 2, considered: 46, runsExplained: 7, runsTotal: 14},
  segments: [
    {kind: 'intro', text: 'Bottom of the 9th.', start: 0, dur: 5},
    {kind: 'play', text: 'Ramirez homers.', start: 5, dur: 8, playIndex: 40},
    {kind: 'outro', text: "That's your final.", start: 13, dur: 7},
  ],
};

const mockFetch = (overrides: Record<string, unknown> = {}) => {
  global.fetch = jest.fn((url: string) => {
    if (`${url}`.includes('/playable')) {
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => overrides.games ?? GAMES,
      });
    }
    if (`${url}`.includes('/recap/')) {
      if (overrides.recapStatus === 409) {
        return Promise.resolve({
          ok: false, status: 409,
          json: async () => ({error: 'no plays yet'}),
        });
      }
      return Promise.resolve({
        ok: true, status: 200, json: async () => MANIFEST,
      });
    }
    return Promise.resolve({ok: true, status: 200, json: async () => ({})});
  }) as any;
};

describe('App', () => {
  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it('lists the games the backend says are worth recapping', async () => {
    mockFetch();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('game-849832')).toBeTruthy());
    expect(screen.getByTestId('game-synthetic')).toBeTruthy();
  });

  it('shows a scheduled game without offering it', async () => {
    // It has no plays to recap, but hiding it would leave the viewer
    // wondering where tonight's game went.
    mockFetch();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('game-849809')).toBeTruthy());
    expect(screen.getByText('Scheduled')).toBeTruthy();
  });

  it('plays a recap when a game is chosen', async () => {
    mockFetch();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('game-849832')).toBeTruthy());
    fireEvent.press(screen.getByTestId('game-849832'));
    await waitFor(() =>
      expect(screen.getByTestId('card-text')).toBeTruthy(),
    );
    expect(screen.getByTestId('card-text').props.children)
      .toContain('Bottom of the 9th.');
  });

  it('advances cards on the manifest clock', async () => {
    // The clock is the manifest's, not the audio element's: the Vega Virtual
    // Device cannot play audio, and currentTime reads NaN there.
    jest.useFakeTimers();
    mockFetch();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('game-849832')).toBeTruthy());
    fireEvent.press(screen.getByTestId('game-849832'));
    await waitFor(() => expect(screen.getByTestId('card-text')).toBeTruthy());

    act(() => {
      jest.advanceTimersByTime(5100);
    });
    expect(screen.getByTestId('card-text').props.children)
      .toContain('Ramirez homers.');

    act(() => {
      jest.advanceTimersByTime(8100);
    });
    expect(screen.getByTestId('card-text').props.children)
      .toContain("That's your final.");
  });

  it('reports run coverage honestly while playing', async () => {
    mockFetch();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('game-849832')).toBeTruthy());
    fireEvent.press(screen.getByTestId('game-849832'));
    await waitFor(() => expect(screen.getByTestId('engine-note')).toBeTruthy());
    const note = screen.getByTestId('engine-note').props.children.join('');
    expect(note).toContain('7');
    expect(note).toContain('14');
  });

  it('keeps playing when audio is unavailable', async () => {
    // Expected on the simulator. A silent recap is still a correct recap.
    mockFetch();
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('game-849832')).toBeTruthy());
    fireEvent.press(screen.getByTestId('game-849832'));
    await waitFor(() => expect(screen.getByTestId('card-text')).toBeTruthy());
    expect(screen.getByTestId('card-text')).toBeTruthy();
  });

  it('treats a game with no plays as information, not a failure', async () => {
    mockFetch({recapStatus: 409});
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('game-849832')).toBeTruthy());
    fireEvent.press(screen.getByTestId('game-849832'));
    await waitFor(() => expect(screen.getByText('no plays yet')).toBeTruthy());
  });
});
