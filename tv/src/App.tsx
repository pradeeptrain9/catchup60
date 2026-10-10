/**
 * Catch-Up 60 — Fire TV (Vega OS).
 *
 * Pick a game, press Catch Up, and get sixty seconds on how it got to where it
 * is now — then land at the live edge. Ask again ten minutes later and the
 * recap is different, because it is rebuilt from the live feed every time.
 */
import React, {useCallback, useEffect, useState} from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';

import {
  fetchPlayable,
  fetchRecap,
  NotStarted,
  type Game,
  type Manifest,
} from './api';
import {GameList} from './components/GameList';
import {RecapPlayer} from './components/RecapPlayer';

type Screen =
  | {name: 'loading'}
  | {name: 'games'; games: Game[]}
  | {name: 'building'; game: Game}
  | {name: 'recap'; game: Game; manifest: Manifest}
  | {name: 'error'; message: string; games: Game[] | null};

export const App = () => {
  const [screen, setScreen] = useState<Screen>({name: 'loading'});

  const loadGames = useCallback(async () => {
    setScreen({name: 'loading'});
    try {
      const games = await fetchPlayable();
      setScreen({name: 'games', games});
    } catch (error: any) {
      setScreen({
        name: 'error',
        message: `${error?.message ?? error}`,
        games: null,
      });
    }
  }, []);

  useEffect(() => {
    void loadGames();
  }, [loadGames]);

  const pick = useCallback(async (game: Game) => {
    setScreen({name: 'building', game});
    try {
      const manifest = await fetchRecap(game.id);
      setScreen({name: 'recap', game, manifest});
    } catch (error: any) {
      // "No plays yet" is not a failure, so it reads as information and the
      // viewer is returned to the list rather than to an error screen.
      const message =
        error instanceof NotStarted
          ? `${error.message}`
          : `${error?.message ?? error}`;
      setScreen({name: 'error', message, games: null});
    }
  }, []);

  const header = (() => {
    if (screen.name === 'recap') {
      const {manifest} = screen;
      return `${manifest.away} ${manifest.gameState.away} · ${manifest.home} ${manifest.gameState.home} — ${manifest.gameState.half} ${manifest.gameState.inning}`;
    }
    if (screen.name === 'building') {
      return `${screen.game.away} at ${screen.game.home}`;
    }
    return 'What do you want to catch up on?';
  })();

  return (
    <View style={styles.screen}>
      <View style={styles.head}>
        <Text style={styles.brand}>Catch-Up 60</Text>
        <Text style={styles.sub}>{header}</Text>
      </View>

      {screen.name === 'loading' && (
        <View style={styles.center}>
          <Text style={styles.hint}>Looking for games…</Text>
        </View>
      )}

      {screen.name === 'games' && (
        <GameList games={screen.games} onPick={pick} />
      )}

      {screen.name === 'building' && (
        <View style={styles.center}>
          <Text style={styles.hint}>Building your recap…</Text>
          <Text style={styles.hintSmall}>
            Ranking what actually moved the game
          </Text>
        </View>
      )}

      {screen.name === 'recap' && (
        <RecapPlayer
          manifest={screen.manifest}
          onAgain={() => pick(screen.game)}
          onBack={loadGames}
        />
      )}

      {screen.name === 'error' && (
        <View style={styles.center}>
          <Text style={styles.error}>{screen.message}</Text>
          <Pressable
            hasTVPreferredFocus
            onPress={loadGames}
            style={({focused}) => [styles.button, focused && styles.buttonOn]}>
            {({focused}) => (
              <Text style={[styles.buttonText, focused && styles.buttonTextOn]}>
                Back to games
              </Text>
            )}
          </Pressable>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: '#07090f', paddingHorizontal: 64,
           paddingVertical: 44},
  head: {marginBottom: 20},
  brand: {color: '#f0f6fc', fontSize: 30, fontWeight: '700',
          letterSpacing: 0.5},
  sub: {color: '#8b949e', fontSize: 21, marginTop: 6},
  center: {flex: 1, alignItems: 'center', justifyContent: 'center', gap: 18},
  hint: {color: '#f0f6fc', fontSize: 28},
  hintSmall: {color: '#6e7681', fontSize: 19},
  error: {color: '#ff7b72', fontSize: 24, textAlign: 'center'},
  button: {paddingHorizontal: 40, paddingVertical: 18, borderRadius: 10,
           backgroundColor: '#161b22', borderWidth: 2, borderColor: '#30363d'},
  buttonOn: {backgroundColor: '#f0f6fc', borderColor: '#f0f6fc'},
  buttonText: {color: '#f0f6fc', fontSize: 24, fontWeight: '600'},
  buttonTextOn: {color: '#07090f'},
});
